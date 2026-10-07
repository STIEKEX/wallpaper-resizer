import io
import threading

from PIL import Image

import app as app_module
from app import RateLimiter, app


def png_upload(w=400, h=300):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(buf, format="PNG")
    buf.seek(0)
    return {"image": (buf, "x.png"), "width": "640", "height": "480",
            "mode": "fit_black", "enhance": "0"}


def test_status_reports_ai_and_limits():
    resp = app.test_client().get("/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data["ai_available"], bool)
    assert data["limits"] == {"min_side": 320, "max_side": 7680,
                              "max_megapixels": 50, "max_upload_mb": 20}


def test_index_renders_with_versioned_assets():
    resp = app.test_client().get("/")
    assert resp.status_code == 200
    assert b"Wallpaper Resizer" in resp.data
    assert b"/static/script.js?v=" in resp.data
    assert resp.headers["Cache-Control"] == "no-cache"


def test_security_headers_present():
    resp = app.test_client().get("/")
    csp = resp.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    # The page must not need inline scripts, or the CSP would block them.
    assert b"<script>" not in resp.data


def test_process_returns_png_of_exact_size():
    resp = app.test_client().post("/process", data=png_upload(),
                                  content_type="multipart/form-data")
    assert resp.status_code == 200
    assert Image.open(io.BytesIO(resp.data)).size == (640, 480)
    assert resp.headers["Cache-Control"] == "no-store"


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr(app_module, "limiter", RateLimiter(1))
    client = app.test_client()
    first = client.post("/process", data=png_upload(), content_type="multipart/form-data")
    second = client.post("/process", data=png_upload(), content_type="multipart/form-data")
    assert first.status_code == 200
    assert second.status_code == 429


def test_rate_limiter_zero_means_off():
    limiter = RateLimiter(0)
    assert all(limiter.allow("1.2.3.4") for _ in range(100))


def test_busy_server_returns_503(monkeypatch):
    sem = threading.BoundedSemaphore(1)
    sem.acquire()  # simulate a job already running
    monkeypatch.setattr(app_module, "jobs", sem)
    monkeypatch.setattr(app_module, "JOB_WAIT_SECONDS", 0)
    resp = app.test_client().post("/process", data=png_upload(),
                                  content_type="multipart/form-data")
    assert resp.status_code == 503
