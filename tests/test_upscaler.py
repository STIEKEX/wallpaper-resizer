import io

import pytest
from PIL import Image

from core import pipeline, upscaler
from core.pipeline import process_image


def make_png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 120, 200)).save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_choose_scale_picks_smallest_enough():
    assert upscaler.choose_scale(1.4, "anime") == 2
    assert upscaler.choose_scale(2.5, "anime") == 3
    assert upscaler.choose_scale(9, "anime") == 4
    assert upscaler.choose_scale(1.1, "photo") == 4


def test_enlargement_needed_per_mode():
    # 1395x655 -> 1920x1080: fit is limited by width, fill by height.
    assert upscaler.enlargement_needed(1395, 655, 1920, 1080, "fit_blur") == pytest.approx(1.376, 0.01)
    assert upscaler.enlargement_needed(1395, 655, 1920, 1080, "fill") == pytest.approx(1.649, 0.01)


def test_fallback_to_lanczos_when_ai_fails(monkeypatch):
    def broken(*_a, **_k):
        raise upscaler.UpscaleError("GPU exploded.")
    monkeypatch.setattr(pipeline.upscaler, "upscale", broken)
    data, info = process_image(make_png(800, 450), 1920, 1080, "fit_blur", enhance=True)
    with Image.open(io.BytesIO(data)) as out:
        assert out.size == (1920, 1080)
    assert info["method"] == "Lanczos (AI fallback)"
    assert any("GPU exploded" in w for w in info["warnings"])


def test_ai_skipped_when_only_shrinking(monkeypatch):
    called = []
    monkeypatch.setattr(pipeline.upscaler, "upscale", lambda *a, **k: called.append(1))
    process_image(make_png(3840, 2160), 1920, 1080, "fit_blur", enhance=True)
    assert not called


def test_ai_output_is_used(monkeypatch):
    # Fake AI: a plain 2x resize, so the test doesn't need the GPU.
    monkeypatch.setattr(pipeline.upscaler, "upscale",
                        lambda img, needed, model: (img.resize((img.width * 2, img.height * 2)), 2))
    data, info = process_image(make_png(1000, 560), 1920, 1080, "fit_blur", enhance=True)
    with Image.open(io.BytesIO(data)) as out:
        assert out.size == (1920, 1080)
    assert info["method"].startswith("Real-ESRGAN")
    assert not any("may look soft" in w for w in info["warnings"])


@pytest.mark.skipif(not upscaler.is_available(), reason="Real-ESRGAN exe not installed")
def test_real_exe_small_image():
    with Image.new("RGB", (64, 48), (200, 80, 40)) as img:
        out, scale = upscaler.upscale(img, 1.5, "anime")
    assert scale == 2 and out.size == (128, 96)
