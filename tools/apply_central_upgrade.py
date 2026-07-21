#!/usr/bin/env python3
import base64
import hashlib
import io
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_DIR = ROOT / "tools" / "upgrade_payload"
EXPECTED = {
    "part00": "899f1b12a552c1aab00f50650661ecedb946f1267ac6f2aa32939cca8df5283b",
    "part01": "6dafa1910f09c4b66a1944403d44038ae4148477d0be73cfff9ab4125fc8e4f9",
    "part02": "9cb4280eb32c7b465c492425d83ec99a5e8815635d5f160a4feda2a8f652cee7",
    "part03": "b5c7cfc0a4d12fa2a67a5b35e98540dca2e8e24aacfe481a3cdfad729bb9fde8",
    "part04": "acdeaf030db4fc7d5b9456f67ce3491231db9988b97e7c4b0e855fe5ea8666ea",
    "part05": "df916f74936079d01f757f99b696860d55f8b81945be9afa79c0537ba4339c76",
    "part06": "c243494904caf3ffec2f602ac008b80ce13b7e6f3678a9bad5fca6d45407fc40",
}
parts = sorted(PAYLOAD_DIR.glob("part*"))
if not parts:
    raise SystemExit("Upgrade payload is missing")

bad = []
for part in parts:
    digest = hashlib.sha256(part.read_bytes()).hexdigest()
    print(f"{part.name}: bytes={part.stat().st_size} sha256={digest}")
    if EXPECTED.get(part.name) != digest:
        bad.append(part.name)
if bad:
    raise SystemExit("Corrupted payload parts: " + ", ".join(bad))

encoded = "".join(part.read_text(encoding="utf-8").strip() for part in parts)
print(f"payload: chars={len(encoded)} sha256={hashlib.sha256(encoded.encode()).hexdigest()}")
archive = base64.b64decode(encoded, validate=True)
with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
    for member in bundle.getmembers():
        target = (ROOT / member.name).resolve()
        if ROOT not in target.parents and target != ROOT:
            raise SystemExit(f"Unsafe bundle path: {member.name}")
    bundle.extractall(ROOT)

shutil.rmtree(PAYLOAD_DIR)
Path(__file__).unlink()
print("A+Pay central multi-vendor upgrade applied")
