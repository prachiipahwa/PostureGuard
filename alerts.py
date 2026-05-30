"""
alerts.py — Smart Break Reminders
===================================
Tracks how long a user has been in bad posture continuously and
fires browser-push-style alerts via Server-Sent Events (SSE).

Rules:
  • Bad posture = score < BAD_SCORE_THRESHOLD for SUSTAINED_BAD_SECS seconds
  • Break due   = GOOD_POSTURE_INTERVAL minutes since last break reminder
  • Cooldown    = don't re-alert for ALERT_COOLDOWN_SECS after firing

Standing desk mode adjusts thresholds for upright body geometry.
"""

import time
from dataclasses import dataclass, field
from typing import Literal

BAD_SCORE_THRESHOLD   = 65        # score below which posture is "bad"
SUSTAINED_BAD_SECS    = 45        # continuous bad posture before alert fires
GOOD_POSTURE_INTERVAL = 30 * 60   # suggest break every 30 min of any posture
ALERT_COOLDOWN_SECS   = 120       # minimum gap between consecutive alerts

# Standing desk mode — looser spine thresholds, tighter neck (screen further)
STANDING_THRESHOLDS = {
    "neck_forward": 12.0,   # standing brings screen further → neck more critical
    "shoulder_tilt": 10.0,  # looser, natural sway when standing
    "spine_curve":   25.0,  # standing naturally has more lordosis
    "head_tilt":     6.0,
}

SEATED_THRESHOLDS = {
    "neck_forward": 15.0,
    "shoulder_tilt": 8.0,
    "spine_curve":   20.0,
    "head_tilt":     5.0,
}


@dataclass
class AlertState:
    mode: Literal["seated", "standing"] = "seated"

    # Bad-posture streak tracking
    bad_streak_start:    float = 0.0
    in_bad_streak:       bool  = False

    # Break interval tracking
    session_start:       float = field(default_factory=time.time)
    last_break_reminder: float = field(default_factory=time.time)

    # Alert cooldown
    last_alert_time:     float = 0.0

    # Pending alert for SSE delivery
    pending_alert:       dict | None = None

    def get_thresholds(self) -> dict:
        return STANDING_THRESHOLDS if self.mode == "standing" else SEATED_THRESHOLDS

    def set_mode(self, mode: Literal["seated", "standing"]):
        self.mode = mode

    def update(self, score: float) -> dict | None:
        """
        Feed latest score. Returns an alert dict if one should fire, else None.
        """
        now = time.time()
        alert = None

        # Cooldown guard
        if now - self.last_alert_time < ALERT_COOLDOWN_SECS:
            self._track_streak(score, now)
            return None

        # 1. Sustained bad posture alert
        if score < BAD_SCORE_THRESHOLD:
            if not self.in_bad_streak:
                self.in_bad_streak    = True
                self.bad_streak_start = now
            elif (now - self.bad_streak_start) >= SUSTAINED_BAD_SECS:
                duration = int(now - self.bad_streak_start)
                alert = {
                    "type":    "bad_posture",
                    "title":   "Posture alert",
                    "message": f"You've been slouching for {duration}s. "
                               f"Take a moment to sit tall and roll your shoulders back.",
                    "score":   round(score, 1),
                    "ts":      now,
                }
        else:
            self.in_bad_streak    = False
            self.bad_streak_start = 0.0

        # 2. Scheduled break reminder
        if alert is None and (now - self.last_break_reminder) >= GOOD_POSTURE_INTERVAL:
            elapsed_min = int((now - self.session_start) / 60)
            alert = {
                "type":    "break_reminder",
                "title":   "Time for a break",
                "message": f"You've been at your desk for {elapsed_min} minutes. "
                           f"Stand up, stretch your neck and walk for 2 minutes.",
                "score":   round(score, 1),
                "ts":      now,
            }
            self.last_break_reminder = now

        if alert:
            self.last_alert_time  = now
            self.pending_alert    = alert
            self.in_bad_streak    = False
            self.bad_streak_start = 0.0

        return alert

    def _track_streak(self, score, now):
        if score < BAD_SCORE_THRESHOLD:
            if not self.in_bad_streak:
                self.in_bad_streak    = True
                self.bad_streak_start = now
        else:
            self.in_bad_streak    = False
            self.bad_streak_start = 0.0

    def consume_alert(self) -> dict | None:
        """Pop and return the pending alert (for SSE polling)."""
        alert = self.pending_alert
        self.pending_alert = None
        return alert

    def streak_seconds(self) -> int:
        if self.in_bad_streak and self.bad_streak_start:
            return int(time.time() - self.bad_streak_start)
        return 0

    def next_break_in(self) -> int:
        """Seconds until next scheduled break reminder."""
        elapsed = time.time() - self.last_break_reminder
        remaining = GOOD_POSTURE_INTERVAL - elapsed
        return max(0, int(remaining))
