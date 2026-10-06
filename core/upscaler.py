"""Phase 2: AI upscaling with the Real-ESRGAN ncnn-vulkan executable.

The exe runs on any Vulkan GPU (including the Ryzen's integrated Radeon), so
no CUDA / PyTorch is needed. We talk to it through files + subprocess, which
also keeps its memory use outside our Python process.
"""
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parent.parent
# Can be overridden if the exe lives somewhere else.
EXE_PATH = Path(os.environ.get(
    "REALESRGAN_PATH",
    PROJECT_DIR / "tools" / "realesrgan" / "realesrgan-ncnn-vulkan.exe",
))

TILE_SIZE = 100          # small tiles = low RAM/VRAM; never 0 (auto) on 8 GB
TIMEOUT_SECONDS = 300
MAX_OUTPUT_MP = 50       # same RAM rule as everywhere else

# "anime" model supports 2x/3x/4x, so we can pick the smallest that is enough.
# The photo model only exists as 4x in the ncnn release.
MODELS = {
    "anime": ("realesr-animevideov3", (2, 3, 4)),
    "photo": ("realesrgan-x4plus", (4,)),
}


# Flask serves requests on several threads; this makes sure only ONE upscale
# runs at a time, because two at once could run an 8 GB laptop out of RAM.
_gpu_lock = threading.Lock()


class UpscaleError(RuntimeError):
    """Upscaling could not run; the caller falls back to Lanczos."""


def is_available() -> bool:
    return EXE_PATH.is_file()


def choose_scale(needed: float, model: str) -> int:
    """Smallest supported factor that reaches the needed enlargement.

    Using 2x when 2x is enough is ~4x less work and memory than 4x.
    """
    scales = MODELS[model][1]
    for s in scales:
        if s >= needed:
            return s
    return scales[-1]  # need more than 4x: do 4x, Lanczos does the rest


def upscale(image: Image.Image, needed: float, model: str = "anime") -> tuple[Image.Image, int]:
    """Return (upscaled RGB image, factor used). Raises UpscaleError on any failure."""
    if model not in MODELS:
        raise UpscaleError(f"Unknown AI model '{model}'.")
    if not is_available():
        raise UpscaleError("Real-ESRGAN is not installed (tools/realesrgan).")

    model_name, _ = MODELS[model]
    scale = choose_scale(needed, model)
    out_mp = image.width * scale * image.height * scale / 1e6
    if out_mp > MAX_OUTPUT_MP:
        raise UpscaleError(
            f"AI output would be {out_mp:.0f} MP, above the {MAX_OUTPUT_MP} MP RAM limit."
        )

    # TemporaryDirectory deletes both files even if something fails.
    with _gpu_lock, tempfile.TemporaryDirectory(prefix="wr_") as tmp:
        src = Path(tmp) / "in.png"
        dst = Path(tmp) / "out.png"
        image.save(src, format="PNG")

        cmd = [
            str(EXE_PATH),
            "-i", str(src), "-o", str(dst),
            "-n", model_name, "-s", str(scale),
            "-t", str(TILE_SIZE), "-f", "png",
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=EXE_PATH.parent,  # exe finds its models/ folder relative to here
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                # Don't flash a console window on Windows.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise UpscaleError("AI upscaling took too long and was stopped.") from exc
        except OSError as exc:
            raise UpscaleError(f"Could not start Real-ESRGAN: {exc}") from exc

        # The exe sometimes exits 0 even on failure, so also check the file.
        if result.returncode != 0 or not dst.is_file():
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            last = detail[-1] if detail else f"exit code {result.returncode}"
            raise UpscaleError(f"Real-ESRGAN failed: {last}")

        with Image.open(dst) as out:
            out.load()  # read pixels now, before the temp folder is deleted
            return out.convert("RGB"), scale


def enlargement_needed(src_w: int, src_h: int, target_w: int, target_h: int, mode: str) -> float:
    """How much the used part of the image must grow for this fit mode."""
    if mode in ("fit_blur", "fit_black"):
        return min(target_w / src_w, target_h / src_h)
    # fill and stretch both need every axis to reach the target
    return max(target_w / src_w, target_h / src_h)
