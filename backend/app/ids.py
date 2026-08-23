"""ULID generation. IDs are client-generatable so offline capture works (docs/DATA_MODEL.md)."""
import os
import time

_ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32, no I L O U


def _encode(number: int, length: int) -> str:
    chars = []
    for _ in range(length):
        number, rem = divmod(number, 32)
        chars.append(_ENCODING[rem])
    return "".join(reversed(chars))


def new_ulid() -> str:
    ts_ms = int(time.time() * 1000)
    randomness = int.from_bytes(os.urandom(10), "big")
    return _encode(ts_ms, 10) + _encode(randomness, 16)
