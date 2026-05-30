"""
calibration.py — Personal Calibration Wizard
============================================
Runs a guided 3-pose calibration session to derive personalised
posture thresholds for each user. Eliminates false positives caused
by body proportion differences (tall vs short, wide vs narrow).

Usage (standalone):
    python calibration.py --user alice

API surface used by app.py:
    CalibrationWizard.capture_pose(pose_name, landmarks, frame_hw)
    CalibrationWizard.compute_thresholds()  → dict
    load_calibration(user_id) → dict | None
    save_calibration(user_id, thresholds)
"""

import json, os, time, numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_THRESHOLDS = {
    "neck_forward": 15.0,
    "shoulder_tilt": 8.0,
    "spine_curve":   20.0,
    "head_tilt":     5.0,
}

CALIBRATION_POSES = [
    {
        "id":   "ideal",
        "name": "Perfect posture",
        "cue":  "Sit tall, ears over shoulders, back straight. Hold for 3 seconds.",
    },
    {
        "id":   "forward",
        "name": "Natural forward lean",
        "cue":  "Lean forward slightly as if reading — how you naturally sit. Hold 3 sec.",
    },
    {
        "id":   "slouch",
        "name": "Relaxed slouch",
        "cue":  "Let yourself slouch normally. This sets your 'bad posture' baseline.",
    },
]


def _midpoint(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _vert_dev(p1, p2):
    dx = abs(p2[0] - p1[0])
    dy = abs(p2[1] - p1[1]) + 1e-9
    return float(np.degrees(np.arctan(dx / dy)))


def _extract_metrics(landmarks, frame_h, frame_w):
    """Extract raw metric values from MediaPipe landmark list."""
    lm = landmarks

    def g(idx):
        p = lm[idx]
        return (p.x * frame_w, p.y * frame_h)

    import mediapipe as mp
    PL = mp.solutions.pose.PoseLandmark

    ear_mid = _midpoint(g(PL.LEFT_EAR), g(PL.RIGHT_EAR))
    sh_mid  = _midpoint(g(PL.LEFT_SHOULDER), g(PL.RIGHT_SHOULDER))
    hip_mid = _midpoint(g(PL.LEFT_HIP), g(PL.RIGHT_HIP))
    le, re  = g(PL.LEFT_EYE), g(PL.RIGHT_EYE)
    ls, rs  = g(PL.LEFT_SHOULDER), g(PL.RIGHT_SHOULDER)

    return {
        "neck_forward": _vert_dev(sh_mid, ear_mid),
        "shoulder_tilt": abs(ls[1] - rs[1]) / frame_h * 100,
        "spine_curve":  _vert_dev(hip_mid, sh_mid),
        "head_tilt":    abs(le[1] - re[1]) / frame_h * 100,
    }


class CalibrationWizard:
    """
    Collects measurements across 3 calibration poses and derives
    personalised alert thresholds halfway between ideal and bad posture.
    """

    def __init__(self):
        self.measurements = {}   # pose_id → list[metric_dict]
        self.completed    = set()

    def capture_pose(self, pose_id: str, landmarks, frame_h: int, frame_w: int):
        """Record one frame's metrics for the given pose."""
        metrics = _extract_metrics(landmarks, frame_h, frame_w)
        if pose_id not in self.measurements:
            self.measurements[pose_id] = []
        self.measurements[pose_id].append(metrics)
        return metrics

    def pose_ready(self, pose_id: str, min_frames: int = 15) -> bool:
        return len(self.measurements.get(pose_id, [])) >= min_frames

    def complete_pose(self, pose_id: str):
        self.completed.add(pose_id)

    def compute_thresholds(self) -> dict:
        """
        Derive thresholds from collected measurements.

        Logic:
          ideal_val    = median of 'ideal' pose frames
          bad_val      = median of 'slouch' pose frames
          threshold    = ideal_val + (bad_val - ideal_val) * 0.4
          (alert fires when you're 40% of the way toward your worst posture)
        """
        keys = ["neck_forward", "shoulder_tilt", "spine_curve", "head_tilt"]
        thresholds = {}

        ideal_data = self.measurements.get("ideal", [])
        slouch_data = self.measurements.get("slouch", [])

        for k in keys:
            if ideal_data and slouch_data:
                ideal_val  = np.median([m[k] for m in ideal_data])
                slouch_val = np.median([m[k] for m in slouch_data])
                # 40% of the way from ideal toward full slouch
                threshold  = ideal_val + (slouch_val - ideal_val) * 0.40
                thresholds[k] = round(float(max(threshold, DEFAULT_THRESHOLDS[k] * 0.5)), 2)
            else:
                thresholds[k] = DEFAULT_THRESHOLDS[k]

        thresholds["calibrated_at"] = time.time()
        thresholds["ideal_baseline"] = {
            k: round(float(np.median([m[k] for m in ideal_data])), 2)
            for k in keys
        } if ideal_data else {}

        return thresholds


def load_calibration(user_id: str) -> dict | None:
    path = DATA_DIR / f"calibration_{user_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_calibration(user_id: str, thresholds: dict):
    path = DATA_DIR / f"calibration_{user_id}.json"
    path.write_text(json.dumps(thresholds, indent=2))


def get_thresholds(user_id: str) -> dict:
    """Return calibrated thresholds or fall back to defaults."""
    cal = load_calibration(user_id)
    if cal:
        return {k: cal.get(k, DEFAULT_THRESHOLDS[k]) for k in DEFAULT_THRESHOLDS}
    return DEFAULT_THRESHOLDS.copy()
