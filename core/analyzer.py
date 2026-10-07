import os

from PIL import Image

# Lower it (e.g. MAX_MEGAPIXELS=25) on a server with little RAM.
MAX_MEGAPIXELS = int(os.environ.get("MAX_MEGAPIXELS", 50))
MIN_SIDE = 320
MAX_SIDE = 7680
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp"}

# Pillow's default only warns at ~89 MP; we set our own hard limit so a
# decompression bomb can never be decoded on an 8 GB machine.
Image.MAX_IMAGE_PIXELS = MAX_MEGAPIXELS * 1_000_000


class ImageRejected(ValueError):
    """Raised with a user-friendly message when input is not acceptable."""


def validate_target(width: int, height: int) -> None:
    for side in (width, height):
        if side < MIN_SIDE or side > MAX_SIDE:
            raise ImageRejected(
                f"Target size must be between {MIN_SIDE} and {MAX_SIDE} pixels per side."
            )
    if width * height > MAX_MEGAPIXELS * 1_000_000:
        raise ImageRejected(f"Target size is above {MAX_MEGAPIXELS} megapixels.")


def check_source_size(image: Image.Image) -> None:
    """Call right after Image.open(): size comes from the header, no decoding yet."""
    w, h = image.size
    if w * h > MAX_MEGAPIXELS * 1_000_000:
        raise ImageRejected(
            f"Image is {w * h / 1e6:.1f} MP; the limit is {MAX_MEGAPIXELS} MP."
        )


def analyze(src_size: tuple[int, int], target_w: int, target_h: int,
            mode: str = "fit_blur") -> dict:
    """Describe the source and return quality warnings for the UI."""
    src_w, src_h = src_size
    warnings = []
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h
    ratio_diff = abs(src_ratio - target_ratio) / target_ratio

    # How much the part of the image that is actually used gets enlarged.
    if mode == "fill":
        if src_w * target_h > target_w * src_h:
            kept_w, kept_h = src_h * target_w / target_h, src_h
        else:
            kept_w, kept_h = src_w, src_w * target_h / target_w
        enlarged = kept_w < target_w or kept_h < target_h
    elif mode == "stretch":
        enlarged = src_w < target_w or src_h < target_h
    else:  # fit modes: the whole image is scaled to fit inside the screen
        enlarged = min(target_w / src_w, target_h / src_h) > 1

    if enlarged:
        warnings.append(
            f"Source ({src_w}x{src_h}) is smaller than your screen "
            f"({target_w}x{target_h}), so it will be enlarged and may look soft."
        )

    if mode == "fill" and ratio_diff > 0.25:
        warnings.append(
            "The image shape differs a lot from your screen, so a large part "
            "of it will be cropped away."
        )
    if mode == "stretch" and ratio_diff > 0.02:
        warnings.append("Stretch changes the image shape, so it will look distorted.")

    return {
        "source_width": src_w,
        "source_height": src_h,
        "source_ratio": round(src_ratio, 3),
        "target_ratio": round(target_ratio, 3),
        "warnings": warnings,
    }
