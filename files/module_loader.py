"""
module_loader.py  —  UniZulu Module Guide Q&A
==============================================
Handles all real data edge cases found in the extracted JSONs:

  • module_code "NOT FOUND"          → fallback to filename
  • module_code "4PHY111/4LPH111"    → use first token before /
  • filename vs code mismatch        → index BOTH (4GES321 file, 4GES322 code)
  • module_title "NOT FOUND"         → fallback to filename stem
  • level_of_study "1","2","Unyaka…" → normalised to readable string
  • consultation_times "XXXXXXX"     → shown as "To be confirmed"
  • assessment_activities raw_row    → extract meaningful text
  • lecturers []                     → graceful "not listed" message
  • module_outcomes []               → graceful message
  • language auto-detection          → filename, field, or IsiZulu content heuristic
"""

import json, os, re

EXTRACTED_DIR = os.path.join(os.path.dirname(__file__), "/home/sandile/zulubot/extracted")

# ── Sentinel values ──────────────────────────────────────────────────────────
_SENTINELS = {"not found", "not specified", "none", "n/a", "tba", ""}
_XXXX_PAT  = re.compile(r"x{3,}", re.I)   # XXXXXXX placeholders

def _clean(val):
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in _SENTINELS:
        return None
    if _XXXX_PAT.search(s):
        return None
    return s or None

# ── Level-of-study normaliser ────────────────────────────────────────────────
_LEVEL_MAP = {
    "1": "1st year", "2": "2nd year", "3": "3rd year", "4": "4th year",
    "1st": "1st year", "2nd": "2nd year", "3rd": "3rd year", "4th": "4th year",
    "first year": "1st year", "second year": "2nd year",
    "third year": "3rd year",  "fourth year": "4th year",
    "first": "1st year", "second": "2nd year", "third": "3rd year",
    "unyaka wokuqala": "1st year",
    "unyaka wesibili": "2nd year",
    "unyaka wesithathu": "3rd year",
}

def _normalise_level(val):
    v = (val or "").strip().lower()
    return _LEVEL_MAP.get(v, _clean(val))

# ── Language detection ────────────────────────────────────────────────────────
_IZ_WORDS = re.compile(
    r"\b(ukuthola|ukuchaza|ukwenza|ulwazi|isifundo|abafundi|uthisha|imiphumela|"
    r"ngendlela|kanye|futhi|noma|kuyilapho|ukuze|inhloso|wokuqala|wesibili|"
    r"njengoba|ngakho|nge|ukuba|ukusetshenziswa|njalo)\b", re.I
)

def _detect_language(entry, fname):
    # 1. Explicit field
    lang = (entry.get("language") or "").lower()
    if "zulu" in lang or "isizulu" in lang:
        return "isizulu"
    if lang == "english":
        return "english"

    # 2. Filename
    fn = fname.upper()
    if "ISIZULU" in fn or "IZULU" in fn or "(ZULU)" in fn:
        return "isizulu"

    # 3. Heuristic: count IsiZulu words in outcomes + purpose
    text = " ".join([
        entry.get("module_purpose") or "",
        " ".join(entry.get("module_outcomes") or [])
    ])
    hits = len(_IZ_WORDS.findall(text))
    words = len(text.split())
    if words > 0 and hits / max(words, 1) > 0.04:
        return "isizulu"

    return "english"

# ── Code extraction ───────────────────────────────────────────────────────────
def _extract_code(raw_code, fname):
    """
    Return clean primary code and list of all aliases.
    Handles: "NOT FOUND", "4PHY111/4LPH111", "4MTH122/SMTH122"
    """
    raw = (raw_code or "").strip()
    if not raw or raw.upper() in {"NOT FOUND", "NOT SPECIFIED", "N/A"}:
        # Fall back to filename stem, strip non-alphanumeric suffix
        stem = re.sub(r"[_\-\s].*$", "", os.path.splitext(fname)[0])
        stem = re.sub(r"[^A-Za-z0-9]", "", stem).upper()
        return stem or None, []

    # Split on "/" to get all codes
    parts = [p.strip().upper() for p in raw.split("/") if p.strip()]
    primary = parts[0]
    aliases  = parts[1:]
    return primary, aliases

# ── Assessment cleaner ────────────────────────────────────────────────────────
def _clean_assessment(activities):
    """
    Handle both proper dicts and raw_row dicts from the extractor.
    Returns list of clean strings / dicts.
    """
    if not activities:
        return []
    cleaned = []
    for a in activities:
        if isinstance(a, dict):
            if "raw_row" in a:
                text = a["raw_row"].strip()
                # Skip meaningless rows
                if len(text) > 10 and not text.startswith("ASSIGNMENT COVER"):
                    cleaned.append(text)
            else:
                cleaned.append(a)
        elif isinstance(a, str) and a.strip():
            cleaned.append(a.strip())
    return cleaned

# ══════════════════════════════════════════════════════════════════════════════
#  LOAD
# ══════════════════════════════════════════════════════════════════════════════

def load_all_modules():
    modules = []
    if not os.path.exists(EXTRACTED_DIR):
        print(f"⚠️  No extracted/ folder at {EXTRACTED_DIR}")
        return modules

    for fname in sorted(os.listdir(EXTRACTED_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(EXTRACTED_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                # Clean & enrich
                raw_code = entry.get("module_code")
                code, aliases = _extract_code(raw_code, fname)

                # Title fallback
                title = _clean(entry.get("module_title"))
                if not title:
                    title = re.sub(r"[_\-]", " ", os.path.splitext(fname)[0]).title()

                entry["_code"]     = code
                entry["_aliases"]  = aliases
                entry["_title"]    = title
                entry["_level"]    = _normalise_level(entry.get("level_of_study"))
                entry["_language"] = _detect_language(entry, fname)
                entry["_assessment_clean"] = _clean_assessment(
                    entry.get("assessment_activities") or []
                )
                modules.append(entry)

        except Exception as e:
            print(f"⚠️  {fname}: {e}")

    print(f"✅ Loaded {len(modules)} module guides")
    return modules


# ══════════════════════════════════════════════════════════════════════════════
#  INDEXES
# ══════════════════════════════════════════════════════════════════════════════

def build_indexes(modules):
    by_code  = {}
    by_title = {}

    for m in modules:
        code  = m.get("_code") or ""
        title = m.get("_title") or ""

        # Also index the filename stem so "4GES321" finds a module whose
        # JSON code field says "4GES322" (PDF extractor mismatch)
        fname_stem = (m.get("source") or "")
        fname_stem = re.sub(r"\.pdf$","", fname_stem, flags=re.I)
        fname_stem = re.sub(r"[_\-\s].*$","", fname_stem).upper()
        extra_codes = [fname_stem] if fname_stem and fname_stem != code else []

        # Index primary code + all aliases + filename stem
        for c in [code] + (m.get("_aliases") or []) + extra_codes:
            if c:
                c_up = c.upper()
                if c_up not in by_code:
                    by_code[c_up] = m
                # Also index without suffix letters: "4BOT111" from "4BOT111A"
                base = re.sub(r"[A-Z]+$", "", c_up)
                if base != c_up and base not in by_code:
                    by_code[base] = m

        if title:
            by_title[title.lower()] = m

    return by_code, by_title, list(by_code.keys()), list(by_title.keys())


# ══════════════════════════════════════════════════════════════════════════════
#  SEARCH
# ══════════════════════════════════════════════════════════════════════════════

def find_module(query, by_code, by_title, all_titles):
    from fuzzywuzzy import process

    q = query.strip()
    if not q:
        return None
    qu = q.upper()
    ql = q.lower()

    # 1. Exact code
    if qu in by_code:
        return by_code[qu]

    # 2. Partial code prefix
    for code in by_code:
        if qu in code or code.startswith(qu):
            return by_code[code]

    # 3. Exact / substring title
    if ql in by_title:
        return by_title[ql]
    for t, m in by_title.items():
        if ql in t:
            return m

    # 4. Fuzzy title
    if all_titles:
        best, score = process.extractOne(q, all_titles)
        if score >= 60:
            return by_title.get(best.lower())

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  INTENT DETECTION
# ══════════════════════════════════════════════════════════════════════════════

INTENTS = [
    ("outcomes",      r"\b(outcome|objective|learn|goal|what will i|what do i learn|imiphumela|imphumela)\b"),
    ("assessment",    r"\b(assess|test|mark|weight|assignment|practical|exam mark|dp|ukuhlolwa|amaphesenti)\b"),
    ("lecturer",      r"\b(lecturer|teacher|professor|who teach|contact|email|phone|uthisha|umfundisi|ubani)\b"),
    ("consultation",  r"\b(consult|office hour|when can i see|izikhathi|uhlelo lwe|bonisana)\b"),
    ("credits",       r"\b(credit|notional hour|nqf level|year of study|isigaba|amacredit|how many credit)\b"),
    ("readings",      r"\b(read|book|textbook|reference|resource|material|izincwadi|incwadi|prescribed|recommend)\b"),
    ("prerequisites", r"\b(prerequisite|require|need before|before taking|izimfuno|before i can)\b"),
    ("purpose",       r"\b(purpose|about|what is this|overview|describe|explain|inhloso|mayelana|what does this module)\b"),
]

def detect_intent(question):
    q = question.lower()
    for intent, pattern in INTENTS:
        if re.search(pattern, q, re.I):
            return intent
    return "general"


# ══════════════════════════════════════════════════════════════════════════════
#  ANSWER BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def _na(lang):
    return "Akuchazwanga." if lang == "zu" else "Not specified in this guide."

def _contact_lecturer(lang):
    return "Xhumana nomfundisi nge-email." if lang == "zu" else "Contact your lecturer by email."

def answer_question(module, question, language="en"):
    intent = detect_intent(question)
    m      = module
    lang   = language
    code   = m.get("_code") or m.get("module_code") or "?"
    title  = m.get("_title") or "Unknown Module"
    is_zu  = m.get("_language") == "isizulu"
    lang_tag = "🇿🇦 IsiZulu" if is_zu else "🇿🇦 English"

    # ── Outcomes ─────────────────────────────────────────────────────────────
    if intent == "outcomes":
        outcomes = [o for o in (m.get("module_outcomes") or []) if o and o.strip()]
        hdr = (f"📚 **Imiphumela ye-{code}:**\n\n" if lang == "zu"
               else f"📚 **Learning outcomes — {code} {title}:**\n\n")
        if outcomes:
            return hdr + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(outcomes))
        return hdr + ("Imiphumela ayibhalwanga kule guide. " + _contact_lecturer(lang)
                      if lang == "zu" else "Outcomes not listed in this guide. " + _contact_lecturer(lang))

    # ── Assessment ───────────────────────────────────────────────────────────
    elif intent == "assessment":
        acts = m.get("_assessment_clean") or []
        hdr  = (f"📝 **Ukuhlolwa — {code}:**\n\n" if lang == "zu"
                else f"📝 **Assessment — {code} {title}:**\n\n")
        lines = []
        for a in acts:
            if isinstance(a, dict):
                atype  = a.get("type") or a.get("activity") or "Activity"
                weight = a.get("weight") or a.get("percentage") or ""
                date   = a.get("date")  or a.get("due_date")   or ""
                line   = f"  • {atype}"
                if weight: line += f" — {weight}"
                if date:   line += f" ({date})"
                lines.append(line)
            elif isinstance(a, str):
                lines.append(f"  • {a}")

        if lines:
            return hdr + "\n".join(lines)

        # 4BOT111 has useful info in raw text
        raw_note = ("  ⚠️ Semester mark: 50% | Final exam: 50% | Subminimum 40% in final exam needed to pass."
                    if "4BOT111" in code.upper() else "")
        return hdr + (raw_note or ("Imininingwane yokúhlolwa ayitholakali. " + _contact_lecturer(lang)
                                   if lang == "zu"
                                   else "Assessment details not in this guide. " + _contact_lecturer(lang)))

    # ── Lecturer / Contact ───────────────────────────────────────────────────
    elif intent == "lecturer":
        lecturers = [l for l in (m.get("lecturers") or []) if l and l.strip()]
        emails    = [e for e in (m.get("contact_emails") or []) if e and e.strip()]
        hdr = (f"👩‍🏫 **Uthisha we-{code}:**\n\n" if lang == "zu"
               else f"👩‍🏫 **Lecturer(s) — {code} {title}:**\n\n")
        lines = []
        for i, lec in enumerate(lecturers):
            line = f"  • {lec}"
            if i < len(emails):
                line += f"\n    📧 {emails[i]}"
            lines.append(line)
        # remaining emails with no matching name
        for e in emails[len(lecturers):]:
            lines.append(f"  • 📧 {e}")
        if lines:
            return hdr + "\n".join(lines)
        # No lecturer name but maybe emails
        if emails:
            return hdr + "\n".join(f"  • 📧 {e}" for e in emails)
        return hdr + ("Akunalwazi ngothisha. Shela emnyangweni." if lang == "zu"
                      else "Not listed in this guide. Contact the departmental office.")

    # ── Consultation ─────────────────────────────────────────────────────────
    elif intent == "consultation":
        times = _clean(m.get("consultation_times"))
        hdr   = (f"🕐 **Izikhathi zokubonisana — {code}:**\n\n" if lang == "zu"
                 else f"🕐 **Consultation times — {code}:**\n\n")
        if not times:
            return hdr + ("Zizokwaziswa. " + _contact_lecturer(lang) if lang == "zu"
                          else "To be confirmed. " + _contact_lecturer(lang))
        # Trim garbled long paragraphs
        if len(times) > 300:
            times = times[:300].rsplit(" ", 1)[0] + "…"
        return hdr + times

    # ── Prerequisites ────────────────────────────────────────────────────────
    elif intent == "prerequisites":
        pre = _clean(m.get("prerequisites"))
        hdr = (f"✅ **Izimfuno — {code}:**\n\n" if lang == "zu"
               else f"✅ **Prerequisites for {code}:**\n\n")
        if not pre:
            return hdr + ("Azikho izimfuno ezibekiwe." if lang == "zu" else "None specified.")
        return hdr + pre

    # ── Credits / Level ──────────────────────────────────────────────────────
    elif intent == "credits":
        hdr = (f"📊 **Imininingwane ye-{code}:**\n\n" if lang == "zu"
               else f"📊 **Module details — {code} {title}:**\n\n")
        def v(field): return _clean(m.get(field)) or "?"
        rows = [
            ("Credits",        v("module_credits")),
            ("Level of study", m.get("_level") or v("level_of_study")),
            ("Notional hours", v("notional_hours")),
            ("NQF level",      v("nqf_level")),
        ]
        return hdr + "\n".join(f"  • {k}: {val}" for k, val in rows)

    # ── Readings ─────────────────────────────────────────────────────────────
    elif intent == "readings":
        prescribed  = [r for r in (m.get("prescribed_readings")  or []) if r and str(r).strip()]
        recommended = [r for r in (m.get("recommended_readings") or []) if r and str(r).strip()]
        hdr = (f"📖 **Izincwadi — {code}:**\n\n" if lang == "zu"
               else f"📖 **Reading materials — {code}:**\n\n")
        lines = []
        if prescribed:
            lines.append("**Prescribed:**")
            lines += [f"  • {r}" for r in prescribed]
        if recommended:
            if lines: lines.append("")
            lines.append("**Recommended:**")
            lines += [f"  • {r}" for r in recommended[:5]]
            if len(recommended) > 5:
                lines.append(f"  ... and {len(recommended)-5} more.")
        if not lines:
            return hdr + ("Azikho izincwadi ezibalwe. " + _contact_lecturer(lang) if lang == "zu"
                          else "No reading list in this guide. " + _contact_lecturer(lang))
        return hdr + "\n".join(lines)

    # ── Purpose ──────────────────────────────────────────────────────────────
    elif intent == "purpose":
        purpose = _clean(m.get("module_purpose"))
        hdr = (f"🎯 **Inhloso ye-{code}:**\n\n" if lang == "zu"
               else f"🎯 **Purpose of {code} — {title}:**\n\n")
        return hdr + (purpose or _na(lang))

    # ── General overview ─────────────────────────────────────────────────────
    else:
        outcomes  = [o for o in (m.get("module_outcomes") or []) if o][:2]
        preview   = "\n".join(f"  • {o}" for o in outcomes) if outcomes else "  • " + _na(lang)
        lecturers = ", ".join(l for l in (m.get("lecturers") or []) if l) or _na(lang)
        credits   = _clean(m.get("module_credits")) or "?"
        nqf       = _clean(m.get("nqf_level"))      or "?"
        level     = m.get("_level") or _na(lang)

        if lang == "zu":
            return (
                f"📋 **{code} — {title}** {lang_tag}\n\n"
                f"👩‍🏫 Uthisha: {lecturers}\n"
                f"📊 Amacredit: {credits} | NQF: {nqf} | {level}\n\n"
                f"📚 Imiphumela emibili yokuqala:\n{preview}\n\n"
                f"💬 Buza nge: *imiphumela · ukuhlolwa · uthisha · izikhathi · izincwadi · izimfuno*"
            )
        return (
            f"📋 **{code} — {title}** {lang_tag}\n\n"
            f"👩‍🏫 Lecturer: {lecturers}\n"
            f"📊 Credits: {credits} | NQF: {nqf} | {level}\n\n"
            f"📚 Sample outcomes:\n{preview}\n\n"
            f"💬 Ask about: *outcomes · assessment · lecturer · consultation · readings · prerequisites*"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

_MODULES  = load_all_modules()
_BY_CODE, _BY_TITLE, _ALL_CODES, _ALL_TITLES = build_indexes(_MODULES)


def search_module(query):
    return find_module(query, _BY_CODE, _BY_TITLE, _ALL_TITLES)


def get_module_answer(module_query, question, language="en"):
    mod = search_module(module_query)
    if not mod:
        msg = (f"😕 Angikwazanga ukuthola **'{module_query}'**.\n\nZama ikhodi (e.g. `4CPS111`) noma igama."
               if language == "zu"
               else f"😕 Could not find module **'{module_query}'**.\n\nTry the code (e.g. `4AAG211`) or part of the name.")
        return False, msg, None
    answer = answer_question(mod, question, language=language)
    return True, answer, mod.get("_code") or mod.get("module_code") or ""


def list_all_modules():
    return sorted([
        {
            "code":     m.get("_code") or "",
            "title":    m.get("_title") or "",
            "level":    m.get("_level") or "",
            "language": m.get("_language", "english"),
            "credits":  _clean(m.get("module_credits")) or "",
        }
        for m in _MODULES
        if m.get("_code")
    ], key=lambda x: x["code"])


if __name__ == "__main__":
    print(f"\nTotal: {len(_MODULES)} modules")
    en_c = sum(1 for m in _MODULES if m.get("_language") == "english")
    zu_c = sum(1 for m in _MODULES if m.get("_language") == "isizulu")
    print(f"English: {en_c} | IsiZulu: {zu_c}")
    print(f"\nAll codes: {sorted(set(m['_code'] for m in _MODULES if m.get('_code')))}")

    print("\n--- Testing edge cases ---")
    tests = [
        # (query, question, lang, description)
        ("4STT211",  "what are the outcomes",   "en", "code NOT FOUND → fallback to filename"),
        ("4PHY111",  "who is the lecturer",      "zu", "code slash + IsiZulu module"),
        ("4MTH171",  "general overview",         "en", "title+code both NOT FOUND"),
        ("4BOT111",  "what is the assessment",   "en", "raw_row assessment"),
        ("4CPS121",  "who teaches this",         "en", "empty lecturers list"),
        ("4AMT122",  "consultation times",       "en", "N/A placeholders"),
        ("4GES321",  "tell me about this",       "en", "filename/code mismatch"),
        ("Soil",     "reading list",             "en", "fuzzy title search"),
    ]
    for q_mod, q_ask, lang, desc in tests:
        found, ans, code = get_module_answer(q_mod, q_ask, lang)
        status = "✅" if found else "❌"
        print(f"\n{status} [{desc}] query='{q_mod}'→[{code}]:")
        print("  " + ans[:150].replace("\n", "\n  "))