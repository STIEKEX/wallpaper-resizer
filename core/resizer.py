from PIL import Image


def resize_to(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize to the exact target size with Lanczos.

    Lanczos keeps edges sharp when shrinking. When enlarging it cannot invent
    detail (that is the Phase 2 AI upscaler's job), but it is still the best
    non-AI filter Pillow offers.
    """
    if image.size == (target_w, target_h):
        return image
    return image.resize((target_w, target_h), Image.LANCZOS)
