"""MMS-TTS service — OPTIMISED tier only (docs/PROJECT_SPEC.md §3 L0).

MVP speech is pre-recorded .wav clips bundled in the Flutter app; this
service is the reach goal: template + slot -> seeded VITS -> WAV, cached by
sha256(template_id + slots + lang + seed). Never on the critical path if it
is slow or unavailable -- the fallback chain is MMS Iban -> MMS BM ->
pre-recorded clip -> flutter_tts ms-MY -> text only.
"""
import base64
import hashlib
import io
from functools import lru_cache

import scipy.io.wavfile
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoTokenizer, VitsModel

app = FastAPI(title="HuluHilir TTS")

MODEL_IDS = {
    "iba": "facebook/mms-tts-iba",
    "ms": "facebook/mms-tts-zlm",
}


@lru_cache(maxsize=len(MODEL_IDS))
def load(language: str):
    model_id = MODEL_IDS[language]
    model = VitsModel.from_pretrained(model_id)
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    return model, tokenizer


class SynthesizeRequest(BaseModel):
    text: str
    language: str
    seed: int = 42


@app.get("/health")
def health():
    return {"ok": True, "service": "huluhilir-tts", "languages": list(MODEL_IDS)}


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    if req.language not in MODEL_IDS:
        raise HTTPException(400, f"unsupported language: {req.language}")

    # MMS is trained on lowercase, unpunctuated text (sandbox/EXPERIMENTS.md EXP-2)
    text = req.text.lower().strip()
    model, tokenizer = load(req.language)
    inputs = tokenizer(text, return_tensors="pt")

    torch.manual_seed(req.seed)  # VITS is stochastic -- must seed for reproducibility
    with torch.no_grad():
        waveform = model(**inputs).waveform

    buf = io.BytesIO()
    scipy.io.wavfile.write(buf, rate=model.config.sampling_rate, data=waveform.squeeze().numpy())
    audio_hash = hashlib.sha256(f"{text}{req.language}{req.seed}".encode()).hexdigest()
    duration_ms = int(waveform.shape[-1] / model.config.sampling_rate * 1000)

    return {
        "hash": audio_hash,
        "duration_ms": duration_ms,
        "sample_rate": model.config.sampling_rate,
        "audio_base64": base64.b64encode(buf.getvalue()).decode(),
    }
