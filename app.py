import json
import os
import threading
import time
from collections import deque
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from core import upscaler
from core.analyzer import (ALLOWED_EXTENSIONS, MAX_MEGAPIXELS, MAX_SIDE,
                           MIN_SIDE, ImageRejected)
from core.pipeline import process_image


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


BASE_DIR = Path(__file__).parent
MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 20)
# Each job can hold a few hundred MB of pixels; this caps peak RAM on a server.
MAX_CONCURRENT_JOBS = _env_int("MAX_CONCURRENT_JOBS", 2)
JOB_WAIT_SECONDS = 10
RATE_LIMIT_PER_MIN = _env_int("RATE_LIMIT_PER_MIN", 20)  # 0 turns it off

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"),
            static_folder=str(BASE_DIR / "static"))
# Flask rejects bigger bodies with a 413 before our code runs.
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
# Static URLs carry ?v=<mtime> (see asset()), so browsers may cache them for a year.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 365

if os.environ.get("TRUST_PROXY") == "1":
    # Only behind a reverse proxy (Render, Railway, nginx...): take the client IP
    # from its X-Forwarded-For. Without a proxy this header could be faked.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
       "script-src 'self'; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


class RateLimiter:
    """Sliding one-minute window per client IP, kept in memory.

    Counts are per process, which is why gunicorn.conf.py runs one worker
    with several threads instead of several workers.
    """

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            if len(self._hits) > 10_000:  # forget idle clients so memory stays bounded
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] <= 60}
            return True


limiter = RateLimiter(RATE_LIMIT_PER_MIN)
jobs = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)


@app.context_processor
def asset_helper():
    def asset(filename: str) -> str:
        # The version changes whenever the file does, so a deploy is never
        # served with an old cached script or stylesheet.
        mtime = int((BASE_DIR / "static" / filename).stat().st_mtime)
        return url_for("static", filename=filename, v=mtime)
    return {"asset": asset}


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return resp


@app.errorhandler(413)
def too_large(_):
    return jsonify(error=f"File is larger than {MAX_UPLOAD_MB} MB."), 413


@app.get("/")
def index():
    resp = Response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-cache"  # always pick up new asset versions
    return resp


@app.get("/status")
def status():
    # Lets the page say up front whether AI enhance can run, instead of
    # finding out only after a slow request falls back to Lanczos.
    return jsonify(
        ai_available=upscaler.is_available(),
        limits=dict(min_side=MIN_SIDE, max_side=MAX_SIDE,
                    max_megapixels=MAX_MEGAPIXELS, max_upload_mb=MAX_UPLOAD_MB),
    )


@app.post("/process")
def process():
    if not limiter.allow(request.remote_addr or "unknown"):
        return jsonify(error="Too many requests. Please wait a minute and try again."), 429

    file = request.files.get("image")
    if file is None or not file.filename:
        return jsonify(error="Please choose an image first."), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify(error="Only jpg, jpeg, png, webp and bmp files are allowed."), 400

    try:
        width = int(request.form["width"])
        height = int(request.form["height"])
    except (KeyError, ValueError):
        return jsonify(error="Width and height must be whole numbers."), 400

    if not jobs.acquire(timeout=JOB_WAIT_SECONDS):
        return jsonify(error="The server is busy with other images. Try again in a few seconds."), 503
    try:
        # Read straight from the upload stream: nothing is written to disk.
        mode = request.form.get("mode", "fit_blur")
        enhance = request.form.get("enhance") == "1"
        ai_model = request.form.get("ai_model", "anime")
        png_bytes, info = process_image(file.stream, width, height, mode, enhance, ai_model)
    except ImageRejected as exc:
        return jsonify(error=str(exc)), 400
    except MemoryError:
        return jsonify(error="Not enough memory for this image. Try a smaller one."), 507
    finally:
        jobs.release()

    resp = Response(png_bytes, mimetype="image/png")
    # Warnings travel in a header so the body can stay the raw PNG for the blob URL.
    resp.headers["X-Wallpaper-Info"] = json.dumps(info)
    resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    # Local development only; production runs gunicorn (see gunicorn.conf.py).
    # debug=False: the Werkzeug debugger allows code execution; keep it off.
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=_env_int("PORT", 5000), debug=False)
