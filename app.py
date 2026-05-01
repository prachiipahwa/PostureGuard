"""
PostureGuard AI — Flask Web Server
====================================
Serves the interactive dashboard and provides:
  - /api/analyze   : POST a base64 frame, get posture JSON back
  - /api/session   : GET session summary stats
  - /               : Serves the frontend dashboard
"""

from flask import Flask, request, jsonify, render_template, send_from_directory
import cv2
import mediapipe as mp
import numpy as np
import base64
import time
import json
import os
import csv
from datetime import datetime
from collections import deque

# Import our core analyzer
import sys
sys.path.insert(0, os.path.dirname(__file__))
from inference import PostureAnalyzer, NECK_FORWARD_THRESHOLD, SHOULDER_TILT_THRESHOLD, SPINE_CURVATURE_THRESHOLD

app = Flask(__name__, template_folder="templates", static_folder="static")

# ── MediaPipe instance (reused across requests) ───────────────────────────────
mp_pose = mp.solutions.pose
pose_model = mp_pose.Pose(
    static_image_mode=True,
    model_complexity=1,
    min_detection_confidence=0.5
)

# ── Per-session state ─────────────────────────────────────────────────────────
session = {
    "analyzer": PostureAnalyzer(),
    "score_history": deque(maxlen=300),  # ~10 seconds at 30fps
    "start_time": time.time(),
    "frame_count": 0,
    "bad_frames": 0,
}

def midpoint(p1, p2):
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)

def vertical_deviation(p1, p2):
    dx = abs(p2[0] - p1[0])
    dy = abs(p2[1] - p1[1]) + 1e-9
    return float(np.degrees(np.arctan(dx / dy)))

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/analyze", methods=["POST"])
def analyze_frame():
    """
    Accepts: { "frame": "<base64 JPEG>" }
    Returns: posture analysis JSON
    """
    data = request.get_json(force=True)
    if not data or "frame" not in data:
        return jsonify({"error": "No frame provided"}), 400

    try:
        # Decode base64 image
        img_bytes = base64.b64decode(data["frame"].split(",")[-1])
        img_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"error": "Invalid image"}), 400

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose_model.process(rgb)

        if not results.pose_landmarks:
            return jsonify({
                "detected": False,
                "score": None,
                "issues": [],
                "message": "No person detected"
            })

        lm = results.pose_landmarks.landmark

        def get(idx):
            p = lm[idx]
            return (p.x * w, p.y * h)

        # Compute posture metrics
        nose        = get(mp_pose.PoseLandmark.NOSE)
        left_ear    = get(mp_pose.PoseLandmark.LEFT_EAR)
        right_ear   = get(mp_pose.PoseLandmark.RIGHT_EAR)
        left_sh     = get(mp_pose.PoseLandmark.LEFT_SHOULDER)
        right_sh    = get(mp_pose.PoseLandmark.RIGHT_SHOULDER)
        left_hip    = get(mp_pose.PoseLandmark.LEFT_HIP)
        right_hip   = get(mp_pose.PoseLandmark.RIGHT_HIP)
        left_eye    = get(mp_pose.PoseLandmark.LEFT_EYE)
        right_eye   = get(mp_pose.PoseLandmark.RIGHT_EYE)

        ear_mid  = midpoint(left_ear, right_ear)
        sh_mid   = midpoint(left_sh, right_sh)
        hip_mid  = midpoint(left_hip, right_hip)

        forward_deg = vertical_deviation(sh_mid, ear_mid)
        sh_tilt     = abs(left_sh[1] - right_sh[1]) / (h + 1e-9) * 100
        spine_dev   = vertical_deviation(hip_mid, sh_mid)
        head_tilt   = abs(left_eye[1] - right_eye[1]) / (h + 1e-9) * 100

        SMOOTH = 0.85
        issues = []
        deductions = 0

        if forward_deg > NECK_FORWARD_THRESHOLD:
            severity = min((forward_deg - NECK_FORWARD_THRESHOLD) / 20, 1.0)
            deductions += 35 * severity
            issues.append({
                "issue": "Forward Head",
                "value": round(forward_deg, 1),
                "unit": "°",
                "severity": "HIGH" if severity > 0.5 else "MODERATE",
                "fix": "Pull chin back — align ears over shoulders"
            })

        if sh_tilt > SHOULDER_TILT_THRESHOLD:
            severity = min((sh_tilt - SHOULDER_TILT_THRESHOLD) / 15, 1.0)
            deductions += 25 * severity
            issues.append({
                "issue": "Shoulder Tilt",
                "value": round(sh_tilt, 1),
                "unit": "%",
                "severity": "MODERATE",
                "fix": "Level your shoulders — check chair height"
            })

        if spine_dev > SPINE_CURVATURE_THRESHOLD:
            severity = min((spine_dev - SPINE_CURVATURE_THRESHOLD) / 25, 1.0)
            deductions += 30 * severity
            issues.append({
                "issue": "Slouching",
                "value": round(spine_dev, 1),
                "unit": "°",
                "severity": "HIGH" if severity > 0.5 else "MODERATE",
                "fix": "Sit tall — imagine a string pulling your crown upward"
            })

        if head_tilt > 5:
            deductions += 10 * min(head_tilt / 10, 1.0)
            issues.append({
                "issue": "Head Tilt",
                "value": round(head_tilt, 1),
                "unit": "%",
                "severity": "LOW",
                "fix": "Keep head level — don't cradle phone on shoulder"
            })

        raw_score = max(0, 100 - deductions)
        prev = session["score_history"][-1] if session["score_history"] else raw_score
        smooth = SMOOTH * prev + (1 - SMOOTH) * raw_score
        score = round(smooth, 1)

        session["score_history"].append(score)
        session["frame_count"] += 1
        if score < 70:
            session["bad_frames"] += 1

        # Landmark positions (normalized 0-1 for frontend rendering)
        keypoints = [
            {"x": lm[i].x, "y": lm[i].y, "visibility": lm[i].visibility}
            for i in range(33)
        ]

        connections = [
            [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
            [11, 23], [12, 24], [23, 24], [23, 25], [24, 26],
            [0, 11], [0, 12],
            [7, 8],   # ears
        ]

        return jsonify({
            "detected": True,
            "score": score,
            "issues": issues,
            "metrics": {
                "forward_deg": round(forward_deg, 1),
                "sh_tilt": round(sh_tilt, 1),
                "spine_dev": round(spine_dev, 1),
                "head_tilt": round(head_tilt, 1),
            },
            "keypoints": keypoints,
            "connections": connections,
            "score_history": list(session["score_history"])[-60:],
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/session", methods=["GET"])
def session_stats():
    """Return current session summary."""
    elapsed = time.time() - session["start_time"]
    history = list(session["score_history"])
    avg = round(np.mean(history), 1) if history else 0
    bad_pct = round((session["bad_frames"] / max(session["frame_count"], 1)) * 100, 1)

    return jsonify({
        "duration_s": round(elapsed),
        "avg_score": avg,
        "bad_posture_pct": bad_pct,
        "total_frames": session["frame_count"],
        "current_score": history[-1] if history else None,
    })


@app.route("/api/reset", methods=["POST"])
def reset_session():
    """Reset session counters."""
    session["analyzer"] = PostureAnalyzer()
    session["score_history"].clear()
    session["start_time"] = time.time()
    session["frame_count"] = 0
    session["bad_frames"] = 0
    return jsonify({"status": "reset"})


if __name__ == "__main__":
    print("[PostureGuard] Starting server at http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
