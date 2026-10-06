import io

from PIL import Image, ImageOps, UnidentifiedImageError

from .analyzer import ImageRejected, analyze, check_source_size, validate_target
from .cropper import crop_to_ratio
from .fitter import fit_on_canvas
from .resizer import resize_to
from . import upscaler

MODES = {"fit_blur", "fit_black", "fill", "stretch"}


def process_image(stream, target_w: int, target_h: int,
                  mode: str = "fit_blur", enhance: bool = False,
                  ai_model: str = "anime") -> tuple[bytes, dict]:
    """Upload stream -> exact-size PNG bytes plus an analysis dict.

    Kept out of app.py so the same function can be reused by a CLI or a
    public deployment later.
    """
    if mode not in MODES:
        raise ImageRejected("Unknown mode.")
    validate_target(target_w, target_h)

    try:
        with Image.open(stream) as img:
            check_source_size(img)  # header-only check, before any decoding
            # Phones store rotation in EXIF; apply it so the picture is upright.
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            info = analyze(img.size, target_w, target_h, mode)
            img, info["method"] = _maybe_upscale(img, target_w, target_h, mode,
                                                 enhance, ai_model, info["warnings"])

            # Every mode below ends in a Lanczos resize, so an AI-upscaled
            # image is simply shrunk to the exact screen size (sharp result).
            if mode == "fit_blur":
                img = fit_on_canvas(img, target_w, target_h, "blur")
            elif mode == "fit_black":
                img = fit_on_canvas(img, target_w, target_h, "black")
            elif mode == "fill":
                img = resize_to(crop_to_ratio(img, target_w, target_h), target_w, target_h)
            else:  # stretch: whole image, but distorted if ratios differ
                img = resize_to(img, target_w, target_h)

            out = io.BytesIO()
            img.save(out, format="PNG")  # lossless, so no extra quality loss
            return out.getvalue(), info
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        if isinstance(exc, Image.DecompressionBombError):
            raise ImageRejected("Image is too large (over 50 megapixels).") from exc
        raise ImageRejected("This file could not be read as a valid image.") from exc


def _maybe_upscale(img, target_w, target_h, mode, enhance, ai_model, warnings):
    """Run AI upscaling only when it can help; never fail the whole request."""
    needed = upscaler.enlargement_needed(img.width, img.height, target_w, target_h, mode)
    if needed <= 1:
        return img, None  # shrinking only: Lanczos is already ideal
    if not enhance:
        return img, "Lanczos (AI enhance was off)"

    try:
        big, scale = upscaler.upscale(img, needed, ai_model)
    except upscaler.UpscaleError as exc:
        warnings.append(f"{exc} Used normal (Lanczos) resizing instead.")
        return img, "Lanczos (AI fallback)"
    except MemoryError:
        warnings.append("Ran out of memory during AI upscaling. Used normal (Lanczos) resizing instead.")
        return img, "Lanczos (AI fallback)"

    img.close()  # free the small original; we only need the big one now
    if scale < needed:
        warnings.append(
            f"Image needed {needed:.1f}x enlargement; AI did {scale}x and the rest was Lanczos."
        )
    else:
        # The AI result is good, so drop the generic "may look soft" warning.
        warnings[:] = [w for w in warnings if "may look soft" not in w]
    return big, f"Real-ESRGAN {ai_model} {scale}x, then Lanczos to exact size"
