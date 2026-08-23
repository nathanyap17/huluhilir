"""Bahasa Malaysia / English -> Iban, for spoken output only.

**This is machine translation, and the response says so.** No Iban speaker
has verified these strings. That matters more here than in a typical app: the
project's whole reason for storing voice labels as audio rather than
transcribing them is that off-the-shelf language tooling for Iban is not
dependable (huluhilir-rules section 1), and it would be incoherent to then
pass unverified machine Iban off as trustworthy advice.

So the contract is:
  - The Iban text is returned to the caller and rendered ON SCREEN alongside
    the Malay, never instead of it, so a farmer or an extension officer can
    see what was actually said.
  - The response carries `translation_source: "machine"` and the voice that
    actually spoke, and the UI is expected to disclose both.
  - Where a native-speaker-verified Iban term exists in `slot_vocabulary`
    (`text_iba`), that is preferred over anything generated here.

There is also no Iban voice in Cloud TTS -- none of the major providers has
one -- so the audio is the Malay voice reading Iban text. Shared phonology and
Latin orthography make that intelligible rather than correct. The real fix is
the MMS-VITS `facebook/mms-tts-iba` model, which is why the unwired `tts/`
service is still in the repo.
"""
from __future__ import annotations

from app.config import settings

_PROMPT = """Translate the following farming message into Iban (Sarawak), the language of
the Iban people. Keep it short, plain and spoken-sounding, as one farmer would
say it to another.

Rules:
- Output ONLY the Iban translation. No quotes, no notes, no romanisation guide.
- Keep any number, unit and day name exactly as given.
- Do NOT add advice, chemicals, doses or timings that are not in the source.
- If a term has no common Iban equivalent, keep the Malay word rather than
  inventing one.

Message:
"""


async def to_iban(text: str) -> tuple[str, str]:
    """Returns (iban_text, source) where source is 'machine' or 'fallback'.

    A translation failure returns the original text with source 'fallback'
    rather than raising: the farmer still hears their advice in Malay, which
    is far better than silence.
    """
    try:
        import litellm

        kwargs = {}
        model = settings.vision_model or settings.litellm_model
        if model.startswith("vertex_ai/"):
            if settings.vertexai_project:
                kwargs["vertex_project"] = settings.vertexai_project
            kwargs["vertex_location"] = settings.vertexai_location

        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": _PROMPT + text}],
            temperature=0,
            max_tokens=1024,
            **kwargs,
        )
        out = (response.choices[0].message.content or "").strip()
        if not out:
            return text, "fallback"
        return out, "machine"
    except Exception as exc:  # noqa: BLE001 -- never block playback
        print(f"[iban] translation failed, speaking source text: {exc}", flush=True)
        return text, "fallback"
