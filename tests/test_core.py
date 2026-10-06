import io

import pytest
from PIL import Image

from core.analyzer import ImageRejected, analyze, validate_target
from core.cropper import crop_to_ratio
from core.pipeline import process_image
from core.resizer import resize_to


def make_png(w, h, color=(200, 50, 50)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    buf.seek(0)
    return buf


@pytest.mark.parametrize(
    "src",
    [(1000, 2000), (3000, 1000), (3440, 1440), (1920, 1080), (100, 100)],
)
def test_crop_matches_target_ratio(src):
    with Image.new("RGB", src) as img:
        out = crop_to_ratio(img, 1920, 1080)
    # Allow 1px rounding error on the ratio.
    assert abs(out.width / out.height - 1920 / 1080) < 0.02
    assert out.width <= src[0] and out.height <= src[1]


def test_crop_is_centered():
    img = Image.new("RGB", (300, 100), (0, 0, 0))
    img.paste((255, 0, 0), (0, 0, 100, 100))      # left third red
    img.paste((0, 255, 0), (100, 0, 200, 100))    # middle third green
    img.paste((0, 0, 255), (200, 0, 300, 100))    # right third blue
    out = crop_to_ratio(img, 1, 1)                # 100x100 from the middle
    assert out.size == (100, 100)
    assert out.getpixel((50, 50)) == (0, 255, 0)
    assert out.getpixel((0, 50)) == (0, 255, 0)


# ---- The five requested cases, each targeting 1920x1080 (16:9) ----

def test_case1_wider_image_to_16_9():
    # 3:1 panorama -> keep full height, trim the sides equally.
    with Image.new("RGB", (3000, 1000)) as img:
        cropped = crop_to_ratio(img, 1920, 1080)
        assert cropped.size == (1778, 1000)          # 1000 * 16/9 = 1777.8
        assert resize_to(cropped, 1920, 1080).size == (1920, 1080)


def test_case2_taller_image_to_16_9():
    # Portrait -> keep full width, trim top and bottom equally.
    with Image.new("RGB", (1000, 2000)) as img:
        cropped = crop_to_ratio(img, 1920, 1080)
        assert cropped.width == 1000
        assert cropped.height in (562, 563)          # 1000 * 9/16 = 562.5
        assert resize_to(cropped, 1920, 1080).size == (1920, 1080)


def test_case3_already_right_ratio_untouched():
    with Image.new("RGB", (3840, 2160)) as img:
        cropped = crop_to_ratio(img, 1920, 1080)
        assert cropped.size == (3840, 2160)          # nothing cut off
        assert resize_to(cropped, 1920, 1080).size == (1920, 1080)


def test_case4_smaller_than_target_is_enlarged_and_warned():
    with Image.new("RGB", (640, 360)) as img:
        cropped = crop_to_ratio(img, 1920, 1080)
        assert cropped.size == (640, 360)
        assert resize_to(cropped, 1920, 1080).size == (1920, 1080)
    assert any("smaller than your screen" in w
               for w in analyze((640, 360), 1920, 1080, "fill")["warnings"])


def test_case5_exif_rotated_image():
    # Camera stored a 2000x1000 landscape buffer but EXIF says "rotate 90",
    # so the real photo is 1000x2000 portrait. It must be treated as portrait.
    img = Image.new("RGB", (2000, 1000), (10, 20, 30))
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    data, info = process_image(buf, 1920, 1080, "fill")
    assert (info["source_width"], info["source_height"]) == (1000, 2000)
    with Image.open(io.BytesIO(data)) as out:
        assert out.size == (1920, 1080)


def test_resize_exact_size_up_and_down():
    img = Image.new("RGB", (800, 450))
    assert resize_to(img, 400, 225).size == (400, 225)
    assert resize_to(img, 1920, 1080).size == (1920, 1080)


@pytest.mark.parametrize("src", [(1000, 2000), (4000, 1000), (50, 50), (3840, 2160)])
def test_pipeline_exact_output_size(src):
    data, _ = process_image(make_png(*src), 1920, 1080)
    with Image.open(io.BytesIO(data)) as out:
        assert out.size == (1920, 1080)
        assert out.format == "PNG"


def test_pipeline_exif_rotation():
    # Orientation 6 = rotate 90 degrees; stored 200x100 becomes 100x200 upright.
    img = Image.new("RGB", (200, 100), (10, 20, 30))
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    _, info = process_image(buf, 320, 320)
    assert (info["source_width"], info["source_height"]) == (100, 200)


def test_warning_when_source_smaller():
    assert analyze((800, 600), 1920, 1080)["warnings"]
    assert not analyze((3840, 2160), 1920, 1080)["warnings"]


@pytest.mark.parametrize("w,h", [(100, 1080), (1920, 8000), (7680, 7680)])
def test_bad_targets_rejected(w, h):
    with pytest.raises(ImageRejected):
        validate_target(w, h)


def test_non_image_rejected():
    with pytest.raises(ImageRejected):
        process_image(io.BytesIO(b"not an image"), 1920, 1080)


def test_source_over_50mp_rejected():
    # Header-only PNG-sized image: 8000x7000 = 56 MP of a flat color compresses small.
    buf = make_png(8000, 7000)
    with pytest.raises(ImageRejected):
        process_image(buf, 1920, 1080)


@pytest.mark.parametrize("mode", ["fit_blur", "fit_black", "stretch", "fill"])
@pytest.mark.parametrize("src", [(1395, 655), (1000, 2000), (50, 50)])
def test_all_modes_exact_size(mode, src):
    data, _ = process_image(make_png(*src), 1920, 1080, mode)
    with Image.open(io.BytesIO(data)) as out:
        assert out.size == (1920, 1080)


def test_fit_keeps_whole_image_nothing_cropped():
    # Mark all four corners of a 1395x655 image; every marker must survive.
    img = Image.new("RGB", (1395, 655), (0, 0, 0))
    for box in [(0, 0, 40, 40), (1355, 0, 1395, 40), (0, 615, 40, 655), (1355, 615, 1395, 655)]:
        img.paste((255, 0, 0), box)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    data, _ = process_image(buf, 1920, 1080, "fit_black")
    with Image.open(io.BytesIO(data)) as out:
        # Fitted image is 1920x901 centered: top offset (1080-901)//2 = 89.
        assert out.getpixel((5, 89 + 5)) == (255, 0, 0)
        assert out.getpixel((1914, 89 + 5)) == (255, 0, 0)
        assert out.getpixel((5, 89 + 895)) == (255, 0, 0)
        assert out.getpixel((1914, 89 + 895)) == (255, 0, 0)
        assert out.getpixel((960, 10)) == (0, 0, 0)  # black bar


def test_unknown_mode_rejected():
    with pytest.raises(ImageRejected):
        process_image(make_png(500, 500), 1920, 1080, "nope")
