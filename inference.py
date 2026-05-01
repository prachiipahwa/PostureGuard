"""
PostureGuard AI — Real-Time Posture Analysis & Ergonomic Coach
==============================================================
Detects poor posture (neck forward, slouching, head tilt) from
webcam or video using MediaPipe Pose. Provides live visual feedback,
posture scoring, and exports session CSV logs.

Usage:
    python inference.py --source 0          # Live webcam
    python inference.py --source video.mp4  # From video file
    python inference.py --source image.jpg  # Single image

Requirements:
    pip install mediapipe opencv-python numpy flask
"""

import cv2
import mediapipe as mp
import numpy as np
import argparse
import time
import csv
import os
from datetime import datetime

# ─── MediaPipe setup ─────────────────────────────────────────────────────────
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# ─── Posture Thresholds (degrees) ────────────────────────────────────────────
NECK_FORWARD_THRESHOLD = 15     # Forward head deviation from vertical
SHOULDER_TILT_THRESHOLD = 8     # Shoulder asymmetry (degrees)
SPINE_CURVATURE_THRESHOLD = 20  # Upper spine curvature from straight
SCORE_SMOOTHING = 0.85          # EMA smoothing for score


# ─── Geometry Helpers ────────────────────────────────────────────────────────

def angle_between(a, b, c):
    """Angle at point b formed by a-b-c (degrees)."""
    a, b, c = np.array(a), np.array(b), np.array(c)
    ba = a - b
    bc = c - b
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
    return np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))


def vertical_deviation(p1, p2):
    """Horizontal displacement of p2 relative to p1, normalized by height."""
    dx = abs(p2[0] - p1[0])
    dy = abs(p2[1] - p1[1]) + 1e-9
    return np.degrees(np.arctan(dx / dy))


def midpoint(p1, p2):
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


# ─── Posture Analyzer ────────────────────────────────────────────────────────

class PostureAnalyzer:
    def __init__(self):
        self.smooth_score = 100.0
        self.session_start = time.time()
        self.frame_count = 0
        self.bad_frames = 0
        self.alerts_log = []
        self.score_history = []

    def analyze(self, landmarks, frame_h, frame_w):
        """
        Analyzes posture from MediaPipe landmark coordinates.
        Returns: dict of metrics + overall score + issue list.
        """
        lm = landmarks.landmark

        def get(idx):
            p = lm[idx]
            return (p.x * frame_w, p.y * frame_h)

        # Key landmarks
        nose        = get(mp_pose.PoseLandmark.NOSE)
        left_eye    = get(mp_pose.PoseLandmark.LEFT_EYE)
        right_eye   = get(mp_pose.PoseLandmark.RIGHT_EYE)
        left_ear    = get(mp_pose.PoseLandmark.LEFT_EAR)
        right_ear   = get(mp_pose.PoseLandmark.RIGHT_EAR)
        left_sh     = get(mp_pose.PoseLandmark.LEFT_SHOULDER)
        right_sh    = get(mp_pose.PoseLandmark.RIGHT_SHOULDER)
        left_hip    = get(mp_pose.PoseLandmark.LEFT_HIP)
        right_hip   = get(mp_pose.PoseLandmark.RIGHT_HIP)

        issues = []
        deductions = 0

        # ── 1. Forward Head Posture ──────────────────────────────────────────
        ear_mid     = midpoint(left_ear, right_ear)
        sh_mid      = midpoint(left_sh, right_sh)
        forward_deg = vertical_deviation(sh_mid, ear_mid)
        if forward_deg > NECK_FORWARD_THRESHOLD:
            severity = min((forward_deg - NECK_FORWARD_THRESHOLD) / 20, 1.0)
            deductions += 35 * severity
            issues.append({
                "issue": "Forward Head",
                "value": round(forward_deg, 1),
                "severity": "HIGH" if severity > 0.5 else "MODERATE",
                "fix": "Pull chin back, align ears over shoulders"
            })

        # ── 2. Shoulder Tilt / Imbalance ────────────────────────────────────
        sh_tilt = abs(left_sh[1] - right_sh[1]) / (frame_h + 1e-9) * 100
        if sh_tilt > SHOULDER_TILT_THRESHOLD:
            severity = min((sh_tilt - SHOULDER_TILT_THRESHOLD) / 15, 1.0)
            deductions += 25 * severity
            issues.append({
                "issue": "Shoulder Tilt",
                "value": round(sh_tilt, 1),
                "severity": "MODERATE",
                "fix": "Level your shoulders, check chair height"
            })

        # ── 3. Upper Spine / Slouch ──────────────────────────────────────────
        hip_mid   = midpoint(left_hip, right_hip)
        spine_dev = vertical_deviation(hip_mid, sh_mid)
        if spine_dev > SPINE_CURVATURE_THRESHOLD:
            severity = min((spine_dev - SPINE_CURVATURE_THRESHOLD) / 25, 1.0)
            deductions += 30 * severity
            issues.append({
                "issue": "Slouching",
                "value": round(spine_dev, 1),
                "severity": "HIGH" if severity > 0.5 else "MODERATE",
                "fix": "Sit tall, imagine string pulling crown of head"
            })

        # ── 4. Head Tilt (left/right) ────────────────────────────────────────
        eye_mid   = midpoint(left_eye, right_eye)
        head_tilt = abs(left_eye[1] - right_eye[1]) / (frame_h + 1e-9) * 100
        if head_tilt > 5:
            deductions += 10 * min(head_tilt / 10, 1.0)
            issues.append({
                "issue": "Head Tilt",
                "value": round(head_tilt, 1),
                "severity": "LOW",
                "fix": "Keep head level, don't cradle phone on shoulder"
            })

        raw_score = max(0, 100 - deductions)
        self.smooth_score = SCORE_SMOOTHING * self.smooth_score + (1 - SCORE_SMOOTHING) * raw_score
        score = round(self.smooth_score, 1)

        self.frame_count += 1
        if score < 70:
            self.bad_frames += 1
        self.score_history.append(score)

        return {
            "score": score,
            "issues": issues,
            "forward_deg": round(forward_deg, 1),
            "sh_tilt": round(sh_tilt, 1),
            "spine_dev": round(spine_dev, 1),
            "keypoints": {
                "ear_mid": ear_mid,
                "sh_mid": sh_mid,
                "hip_mid": hip_mid,
                "nose": nose,
            }
        }

    def session_summary(self):
        elapsed = time.time() - self.session_start
        avg_score = np.mean(self.score_history) if self.score_history else 0
        bad_pct   = (self.bad_frames / max(self.frame_count, 1)) * 100
        return {
            "duration_s": round(elapsed),
            "avg_score": round(avg_score, 1),
            "bad_posture_pct": round(bad_pct, 1),
            "total_frames": self.frame_count,
        }


# ─── Overlay Renderer ────────────────────────────────────────────────────────

def score_color(score):
    if score >= 85:
        return (0, 220, 100)      # Green
    elif score >= 65:
        return (0, 190, 255)      # Amber
    else:
        return (0, 60, 255)       # Red


def draw_overlay(frame, result, fps):
    h, w = frame.shape[:2]
    score = result["score"]
    issues = result["issues"]
    color = score_color(score)

    # ── Score circle ─────────────────────────────────────────────────────────
    cx, cy, r = 70, 70, 52
    cv2.circle(frame, (cx, cy), r, (20, 20, 20), -1)
    cv2.circle(frame, (cx, cy), r, color, 3)
    cv2.putText(frame, str(int(score)), (cx - 22, cy + 10),
                cv2.FONT_HERSHEY_DUPLEX, 1.1, color, 2, cv2.LINE_AA)
    cv2.putText(frame, "SCORE", (cx - 22, cy + 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1, cv2.LINE_AA)

    # ── Status label ─────────────────────────────────────────────────────────
    if score >= 85:
        label, lcolor = "GOOD POSTURE", (0, 220, 100)
    elif score >= 65:
        label, lcolor = "NEEDS ATTENTION", (0, 190, 255)
    else:
        label, lcolor = "POOR POSTURE!", (0, 60, 255)

    cv2.putText(frame, label, (140, 55),
                cv2.FONT_HERSHEY_DUPLEX, 0.9, lcolor, 2, cv2.LINE_AA)

    # ── Metric bars ──────────────────────────────────────────────────────────
    metrics = [
        ("Forward Head", result["forward_deg"], NECK_FORWARD_THRESHOLD * 2),
        ("Shoulder Tilt", result["sh_tilt"], SHOULDER_TILT_THRESHOLD * 2),
        ("Spine",         result["spine_dev"], SPINE_CURVATURE_THRESHOLD * 2),
    ]
    bar_x, bar_y = 140, 80
    for i, (name, val, max_val) in enumerate(metrics):
        ratio = min(val / max_val, 1.0)
        bcolor = (0, 220, 100) if ratio < 0.4 else ((0, 190, 255) if ratio < 0.7 else (0, 60, 255))
        bw = 110
        bh = 8
        y = bar_y + i * 22
        cv2.rectangle(frame, (bar_x, y), (bar_x + bw, y + bh), (40, 40, 40), -1)
        cv2.rectangle(frame, (bar_x, y), (bar_x + int(bw * ratio), y + bh), bcolor, -1)
        cv2.putText(frame, f"{name}: {val:.0f}", (bar_x + bw + 8, y + 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1, cv2.LINE_AA)

    # ── Issues panel ─────────────────────────────────────────────────────────
    if issues:
        panel_y = h - 30 - len(issues) * 28
        for i, iss in enumerate(issues):
            sev_color = (0, 60, 255) if iss["severity"] == "HIGH" else \
                        ((0, 190, 255) if iss["severity"] == "MODERATE" else (0, 200, 200))
            y = panel_y + i * 28
            cv2.rectangle(frame, (8, y), (w - 8, y + 22), (10, 10, 10), -1)
            cv2.putText(frame, f"[{iss['severity']}] {iss['issue']}: {iss['fix']}",
                        (14, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.42, sev_color, 1, cv2.LINE_AA)

    # ── FPS ──────────────────────────────────────────────────────────────────
    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 80, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1, cv2.LINE_AA)

    # ── Posture line overlay (spine) ─────────────────────────────────────────
    kp = result["keypoints"]
    pts = ["sh_mid", "hip_mid"]
    colors_line = [(0, 200, 255), (0, 200, 255)]
    for p, c in zip(pts, colors_line):
        x, y2 = int(kp[p][0]), int(kp[p][1])
        cv2.circle(frame, (x, y2), 6, c, -1)
    cv2.line(frame,
             (int(kp["sh_mid"][0]), int(kp["sh_mid"][1])),
             (int(kp["hip_mid"][0]), int(kp["hip_mid"][1])),
             score_color(score), 3)
    cv2.line(frame,
             (int(kp["ear_mid"][0]), int(kp["ear_mid"][1])),
             (int(kp["sh_mid"][0]), int(kp["sh_mid"][1])),
             score_color(score), 3)

    return frame


# ─── Main Inference Loop ─────────────────────────────────────────────────────

def run_inference(source=0, save_log=True, output_video=None):
    """
    Main inference entry point.
    source: 0 for webcam, path string for video/image.
    """
    analyzer = PostureAnalyzer()

    # Image mode
    if isinstance(source, str) and source.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
        frame = cv2.imread(source)
        if frame is None:
            print(f"[ERROR] Could not read image: {source}")
            return
        with mp_pose.Pose(static_image_mode=True, model_complexity=1,
                          min_detection_confidence=0.5) as pose:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)
            if results.pose_landmarks:
                h, w = frame.shape[:2]
                mp_drawing.draw_landmarks(frame, results.pose_landmarks,
                                          mp_pose.POSE_CONNECTIONS,
                                          mp_drawing_styles.get_default_pose_landmarks_style())
                result = analyzer.analyze(results.pose_landmarks, h, w)
                frame = draw_overlay(frame, result, 0)
                print(f"[RESULT] Score: {result['score']} | Issues: {[i['issue'] for i in result['issues']]}")
            else:
                print("[WARN] No person detected in image.")
            cv2.imshow("PostureGuard AI", frame)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return

    # Video / webcam mode
    cap = cv2.VideoCapture(int(source) if str(source).isdigit() else source)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open source: {source}")
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_in = cap.get(cv2.CAP_PROP_FPS) or 30

    writer = None
    if output_video:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(output_video, fourcc, fps_in, (w, h))

    log_rows = []
    prev_time = time.time()

    print("[INFO] PostureGuard AI — Press Q to quit")

    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as pose:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # FPS calculation
            curr_time = time.time()
            fps = 1.0 / (curr_time - prev_time + 1e-9)
            prev_time = curr_time

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = pose.process(rgb)
            rgb.flags.writeable = True

            if results.pose_landmarks:
                # Draw skeleton
                mp_drawing.draw_landmarks(
                    frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                    mp_drawing_styles.get_default_pose_landmarks_style()
                )
                result = analyzer.analyze(results.pose_landmarks, h, w)
                frame = draw_overlay(frame, result, fps)

                if save_log:
                    log_rows.append({
                        "timestamp": datetime.now().isoformat(),
                        "score": result["score"],
                        "forward_deg": result["forward_deg"],
                        "sh_tilt": result["sh_tilt"],
                        "spine_dev": result["spine_dev"],
                        "issues": "|".join([i["issue"] for i in result["issues"]])
                    })
            else:
                cv2.putText(frame, "No person detected", (20, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

            if writer:
                writer.write(frame)

            cv2.imshow("PostureGuard AI", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    if writer:
        writer.release()
    cv2.destroyAllWindows()

    # ── Session summary ───────────────────────────────────────────────────────
    summary = analyzer.session_summary()
    print("\n" + "=" * 50)
    print("  SESSION SUMMARY")
    print("=" * 50)
    print(f"  Duration    : {summary['duration_s']}s")
    print(f"  Avg Score   : {summary['avg_score']}")
    print(f"  Bad Posture : {summary['bad_posture_pct']}% of session")
    print(f"  Total Frames: {summary['total_frames']}")
    print("=" * 50)

    # ── Save log CSV ──────────────────────────────────────────────────────────
    if save_log and log_rows:
        os.makedirs("logs", exist_ok=True)
        log_path = f"logs/session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(log_path, "w", newline="") as f:
            writer_csv = csv.DictWriter(f, fieldnames=log_rows[0].keys())
            writer_csv.writeheader()
            writer_csv.writerows(log_rows)
        print(f"  Log saved   : {log_path}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PostureGuard AI Inference")
    parser.add_argument("--source", default="0",
                        help="Source: 0 for webcam, path for video/image")
    parser.add_argument("--save-log", action="store_true", default=True,
                        help="Save session CSV log")
    parser.add_argument("--output", default=None,
                        help="Output video path (optional)")
    args = parser.parse_args()

    src = args.source if not args.source.isdigit() else int(args.source)
    run_inference(source=src, save_log=args.save_log, output_video=args.output)
