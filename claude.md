# Wallpaper Resizer

## What this project is
A local website where a user uploads any image, the site auto-detects the
user's real screen resolution, and the backend returns a wallpaper that fits
that screen exactly, in the best possible quality.

Problems it solves:
1. Wallpaper looks "far away" or "too zoomed in" -> caused by aspect ratio
   mismatch. Fix: crop to the screen's aspect ratio before resizing.
2. Wallpaper looks blurry -> caused by bad resizing or upscaling. Fix: use
   Lanczos for shrinking, and (Phase 2) AI upscaling for enlarging.

Right now this runs ONLY on my own laptop (localhost). Public hosting is a
future idea. Do not add deployment code, auth, or databases during Phase 1
and Phase 2. A database and auth ARE planned for Phase 3 (see below), so keep
image logic in core/ and web logic in app.py to make that easy to add later.

## My machine
- Windows 11 Home (25H2), HP Victus 15 laptop
- CPU: AMD Ryzen 5 5600H (6 cores / 12 threads)
- GPU: integrated AMD Radeon graphics (shares system RAM)
- RAM: 8 GB installed, only 7.34 GB usable. This is the main limit.
- No NVIDIA GPU, so NO CUDA and NO PyTorch. Use Vulkan-based tools only.
- Use Windows-friendly commands (PowerShell), not Linux-only ones.

### Memory rules (because of 7.34 GB usable RAM)
- Reject images above 50 megapixels (width * height) with a clear message.
- Process one image at a time. No parallel processing.
- Open images with Pillow and release them (use `with` blocks / close()).
- Real-ESRGAN: always use a small tile size (-t 100 default, never 0/auto),
  and use the 2x model first. Only use 4x if memory allows.
- Never load the whole upload into a list or cache in memory.
- If upscaling fails or runs out of memory, fall back to Lanczos and tell me.

## Tech stack (do not change without asking me)
- Python 3.11+
- Flask (backend)
- Pillow (crop + resize)
- Plain HTML + CSS + vanilla JavaScript (one page, no React, no build step)
- Phase 2 only: Real-ESRGAN ncnn-vulkan executable, called with subprocess

## Core flow
1. User opens the page. JavaScript detects the real screen resolution:
   width = screen.width * devicePixelRatio, height = screen.height * devicePixelRatio
   (rounded to integers). Show it on the page and let the user edit it manually
   (for multi-monitor or wrong detection).
2. User uploads an image (drag and drop or file picker), with a preview.
3. Frontend sends image + target width + target height to the Flask endpoint.
4. Backend:
   a. Open image, fix rotation using EXIF (ImageOps.exif_transpose), convert to RGB.
   b. Crop to the target aspect ratio (center crop first).
   c. Resize to the exact target size.
      - If shrinking: Image.LANCZOS.
      - If enlarging: Phase 1 uses LANCZOS too, and the response includes a
        warning that the source is smaller than the screen.
        Phase 2 replaces this with AI upscaling.
   d. Save as PNG (lossless).
5. Frontend shows before/after preview and a Download button.

## Decisions (agreed before Phase 1 build)
- Output size is capped at 50 megapixels too (same RAM rule as the source).
- No temp upload on disk: read the upload stream directly with Pillow.
- Phase 1 returns the PNG bytes in the POST response; JS shows it via a blob
  URL. No `outputs/` folder in Phase 1 (`uploads/` is also not needed).
- The detected resolution is labelled "best guess" in the UI (Windows scaling,
  browser zoom and multi-monitor can make it wrong).
- Enforce the 50 MP source limit from the image header BEFORE decoding, and set
  `Image.MAX_IMAGE_PIXELS` explicitly.
- Test images: portrait, landscape, ultrawide, tiny, EXIF-rotated, plus one
  real wallpaper supplied by me.
- Leave `.git` alone (I will fix the repo myself).
- CORRECTION: the default must NOT crop. The whole image is kept, undistorted,
  and the leftover space is filled with a blurred copy of the image. Modes:
  fit_blur (default), fit_black, stretch, fill (crop, optional). This replaces
  "crop first" in the Core flow step 4b. Logic lives in core/fitter.py.
- A portrait image cannot fill a landscape screen without cropping, bars,
  distortion or AI outpainting. Outpainting is NOT feasible on this laptop.
  The interactive crop frame idea was considered and dropped by me for now.
- On-site "Preview on my desktop": full-screen overlay with fake icons and a
  taskbar, plus a zoom-in to check sharpness. Pure frontend.
- Phase 2 AI upscaling uses Real-ESRGAN ncnn-vulkan v0.2.5.0 (20220424) from
  github.com/xinntao/Real-ESRGAN, unzipped into tools/realesrgan/ (git-ignored).
  The release has no official checksum; the SHA-256 we measured is recorded
  in tools/realesrgan/SHA256.txt.
  - Models: "anime" = realesr-animevideov3 (2x/3x/4x, picks the smallest
    enough), "photo" = realesrgan-x4plus (4x only).
  - Tile size 100. One upscale at a time (threading lock). AI output capped
    at 50 MP. Any failure falls back to Lanczos with a warning on the page.
  - Flow: AI upscale the source -> apply fit mode -> Lanczos down to exact size.

## Folder structure
```
wallpaper-resizer/
├── CLAUDE.md
├── app.py                 # Flask routes only, no image logic
├── core/
│   ├── __init__.py
│   ├── cropper.py         # crop_to_ratio(image, w, h)
│   ├── resizer.py         # resize_to(image, w, h)
│   ├── analyzer.py        # source size, ratio, quality warnings
│   └── upscaler.py        # Phase 2: Real-ESRGAN wrapper
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── script.js
├── tests/
│   └── test_core.py
├── uploads/               # temp, git-ignored
├── outputs/               # temp, git-ignored
├── requirements.txt
└── .gitignore
```
Keep image logic in `core/` and web logic in `app.py`, so the core can be
reused later if the project goes public.

## Rules for writing code
- Keep it simple and readable. I am building this to learn, so add short
  comments explaining WHY, not what.
- One small feature at a time. Do not build Phase 2 while doing Phase 1.
- Validate uploads: allow only jpg, jpeg, png, webp, bmp. Max 20 MB.
  Use werkzeug's secure_filename or random UUID filenames.
- Reject absurd target sizes (below 320 or above 7680 on either side).
- Reject source images above 50 megapixels (RAM protection, see Memory rules).
- Delete temp files after the response is sent.
- Never hardcode absolute paths. Use pathlib.
- Handle errors with clear messages shown on the page (not just a crash).
- Pin versions in requirements.txt.

## Commands
- Create venv: `python -m venv .venv`
- Activate (PowerShell): `.venv\Scripts\Activate.ps1`
- Install: `pip install -r requirements.txt`
- Run: `python app.py` (opens at http://127.0.0.1:5000)
- Test: `pytest`

## Phases
### Phase 1 (days 1-3): core site, no AI
- [x] Project setup, venv, requirements, .gitignore
- [x] core/cropper.py, core/resizer.py with tests
- [x] Flask upload endpoint
- [x] Frontend: resolution detection, manual override, upload, preview, download
- [x] Warning when source image is smaller than target

### Phase 2 (day 4): AI upscaling
- [x] core/upscaler.py calling realesrgan-ncnn-vulkan.exe via subprocess
- [x] Use small tile size (-t 100 or 200) so 7 GB RAM does not run out
- [x] Optional "Enhance quality" checkbox, only used when source is smaller than target
- [x] Upscale 2x or 4x, then Lanczos down to the exact target size
- [x] Show a "processing..." state, since it can take 10-60 seconds

### Phase 3 (only after Phase 1 and 2 work): accounts and history
ON HOLD (decided 2026-10-06): do not build until I ask. The plan and the 5 open
decisions (SQLAlchemy vs sqlite3, login optional, save output only, 50-item
limit, new deps) were proposed but not answered yet.
- [ ] SQLite database (built into Python) using SQLAlchemy or plain sqlite3
- [ ] Tables: users, wallpapers (original name, target size, created time, file path),
      presets (saved screen resolutions per user)
- [ ] Flask-Login for register / login / logout, passwords hashed with werkzeug
- [ ] "My history" page and saved presets dropdown
- [ ] Per-user storage folders, delete files when a user deletes a history item
- [ ] Do NOT store secrets in code. Use a .env file for SECRET_KEY (git-ignored).

### Later (do NOT build now)
Smart cropping (saliency/faces), rate limiting, job queue, public deployment.

## Definition of done for each task
- The app runs without errors
- I can test it in the browser
- Tests pass for any new core function
- Changes are summarized briefly so I can commit them
