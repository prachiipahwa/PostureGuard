"""
app.py — PostureGuard AI Flask Server (v2)
==========================================
All 11 features wired:
  01 /api/calibration/*         — personal calibration wizard
  02 /api/alerts/poll           — smart break reminders
  03 mode toggle via /api/mode  — standing desk mode
  04 /api/profiles/*            — user profiles CRUD
  05 /api/trends/<user>         — score trend data
  06 /api/streaks/<user>        — streak + milestones
  07 /obs                       — OBS stream widget
  08 voice coaching is frontend-only (Web Speech API)
  09 /api/plan/*                — AI 7-day plan
  10 /api/challenges/*          — friend challenges
  11 /api/report/<user>         — PDF weekly report download
"""

from flask import Flask, request, jsonify, render_template, send_file, session
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_API_URL, has_api_key, SECRET_KEY
import cv2, mediapipe as mp, numpy as np
import base64, time, json
from pathlib import Path

from calibration  import CalibrationWizard, save_calibration, load_calibration, \
                         get_thresholds, CALIBRATION_POSES, DEFAULT_THRESHOLDS
from alerts       import AlertState, STANDING_THRESHOLDS, SEATED_THRESHOLDS
from profiles     import ProfileManager
from ai_features  import (generate_7day_plan, save_plan, load_plan,
                           create_challenge, join_challenge,
                           submit_score, get_leaderboard, load_challenge)
from weekly_report import generate_weekly_report
from auth import signup, login, get_user, list_users, change_display_name

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = SECRET_KEY

mp_pose    = mp.solutions.pose
pose_model = mp_pose.Pose(static_image_mode=True, model_complexity=1,
                          min_detection_confidence=0.5)
pm          = ProfileManager()
alert_state = AlertState()

_cal_wizards: dict = {}
_active_user = {"id": "default"}
_sessions: dict = {}


def midpt(a, b): return ((a[0]+b[0])/2, (a[1]+b[1])/2)

def vert_dev(p1, p2):
    dx = abs(p2[0]-p1[0]); dy = abs(p2[1]-p1[1])+1e-9
    return float(np.degrees(np.arctan(dx/dy)))

def decode_frame(b64):
    data = base64.b64decode(b64.split(",")[-1])
    arr  = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def get_uid():
    return request.args.get("user", _active_user["id"])

def get_session(uid):
    if uid not in _sessions:
        _sessions[uid] = {"smooth":80,"history":[],"bad":0,"total":0,
                          "start":time.time(),"issues_seen":set()}
    return _sessions[uid]

def reset_session(uid):
    _sessions[uid] = {"smooth":80,"history":[],"bad":0,"total":0,
                      "start":time.time(),"issues_seen":set()}


def _analyse(frame, thresholds):
    h, w = frame.shape[:2]
    res  = pose_model.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    if not res.pose_landmarks: return None
    lm = res.pose_landmarks.landmark
    PL = mp_pose.PoseLandmark
    def g(i): p=lm[i]; return (p.x*w, p.y*h)

    ear_mid = midpt(g(PL.LEFT_EAR),      g(PL.RIGHT_EAR))
    sh_mid  = midpt(g(PL.LEFT_SHOULDER), g(PL.RIGHT_SHOULDER))
    hip_mid = midpt(g(PL.LEFT_HIP),      g(PL.RIGHT_HIP))
    le, re  = g(PL.LEFT_EYE), g(PL.RIGHT_EYE)
    ls, rs  = g(PL.LEFT_SHOULDER), g(PL.RIGHT_SHOULDER)

    fwd = vert_dev(sh_mid, ear_mid)
    sht = abs(ls[1]-rs[1])/(h+1e-9)*100
    spd = vert_dev(hip_mid, sh_mid)
    hdt = abs(le[1]-re[1])/(h+1e-9)*100

    T = thresholds; issues = []; ded = 0
    if fwd > T["neck_forward"]:
        s=min((fwd-T["neck_forward"])/20,1); ded+=35*s
        issues.append({"issue":"Forward Head","value":round(fwd,1),"unit":"°",
                       "severity":"HIGH" if s>.5 else "MODERATE",
                       "fix":"Pull chin back — align ears over shoulders"})
    if sht > T["shoulder_tilt"]:
        s=min((sht-T["shoulder_tilt"])/15,1); ded+=25*s
        issues.append({"issue":"Shoulder Tilt","value":round(sht,1),"unit":"%",
                       "severity":"MODERATE","fix":"Level shoulders — check chair height"})
    if spd > T["spine_curve"]:
        s=min((spd-T["spine_curve"])/25,1); ded+=30*s
        issues.append({"issue":"Slouching","value":round(spd,1),"unit":"°",
                       "severity":"HIGH" if s>.5 else "MODERATE",
                       "fix":"Sit tall — imagine string pulling crown upward"})
    if hdt > T["head_tilt"]:
        ded+=10*min(hdt/10,1)
        issues.append({"issue":"Head Tilt","value":round(hdt,1),"unit":"%",
                       "severity":"LOW","fix":"Keep head level"})

    kps  = [{"x":p.x,"y":p.y,"visibility":p.visibility} for p in lm]
    conn = [[11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],
            [23,24],[0,11],[0,12],[7,8],[23,25],[24,26]]
    return {"detected":True,"raw_score":round(max(0,100-ded),1),
            "issues":issues,"issue_names":[i["issue"] for i in issues],
            "metrics":{"fwd_deg":round(fwd,1),"sh_tilt":round(sht,1),
                       "spine_d":round(spd,1),"head_t":round(hdt,1)},
            "keypoints":kps,"connections":conn}


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", profiles=pm.list_profiles())

@app.route("/obs")
def obs():
    return render_template("obs_widget.html")


# ── Core ──────────────────────────────────────────────────────────────────────
@app.route("/api/analyze", methods=["POST"])
def analyze():
    data  = request.get_json(force=True)
    uid   = data.get("user","default")
    frame = decode_frame(data.get("frame",""))
    if frame is None: return jsonify({"error":"bad frame"}),400

    T = get_thresholds(uid)
    if alert_state.mode == "standing":
        T.update(STANDING_THRESHOLDS)

    r = _analyse(frame, T)
    if r is None: return jsonify({"detected":False,"message":"No person detected"})

    sess = get_session(uid)
    sess["smooth"] = 0.85*sess["smooth"] + 0.15*r["raw_score"]
    score = round(sess["smooth"],1)
    sess["history"].append(score)
    if len(sess["history"])>600: sess["history"].pop(0)
    sess["total"]+=1
    if score<70: sess["bad"]+=1
    for iss in r["issue_names"]: sess["issues_seen"].add(iss)

    alert = alert_state.update(score)
    if data.get("challenge_id"):
        submit_score(data["challenge_id"], uid, score)

    return jsonify({**r,"score":score,
                    "score_history":sess["history"][-60:],
                    "alert":alert,"mode":alert_state.mode,
                    "streak_seconds":alert_state.streak_seconds(),
                    "next_break_in":alert_state.next_break_in()})


@app.route("/api/mode", methods=["POST"])
def set_mode():
    data = request.get_json(force=True)
    mode = data.get("mode","seated"); uid = data.get("user","default")
    alert_state.set_mode(mode); pm.set_mode(uid, mode)
    return jsonify({"mode":mode,
                    "thresholds":STANDING_THRESHOLDS if mode=="standing" else SEATED_THRESHOLDS})


@app.route("/api/session")
def session_stats():
    uid=get_uid(); sess=get_session(uid)
    h=sess["history"]
    return jsonify({"duration_s":round(time.time()-sess["start"]),
                    "avg_score":round(sum(h)/len(h),1) if h else 0,
                    "bad_posture_pct":round(sess["bad"]/max(sess["total"],1)*100,1),
                    "total_frames":sess["total"],
                    "current_score":h[-1] if h else None})


@app.route("/api/session/end", methods=["POST"])
def end_session():
    uid=get_uid(); sess=get_session(uid); h=sess["history"]
    avg=round(sum(h)/len(h),1) if h else 0
    dur=int(time.time()-sess["start"])
    bad=round(sess["bad"]/max(sess["total"],1)*100,1)
    result=pm.record_session(uid,avg_score=avg,duration_s=dur,
                              bad_pct=bad,issues_seen=list(sess["issues_seen"]))
    reset_session(uid)
    return jsonify(result)


@app.route("/api/reset", methods=["POST"])
def reset():
    reset_session(get_uid()); return jsonify({"status":"reset"})


# ── Profiles ──────────────────────────────────────────────────────────────────
@app.route("/api/profiles", methods=["GET"])
def list_profiles(): return jsonify(pm.list_profiles())

@app.route("/api/profiles", methods=["POST"])
def create_profile():
    data=request.get_json(force=True)
    uid=data.get("id","").strip().lower().replace(" ","_")
    if not uid: return jsonify({"error":"id required"}),400
    return jsonify(pm.create_profile(uid, display_name=data.get("name",uid.capitalize())))

@app.route("/api/profiles/<uid>")
def get_profile(uid): return jsonify(pm.get_profile(uid))

@app.route("/api/profiles/<uid>", methods=["DELETE"])
def del_profile(uid): pm.delete_profile(uid); return jsonify({"deleted":uid})

@app.route("/api/profiles/switch", methods=["POST"])
def switch_profile():
    uid=request.get_json(force=True).get("user")
    _active_user["id"]=uid; return jsonify({"active":uid})


# ── Trends & Streaks ──────────────────────────────────────────────────────────
@app.route("/api/trends/<uid>")
def trends(uid):
    return jsonify(pm.get_weekly_scores(uid, int(request.args.get("weeks",8))))

@app.route("/api/streaks/<uid>")
def streaks(uid):
    return jsonify({"streak":pm.get_streak(uid),
                    "milestones":pm.get_milestones(uid),
                    "summary":pm.get_summary(uid)})


# ── Calibration ───────────────────────────────────────────────────────────────
@app.route("/api/calibration/poses")
def cal_poses(): return jsonify(CALIBRATION_POSES)

@app.route("/api/calibration/start", methods=["POST"])
def cal_start():
    uid=get_uid(); _cal_wizards[uid]=CalibrationWizard()
    return jsonify({"status":"started","poses":CALIBRATION_POSES})

@app.route("/api/calibration/capture", methods=["POST"])
def cal_capture():
    data=request.get_json(force=True)
    uid=data.get("user","default"); pose_id=data.get("pose_id")
    frame=decode_frame(data.get("frame",""))
    wiz=_cal_wizards.get(uid)
    if not wiz or frame is None: return jsonify({"error":"not started"}),400
    h,w=frame.shape[:2]
    res=pose_model.process(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
    if not res.pose_landmarks: return jsonify({"detected":False})
    metrics=wiz.capture_pose(pose_id,res.pose_landmarks,h,w)
    return jsonify({"detected":True,"metrics":metrics,
                    "frames_captured":len(wiz.measurements.get(pose_id,[])),
                    "ready":wiz.pose_ready(pose_id)})

@app.route("/api/calibration/complete_pose", methods=["POST"])
def cal_complete():
    data=request.get_json(force=True); uid=data.get("user","default")
    wiz=_cal_wizards.get(uid)
    if not wiz: return jsonify({"error":"no wizard"}),400
    wiz.complete_pose(data.get("pose_id")); return jsonify({"done":list(wiz.completed)})

@app.route("/api/calibration/finish", methods=["POST"])
def cal_finish():
    uid=get_uid(); wiz=_cal_wizards.get(uid)
    if not wiz: return jsonify({"error":"no wizard"}),400
    T=wiz.compute_thresholds(); save_calibration(uid,T)
    p=pm.get_profile(uid); p["calibrated"]=True; pm._save(uid,p)
    del _cal_wizards[uid]; return jsonify({"status":"saved","thresholds":T})

@app.route("/api/calibration/<uid>")
def get_cal(uid): return jsonify(load_calibration(uid) or DEFAULT_THRESHOLDS)


# ── Alerts ────────────────────────────────────────────────────────────────────
@app.route("/api/alerts/poll")
def poll_alerts():
    return jsonify({"alert":alert_state.consume_alert(),
                    "streak_seconds":alert_state.streak_seconds(),
                    "next_break_in":alert_state.next_break_in(),
                    "mode":alert_state.mode})


# ── AI Plan ───────────────────────────────────────────────────────────────────
@app.route("/api/plan/<uid>")
def get_plan(uid): return jsonify(load_plan(uid) or {})

@app.route("/api/plan/<uid>/generate", methods=["POST"])
def gen_plan(uid):
    plan=generate_7day_plan(pm.get_profile(uid)); save_plan(uid,plan)
    return jsonify(plan)


# ── Challenges ────────────────────────────────────────────────────────────────
@app.route("/api/challenges/create", methods=["POST"])
def chal_create():
    data=request.get_json(force=True); uid=data.get("user","default")
    name=data.get("name",pm.get_profile(uid).get("name",uid))
    return jsonify(create_challenge(uid,name,data.get("hours",24)))

@app.route("/api/challenges/join", methods=["POST"])
def chal_join():
    data=request.get_json(force=True)
    uid=data.get("user","default"); name=data.get("name",pm.get_profile(uid).get("name",uid))
    ch=join_challenge(data.get("room_id","").upper(),uid,name)
    return jsonify(ch) if ch else (jsonify({"error":"Room not found or expired"}),404)

@app.route("/api/challenges/<room_id>")
def chal_get(room_id):
    ch=load_challenge(room_id.upper())
    return jsonify({**ch,"leaderboard":get_leaderboard(room_id.upper())}) if ch else (jsonify({"error":"not found"}),404)


# ── PDF Report ────────────────────────────────────────────────────────────────
@app.route("/api/report/<uid>")
def weekly_report(uid):
    profile=pm.get_profile(uid); weekly=pm.get_weekly_scores(uid,8)
    path=generate_weekly_report(uid,profile,weekly)
    return send_file(path,mimetype="application/pdf",as_attachment=True,
                     download_name=f"postureguard_weekly_{uid}.pdf")


# ── Auth routes ──────────────────────────────────────────────────────────

@app.route("/auth/signup", methods=["POST"])
def do_signup():
    data = request.get_json(force=True)
    result = signup(
        username=data.get("username",""),
        password=data.get("password",""),
        display_name=data.get("display_name","")
    )
    if result["ok"]:
        uid = result["user_id"]
        # Auto-create a PostureGuard profile for the new user
        pm.create_profile(uid, display_name=result["display_name"])
        session["user_id"] = uid
        _active_user["id"] = uid
    return jsonify(result), (200 if result["ok"] else 400)


@app.route("/auth/login", methods=["POST"])
def do_login():
    data = request.get_json(force=True)
    result = login(
        username=data.get("username",""),
        password=data.get("password","")
    )
    if result["ok"]:
        session["user_id"] = result["user_id"]
        _active_user["id"] = result["user_id"]
        # Ensure a posture profile exists for this user
        pm.create_profile(result["user_id"], display_name=result["display_name"])
    return jsonify(result), (200 if result["ok"] else 401)


@app.route("/auth/logout", methods=["POST"])
def do_logout():
    session.clear()
    _active_user["id"] = "default"
    return jsonify({"ok": True})


@app.route("/auth/me")
def auth_me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"logged_in": False})
    user = get_user(uid)
    if not user:
        return jsonify({"logged_in": False})
    return jsonify({
        "logged_in":    True,
        "user_id":      uid,
        "display_name": user["display_name"],
    })


# ── AI Coach (server-side, key never exposed) ────────────────────────────
@app.route("/api/ai_coach", methods=["POST"])
def ai_coach():
    import requests as req
    data   = request.get_json(force=True)
    prompt = data.get("prompt", "Give a posture tip.")
    if not has_api_key():
        return jsonify({"tip": None, "error": "No API key configured — set GROQ_API_KEY in .env (free at console.groq.com)"})
    try:
        # Groq: OpenAI-compatible, free, no billing required
        resp = req.post(
            GROQ_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}"
            },
            json={
                "model": GROQ_MODEL,
                "max_tokens": 1000,
                "messages": [
                    {"role": "system", "content": "You are a concise ergonomic posture coach. Give short, direct, actionable advice."},
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=20
        )
        text = resp.json()["choices"][0]["message"]["content"]
        return jsonify({"tip": text})
    except Exception as e:
        return jsonify({"tip": None, "error": str(e)})


# ── Auth status (for UI to check if user is logged in) ───────────────────
@app.route("/api/auth/status")
def auth_status():
    return jsonify({
        "has_api_key": has_api_key(),
        "active_user": _active_user["id"],
        "profiles_count": len(pm.list_profiles())
    })


if __name__ == "__main__":
    print("[PostureGuard v2] http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
