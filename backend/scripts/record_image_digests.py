"""Record the content-addressed digests of the locally built images."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _digest(image: str) -> str:
    try:
        value = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except FileNotFoundError as exc:
        raise RuntimeError(
            "docker is required to record image digests; build the stack with "
            "`docker compose up -d --build` first"
        ) from exc
    if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise RuntimeError(f"Docker returned a non-content-addressed ID for {image}")
    return value


def record_image_digests(output: Path | None = None) -> dict[str, str]:
    # The same defaults `docker-compose.yml` uses, and the same overrides, so
    # a stack built under different tags records the images it actually built.
    manifest = {
        "api": _digest(os.environ.get("BACKEND_IMAGE") or "shiftmind-backend:local"),
        "web": _digest(os.environ.get("WEB_IMAGE") or "shiftmind-web:local"),
        "database": "postgres:18",
    }
    target = output or (REPO_ROOT / ".build" / "image-digests.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    record_image_digests()
