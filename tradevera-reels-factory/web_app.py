#!/usr/bin/env python3
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, Response, flash, redirect, render_template, request, send_file, send_from_directory, url_for
from werkzeug.utils import secure_filename

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
UPLOADS_DIR = PROJECT_ROOT / "inputs" / "web_uploads"
TV_REELS = PROJECT_ROOT / "tv_reels.py"

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
RESULT_FILES = ["reel.mp4", "thumbnail.png", "caption.txt", "hooks.txt", "script.json", "build_log.txt"]

app = Flask(__name__, template_folder=str(PROJECT_ROOT / "web" / "templates"), static_folder=str(PROJECT_ROOT / "web" / "static"))
app.secret_key = os.environ.get("TV_WEB_SECRET", "tradevera-local-secret")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64MB total upload payload

_BUILD_LOCK = threading.Lock()


@dataclass
class BuildResult:
    ok: bool
    output_dir: Path | None
    stdout: str
    stderr: str
    error: str | None


def _parse_success_output(stdout: str, stderr: str) -> Path | None:
    combined = (stdout or "") + "\n" + (stderr or "")
    m = re.search(r"SUCCESS:\s+(.+)$", combined, re.MULTILINE)
    if not m:
        return None
    p = Path(m.group(1).strip())
    return p if p.exists() else p


def _save_uploaded_images(files: list[Any]) -> list[Path]:
    if not files:
        return []
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    upload_batch = Path(tempfile.mkdtemp(prefix="job_", dir=str(UPLOADS_DIR)))
    saved: list[Path] = []
    for f in files[:12]:
        if not getattr(f, "filename", ""):
            continue
        name = secure_filename(f.filename)
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTS:
            continue
        out = upload_batch / name
        f.save(out)
        if out.exists() and out.stat().st_size > 0:
            saved.append(out)
    return saved


def _run_generator(idea: str, length: str | None, style: str | None, no_broll: bool, image_paths: list[Path]) -> BuildResult:
    cmd = [sys.executable, str(TV_REELS), "--idea", idea.strip()]
    if style and style.strip():
        cmd += ["--style", style.strip()]
    if length and length.strip():
        cmd += ["--length", length.strip()]
    if no_broll:
        cmd.append("--no_broll")
    if image_paths:
        cmd.append("--images")
        cmd.extend(str(p) for p in image_paths)

    env = os.environ.copy()
    # Ensure ffmpeg-full is preferred on macOS dev environments; harmless elsewhere.
    extra_bin = "/opt/homebrew/opt/ffmpeg-full/bin"
    if Path(extra_bin).exists():
        env["PATH"] = extra_bin + os.pathsep + env.get("PATH", "")

    try:
        cp = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            text=True,
            capture_output=True,
            env=env,
            timeout=60 * 20,
        )
    except subprocess.TimeoutExpired as exc:
        return BuildResult(False, None, exc.stdout or "", exc.stderr or "", "Build timed out")
    except Exception as exc:
        return BuildResult(False, None, "", "", str(exc))

    out_dir = _parse_success_output(cp.stdout, cp.stderr)
    if cp.returncode == 0 and out_dir:
        return BuildResult(True, out_dir, cp.stdout, cp.stderr, None)

    err_text = None
    combined = (cp.stderr or "") + "\n" + (cp.stdout or "")
    m = re.search(r"ERROR:\s+(.+)$", combined, re.MULTILINE)
    if m:
        err_text = m.group(1).strip()
    return BuildResult(False, out_dir, cp.stdout, cp.stderr, err_text or f"Generator exited with code {cp.returncode}")


def _safe_output_dir(job_id: str) -> Path | None:
    if not re.fullmatch(r"\d{8}_\d{6}", job_id or ""):
        return None
    p = (OUTPUTS_DIR / job_id).resolve()
    try:
        p.relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        return None
    return p if p.exists() and p.is_dir() else None


def _list_recent_outputs(limit: int = 12) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not OUTPUTS_DIR.exists():
        return items
    for p in sorted([d for d in OUTPUTS_DIR.iterdir() if d.is_dir()], reverse=True)[:limit]:
        files = {f.name for f in p.iterdir() if f.is_file()}
        items.append(
            {
                "id": p.name,
                "has_reel": "reel.mp4" in files,
                "has_thumbnail": "thumbnail.png" in files,
                "files": sorted(files),
            }
        )
    return items


def _zip_output_dir(job_dir: Path) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in RESULT_FILES:
            fp = job_dir / name
            if fp.exists() and fp.is_file():
                zf.write(fp, arcname=name)
    bio.seek(0)
    return bio.read()


@app.get("/healthz")
def healthz() -> tuple[str, int]:
    return "ok", 200


@app.get("/")
def index() -> str:
    return render_template("index.html", recent=_list_recent_outputs(), busy=_BUILD_LOCK.locked())


@app.post("/generate")
def generate() -> Response:
    idea = (request.form.get("idea") or "").strip()
    style = (request.form.get("style") or "tradevera_premium").strip()
    length = (request.form.get("length") or "").strip()
    no_broll = request.form.get("no_broll") in {"on", "true", "1"}

    if not idea:
        flash("Idea is required.", "error")
        return redirect(url_for("index"))

    if length and (not length.isdigit() or not (20 <= int(length) <= 35)):
        flash("Length must be blank or a number between 20 and 35.", "error")
        return redirect(url_for("index"))

    images = _save_uploaded_images(request.files.getlist("images"))

    acquired = _BUILD_LOCK.acquire(blocking=False)
    if not acquired:
        flash("A build is already running. Try again in a minute.", "error")
        return redirect(url_for("index"))

    try:
        result = _run_generator(idea, length, style, no_broll, images)
    finally:
        _BUILD_LOCK.release()
        # cleanup uploaded files for this request
        if images:
            batch_dir = images[0].parent
            shutil.rmtree(batch_dir, ignore_errors=True)

    if result.ok and result.output_dir:
        job_id = result.output_dir.name
        return redirect(url_for("job_detail", job_id=job_id), code=303)

    flash(result.error or "Build failed.", "error")
    debug_log = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    return render_template(
        "index.html",
        recent=_list_recent_outputs(),
        busy=_BUILD_LOCK.locked(),
        last_error=debug_log[-12000:] if debug_log else None,
        form_data={
            "idea": idea,
            "style": style,
            "length": length,
            "no_broll": no_broll,
        },
    )


@app.get("/jobs/<job_id>")
def job_detail(job_id: str) -> str:
    job_dir = _safe_output_dir(job_id)
    if not job_dir:
        flash("Output not found.", "error")
        return redirect(url_for("index"))
    files = [name for name in RESULT_FILES if (job_dir / name).exists()]
    build_log = None
    bl = job_dir / "build_log.txt"
    if bl.exists():
        try:
            build_log = bl.read_text(encoding="utf-8")
        except Exception:
            build_log = None
    return render_template(
        "index.html",
        recent=_list_recent_outputs(),
        busy=_BUILD_LOCK.locked(),
        current_job={"id": job_id, "files": files},
        build_log=build_log,
    )


@app.get("/outputs/<job_id>/<path:filename>")
def output_file(job_id: str, filename: str) -> Response:
    job_dir = _safe_output_dir(job_id)
    if not job_dir:
        return Response("Not found", status=404)
    if filename not in RESULT_FILES:
        return Response("Not found", status=404)
    fp = job_dir / filename
    if not fp.exists():
        return Response("Not found", status=404)
    force_download = request.args.get("download") in {"1", "true"}
    return send_from_directory(job_dir, filename, as_attachment=force_download)


@app.get("/outputs/<job_id>/bundle.zip")
def output_bundle(job_id: str) -> Response:
    job_dir = _safe_output_dir(job_id)
    if not job_dir:
        return Response("Not found", status=404)
    data = _zip_output_dir(job_dir)
    return send_file(
        io.BytesIO(data),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"tradevera_reel_{job_id}.zip",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
