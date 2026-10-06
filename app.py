import json
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from core.analyzer import ALLOWED_EXTENSIONS, ImageRejected
from core.pipeline import process_image

BASE_DIR = Path(__file__).parent
MAX_UPLOAD_MB = 20

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"),
            static_folder=str(BASE_DIR / "static"))
# Flask rejects bigger bodies with a 413 before our code runs.
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


@app.errorhandler(413)
def too_large(_):
    return jsonify(error=f"File is larger than {MAX_UPLOAD_MB} MB."), 413


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/process")
def process():
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

    resp = Response(png_bytes, mimetype="image/png")
    # Warnings travel in a header so the body can stay the raw PNG for the blob URL.
    resp.headers["X-Wallpaper-Info"] = json.dumps(info)
    resp.headers["Access-Control-Expose-Headers"] = "X-Wallpaper-Info"
    return resp


if __name__ == "__main__":
    # debug=False: the Werkzeug debugger allows code execution; keep it off.
    app.run(host="127.0.0.1", port=5000, debug=False)
