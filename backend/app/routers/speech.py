"""Speech synthesis for agent output. docs/PROJECT_SPEC.md §3 L0.

Block E, revised: the original plan bundled pre-recorded .wav clips per
template and treated synthesis as an "optimised tier" reach goal. That
inverts badly once the agent is the thing talking -- a recommendation's
`reason_ms` is composed at runtime from real weather and real block state,
so there is no finite set of sentences to pre-record. This synthesises
agent output directly instead.

**This is output only.** Nothing here transcribes anything; there is no ASR
endpoint in this codebase and adding one would break a submitted proposal
commitment (pepperdex-rules §2).

Rule #7 (every user-facing string carries a `speech_template_id`) still
holds and is not weakened by this: templates remain the canonical source of
*phrasing*, and `/speech/render` is the path that uses them. `/speech/say`
exists for the genuinely runtime-composed strings the agent produces, which
no template can cover.

**Never on the critical path.** Every failure here degrades to text rather
than raising: a farmer who cannot hear the advice must still be able to
read it. Callers get `audio_uri: null` plus a reason, never a 500.
"""
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.speech import AudioCache, SlotVocabulary, SpeechTemplate
from app.schemas.enums import Language
from app.schemas.speech import RenderSpeechRequest, SpeechTemplateOut
from app.speech.synth import SynthResult, synthesize, voice_for

router = APIRouter(prefix="/speech", tags=["speech"])


def _audio_dir() -> Path:
    path = Path(settings.media_root) / "speech"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(text: str, language: str, voice: str) -> str:
    return hashlib.sha256(f"{text}|{language}|{voice}".encode()).hexdigest()


async def _synthesize_cached(
    text: str,
    language: Language,
    session: AsyncSession,
    template_id: str = "_adhoc",
) -> dict:
    """Synthesise, or return an already-synthesised copy.

    Cached on sha256(text + language + voice) rather than on
    (template_id, slots): agent-composed strings have no template, and two
    different templates that happen to render identical text should not pay
    for synthesis twice.
    """
    lang_value = language.value if isinstance(language, Language) else str(language)
    voice = voice_for(lang_value)
    key = _cache_key(text, lang_value, voice)

    cached = await session.get(AudioCache, key)
    if cached is not None and (Path(cached.audio_path).is_file()):
        return {
            "text": text,
            "language": lang_value,
            "audio_uri": f"/speech/audio/{key}",
            "duration_ms": cached.duration_ms,
            "cache_hit": True,
            "voice": voice,
            "degraded_reason": None,
        }

    result: SynthResult = await synthesize(text=text, language=lang_value)
    if not result.ok:
        # Degrade to text. The caller still has `text` and can display it.
        return {
            "text": text,
            "language": lang_value,
            "audio_uri": None,
            "duration_ms": None,
            "cache_hit": False,
            "voice": voice,
            "degraded_reason": result.error,
        }

    path = _audio_dir() / f"{key}.mp3"
    path.write_bytes(result.audio)

    if cached is None:
        session.add(AudioCache(
            hash=key,
            template_id=template_id,
            language=lang_value,
            slots_json={},
            audio_path=str(path),
            duration_ms=result.duration_ms,
            seed=0,  # Cloud TTS is deterministic; the MMS seed field is unused here.
        ))
    else:
        cached.audio_path = str(path)
        cached.duration_ms = result.duration_ms
    await session.commit()

    return {
        "text": text,
        "language": lang_value,
        "audio_uri": f"/speech/audio/{key}",
        "duration_ms": result.duration_ms,
        "cache_hit": False,
        "voice": voice,
        "degraded_reason": None,
    }


class SayRequest(RenderSpeechRequest):
    pass


@router.get("/templates", response_model=list[SpeechTemplateOut])
async def list_templates(
    language: Language | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[SpeechTemplateOut]:
    stmt = select(SpeechTemplate)
    if language is not None:
        stmt = stmt.where(SpeechTemplate.language == language.value)
    rows = (await session.execute(stmt.order_by(SpeechTemplate.template_id))).scalars().all()
    return [SpeechTemplateOut.model_validate(r) for r in rows]


@router.post("/render")
async def render_template(
    req: RenderSpeechRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Render a speech template with slots, then speak it.

    Slot values are looked up in slot_vocabulary when the caller passes a
    slot_id, so the spoken noun is the native-speaker-verified term rather
        than whatever the LLM happened to write.
    """
    template = await session.get(SpeechTemplate, req.template_id)
    if template is None:
        raise HTTPException(404, f"unknown template_id: {req.template_id}")

    lang_value = req.language.value if isinstance(req.language, Language) else str(req.language)

    filled: dict[str, str] = {}
    for name, value in req.slots.items():
        vocab = await session.get(SlotVocabulary, value)
        if vocab is not None:
            filled[name] = vocab.text_iba if (lang_value == "iba" and vocab.text_iba) else vocab.text_ms
        else:
            filled[name] = value

    try:
        text = template.text_template.format(**filled)
    except KeyError as exc:
        raise HTTPException(422, f"template {req.template_id} needs slot {exc}") from exc

    out = await _synthesize_cached(text, req.language, session, template_id=req.template_id)
    out["template_id"] = req.template_id
    return out


@router.post("/say")
async def say(req: SayRequest, session: AsyncSession = Depends(get_session)) -> dict:
    """Speak a runtime-composed string -- an agent's `reason_ms`, an advisor
    verdict, a rain-pulse warning. These are assembled from live data, so no
    pre-recorded clip or fixed template can cover them.

    `template_id` is still accepted and recorded, so a spoken string remains
    traceable to the phrasing it came from where one exists.
    """
    text = (req.slots.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "slots.text is required and must be non-empty")

    lang = req.language.value if isinstance(req.language, Language) else str(req.language)

    # Iban is spoken, but it is MACHINE-translated and the response says so.
    # The Iban text comes back to the caller so the UI can show it beside the
    # Malay rather than replacing it -- an unverified translation a farmer
    # cannot see is not something to hand them as advice.
    if lang == "iba":
        from app.speech.iban import to_iban

        iban_text, source = await to_iban(text)
        out = await _synthesize_cached(
            iban_text, req.language, session, template_id=req.template_id or "_adhoc"
        )
        out["source_text"] = text
        out["translation_source"] = source
        # Stated explicitly: there is no Iban voice in Cloud TTS, so this is a
        # Malay voice reading Iban words.
        out["voice_is_iban"] = False
        return out

    return await _synthesize_cached(
        text, req.language, session, template_id=req.template_id or "_adhoc"
    )


@router.get("/audio/{key}")
async def fetch_audio(key: str) -> FileResponse:
    if not key.isalnum() or len(key) != 64:
        raise HTTPException(400, "invalid audio key")
    path = _audio_dir() / f"{key}.mp3"
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="audio/mpeg")
