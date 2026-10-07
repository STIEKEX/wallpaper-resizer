# Wallpaper Resizer

Turn any image into a wallpaper that fits your screen **exactly**: no
stretching, no "zoomed in" look, and sharper results for small images thanks
to optional AI upscaling.

Run it locally (Flask on `localhost`, nothing leaves your computer) or deploy
it as a small web app. Either way, images are processed in memory and never
kept on disk (AI upscaling uses a temporary folder that is deleted right after
each run).

## Features

- **Detects your screen resolution** (editable, in case detection is wrong
  because of Windows scaling, browser zoom or multiple monitors).
- **Four fit modes**
  | Mode | Keeps whole image | Distortion | Fills the gap with |
  |---|---|---|---|
  | Fit, blurred background (default) | Yes | No | Blurred copy of the image |
  | Fit, black bars | Yes | No | Black |
  | Stretch | Yes | Yes | Nothing |
  | Fill | No (edges cropped) | No | Nothing |
- **AI upscaling (optional)** with
  [Real-ESRGAN ncnn-vulkan](https://github.com/xinntao/Real-ESRGAN): makes
  small images sharp instead of blurry. Works on any Vulkan GPU, including
  integrated AMD/Intel graphics. No NVIDIA/CUDA needed.
  - *Anime / illustration* model (2x/3x/4x, fast)
  - *Real photo* model (4x, slower)
- **Live preview** in the browser that updates instantly as you change the
  size or fit mode, plus a before/after slider when AI was used.
- **Desktop preview**: see the wallpaper full-screen with a mock taskbar and
  icons before downloading.
- Responsive UI with a resizable, collapsible settings sidebar, dark mode,
  drag-and-drop and paste (Ctrl+V). Tested in Chrome, Firefox and WebKit
  (Safari's engine) from 320 px phones to desktop.
- Lossless **PNG** output, automatic EXIF rotation fix.

## Requirements

- Windows 10/11 (other OSes work for the non-AI part; the AI step uses the
  Windows build of Real-ESRGAN)
- Python 3.11+
- For AI upscaling: a GPU with Vulkan support (most GPUs from the last ~8 years)

## Setup

```powershell
git clone https://github.com/STIEKEX/wallpaper-resizer.git
cd wallpaper-resizer
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Optional: install Real-ESRGAN for AI upscaling

The app works without this. AI enhance then falls back to normal (Lanczos)
resizing and tells you so.

1. Download `realesrgan-ncnn-vulkan-20220424-windows.zip` (≈45 MB) from the
   official release:
   https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0
2. (Optional) check the file: the release has no official checksum, but the
   copy this project was tested with had
   ```
   SHA256  ABC02804E17982A3BE33675E4D471E91EA374E65B70167ABC09E31ACB412802D
   ```
   ```powershell
   Get-FileHash .\realesrgan-ncnn-vulkan-20220424-windows.zip -Algorithm SHA256
   ```
3. Unzip it so the exe ends up here:
   ```
   tools/realesrgan/realesrgan-ncnn-vulkan.exe
   tools/realesrgan/models/...
   ```
   Or point to another location with the `REALESRGAN_PATH` environment variable.

## Run

```powershell
python app.py
```

Open http://127.0.0.1:5000, check the detected resolution, pick an image and
a fit mode, then click **Make wallpaper**.

`python app.py` uses Flask's development server and is meant for local use
only. For a public site, see [Deploy](#deploy).

## Deploy

The production setup is `gunicorn` (configured in `gunicorn.conf.py`) behind
the HTTPS proxy that your host provides.

**Docker** (Render, Railway, Fly.io, Koyeb, any VPS):

```bash
docker build -t wallpaper-resizer .
docker run -p 8000:8000 -e TRUST_PROXY=1 wallpaper-resizer
```

**Without Docker** (Linux host or a PaaS that reads `Procfile`):

```bash
pip install -r requirements.txt
gunicorn app:app        # reads gunicorn.conf.py and $PORT
```

Health check URL: `/status`.

### Settings (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | 8000 (gunicorn), 5000 (`app.py`) | Port to listen on |
| `TRUST_PROXY` | off | Set to `1` **only** behind a reverse proxy, so rate limiting sees the real client IP |
| `RATE_LIMIT_PER_MIN` | 20 | Image jobs per IP per minute (`0` = off) |
| `MAX_CONCURRENT_JOBS` | 2 | Images processed at once; extra requests wait up to 10 s, then get "busy" |
| `MAX_UPLOAD_MB` | 20 | Largest upload |
| `MAX_MEGAPIXELS` | 50 | Largest source and output image; use about 25 on a 512 MB server |
| `THREADS` | 8 | gunicorn threads |
| `REALESRGAN_PATH` | `tools/realesrgan/...exe` | Real-ESRGAN binary |

### What the production setup adds

- Security headers: a strict Content-Security-Policy (no inline scripts or
  styles), `nosniff`, no framing, `no-referrer`.
- Per-IP rate limit and a cap on concurrent jobs, so a few users can't
  exhaust the server's memory.
- Static files are versioned (`?v=<mtime>`) and cached for a year; the page
  itself is never cached, so a new deploy shows up immediately.
- The container runs as a non-root user.

### AI upscaling on a server

Typical cloud hosts have **no GPU and no Vulkan**, and the bundled binary is
the Windows build. There, AI enhance is reported as unavailable and the app
uses Lanczos resizing instead (the page says so before you click). To get AI on
a server you need a Vulkan-capable GPU host and the Linux build of
`realesrgan-ncnn-vulkan`, pointed to with `REALESRGAN_PATH`.

## Tests

```powershell
pytest
```

The test that runs the real Real-ESRGAN exe is skipped automatically if it is
not installed.

## How it works

1. Open the image, apply EXIF rotation, convert to RGB.
2. If the image must be **enlarged** and AI enhance is on, upscale it 2x/3x/4x
   with Real-ESRGAN (smallest factor that is enough).
3. Apply the chosen fit mode (fit on a blurred/black canvas, stretch, or
   center-crop).
4. Resize to the exact screen size with Lanczos and return a PNG.

Image logic lives in `core/` (no Flask code), the web layer is `app.py`.

```
app.py              Flask routes, security headers, rate limit
gunicorn.conf.py    production server settings
Dockerfile          container image
core/analyzer.py    validation, limits, quality warnings
core/cropper.py     center crop to an aspect ratio
core/fitter.py      fit whole image on blurred/black background
core/resizer.py     Lanczos resize
core/upscaler.py    Real-ESRGAN wrapper (subprocess)
core/pipeline.py    ties the steps together
templates/, static/ single-page frontend (plain HTML/CSS/JS)
tests/              pytest
```

## Limits

- Upload: jpg, jpeg, png, webp, bmp, up to 20 MB and 50 megapixels.
- Target size: 320 to 7680 px per side, up to 50 megapixels.
- AI output is capped at 50 megapixels; one AI job runs at a time.
  These limits keep it usable on an 8 GB RAM laptop.

## Known limitations

- AI upscaling **guesses** detail. It looks sharp, but small text, faces or
  logos may come out slightly wrong.
- AI does not change the image's **shape**. A portrait image on a landscape
  screen still needs bars, a blurred background, or cropping.
- The rate limit and job limit live in memory, so they hold per process. That
  is why gunicorn runs one worker with threads. If you scale to several
  instances, each one counts separately; use your host's limits or a shared
  store (e.g. Redis) at that point.
- No accounts or analytics.
