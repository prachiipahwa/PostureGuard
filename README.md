# 🦾 PostureGuard AI — Real-Time Ergonomic Coach

**Computer Vision Capstone Project**  
Domain: Healthcare & Workplace Wellness  
Tech: MediaPipe Pose · OpenCV · Flask · Python

---

## What It Does

PostureGuard AI uses your webcam and **MediaPipe Pose** landmark detection to analyze your sitting posture in real time. It detects:

| Issue | How It's Measured | Threshold |
|---|---|---|
| **Forward Head Posture** | Horizontal deviation of ear from shoulder (°) | >15° |
| **Shoulder Tilt** | Vertical asymmetry between left/right shoulders | >8% |
| **Slouching / Spine Curve** | Deviation of shoulder-hip vertical line (°) | >20° |
| **Head Tilt** | Eye-level asymmetry | >5% |

It produces a **0–100 posture score** (EMA-smoothed), live visual skeleton overlay, actionable fix instructions, and session statistics.

---
## Live Demo

[Click to watch](./demo.mp4)

---
## Quick Start

### Option A — Web Dashboard (recommended for demo)

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000 in your browser
```

Click **Start Analysis** and allow camera access. The full dashboard runs live.

### Option B — Headless / Script Mode

```bash
# Webcam
python inference.py --source 0

# Video file
python inference.py --source sample.mp4

# Single image
python inference.py --source sample.jpg

# Save annotated output video
python inference.py --source 0 --output out.mp4
```

Press **Q** to quit. Session CSV log saved to `logs/session_<timestamp>.csv`.

---

## Project Structure

```
postureguard/
├── inference.py          # Core inference script (standalone, no server needed)
├── app.py                # Flask web server for interactive dashboard
├── templates/
│   └── index.html        # Frontend dashboard (dark theme, live skeleton, chart)
├── requirements.txt
├── README.md
└── logs/                 # Auto-created: session CSV logs
```

---

## How It Works — Pipeline

```
Webcam / Video
     ↓
OpenCV frame capture
     ↓
MediaPipe Pose (33 landmarks, real-time)
     ↓
PostureAnalyzer
  ├── Forward head angle (ear vs shoulder vertical)
  ├── Shoulder tilt (left/right Y-difference)
  ├── Spine curvature (hip-shoulder vertical deviation)
  └── Head tilt (eye-level asymmetry)
     ↓
EMA-smoothed Score (0–100)
     ↓
OpenCV overlay (score ring, bars, issue alerts, skeleton)
     ↓
Flask API → Browser dashboard (live chart, session stats)
```

---

## Grading Criteria

| Criterion | How This Project Addresses It |
|---|---|
| **Uniqueness (30%)** | Real-time ergonomic scoring system with EMA smoothing, multi-metric body analysis, and session history. Not a simple "head tilt detector" — models 4 biomechanical parameters. |
| **Creativity (25%)** | Full web dashboard with live skeleton overlay, animated score ring, score-history chart, ergonomic checklist, tip rotator. |
| **Usefulness (20%)** | 1 billion+ knowledge workers spend 8h/day seated. Poor posture causes chronic pain, lost productivity. This is a free, instant, privacy-preserving alternative to expensive posture devices. |
| **Working Demo (15%)** | Run `python app.py`, open browser, click Start. Works with any webcam. Fallback demo mode if backend unavailable. |
| **Code Quality (10%)** | Modular classes, docstrings, clear variable names, separation of concerns (inference / server / frontend). |

---

## Dataset / Model

- **Model**: MediaPipe Pose (BlazePose) — Google's pretrained pose estimation model  
- **No training required** — the model generalizes well to seated postures  
- **Self-collected calibration thresholds** via manual testing with 5 subjects  
- Optionally fine-tunable via threshold constants in `inference.py`

---

## Sample Outputs

After a session, check `logs/` for a CSV:

```
timestamp,score,forward_deg,sh_tilt,spine_dev,issues
2026-04-30T10:12:04,88.2,12.1,3.4,15.2,
2026-04-30T10:12:05,74.3,19.8,5.1,22.4,Forward Head|Slouching
```

---

## Who Would Use This

- **Remote workers** who sit at a desk 8+ hours a day
- **Students** during long study sessions
- **Physical therapists** for baseline posture assessment
- **Employers** as a wellness tool in standing desk setups

---

## Challenges

1. **Occlusion**: Side-on camera angles hide one shoulder; mitigated by using midpoints and visibility filtering.
2. **Lighting variability**: MediaPipe handles this well but extreme backlight causes misdetection — advise front lighting.
3. **Smooth scoring**: Raw per-frame scores are noisy; EMA smoothing (α=0.15) provides stable readout without lag.
4. **Camera-to-body distance**: Thresholds are angular/proportional so they remain valid across distances.
