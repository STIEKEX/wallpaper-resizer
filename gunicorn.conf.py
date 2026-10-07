"""Production server settings, read automatically by `gunicorn app:app`."""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
# One process, several threads: the rate limiter and the job limit in app.py
# live in memory, so they only work if every request sees the same process.
# Pillow releases the GIL while resizing, so threads still run in parallel.
workers = 1
threads = int(os.environ.get("THREADS", "8"))
timeout = 120
accesslog = "-"
