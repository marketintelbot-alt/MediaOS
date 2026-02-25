# tradevera-reels-factory

Offline reel generator for TradeVera-style trading reels.

Given an idea (and optional images), it outputs:
- `reel.mp4` (1080x1920, 30fps, 20-35s)
- `thumbnail.png`
- `caption.txt`
- `hooks.txt`
- `script.json`
- `build_log.txt`

IMPORTANT: This project is designed to remain completely free; do not add paid APIs.

## What It Uses (Free Only)
- Python 3 (orchestration)
- FFmpeg (video rendering, audio processing, caption burn-in)
- Local TTS: Piper (preferred) or eSpeak NG fallback
- Captions: local Whisper if available, otherwise phrase-level fallback (no API keys)
- Pillow (programmatic TradeVera slide generation)

## Folder Structure
```text
tradevera-reels-factory/
  tv_reels.py
  requirements.txt
  README.md
  assets/
    brand/
      logo.png
      palette.json
      fonts/
    broll/
    music/
    sfx/
  inputs/
  outputs/
  templates/
    captions/
    slides/
    ffmpeg/
  modules/
    idea_to_script.py
    storyboard.py
    slides.py
    broll_select.py
    tts.py
    captions.py
    audio_mix.py
    render.py
    caption_writer.py
    utils.py
  tools/
    setup_check.py
    download_free_assets.py
    tag_broll.py
```

## Install (macOS)
1. Install Python 3.10+ (if needed).
2. Install FFmpeg:
   - `brew install ffmpeg`
3. Install eSpeak fallback (free):
   - `brew install espeak`
4. Install Piper (preferred, free local TTS):
   - Install Piper binary (free/open source) and place it on your `PATH`.
   - Download a free `.onnx` voice model and set `PIPER_MODEL=/absolute/path/to/voice.onnx`
5. Install Python deps:
   - `python3 -m pip install -r requirements.txt`
6. Optional better captions (heavy install):
   - `python3 -m pip install openai-whisper`
   - Pre-download a local Whisper model (e.g. `tiny`) before offline use.

## Install (Windows)
1. Install Python 3.10+ from python.org (check “Add Python to PATH”).
2. Install FFmpeg (free static build) and add `ffmpeg/bin` to `PATH`.
3. Install eSpeak NG (free) and add it to `PATH`.
4. Install Piper (preferred, free local TTS):
   - Install Piper binary and add it to `PATH`.
   - Download a free `.onnx` voice model and set environment variable `PIPER_MODEL` to the full path.
5. Install Python deps:
   - `py -m pip install -r requirements.txt`
6. Optional better captions (heavy):
   - `py -m pip install openai-whisper`

## Install (Linux)
1. Install Python 3.10+.
2. Install FFmpeg:
   - Debian/Ubuntu: `sudo apt update && sudo apt install -y ffmpeg`
3. Install eSpeak NG fallback:
   - Debian/Ubuntu: `sudo apt install -y espeak-ng`
4. Install Piper (preferred, free local TTS):
   - Install Piper binary (free/open source) and add to `PATH`.
   - Download a free `.onnx` voice model and set `PIPER_MODEL=/absolute/path/to/voice.onnx`
5. Install Python deps:
   - `python3 -m pip install -r requirements.txt`
6. Optional better captions (heavy):
   - `python3 -m pip install openai-whisper`

## Verify Setup
Run:
```bash
python3 tools/setup_check.py
```
The checker prints missing dependencies and exact next steps.

## Optional Free Asset Starter Pack (No Keys)
Downloads free/open licensed starter b-roll (Blender open movie trailers) and derives a local music bed + subtle SFX into `assets/music` and `assets/sfx`.

```bash
python3 tools/download_free_assets.py
python3 tools/tag_broll.py
```

Notes:
- Core reel generation does NOT require these assets.
- If `assets/broll`, `assets/music`, and `assets/sfx` are empty, the tool still renders a reel using generated TradeVera slides + voice + captions.

## Run A Demo Reel Immediately After Setup
From the project root:

```bash
python3 tv_reels.py --idea "Why most traders fail risk management" --no_broll
```

Or with images:

```bash
python3 tv_reels.py --idea "Stop loss mistake" --images ./inputs/*.png --length 28
```

## Local Click UI (Least Work, Offline)
Run the local desktop GUI (Tkinter) to generate reels by clicking:

```bash
python3 tv_reels_gui.py
```

Notes:
- This is the easiest clickable option and keeps the project offline/free.
- A Render static site alone cannot run the FFmpeg/Python/TTS reel pipeline.

## Hosted Web UI (Render)
If you want to run it on the internet, deploy it as a **Render Web Service** (not Static Site). A Static Site cannot execute the Python + FFmpeg + TTS backend.

This repo now includes:
- `web_app.py` (browser UI + hosted backend wrapper)
- `Dockerfile` (installs `ffmpeg` + `espeak-ng`)
- `render.yaml` (Render Blueprint config, inside `tradevera-reels-factory/`)

### Quick Render Setup (Web Service, Docker)
Use **New Web Service** in Render (not New Static Site), then set:

- Repository: your repo
- Branch: `main`
- Root Directory: `tradevera-reels-factory`
- Runtime: `Docker`
- Build Command: leave blank (Dockerfile is used)
- Start Command: leave blank (Dockerfile CMD is used)

Optional env vars:
- `TV_WEB_SECRET` = any random string (recommended)
- `PIPER_MODEL` = path inside the container only if you later customize Piper (default hosted fallback is eSpeak)
- `TV_OUTPUT_RETENTION_COUNT` = number of recent jobs to keep on disk (default `25`)
- `TV_OUTPUT_RETENTION_HOURS` = maximum job age in hours before cleanup (default `168`)

After deploy, open the site URL and use the browser form to generate reels.

Operational safety notes:
- The hosted UI enforces a single-build queue, upload size limits, and a short IP cooldown between builds.
- Successful builds clean temporary intermediates (`_work`) by default to reduce disk usage.
- `/healthz` checks runtime dependencies (`ffmpeg`, `ffprobe`, local TTS engine) and write access.

## CLI Reference
- `--idea "text"` (required)
- `--images path(s)` optional, 0-12 images
- `--style tradevera_premium` optional (default)
- `--no_broll` optional
- `--length <seconds>` optional (20-35; default random 22-30)

## Idea Examples (Built-In Friendly Topics)
- Why most traders fail risk management
- Stop loss mistake that ruins good setups
- How to size positions without emotion
- Win rate vs expectancy: what actually matters
- Why overtrading kills your edge
- Revenge trading after a red day
- FOMO entries vs planned execution
- How to build a pre-market checklist
- Journal mistakes that keep repeating
- How to define invalidation before entry
- R multiple thinking for consistent traders
- Drawdown rules every trader needs
- When to skip a trade even if it looks good
- Setup quality vs market noise
- How pros handle losing streaks
- The position sizing formula traders ignore
- Breakout entry mistakes most traders make
- Why late entries destroy risk-reward
- Partial profits without sabotaging the trade
- News volatility and execution discipline
- Session timing: stop trading the dead hours
- A simple post-trade review framework

## Behavior Notes
- Default palette is stored in `assets/brand/palette.json` and always read from disk.
- If `assets/brand/logo.png` is missing, a branded placeholder TRADEVERA wordmark PNG is generated automatically.
- If custom fonts are added to `assets/brand/fonts/`, the first available font is used automatically.
- Captions are always burned into the final MP4 via FFmpeg (ASS subtitles).
- The renderer performs a self-check (resolution, duration, audio stream, clipping risk, caption burn flag) and auto re-renders once if checks fail.

## Free-Only Rule (Repeat)
This project is designed to remain completely free; do not add paid APIs, paid SaaS dependencies, or billing-enabled services.
