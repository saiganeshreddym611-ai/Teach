"""Fetch the TTS model files into services/tutor/models (gitignored).

    python scripts/download_tts_models.py            # Piper default voice only (~60 MB)
    python scripts/download_tts_models.py --kokoro   # + Kokoro fp32 model + voices (~340 MB)
    python scripts/download_tts_models.py --piper en_GB-jenny_dioco-medium en_US-lessac-medium

Piper voices come from rhasspy/piper-voices on Hugging Face via piper's own
downloader; Kokoro files from the thewh1teagle/kokoro-onnx GitHub release.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

MODELS = Path(__file__).resolve().parents[1] / "models"
KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"


def fetch(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"exists  {dest.name}")
        return
    print(f"getting {dest.name} ...", flush=True)
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    print(f"done    {dest.name} ({dest.stat().st_size // (1 << 20)} MB)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--piper", nargs="*", default=["en_GB-jenny_dioco-medium", "en_US-hfc_female-medium", "en_US-amy-medium", "en_GB-alba-medium", "en_GB-alan-medium"], help="Piper voice names")
    ap.add_argument("--kokoro", action="store_true", help="also fetch Kokoro fp32 + voices")
    ap.add_argument("--kokoro-variant", default="kokoro-v1.0.onnx",
                    help="kokoro-v1.0.onnx (fp32, fastest on CPUs without VNNI) | kokoro-v1.0.fp16.onnx | kokoro-v1.0.int8.onnx")
    args = ap.parse_args()
    MODELS.mkdir(exist_ok=True)

    if args.piper:
        subprocess.run(
            [sys.executable, "-m", "piper.download_voices", "--download-dir", str(MODELS), *args.piper],
            check=True,
        )
    if args.kokoro:
        fetch(KOKORO_BASE + args.kokoro_variant, MODELS / args.kokoro_variant)
        fetch(KOKORO_BASE + "voices-v1.0.bin", MODELS / "voices-v1.0.bin")


if __name__ == "__main__":
    main()
