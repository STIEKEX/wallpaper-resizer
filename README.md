# Wallpaper Resizer

Turn any image into a wallpaper that fits your screen **exactly**: no
stretching, no "zoomed in" look, and sharper results for small images thanks
to optional AI upscaling.

It runs locally in your browser (Flask on `localhost`). Nothing is uploaded to
the internet, and images are not kept on disk (AI upscaling uses a temporary
folder that is deleted right after each run).

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
- **Desktop preview**: see the wallpaper full-screen with a mock taskbar and
  icons before downloading.
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
app.py              Flask routes
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
- Built for local use. It has no rate limiting or accounts and uses Flask's
  development server, so it is **not** ready to be exposed to the internet
  as-is.
