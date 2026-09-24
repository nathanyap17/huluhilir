"""Media upload — block photos, observation photos, and voice labels.

A voice label is an audio sticker, not data to be parsed: it is stored as a
blob and replayed to the farmer beside the block photo. **Nothing in this
codebase transcribes it** (pepperdex-rules skill §2) — there is deliberately
no ASR endpoint here, and adding one would break a submitted proposal
commitment.
"""
import hashlib
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter(prefix="/media", tags=["media"])

_ALLOWED = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
}


def _media_dir() -> Path:
    path = Path(settings.media_root)
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("", status_code=201)
async def upload_media(file: UploadFile = File(...)) -> dict:
    """Content-addressed by SHA-256 so the offline outbox can retry a flush
    without creating duplicates (docs/DATA_MODEL.md §9 image_hash)."""
    if file.content_type not in _ALLOWED:
        raise HTTPException(415, f"unsupported content type: {file.content_type}")

    payload = await file.read()
    digest = hashlib.sha256(payload).hexdigest()
    filename = f"{digest}{_ALLOWED[file.content_type]}"
    destination = _media_dir() / filename

    if not destination.exists():
        destination.write_bytes(payload)

    return {"uri": f"/media/{filename}", "sha256": digest, "bytes": len(payload)}


@router.get("/{filename}")
async def fetch_media(filename: str) -> FileResponse:
    # Reject any path separator or traversal before touching the filesystem --
    # filename comes straight off the URL.
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "invalid filename")

    path = _media_dir() / filename
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path)
