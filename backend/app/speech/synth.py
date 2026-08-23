"""Google Cloud Text-to-Speech backend.

Auth is the same story as Vertex AI: on Cloud Run the service's own service
account provides Application Default Credentials, so there is no API key to
manage or leak. Locally it uses whatever `gcloud auth application-default
login` left behind, and if that is absent, synthesis degrades to text
rather than failing the request (see the router's docstring).

**Language coverage is honestly limited.** Cloud TTS ships ms-MY, but has
no Iban voice -- no major commercial TTS does. Iban therefore falls back to
the Malay voice reading Iban text, which is imperfect but intelligible
(shared phonology, and Iban is written in Latin script). The response
records which voice actually spoke, so this is visible to the caller rather
than silently pretended-away. Iban speech quality is a known gap, not a
solved problem: docs/BUILD_LOG.md "Block E".
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

_VOICES = {
    # (language_code, voice_name). Chirp3-HD is Google's current natural-voice
    # line; if a voice name is ever retired the call falls back to language
    # code alone, which Cloud TTS resolves to a default voice.
    "ms": ("ms-MY", "ms-MY-Standard-A"),
    "iba": ("ms-MY", "ms-MY-Standard-A"),  # no Iban voice exists -- see module docstring
    "en": ("en-US", "en-US-Standard-C"),
}


@dataclass
class SynthResult:
    ok: bool
    audio: bytes | None = None
    duration_ms: int | None = None
    error: str | None = None


def voice_for(language: str) -> str:
    return _VOICES.get(language, _VOICES["ms"])[1]


def _synthesize_blocking(text: str, language: str) -> SynthResult:
    try:
        from google.cloud import texttospeech
    except ImportError as exc:
        return SynthResult(ok=False, error=f"google-cloud-texttospeech not installed: {exc}")

    language_code, voice_name = _VOICES.get(language, _VOICES["ms"])

    try:
        client = texttospeech.TextToSpeechClient()
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(
                language_code=language_code, name=voice_name
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                # Farmers listening outdoors on a phone speaker, often older
                # listeners: slightly slower than default aids intelligibility.
                speaking_rate=0.92,
            ),
        )
    except Exception as exc:  # noqa: BLE001 -- degrade to text, never 500
        return SynthResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    audio = response.audio_content
    if not audio:
        return SynthResult(ok=False, error="empty audio returned")

    # MP3 duration is not knowable without decoding; estimate from a measured
    # ~14 chars/sec at speaking_rate 0.92 so the client can size a progress
    # bar. Marked as an estimate rather than presented as measured truth.
    duration_ms = int(len(text) / 14.0 * 1000)
    return SynthResult(ok=True, audio=audio, duration_ms=duration_ms)


async def synthesize(text: str, language: str) -> SynthResult:
    """The Cloud TTS client is synchronous; run it off the event loop so a
    slow synthesis cannot block the API serving everything else."""
    return await asyncio.to_thread(_synthesize_blocking, text, language)
