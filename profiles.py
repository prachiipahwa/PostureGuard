"""
profiles.py — Multiple User Profiles + Streak & Milestone System
=================================================================
Manages per-user profiles stored as JSON files in data/.
Each profile tracks: name, avatar colour, session history,
streak data, milestone achievements, and calibration link.

Usage:
    pm = ProfileManager()
    pm.create_profile("alice")
    pm.record_session("alice", avg_score=82, duration_s=1800, bad_pct=18)
    pm.get_streak("alice")        → {"current": 3, "best": 7, "today_done": True}
    pm.get_milestones("alice")    → [{"id": "first_session", "unlocked": True, ...}, ...]
"""

import json, time, hashlib
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

AVATAR_COLORS = [
    "#5DCAA5", "#378ADD", "#EF9F27", "#D4537E",
    "#7F77DD", "#D85A30", "#639922", "#E24B4A",
]

MILESTONES = [
    {"id": "first_session",   "name": "First step",       "desc": "Complete your first session",               "icon": "star",    "target": 1,   "metric": "sessions"},
    {"id": "sessions_7",      "name": "Week warrior",     "desc": "Complete 7 sessions",                       "icon": "fire",    "target": 7,   "metric": "sessions"},
    {"id": "sessions_30",     "name": "Monthly habit",    "desc": "Complete 30 sessions",                      "icon": "trophy",  "target": 30,  "metric": "sessions"},
    {"id": "streak_3",        "name": "On a roll",        "desc": "3-day streak with avg score above 75",      "icon": "bolt",    "target": 3,   "metric": "streak"},
    {"id": "streak_7",        "name": "Week streak",      "desc": "7-day streak with avg score above 75",      "icon": "flame",   "target": 7,   "metric": "streak"},
    {"id": "streak_30",       "name": "Posture champion", "desc": "30-day streak with avg score above 75",     "icon": "crown",   "target": 30,  "metric": "streak"},
    {"id": "score_85",        "name": "Good form",        "desc": "Achieve avg score of 85+ in a session",     "icon": "check",   "target": 85,  "metric": "best_score"},
    {"id": "score_95",        "name": "Perfect posture",  "desc": "Achieve avg score of 95+ in a session",     "icon": "diamond", "target": 95,  "metric": "best_score"},
    {"id": "hour_session",    "name": "Deep focus",       "desc": "Complete a session longer than 60 minutes", "icon": "clock",   "target": 3600,"metric": "longest_session"},
    {"id": "ten_hours_total", "name": "Dedicated",        "desc": "Accumulate 10 hours of total tracked time", "icon": "medal",   "target": 36000,"metric":"total_duration"},
]


class ProfileManager:

    def __init__(self):
        self._ensure_default()

    # ── Profile CRUD ─────────────────────────────────────────────────────────

    def _profile_path(self, user_id: str) -> Path:
        safe = "".join(c for c in user_id if c.isalnum() or c in "-_")
        return DATA_DIR / f"profile_{safe}.json"

    def _load(self, user_id: str) -> dict:
        p = self._profile_path(user_id)
        if p.exists():
            return json.loads(p.read_text())
        return {}

    def _save(self, user_id: str, data: dict):
        self._profile_path(user_id).write_text(json.dumps(data, indent=2))

    def _ensure_default(self):
        if not self.list_profiles():
            self.create_profile("default", display_name="You")

    def create_profile(self, user_id: str, display_name: Optional[str] = None) -> dict:
        if self._profile_path(user_id).exists():
            return self._load(user_id)
        idx   = len(self.list_profiles()) % len(AVATAR_COLORS)
        color = AVATAR_COLORS[idx]
        profile = {
            "id":             user_id,
            "name":           display_name or user_id.capitalize(),
            "color":          color,
            "created_at":     time.time(),
            "sessions":       [],          # list of session summary dicts
            "streak":         {"current": 0, "best": 0, "last_date": None},
            "milestones":     {},          # id → {"unlocked_at": timestamp}
            "calibrated":     False,
            "mode":           "seated",    # "seated" | "standing"
            "total_duration": 0,
            "best_score":     0,
        }
        self._save(user_id, profile)
        return profile

    def list_profiles(self) -> list[dict]:
        profiles = []
        for p in DATA_DIR.glob("profile_*.json"):
            try:
                profiles.append(json.loads(p.read_text()))
            except Exception:
                pass
        return sorted(profiles, key=lambda x: x.get("created_at", 0))

    def get_profile(self, user_id: str) -> dict:
        p = self._load(user_id)
        if not p:
            return self.create_profile(user_id)
        return p

    def delete_profile(self, user_id: str):
        p = self._profile_path(user_id)
        if p.exists():
            p.unlink()

    def set_mode(self, user_id: str, mode: str):
        profile = self.get_profile(user_id)
        profile["mode"] = mode
        self._save(user_id, profile)

    # ── Session recording ─────────────────────────────────────────────────────

    def record_session(self, user_id: str, avg_score: float,
                       duration_s: int, bad_pct: float,
                       issues_seen: list = None) -> dict:
        """
        Record a completed session and update streaks + milestones.
        Returns dict with new_milestones list.
        """
        profile = self.get_profile(user_id)
        today   = date.today().isoformat()

        session = {
            "date":       today,
            "ts":         time.time(),
            "avg_score":  round(avg_score, 1),
            "duration_s": duration_s,
            "bad_pct":    round(bad_pct, 1),
            "issues":     issues_seen or [],
        }
        profile["sessions"].append(session)

        # Stats
        profile["total_duration"] += duration_s
        if avg_score > profile.get("best_score", 0):
            profile["best_score"] = round(avg_score, 1)

        # Streak update
        self._update_streak(profile, today, avg_score)

        # Milestone check
        newly_unlocked = self._check_milestones(profile)

        self._save(user_id, profile)
        return {"session": session, "new_milestones": newly_unlocked}

    def _update_streak(self, profile: dict, today: str, avg_score: float):
        streak     = profile["streak"]
        last_date  = streak.get("last_date")
        qualifies  = avg_score >= 75   # must score 75+ to count toward streak

        if qualifies:
            if last_date is None:
                streak["current"] = 1
            else:
                last_d = date.fromisoformat(last_date)
                today_d = date.fromisoformat(today)
                diff = (today_d - last_d).days
                if diff == 1:
                    streak["current"] += 1
                elif diff == 0:
                    pass   # same day — no change
                else:
                    streak["current"] = 1  # reset

            streak["last_date"] = today
            streak["best"] = max(streak["best"], streak["current"])
        else:
            # Bad day breaks streak
            if last_date:
                last_d  = date.fromisoformat(last_date)
                today_d = date.fromisoformat(today)
                if (today_d - last_d).days > 1:
                    streak["current"] = 0

    def _check_milestones(self, profile: dict) -> list:
        unlocked = profile.get("milestones", {})
        newly    = []
        sessions = profile["sessions"]

        values = {
            "sessions":        len(sessions),
            "streak":          profile["streak"]["current"],
            "best_score":      profile["best_score"],
            "longest_session": max((s["duration_s"] for s in sessions), default=0),
            "total_duration":  profile["total_duration"],
        }

        for m in MILESTONES:
            mid = m["id"]
            if mid in unlocked:
                continue
            if values.get(m["metric"], 0) >= m["target"]:
                unlocked[mid] = {"unlocked_at": time.time()}
                newly.append({**m, "unlocked_at": unlocked[mid]["unlocked_at"]})

        profile["milestones"] = unlocked
        return newly

    # ── Getters ───────────────────────────────────────────────────────────────

    def get_streak(self, user_id: str) -> dict:
        profile = self.get_profile(user_id)
        streak  = profile.get("streak", {"current": 0, "best": 0, "last_date": None})
        today   = date.today().isoformat()
        last    = streak.get("last_date")
        streak["today_done"] = (last == today)
        return streak

    def get_milestones(self, user_id: str) -> list:
        profile  = self.get_profile(user_id)
        unlocked = profile.get("milestones", {})
        result   = []
        for m in MILESTONES:
            entry = {**m}
            if m["id"] in unlocked:
                entry["unlocked"]    = True
                entry["unlocked_at"] = unlocked[m["id"]]["unlocked_at"]
            else:
                entry["unlocked"]    = False
            result.append(entry)
        return result

    def get_weekly_scores(self, user_id: str, weeks: int = 8) -> list:
        """Returns list of {week, avg_score} dicts for trend graph."""
        profile  = self.get_profile(user_id)
        sessions = profile.get("sessions", [])
        today    = date.today()
        result   = []

        for w in range(weeks - 1, -1, -1):
            week_start = today - timedelta(days=today.weekday() + 7 * w)
            week_end   = week_start + timedelta(days=6)
            week_sessions = [
                s for s in sessions
                if week_start.isoformat() <= s.get("date", "") <= week_end.isoformat()
            ]
            avg = round(sum(s["avg_score"] for s in week_sessions) / len(week_sessions), 1) \
                  if week_sessions else None
            result.append({
                "week":        week_start.isoformat(),
                "label":       week_start.strftime("%b %d"),
                "avg_score":   avg,
                "sessions":    len(week_sessions),
            })
        return result

    def get_summary(self, user_id: str) -> dict:
        profile = self.get_profile(user_id)
        sessions = profile.get("sessions", [])
        return {
            "total_sessions":  len(sessions),
            "total_duration":  profile.get("total_duration", 0),
            "best_score":      profile.get("best_score", 0),
            "streak":          self.get_streak(user_id),
            "milestones_count": len(profile.get("milestones", {})),
        }
