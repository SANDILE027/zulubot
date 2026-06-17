"""
app.py — UniZulu Assistant Backend
===================================
Powers both tabs of the chatbot widget:

  • Chat tab             → /get_response, /welcome
  • Programme Finder tab → /programmes, /recommend
  • Exam lookup          → /exam (search by code or name)

Run:
    python app.py
"""

import re
import json
import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from fuzzywuzzy import process

from data_loader import load_all_programmes
from module_loader import get_module_answer, search_module, list_all_modules
from registration_kb import get_registration_answer, list_topics as list_registration_topics
from db_config import get_db_connection

app = Flask(__name__)
CORS(app)

# ══════════════════════════════════════════════════════════════════════════════
#  DATA — loaded once at startup
# ══════════════════════════════════════════════════════════════════════════════

# Programmes (106 from the 4 faculty JSONs)
PROGRAMMES = load_all_programmes()
print(f"✅ Loaded {len(PROGRAMMES)} programmes")

_BY_CODE      = {p["code"].lower(): p for p in PROGRAMMES}
_BY_ID        = {p["id"].lower():   p for p in PROGRAMMES}
_PROG_NAMES   = [p["programme"] for p in PROGRAMMES]
_NAME_TO_PROG = {p["programme"]: p for p in PROGRAMMES}


# Exam timetable
def _load_exams():
    candidates = [
        os.path.join(os.path.dirname(__file__), "cache", "exam_timetable.json"),
        os.path.join(os.path.dirname(__file__), "exam_timetable.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            print(f"✅ Loaded {len(data)} exams")
            return data
    print("⚠️  exam_timetable.json not found")
    return []

EXAMS = _load_exams()

# Exam indexes
_EXAM_BY_CODE = {}  # stripped code → list of exams
_EXAM_NAMES   = [e["exam_name"] for e in EXAMS]

for _e in EXAMS:
    # Strip trailing _P_1_15 / _P_2_15 style suffixes for flexible matching
    _stripped = re.sub(r"_[Pp]_\d+_\d+$", "", _e["exam_code"]).lower()
    _EXAM_BY_CODE.setdefault(_stripped, []).append(_e)
    _EXAM_BY_CODE.setdefault(_e["exam_code"].lower(), []).append(_e)


# ══════════════════════════════════════════════════════════════════════════════
#  SUBJECT NORMALISATION (shared by /recommend)
# ══════════════════════════════════════════════════════════════════════════════
ALIASES = {
    "english (hl)": "english", "english (fal)": "english",
    "isizulu (hl)": "isizulu", "isizulu (fal)": "isizulu",
    "mathematical literacy": "mathematics or mathematical literacy",
    "maths literacy": "mathematics or mathematical literacy",
    "math lit": "mathematics or mathematical literacy",
    "maths": "mathematics",
    "physical sciences": "physical science",
    "physical science or info": "physical science or information technology",
    "physical science or it": "physical science or information technology",
    "geog": "geography", "hist": "history", "engl": "english",
}

def _norm_subject(name):
    n = name.lower().strip()
    return ALIASES.get(n, n)


# ══════════════════════════════════════════════════════════════════════════════
#  EXAM HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _search_exams(query):
    """
    Find exams matching a code or name.
    Returns list of matching exam dicts, or empty list.
    """
    q = query.strip()
    if not q:
        return []

    q_lower = q.lower()

    # 1. Exact / prefix code match
    stripped_q = re.sub(r"_[Pp]_\d+_\d+$", "", q_lower)
    if stripped_q in _EXAM_BY_CODE:
        return _EXAM_BY_CODE[stripped_q]

    # 2. Partial code match (user typed "4MTH271" without suffix)
    for key, exams in _EXAM_BY_CODE.items():
        if q_lower in key or key.startswith(q_lower):
            return exams

    # 3. Substring name match
    matches = [e for e in EXAMS if q_lower in e["exam_name"].lower()]
    if matches:
        return matches

    # 4. Fuzzy name match
    if _EXAM_NAMES:
        best, score = process.extractOne(q, _EXAM_NAMES)
        if score >= 65:
            return [e for e in EXAMS if e["exam_name"] == best]

    return []


def _format_exam(e):
    """Format one exam entry as a chat-friendly string."""
    # Parse date
    try:
        from datetime import datetime
        dt = datetime.strptime(e["date"], "%Y/%m/%d")
        date_str = dt.strftime("%A, %d %B %Y")
    except Exception:
        date_str = e.get("date", "TBA")

    duration_hrs = e["duration"] // 60
    duration_min = e["duration"] % 60
    dur_str = f"{duration_hrs}h" + (f" {duration_min}min" if duration_min else "")

    return (
        f"📋 **{e['exam_name']}**\n"
        f"🔑 Code: `{e['exam_code']}`\n"
        f"📅 Date: {date_str}\n"
        f"🕗 Time: {e['start_time']} | Duration: {dur_str}\n"
        f"📍 Site: {e['site']}\n"
        f"🏫 Room: {e['room_name']} ({e['room_code']})\n"
        f"👥 Candidates: {e['candidates']}"
    )


def _is_exam_query(msg):
    """Detect if a message is asking about an exam."""
    keywords = [
        "exam", "test", "timetable", "time table",
        "exam date", "exam time", "exam room", "exam venue",
        "write my", "writing my"
    ]
    return any(k in msg.lower() for k in keywords)


# ══════════════════════════════════════════════════════════════════════════════
#  PROGRAMME FINDER ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/programmes", methods=["GET"])
def programmes():
    progs = PROGRAMMES
    fac_q = request.args.get("faculty", "").strip().lower()
    if fac_q:
        progs = [p for p in progs if fac_q in p["faculty"].lower()]
    return jsonify(progs)


@app.route("/recommend", methods=["POST"])
def recommend():
    data     = request.get_json(force=True, silent=True) or {}
    subjects = data.get("subjects", [])
    aps      = int(data.get("aps", 0))
    faculty  = (data.get("faculty") or "").strip().lower()

    progs = PROGRAMMES
    if faculty:
        progs = [p for p in progs if faculty in p["faculty"].lower()]

    student_map = {}
    for s in subjects:
        n = _norm_subject(s.get("name", ""))
        l = int(s.get("level", 0))
        if n:
            student_map[n] = max(student_map.get(n, 0), l)

    qualified, almost, others = [], [], []

    for prog in progs:
        if prog.get("aps_unknown"):
            others.append({**prog, "subject_checks": [], "qualifies": False, "aps_gap": None})
            continue

        aps_ok  = aps >= prog["aps"]
        aps_gap = prog["aps"] - aps

        checks = []
        for req in prog.get("subjects", []):
            req_alts = [_norm_subject(a.strip()) for a in req["name"].split(" or ")]
            best     = max((student_map.get(a, 0) for a in req_alts), default=0)
            checks.append({
                "required":      req["name"],
                "min_level":     req["min_level"],
                "student_level": best,
                "ok":            best >= req["min_level"],
            })

        subjects_ok = all(c["ok"] for c in checks)
        qualifies   = aps_ok and subjects_ok
        entry = {**prog, "subject_checks": checks, "qualifies": qualifies, "aps_gap": aps_gap}

        if qualifies:         qualified.append(entry)
        elif 0 < aps_gap <= 5: almost.append(entry)
        else:                 others.append(entry)

    return jsonify({
        "aps": aps, "qualified": qualified, "almost": almost, "others": others,
        "counts": {"qualified": len(qualified), "almost": len(almost), "total": len(progs)}
    })


# ══════════════════════════════════════════════════════════════════════════════
#  EXAM ROUTE
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/exam", methods=["POST"])
def exam_lookup():
    """
    Search for exam(s) by module code or name.
    Body: { "query": "4MTH271" }  or  { "query": "Advanced Calculus" }
    """
    data  = request.get_json(force=True, silent=True) or {}
    query = (data.get("query") or "").strip()

    if not query:
        return jsonify({"found": False, "message": "Please provide a module code or name."})

    results = _search_exams(query)

    if not results:
        return jsonify({
            "found": False,
            "message": (
                f"😕 No exam found for **'{query}'**.\n\n"
                "Try:\n"
                "• The module code (e.g. `4MTH271`)\n"
                "• Part of the module name (e.g. `Calculus`)"
            )
        })

    formatted = [_format_exam(e) for e in results]
    return jsonify({
        "found": True,
        "count": len(results),
        "results": results,        # raw data
        "formatted": formatted,    # display-ready strings
    })


# ══════════════════════════════════════════════════════════════════════════════
#  MODULE GUIDE ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/registration_topics", methods=["GET"])
def registration_topics():
    """List available registration/admissions topics for the frontend."""
    return jsonify(list_registration_topics())


@app.route("/modules", methods=["GET"])
def modules_list():
    """List all available module guides."""
    return jsonify(list_all_modules())


@app.route("/module_qa", methods=["POST"])
def module_qa():
    """
    Answer a question about a specific module guide.

    Body: {
      "module": "4AAG211",     ← code or title fragment
      "question": "what are the outcomes",
      "language": "en"         ← "en" or "zu"
    }
    """
    data     = request.get_json(force=True, silent=True) or {}
    module_q = (data.get("module") or "").strip()
    question = (data.get("question") or "general").strip()
    language = (data.get("language") or "en").strip().lower()

    if not module_q:
        return jsonify({
            "found": False,
            "answer": "Please provide a module code or name.",
            "suggestions": ["outcomes", "assessment", "lecturer", "readings"]
        })

    found, answer, code = get_module_answer(module_q, question, language)
    return jsonify({
        "found":  found,
        "answer": answer,
        "module_code": code,
        "suggestions": [
            "What are the learning outcomes?",
            "Who is the lecturer?",
            "When are consultation times?",
            "What is the assessment?",
            "What books do I need?"
        ] if found else []
    })


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _format_programme_info(prog):
    subj_lines = "\n".join(
        f"  • {s['name']}: Level {s['min_level']} (≈{s['min_pct']}%)"
        for s in prog.get("subjects", [])
    ) or "  • See faculty handbook"
    aps_str     = "Contact faculty" if prog.get("aps_unknown") else str(prog["aps"])
    streams_blk = ("\n\n🧭 **Streams:**\n" + "\n".join(f"  • {s}" for s in prog["streams"])) if prog.get("streams") else ""
    sel_blk     = "\n\n⚠️ Selection test / interview / audition required." if prog.get("selection_test") else ""
    return (
        f"🎓 **{prog['programme']}**\n"
        f"🏛️ {prog['faculty']}\n"
        f"📋 Code: {prog['code']} | {prog['qualification']}\n"
        f"⏳ {prog['duration']} year{'s' if prog['duration']>1 else ''} | NQF {prog['nqf']}\n"
        f"📊 Minimum APS: {aps_str}\n\n"
        f"📚 **Subject Requirements:**\n{subj_lines}"
        f"{streams_blk}{sel_blk}\n\n"
        f"📌 Visit [link:https://www.unizulu.ac.za|UniZulu Admissions] for official applications."
    )


def _find_programme_in_message(msg):
    for m in re.finditer(r"\b([0-9A-Za-z][0-9A-Za-z\-]{3,20})\b", msg):
        token = m.group(1).lower()
        if token in _BY_CODE: return _BY_CODE[token]
        if token in _BY_ID:   return _BY_ID[token]
    if any(kw in msg.lower() for kw in ["programme","program","course","degree","diploma",
                                          "bachelor","tell me about","more about","b ed","bsc","ba "]):
        best, score = process.extractOne(msg, _PROG_NAMES) if _PROG_NAMES else (None, 0)
        if best and score >= 75:
            return _NAME_TO_PROG[best]
    return None


def get_sql_response(msg):
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT keyword, intro, response, suggestions FROM responses")
        rows   = cursor.fetchall()
        cursor.close(); conn.close()
    except Exception as e:
        print(f"⚠️ DB error: {e}")
        return None, None

    msg_l = msg.lower()
    for keyword, intro, response, suggestions in rows:
        if keyword.lower() in msg_l:
            reply = f"{intro}\n\n{response}" if intro else response
            sugg  = [s.strip() for s in (suggestions or "").split(",") if s.strip()]
            return reply, sugg

    keywords = [row[0] for row in rows]
    if keywords:
        best, score = process.extractOne(msg, keywords)
        if score >= 70:
            for keyword, intro, response, suggestions in rows:
                if keyword == best:
                    reply = f"{intro}\n\n{response}" if intro else response
                    sugg  = [s.strip() for s in (suggestions or "").split(",") if s.strip()]
                    return reply, sugg
    return None, None


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/get_response", methods=["POST"])
def get_response():
    data  = request.get_json(force=True, silent=True) or {}
    msg   = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"reply": "🤔 I didn't catch that — could you rephrase?", "suggestions": []})

    msg_l = msg.lower()

    # 1a — Exam queries
    if _is_exam_query(msg_l):
        exam_q = re.sub(
            r"\b(exam|timetable|time table|when is|when does|my|the|for|i have|"
            r"i am writing|i write|what time|what room|where is)\b",
            " ", msg_l, flags=re.I
        ).strip()
        exam_q = re.sub(r"\s+", " ", exam_q).strip()
        if exam_q:
            results = _search_exams(exam_q)
            if results:
                parts = [_format_exam(e) for e in results]
                reply = "\n\n---\n\n".join(parts)
                if len(results) > 1:
                    reply = f"📚 Found **{len(results)} exam session(s)**:\n\n" + reply
                return jsonify({"reply": reply, "suggestions": ["Check another exam", "registration", "contact support"]})
            else:
                return jsonify({
                    "reply": (f"😕 No exam found for **\'{exam_q}\'**.\n\n"
                              "Try:\n• The module code (e.g. `4MTH271`)\n• Part of the module name"),
                    "suggestions": ["Check another exam", "registration"]
                })

    # 1b — Module guide Q&A (code in message OR module-related keyword)
    module_kws = ["outcomes","lecturer","assessment","consultation","readings",
                  "textbook","study guide","credits","nqf","prerequisites",
                  "who teaches","module guide","notional","contact email"]
    code_m = re.search(r"\b([0-9][A-Za-z]{2,4}[0-9]{2,3})\b", msg)
    has_mod_kw = any(k in msg_l for k in module_kws)

    if code_m or has_mod_kw:
        mod_q    = code_m.group(1).upper() if code_m else msg
        lang_mod = "zu" if any(w in msg_l for w in ["ngifuna","chaza","yini","uthisha","imiphumela","izincwadi"]) else "en"
        found, answer, mcode = get_module_answer(mod_q, msg, lang_mod)
        if found:
            return jsonify({
                "reply": answer,
                "suggestions": ["What is the assessment?", "Who is the lecturer?",
                                "When are consultation times?", "What books do I need?", "Check my exam"]
            })

    # 2 — Programme info ("Ask about this programme" button)
    prog = _find_programme_in_message(msg)
    if prog:
        return jsonify({
            "reply": _format_programme_info(prog),
            "suggestions": ["How do I apply?", "What documents do I need?", "Check my exam"]
        })

    # 3 — APS / finder nudge
    if any(k in msg_l for k in ["aps", "qualify", "which programme", "what can i study", "recommend"]):
        reply, suggestions = get_sql_response("aps")
        if reply:
            return jsonify({"reply": reply, "suggestions": suggestions})

    # 4 — Registration & Admissions knowledge base (rich PDF content)
    reg_found, reg_answer = get_registration_answer(msg)
    if reg_found:
        return jsonify({
            "reply": reg_answer,
            "suggestions": ["What documents do I need?", "Check my exam",
                            "registration", "contact support"]
        })

    # 5 — Registration & FAQ (SQL)
    reply, suggestions = get_sql_response(msg)
    if reply:
        return jsonify({"reply": reply, "suggestions": suggestions or []})

    # 6 — Fallback
    return jsonify({
        "reply": (
            "🤔 I\'m not sure about that, but I can help with:\n\n"
            "📝 Registration steps\n"
            "📊 APS & programme eligibility → **Programme Finder** tab\n"
            "📅 Exam timetable → type your module code or name\n"
            "📖 Module guides → use the **Modules** tab\n"
            "📂 Required documents\n"
            "📞 Support contacts"
        ),
        "suggestions": ["registration", "Check my exam", "aps", "contact support"]
    })


@app.route("/welcome")
def welcome():
    return jsonify({
        "reply": (
            "👋 **Welcome to the UniZulu Assistant!**\n\n"
            "I can help you with:\n"
            "📝 Registration steps & troubleshooting\n"
            "🎓 Programme eligibility → **Programme Finder** tab\n"
            "📅 Exam dates, times & venues\n"
            "📂 Required documents\n\n"
            "What would you like to know?"
        ),
        "suggestions": ["registration", "Check my exam", "How do I check my APS?", "documents needed"]
    })


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)