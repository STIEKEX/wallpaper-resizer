from PIL import Image


def crop_to_ratio(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Center-crop `image` so its aspect ratio matches target_w:target_h.

    Cropping BEFORE resizing is what stops the wallpaper looking stretched or
    zoomed: we remove the extra edges instead of squashing the picture.
    """
    src_w, src_h = image.size

    # Compare ratios with integer cross-multiplication to avoid float rounding.
    if src_w * target_h > target_w * src_h:
        # Source is too wide: keep full height, trim left/right.
        new_w = round(src_h * target_w / target_h)
        new_h = src_h
    else:
        # Source is too tall (or already equal): keep full width, trim top/bottom.
        new_w = src_w
        new_h = round(src_w * target_h / target_w)

    new_w = max(1, min(new_w, src_w))
    new_h = max(1, min(new_h, src_h))

    left = (src_w - new_w) // 2
    top = (src_h - new_h) // 2
    return image.crop((left, top, left + new_w, top + new_h))
