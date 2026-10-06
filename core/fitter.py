from PIL import Image, ImageFilter

from .cropper import crop_to_ratio


def fit_inside(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Scale the WHOLE image to the largest size that fits inside the target.

    Aspect ratio is preserved, so nothing is cropped and nothing is distorted.
    """
    scale = min(target_w / image.width, target_h / image.height)
    new_w = max(1, min(target_w, round(image.width * scale)))
    new_h = max(1, min(target_h, round(image.height * scale)))
    return image.resize((new_w, new_h), Image.LANCZOS)


def blurred_background(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Fill the leftover space with a blurred copy of the same picture.

    The blur is done on a tiny version and then enlarged: it looks identical
    (blur removes detail anyway) but uses far less RAM and time at 4K.
    """
    bg = crop_to_ratio(image, target_w, target_h)
    small_w = 192
    small_h = max(1, round(small_w * target_h / target_w))
    bg = bg.resize((small_w, small_h), Image.BILINEAR)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=6))
    bg = bg.resize((target_w, target_h), Image.BICUBIC)
    # Slightly darken so the real image stands out from its own background.
    return Image.eval(bg, lambda v: int(v * 0.7))


def fit_on_canvas(image: Image.Image, target_w: int, target_h: int,
                  background: str = "blur") -> Image.Image:
    """Whole image, centered, on a canvas of exactly target_w x target_h."""
    if background == "blur":
        canvas = blurred_background(image, target_w, target_h)
    else:
        canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    fg = fit_inside(image, target_w, target_h)
    canvas.paste(fg, ((target_w - fg.width) // 2, (target_h - fg.height) // 2))
    return canvas
