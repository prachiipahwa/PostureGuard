# 🦾 PostureGuard AI

<<<<<<< HEAD
> **Real-time posture analysis and ergonomic coaching powered by computer vision**

PostureGuard AI uses your webcam and Google's **MediaPipe Pose** model to analyze your sitting (or standing) posture in real time. It detects biomechanical issues, scores your posture 0–100, gives live AI coaching tips, tracks your progress over weeks, and lets you compete with friends — all running locally with no cloud dependency except the optional Anthropic AI features.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Feature Breakdown](#feature-breakdown)
- [How Everything Works](#how-everything-works)
- [Testing Each Feature](#testing-each-feature)
- [Setup & Installation](#setup--installation)
- [API Key Setup](#api-key-setup)
- [Project Structure](#project-structure)
- [The Profile System — Design Decisions](#the-profile-system--design-decisions)
- [Frequently Asked Questions](#frequently-asked-questions)
- [Roadmap](#roadmap)
=======
**Computer Vision Capstone Project**  
Domain: Healthcare & Workplace Wellness  
Tech: MediaPipe Pose · OpenCV · Flask · Python
>>>>>>> 7b9dbed3ce11faa9409e73cae84bb4a13bd0761a

---

## What It Does

PostureGuard tracks **4 biomechanical posture metrics** in real time from your webcam:

| Metric | What's measured | Alert threshold |
|---|---|---|
| **Forward Head** | Horizontal deviation of ear from shoulder (degrees) | > 15° |
| **Shoulder Tilt** | Left/right shoulder height asymmetry | > 8% of frame height |
| **Spine Curve** | Deviation of shoulder-hip vertical line (degrees) | > 20° |
| **Head Tilt** | Eye-level asymmetry (left/right) | > 5% |

These are combined into a **smooth 0–100 posture score** (EMA-filtered so it doesn't flicker) with color coding: green (≥85), amber (65–84), red (<65).

---
## Live Demo

<<<<<<< HEAD
## Feature Breakdown
=======
[Click to watch](./demo.mp4)

---
## Quick Start
>>>>>>> 7b9dbed3ce11faa9409e73cae84bb4a13bd0761a

### 1. Live Posture Analysis
**What it does:** Real-time skeleton overlay on your webcam feed. Score ring, metric bars, and issue cards update at ~10fps. Works with any standard webcam.

**How it works technically:**
- OpenCV captures a frame every 100ms
- Frame is sent as a base64 JPEG to `/api/analyze` via `fetch()`
- Flask decodes the frame, runs MediaPipe Pose (33 landmarks), computes the 4 metrics
- EMA smoothing (`α = 0.15`) stabilizes the score: `smooth = 0.85 × prev + 0.15 × raw`
- JSON result returned with score, issues, keypoints, connections
- Frontend draws skeleton on a `<canvas>` overlay, updates the score ring SVG

---

### 2. Personal Calibration Wizard
**What it does:** Adapts the alert thresholds to *your* body. A 6ft person and a 5ft person have different geometry — without calibration, short people get false forward-head alerts constantly.

**How it works:**
- You hold 3 poses: *perfect posture*, *natural forward lean*, *natural slouch*
- The app captures 15 frames per pose and computes median values for each metric
- Thresholds are set at **40% of the way between your ideal and your worst pose**
- Saved to `data/calibration_{user_id}.json`

**Result:** If your natural perfect posture reads as 12° forward (due to camera angle or build), your alert fires at ~16° instead of the generic 15° — massively fewer false positives.

---

### 3. Smart Break Reminders
**What it does:** Fires a browser notification when you've been in bad posture *continuously* for 45 seconds, OR when 30 minutes have passed since your last break reminder. Not a dumb timer — it only fires for *sustained* bad posture.

**How it works:**
- `alerts.py` maintains `AlertState` — tracks start time of bad-posture streaks
- Every frame result is passed to `alert_state.update(score)`
- If score < 65 for 45+ seconds → fires "bad posture" alert
- Every 30 minutes → fires "break reminder" regardless of score
- 2-minute cooldown between any two alerts (no spam)
- Frontend polls `/api/alerts/poll` every 5 seconds to receive pending alerts
- Alert shown as toast notification (bottom-right) + spoken via voice coach if enabled

---

### 4. Standing Desk Mode
**What it does:** Switches all 4 posture thresholds to values calibrated for *standing* body geometry. Standing naturally involves more lordosis (lower back curve) and different neck angles.

**Standing vs seated thresholds:**

| Metric | Seated | Standing |
|---|---|---|
| Forward Head | 15° | 12° (screen further away when standing) |
| Shoulder Tilt | 8% | 10% (natural sway) |
| Spine Curve | 20° | 25° (natural lordosis) |
| Head Tilt | 5° | 6° |

**How to test:** Toggle "🧍 Standing" in the topbar. Your score and issue alerts will immediately reflect the different thresholds.

---

### 5. Voice Coaching
**What it does:** Text-to-speech reads out posture tips when issues are detected — hands-free feedback so you don't need to look at the screen.

**How it works:**
- Uses the browser's built-in `window.speechSynthesis` API — zero dependencies
- Only fires every 18 seconds maximum (no repeated nagging)
- Reads the top issue's name + fix text: e.g. *"Forward Head detected. Pull chin back — align ears over shoulders."*
- Toggle with the "Voice" chip in the topbar

**No API key needed** — this is 100% built into the browser.

---

### 6. Score Trend Graph (8 Weeks)
**What it does:** A canvas chart showing your average posture score by week over the past 8 weeks. See if you're actually improving.

**How it works:**
- `ProfileManager.get_weekly_scores(user_id, weeks=8)` groups your saved sessions by ISO week
- Returns `[{week, label, avg_score, sessions_count}, ...]`
- Frontend draws a gradient line chart with dots and week labels on the Trends panel
- Bar overlays show session frequency per week

**How to see real data:** Complete a few sessions using "End Session" button (this saves to your profile). Then click Trends panel.

---

### 7. Streaks & Milestones
**What it does:** Tracks consecutive days where you completed a session with average score ≥ 75. 10 milestone badges unlock as you hit targets.

**Milestones:**

| Badge | Condition |
|---|---|
| ⭐ First step | Complete first session |
| 🔥 Week warrior | 7 sessions total |
| 🏆 Monthly habit | 30 sessions total |
| ⚡ On a roll | 3-day streak |
| 🔥 Week streak | 7-day streak |
| 👑 Posture champion | 30-day streak |
| ✅ Good form | Single session avg score ≥ 85 |
| 💎 Perfect posture | Single session avg score ≥ 95 |
| ⏰ Deep focus | Session longer than 60 minutes |
| 🏅 Dedicated | 10 total hours tracked |

**Streak rules:** You must score ≥75 average AND click "End Session" to save the session. Sessions that aren't ended don't count.

---

### 8. AI 7-Day Improvement Plan
**What it does:** Calls the **Groq API** (free, no billing) with your session history, top posture issues, and stats to generate a personalised 7-day programme. Each day has a theme, morning habit, exercise, desk tip, and evening action.

**How it works:**
1. Frontend calls `/api/plan/{user_id}/generate`
2. Flask fetches your profile data and builds a detailed prompt
3. Backend calls Anthropic API **server-side** (your API key is never sent to the browser)
4. Response parsed as JSON, saved to `data/plan_{user_id}.json`
5. If no API key is set → falls back to a smart rule-based 7-day plan

**Requires API key** — see [API Key Setup](#api-key-setup).

---

### 9. AI Live Coach Tips
**What it does:** Every 20 seconds when posture issues are active, a 2-sentence tip appears in the "AI Coach" box, specific to your current issue and severity.

**How it works:**
- Frontend sends prompt to `/api/ai_coach` (Flask route)
- Flask adds the API key server-side and calls Anthropic
- Response streamed back as `{tip: "..."}` JSON
- If no API key → falls back to 5 built-in tips locally

**Key security note:** The API key is *never* sent to the browser. It lives in `.env`, loaded by `config.py`, and only used server-side.

---

### 10. Friend Challenges
**What it does:** Create a 6-character room code and share it with a friend. Both compete on average posture score over 24 hours. Live leaderboard updates every 5 seconds.

**How it works:**
- `create_challenge()` in `ai_features.py` generates a UUID-based 6-char room code
- Stored as `data/challenge_{ROOM_ID}.json`
- Every analysis frame optionally submits score to the active challenge via `challenge_id` in the request body
- `/api/challenges/{room_id}` returns current leaderboard sorted by avg score
- Challenge expires after 24 hours

**How to test locally:** Open two browser tabs. Create a challenge in tab 1, join with the code in tab 2. Start camera in both. Leaderboard will update as both sessions run.

---

### 11. PDF Weekly Report
**What it does:** Generates and downloads a formatted A4 PDF with your week's stats — score trend chart (drawn with ReportLab), top issues table, session log, streak info.

**How it works:**
- Button calls `/api/report/{user_id}` which opens in a new tab
- Flask calls `generate_weekly_report()` from `weekly_report.py`
- ReportLab draws the chart as vector paths (no image dependencies)
- PDF saved to `reports/` directory and served for download

**No API key needed** — ReportLab is a pure Python library.

---

### 12. OBS Stream Widget
**What it does:** A transparent browser overlay showing your live posture score ring, status label, and alert bar. Streamers can add this as a Browser Source in OBS.

**URL:** `http://localhost:5000/obs`

**OBS Setup:**
1. Add > Browser Source
2. URL: `http://localhost:5000/obs`
3. Width: 220, Height: 100
4. Check "Shutdown source when not visible"
5. Check "Refresh browser when scene becomes active"
6. Custom CSS: `body { background-color: rgba(0,0,0,0); }`

**How it syncs:** Polls `/api/session` every 2 seconds and `/api/alerts/poll` every 5 seconds. Also receives score updates via `localStorage` if main app is open in same browser.

---

### 13. Login / Signup System
**What it does:** Account creation and login so multiple real users can use the app on the same machine with completely separate data — separate posture history, calibration, plans, streaks, everything.

**How it works:**
- Credentials stored in `data/auth.json` (SHA-256 password hashing with per-user salts)
- Flask `session` cookie keeps you logged in across page refreshes
- Each account auto-creates a matching PostureGuard profile on signup
- Guest mode available ("Continue as guest") — uses `default` profile

**This is different from the "Profiles" panel**, which was the original placeholder system. Login/signup creates full separate accounts. The Profiles panel is now used to view your account details and calibration status.

---

### 14. Multiple User Profiles
**Why they exist — original intent explained:**

The profiles system was built to solve the problem of *shared computers*. In a household or office where multiple people share one machine, each person should have their own posture data, calibration thresholds, streak, and plan. Without profiles, everyone's data mixes together.

**With the login system added**, profiles are now fully tied to accounts:
- Sign up → account created → profile auto-created with same ID
- All posture data, calibration, plan, streaks stored under `profile_{user_id}.json`
- Switch users by logging out and logging in as someone else
- Profiles panel shows your current profile's stats, calibration status, and quick links

---

## Testing Each Feature

Here's exactly how to verify every feature is working:

### Quick-start test
```bash
python app.py
# Open http://localhost:5000
```

### Feature-by-feature verification

| Feature | How to test |
|---|---|
| **Login/Signup** | Open app → signup screen appears → create account → verify name shows in sidebar |
| **Live Analysis** | Click Start → allow camera → see skeleton overlay and score ring updating |
| **Calibration** | Go to Calibration panel → click Start → hold each pose for 3 seconds → thresholds update |
| **Standing Mode** | Toggle "Standing" in topbar → check Calibration panel shows different threshold values |
| **Voice coaching** | Enable voice toggle in topbar → let bad posture be detected → hear spoken tip |
| **Break reminders** | Edit `alerts.py`: change `SUSTAINED_BAD_SECS = 45` to `5` → slouch for 5s → see toast |
| **Score trends** | End 2–3 sessions → go to Trends panel → see weekly chart with data points |
| **Streaks** | End a session with avg score ≥ 75 → go to Streaks panel → see streak = 1 |
| **Milestones** | End first session → "First step" milestone auto-unlocks → see modal popup |
| **7-Day Plan** | Set API key → go to Plan panel → click Generate → see 7 day cards appear |
| **AI Coach tips** | Set API key + start camera + have bad posture → watch AI coach text update every 20s |
| **Friend challenge** | Open 2 browser tabs → create challenge in tab 1 → join in tab 2 → start cameras |
| **PDF Report** | End a session → click "Download PDF" in Live panel → PDF opens in new tab |
| **OBS Widget** | Start camera → open `http://localhost:5000/obs` → see score ring updating |
| **Guest mode** | Click "Continue as guest" on login screen → uses default profile |

---

## Setup & Installation

### Requirements
- Python 3.10+
- Webcam
- ~500MB disk (MediaPipe model weights download on first run)

### Install

```bash
# Clone or unzip the project
cd postureguard

# Install dependencies
pip install -r requirements.txt

# Copy env file and fill in your API key
cp .env.example .env
# Edit .env — add your GROQ_API_KEY (free at console.groq.com)

# Run
python app.py
```

Open `http://localhost:5000` in your browser. Allow camera access when prompted.

### CLI inference (no browser needed)

```bash
# Webcam
python inference.py --source 0

# Video file
python inference.py --source myvideo.mp4

# Single image
python inference.py --source photo.jpg

# Save annotated output
python inference.py --source 0 --output out.mp4
```

Press `Q` to quit. Session CSV saved to `logs/session_TIMESTAMP.csv`.

---

## API Key Setup

The API key is needed for **2 features only**: AI 7-day plan generation and live AI coach tips. Everything else works without it.

### How to get a key
1. Go to [console.groq.com](https://console.groq.com/)
2. Create a free account — **no credit card, no billing setup**
3. Click **API Keys** → **Create API Key**
4. Copy the key (starts with `gsk_...`)

### How to add it
```bash
# In the project folder:
cp .env.example .env
```

Open `.env` and replace the placeholder:
```
GROQ_API_KEY=gsk_YOUR_ACTUAL_KEY_HERE
```

Restart the server. The key is loaded by `config.py` at startup.

### Choosing a model

You can override the model in `.env`:

```
# Fast and capable (default)
GROQ_MODEL=llama-3.3-70b-versatile

# Fastest response time
GROQ_MODEL=llama-3.1-8b-instant

# Longer context window
GROQ_MODEL=mixtral-8x7b-32768
```

All of the above are free on Groq.

### Security
- The key lives only in `.env` on your machine — never committed to git (`.gitignore` excludes it)
- The key is **never sent to the browser** — all AI calls go through Flask routes (`/api/ai_coach`, `/api/plan/*/generate`)
- Groq keys start with `gsk_` — `config.py` checks for this prefix to validate the key
- If no key is configured, the app falls back to local built-in tips and a rule-based 7-day plan — no errors

---

## Project Structure

```
postureguard/
│
├── app.py                  # Flask server — all API routes wired here
├── inference.py            # Standalone CLI inference script
│
├── config.py               # Loads .env, exposes GROQ_API_KEY, GROQ_MODEL etc.
├── auth.py                 # Login/signup — password hashing, sessions
├── calibration.py          # Personal calibration wizard logic
├── alerts.py               # Smart break reminders + standing desk thresholds
├── profiles.py             # User profiles, streaks, milestones, session history
├── ai_features.py          # 7-day plan (AI + fallback), friend challenges
├── weekly_report.py        # PDF weekly report generator (ReportLab)
│
├── templates/
│   ├── index.html          # Full frontend dashboard (7 panels, all features)
│   └── obs_widget.html     # Transparent OBS browser source overlay
│
├── static/                 # CSS/JS assets (currently inline for simplicity)
├── data/                   # Auto-created: profiles, calibration, challenges, auth
├── logs/                   # Auto-created: per-session CSV logs
├── reports/                # Auto-created: generated PDF reports
│
├── .env.example            # Template for environment variables
├── .env                    # YOUR config (never commit this — in .gitignore)
└── requirements.txt        # Python dependencies
```

---

## The Profile System — Design Decisions

### What we built vs what you might expect

There are **two layers** in PostureGuard:

**Layer 1 — Auth (login/signup):** Real accounts with username + password. This is what you see on first open. Each account = one person. Data is completely isolated. This is the "product" layer.

**Layer 2 — Profiles:** The underlying data store (`data/profile_{id}.json`) that holds posture history, streaks, calibration, and plan. When you sign up, a profile is auto-created with the same ID as your username.

### Why not a proper database?

For a local/capstone project, JSON files are actually the right call:
- Zero setup — no Postgres, no migrations, no ORM
- Fully portable — zip the project and move it anywhere
- Human-readable — you can open `data/profile_alice.json` and read your own data
- For a production SaaS you'd swap `profiles.py` and `auth.py` to use SQLAlchemy + PostgreSQL — the rest of the app wouldn't need to change

### Why profiles exist separately from auth

Calibration, streaks, and session history are "posture profile" data — they make sense as a separate concept from "account credentials." This separation means:
- Future: one account could have multiple "environments" (home desk, office desk) with different calibrations
- The `inference.py` CLI script works without any auth — just uses profile directly by ID

---

## Frequently Asked Questions

**Q: The camera feed shows a skeleton but the score is always in simulation mode — why?**
The backend `/api/analyze` might not be reachable. Make sure `python app.py` is running and you're accessing `http://localhost:5000` (not opening the HTML file directly).

**Q: The AI coach box shows "No API key configured" — how do I fix it?**
See [API Key Setup](#api-key-setup). The 7-day plan and coach tips fall back gracefully without a key — they still work, just use pre-written tips.

**Q: Where is my data stored?**
Everything lives in the `data/` folder: `auth.json` (credentials), `profile_*.json` (posture history), `calibration_*.json`, `plan_*.json`, `challenge_*.json`. Sessions are also logged to `logs/`.

**Q: Does any data leave my computer?**
Only if you have an API key configured — in that case the posture issue summary (e.g. "Forward Head 18°, score 62") is sent to Anthropic to generate a coaching tip. No video, no images, no personal info is ever sent anywhere.

**Q: Can I use this on my phone?**
The Flask server runs on your local network. On mobile browser, go to `http://YOUR_COMPUTER_IP:5000`. Camera access works on mobile Chrome/Safari over LAN. MediaPipe inference still runs server-side.

**Q: Why 10fps and not 30fps?**
MediaPipe on CPU takes ~80-120ms per frame. At 10fps the pipeline has headroom and the score EMA smoothing makes it feel continuous anyway. If you have a GPU, set `model_complexity=2` and remove the `setTimeout` throttle in `loop()`.

**Q: How do I reset everything?**
Delete the `data/` folder. All profiles, calibrations, challenges, auth data, and plans will be wiped. Logs in `logs/` are separate.

---

## Roadmap

Features not yet built but planned:

- [ ] **Heatmap calendar** — GitHub contribution-style grid showing posture quality by hour of day
- [ ] **Guided stretch panel** — when score drops below 65, slide-out panel shows a 60-sec stretch routine with timers
- [ ] **Email weekly report** — automatically email the PDF summary every Monday
- [ ] **Multi-camera support** — use a side camera for lateral spine curvature detection
- [ ] **Custom exercise library** — attach your own corrective exercises to specific detected issues
- [ ] **REST API** — expose PostureGuard as an API so it can integrate with productivity tools (Notion, Slack bot alerts)

---

## Tech Stack

| Layer | Tech |
|---|---|
| Pose estimation | MediaPipe BlazePose (Google, pretrained) |
| Computer vision | OpenCV 4.10 |
| Backend | Python 3.11 + Flask 3.0 |
| AI features | Groq API — llama-3.3-70b-versatile (free, no billing) |
| PDF generation | ReportLab 4.0 |
| Frontend | Vanilla JS + HTML Canvas (no framework) |
| Auth | SHA-256 + Flask sessions |
| Data storage | JSON files (no database) |

---

## License

MIT License — free to use, modify, and distribute. Attribution appreciated.

---

*PostureGuard AI — Computer Vision Capstone Project, 2026*
