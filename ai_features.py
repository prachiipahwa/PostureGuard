"""
ai_features.py — AI 7-day Plan + Friend Challenges
====================================================
AI Plan: calls Claude API with session history to generate a
         personalised 7-day posture improvement programme.

Challenges: lightweight room-code system — two users join the same
            code, compete on avg score over a 24-hour window.
            Stored as JSON files, no database needed.
"""

import json, time, uuid, hashlib, requests
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_API_URL, has_api_key
from pathlib import Path
from datetime import datetime, timedelta, date

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── AI 7-day Plan ─────────────────────────────────────────────────────────────

def generate_7day_plan(profile: dict) -> dict:
    """
    Given a user profile dict, return a structured 7-day posture plan.
    Falls back to a rule-based plan if no API key is available.
    """
    sessions  = profile.get("sessions", [])
    name      = profile.get("name", "there")
    best      = profile.get("best_score", 0)
    total_min = int(profile.get("total_duration", 0) / 60)
    streak    = profile.get("streak", {}).get("current", 0)

    # Derive top issues from last 10 sessions
    from collections import Counter
    issue_counts = Counter()
    for s in sessions[-10:]:
        for iss in s.get("issues", []):
            issue_counts[iss] += 1
    top_issues = [k for k, _ in issue_counts.most_common(3)]
    issues_str = ", ".join(top_issues) if top_issues else "general posture"

    prompt = f"""You are an expert ergonomics and physiotherapy coach.

User profile:
- Name: {name}
- Sessions completed: {len(sessions)}
- Best session score: {best}/100
- Current streak: {streak} days
- Total tracked time: {total_min} minutes
- Most common posture issues: {issues_str}

Generate a personalised 7-day posture improvement plan. 
Respond ONLY with a JSON object. No markdown, no preamble.

Format:
{{
  "title": "short motivating plan title",
  "overview": "2 sentence personalised intro",
  "days": [
    {{
      "day": 1,
      "theme": "short theme name",
      "morning": "1 specific morning habit (1 sentence)",
      "exercise": "1 specific exercise with reps/duration",
      "desk_tip": "1 specific desk setup tip",
      "evening": "1 evening wind-down action"
    }}
  ]
}}"""

    try:
        if not has_api_key():
            return _fallback_plan(name, top_issues)

        # Groq uses OpenAI-compatible API — fast, free, no billing required
        resp = requests.post(
            GROQ_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}"
            },
            json={
                "model": GROQ_MODEL,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        text = resp.json()["choices"][0]["message"]["content"]
        text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        plan = json.loads(text)
        plan["generated_at"] = time.time()
        plan["source"] = "ai"
        return plan
    except Exception as e:
        return _fallback_plan(name, top_issues)


def _fallback_plan(name: str, top_issues: list) -> dict:
    """Rule-based plan when AI is unavailable."""
    base_days = [
        {"theme": "Awareness",      "morning": "Set a phone reminder every 30 min to check posture.",
         "exercise": "Chin tucks: 10 reps, 3 sets. Pull chin straight back, hold 5 sec.",
         "desk_tip": "Raise monitor so top of screen is at eye level.",
         "evening": "5 min neck stretches before bed."},
        {"theme": "Foundation",     "morning": "Sit at edge of chair and feel your sit bones before starting work.",
         "exercise": "Cat-cow stretch: 10 slow reps to warm up the spine.",
         "desk_tip": "Check that your feet are flat on the floor or a footrest.",
         "evening": "Roll a tennis ball under each foot for 60 seconds."},
        {"theme": "Neck strength",  "morning": "Before opening laptop, do 5 head nods and 5 slow neck rotations.",
         "exercise": "Wall angels: 10 reps with back flat against a wall.",
         "desk_tip": "Move keyboard closer so elbows stay at 90 degrees.",
         "evening": "Apply heat pack to neck for 10 minutes if any tension."},
        {"theme": "Core activation","morning": "Engage core lightly all morning — imagine pulling navel to spine.",
         "exercise": "Dead bug: 8 reps each side. Slow and controlled.",
         "desk_tip": "Try sitting without chair back for 10 min bursts to activate core.",
         "evening": "3-minute plank (broken into sets if needed)."},
        {"theme": "Shoulder reset", "morning": "Roll shoulders back and down 10x as your first waking action.",
         "exercise": "Band pull-aparts or doorway stretch: 3x15 reps.",
         "desk_tip": "Check armrests are level and not forcing shoulders up.",
         "evening": "Thread-the-needle stretch: 30 sec each side."},
        {"theme": "Movement",       "morning": "Take a 5-minute walk before sitting down to work.",
         "exercise": "Thoracic spine rotation: 10 reps each direction seated.",
         "desk_tip": "Set a 25-min Pomodoro timer — stand during every break.",
         "evening": "10-min gentle yoga or stretching session."},
        {"theme": "Consolidation",  "morning": "Review your PostureGuard scores from the week — celebrate progress.",
         "exercise": "Full body stretch circuit: neck, chest, spine, hips, 20 min.",
         "desk_tip": "Write down your 1 desk setup change that made the biggest difference.",
         "evening": "Plan next week's posture goals. Aim to beat this week's avg score."},
    ]
    return {
        "title":        f"7-day reset for {name}",
        "overview":     f"Based on your sessions, we'll focus on {', '.join(top_issues[:2]) or 'core habits'}. "
                        f"Each day builds on the last — small changes compound fast.",
        "days":         [{"day": i+1, **d} for i, d in enumerate(base_days)],
        "generated_at": time.time(),
        "source":       "fallback",
    }


def save_plan(user_id: str, plan: dict):
    (DATA_DIR / f"plan_{user_id}.json").write_text(json.dumps(plan, indent=2))


def load_plan(user_id: str) -> dict | None:
    p = DATA_DIR / f"plan_{user_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


# ── Friend Challenges ─────────────────────────────────────────────────────────

def create_challenge(host_user_id: str, host_name: str, duration_hours: int = 24) -> dict:
    """Create a new challenge room. Returns the room dict."""
    room_id   = str(uuid.uuid4())[:6].upper()
    challenge = {
        "room_id":        room_id,
        "host_id":        host_user_id,
        "created_at":     time.time(),
        "expires_at":     time.time() + duration_hours * 3600,
        "duration_hours": duration_hours,
        "participants":   {
            host_user_id: {
                "name":       host_name,
                "scores":     [],
                "avg_score":  0,
                "joined_at":  time.time(),
            }
        },
        "status": "waiting",  # waiting | active | finished
    }
    _save_challenge(room_id, challenge)
    return challenge


def join_challenge(room_id: str, user_id: str, user_name: str) -> dict | None:
    ch = load_challenge(room_id)
    if not ch:
        return None
    if time.time() > ch["expires_at"]:
        ch["status"] = "finished"
        _save_challenge(room_id, ch)
        return None
    ch["participants"][user_id] = {
        "name":      user_name,
        "scores":    [],
        "avg_score": 0,
        "joined_at": time.time(),
    }
    if len(ch["participants"]) >= 2:
        ch["status"] = "active"
    _save_challenge(room_id, ch)
    return ch


def submit_score(room_id: str, user_id: str, score: float) -> dict | None:
    ch = load_challenge(room_id)
    if not ch or user_id not in ch["participants"]:
        return None
    p = ch["participants"][user_id]
    p["scores"].append({"score": round(score, 1), "ts": time.time()})
    p["avg_score"] = round(sum(s["score"] for s in p["scores"]) / len(p["scores"]), 1)
    if time.time() > ch["expires_at"]:
        ch["status"] = "finished"
    _save_challenge(room_id, ch)
    return ch


def get_leaderboard(room_id: str) -> list:
    ch = load_challenge(room_id)
    if not ch:
        return []
    board = sorted(
        [{"user_id": uid, "name": p["name"], "avg_score": p["avg_score"],
          "samples": len(p["scores"])}
         for uid, p in ch["participants"].items()],
        key=lambda x: x["avg_score"], reverse=True
    )
    for i, entry in enumerate(board):
        entry["rank"] = i + 1
    return board


def _save_challenge(room_id: str, data: dict):
    (DATA_DIR / f"challenge_{room_id}.json").write_text(json.dumps(data, indent=2))


def load_challenge(room_id: str) -> dict | None:
    p = DATA_DIR / f"challenge_{room_id}.json"
    return json.loads(p.read_text()) if p.exists() else None
