#!/usr/bin/env python3
import base64
import io
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_DIR = ROOT / "tools" / "upgrade_payload"
parts = sorted(PAYLOAD_DIR.glob("part*"))
if not parts:
    raise SystemExit("Upgrade payload is missing")

encoded = "".join(part.read_text(encoding="utf-8").strip() for part in parts)
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
