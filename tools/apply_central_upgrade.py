#!/usr/bin/env python3
import base64
import hashlib
import io
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_DIR = ROOT / "tools" / "upgrade_payload"
PARTS = [
    ("part00", "899f1b12a552c1aab00f50650661ecedb946f1267ac6f2aa32939cca8df5283b"),
    ("part01", "6dafa1910f09c4b66a1944403d44038ae4148477d0be73cfff9ab4125fc8e4f9"),
    ("part02a", "49c00a6990547d25cfcb348f1fafd0ff827bd27cee9d9f05c6a7c8f508b77cf1"),
    ("part02b", "8da252415b547a90542a217296fc4f5281ca2a5aff76c9602a1dc29fa07f1697"),
    ("part03a", "332f53e7cc8303403a594782ddeec7485eddc659433faa9f066e96f6cced833d"),
    ("part03b", "a93922b9afc4c709c27ea8bea3a95eda1d9b3ebf0a66fee0ecf6b13fd4e071b9"),
    ("part04", "acdeaf030db4fc7d5b9456f67ce3491231db9988b97e7c4b0e855fe5ea8666ea"),
    ("part05", "df916f74936079d01f757f99b696860d55f8b81945be9afa79c0537ba4339c76"),
    ("part06", "c243494904caf3ffec2f602ac008b80ce13b7e6f3678a9bad5fca6d45407fc40"),
]

encoded_parts = []
for name, expected in PARTS:
    part = PAYLOAD_DIR / name
    if not part.is_file():
        raise SystemExit(f"Upgrade payload part is missing: {name}")
    raw = part.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    print(f"{name}: bytes={len(raw)} sha256={digest}")
    if digest != expected:
        raise SystemExit(f"Corrupted payload part: {name}")
    encoded_parts.append(raw.decode("utf-8").strip())

encoded = "".join(encoded_parts)
encoded_hash = hashlib.sha256(encoded.encode()).hexdigest()
print(f"payload: chars={len(encoded)} sha256={encoded_hash}")
if len(encoded) != 53920 or encoded_hash != "8879851d87e81af3471cb959898f137f1644e39100786545e78d7bb1138e870b":
    raise SystemExit("Combined upgrade payload failed integrity validation")

archive = base64.b64decode(encoded, validate=True)
archive_hash = hashlib.sha256(archive).hexdigest()
if archive_hash != "e94cd96c49c1247f48b06cff531fb22fd646fb1708a4ef281c8505264e16e07e":
    raise SystemExit("Decoded upgrade archive failed integrity validation")

with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
    for member in bundle.getmembers():
        target = (ROOT / member.name).resolve()
        if ROOT not in target.parents and target != ROOT:
            raise SystemExit(f"Unsafe bundle path: {member.name}")
    bundle.extractall(ROOT)

shutil.rmtree(PAYLOAD_DIR)
Path(__file__).unlink()
print("A+Pay central multi-vendor upgrade applied")
