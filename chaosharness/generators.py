import hashlib
from typing import Any

def stable_seed(master_seed: int, *parts: Any) -> int:
    """
    Derives a deterministic, 32-bit positive integer seed from a master seed and
    arbitrary input parts using SHA-256. Does not depend on Python's randomized hash().
    """
    hasher = hashlib.sha256()
    hasher.update(str(master_seed).encode("utf-8"))
    for part in parts:
        hasher.update(b"::")
        hasher.update(str(part).encode("utf-8"))
    digest = hasher.digest()
    # Convert first 4 bytes to an unsigned 32-bit integer
    seed_int = int.from_bytes(digest[:4], byteorder="big", signed=False)
    return seed_int
