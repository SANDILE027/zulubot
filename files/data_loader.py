"""
data_loader.py  —  UniZulu Programme Normaliser
================================================
Reads the 4 real faculty JSON files and produces one unified list.

Unified shape per programme:
{
  "id":               str,
  "faculty":          str,
  "department":       str,
  "programme":        str,   # clean display name
  "code":             str,   # e.g. "3BFPT1"
  "qualification":    str,   # "Bachelor of Science", "Diploma", etc.
  "aps":              int,   # 0 if null (shown as "Contact faculty")
  "aps_unknown":      bool,  # True when original was null
  "duration":         int,
  "nqf":              int,
  "streams":          list[str],
  "subjects":         list[{"name":str, "min_level":int, "min_pct":int}],
  "selection_test":   bool,
  "access_programme": bool,  # True for 4FBS/4FSC extended access programmes
  "raw_admission_text": str,
}
"""

import json, os, re

UPLOADS = "/mnt/user-data/uploads"   # where the real files may live
CACHE   = os.path.join(os.path.dirname(__file__), "cache")

def _load(filename):
    # Try cache dir first (project data), fall back to uploads (dev convenience)
    for folder in (CACHE, UPLOADS):
        p = os.path.join(folder, filename)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return []

def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")

def _int(val, default=0):
    try: return int(val)
    except: return default

def _dur(val):
    try: return int(str(val).strip())
    except: return 3

# ── Subject name canonical map ────────────────────────────────────────────────
CANON = {
    "english":                          "English",
    "engl":                             "English",
    "isizulu":                          "IsiZulu",
    "mathematics":                      "Mathematics",
    "maths":                            "Mathematics",
    "mathematical literacy":            "Mathematical Literacy",
    "maths literacy":                   "Mathematical Literacy",
    "math lit":                         "Mathematical Literacy",
    "physical science":                 "Physical Science",
    "physical sciences":                "Physical Science",
    "life sciences":                    "Life Sciences",
    "geography":                        "Geography",
    "geog":                             "Geography",
    "history":                          "History",
    "hist":                             "History",
    "accounting":                       "Accounting",
    "economics":                        "Economics",
    "business studies":                 "Business Studies",
    "information technology":           "Information Technology",
    "visual arts":                      "Visual Arts",
    "dramatic arts":                    "Dramatic Arts",
    "tourism":                          "Tourism",
    "hospitality":                      "Hospitality Studies",
    "agricultural sciences":            "Agricultural Sciences",
    "computer applications technology": "Computer Applications Technology",
}

def _canon(name):
    """Canonicalise a subject name, preserving 'or' compounds."""
    parts = [p.strip() for p in str(name).split(" or ")]
    out = []
    for p in parts:
        k = p.lower().strip()
        out.append(CANON.get(k, p.title()))
    return " or ".join(out)

def _level_from_text(text, default=3):
    """Extract first NSC level digit from strings like 'Level 3 or SG level D'."""
    m = re.search(r"\blevel\s+(\d)\b", str(text), re.I)
    return int(m.group(1)) if m else default

def _english_level_from_admission(text):
    """
    Parse English requirement level from FCSS free-text admission strings.
    Returns (level, is_fal_or_hl_distinction) tuple.
    """
    t = str(text)
    # "achievement rating of 4 (50-59%) in English as a Home Language"
    # "achievement rating of 5 (60-69) in English as a First Additional Language"
    # "English HL 5"
    # "English level 4"
    m = re.search(r"English\s+(?:as\s+a?\s*(?:Home|First\s+Additional)\s+Language|HL|FAL)[^\d]*(\d)", t, re.I)
    if m:
        return int(m.group(1))
    # generic "rating of N ... English"
    m = re.search(r"rating\s+of\s+(\d)[^.]*English", t, re.I)
    if m:
        return int(m.group(1))
    # "English level N" or "English HL N"
    m = re.search(r"English\s+(?:HL|FAL|level)?\s*(\d)", t, re.I)
    if m:
        return int(m.group(1))
    return 4  # safe default for degree programmes


# ══════════════════════════════════════════════════════════════════════════════
#  LOADER: EDUCATION
# ══════════════════════════════════════════════════════════════════════════════
def _parse_edu_subjects(nsc_str):
    """
    Parse pipe-delimited NSC subject strings like:
      "NSC endorsement with: | | IsiZulu HL4 and | Engl FAL4 | Maths 3 or Maths Literacy 4"
    Returns list of {name, min_level, min_pct}.
    """
    subjects = []
    seen = set()
    parts = [p.strip() for p in nsc_str.split("|")]

    pat = re.compile(
        r"(IsiZulu|English|Engl|Maths Literacy|Math Lit|Mathematics|Maths|"
        r"Physical Science|Life Sciences|Geography|Geog|History|Hist)"
        r"[^|]*?(\d)",
        re.I
    )
    for part in parts:
        if re.search(r"endorsement|exemption|nsc|matric", part, re.I):
            continue
        m = pat.search(part)
        if not m:
            continue
        raw   = m.group(1)
        level = int(m.group(2))

        # Detect "or" alternative (e.g. "Maths 3 or Maths Literacy 4")
        if re.search(r"\bor\b", part, re.I):
            alts = re.findall(
                r"(Maths Literacy|Math Lit|Mathematics|Maths|Physical Science)\s+(\d)",
                part, re.I
            )
            if len(alts) >= 2:
                # "Mathematics X or Maths Literacy Y" → compound, use lower level
                name  = "Mathematics or Mathematical Literacy"
                level = min(int(a[1]) for a in alts)
                key   = name.lower()
                if key not in seen:
                    seen.add(key)
                    subjects.append({"name": name, "min_level": level, "min_pct": level*10})
                continue

        name = _canon(raw)
        key  = name.lower()
        if key not in seen:
            seen.add(key)
            subjects.append({"name": name, "min_level": level, "min_pct": level*10})

    return subjects

def load_education():
    rows = _load("education_output.json")
    out  = []
    for r in rows:
        subjects = _parse_edu_subjects(r.get("required_nsc_subjects",""))
        # Always ensure IsiZulu + English are listed first
        names = {s["name"].lower() for s in subjects}
        if not any("isizulu" in n for n in names):
            subjects.insert(0, {"name":"IsiZulu","min_level":4,"min_pct":40})
        if not any("english" in n for n in names):
            subjects.insert(1, {"name":"English","min_level":4,"min_pct":40})

        code = r.get("programme_code","")
        out.append({
            "id":               code,
            "faculty":          "Faculty of Education",
            "department":       "School of Education",
            "programme":        r.get("programme",""),
            "code":             code,
            "qualification":    "Bachelor of Education",
            "aps":              _int(r.get("aps"),26),
            "aps_unknown":      r.get("aps") is None,
            "duration":         4,
            "nqf":              7,
            "streams":          [],
            "subjects":         subjects,
            "selection_test":   str(r.get("selection_test","No")).strip().lower()=="yes",
            "access_programme": False,
            "raw_admission_text": r.get("required_nsc_subjects",""),
        })
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  LOADER: FCAL
# ══════════════════════════════════════════════════════════════════════════════
def _qual_nqf(qual):
    q = str(qual).lower()
    if "higher certificate" in q: return 5
    if "diploma"            in q: return 6
    return 7

def load_fcal():
    rows = _load("fcal_output.json")
    out  = []
    for r in rows:
        qual = r.get("qualification","")
        aps  = r.get("aps")
        # Skip entirely null/incomplete rows
        if not qual or (aps is None and r.get("english_requirement") is None):
            continue

        eng_lvl  = _level_from_text(r.get("english_requirement",""), 3)
        math_lvl = _level_from_text(r.get("maths_requirement",""),   3)

        subjects = [
            {"name":"English",                            "min_level":eng_lvl,  "min_pct":eng_lvl*10},
            {"name":"Mathematics or Mathematical Literacy","min_level":math_lvl,"min_pct":math_lvl*10},
        ]

        uid = "FCAL-" + _slug(qual)
        out.append({
            "id":               uid,
            "faculty":          "Faculty of Commerce, Administration & Law",
            "department":       "Commerce, Administration & Law",
            "programme":        qual,
            "code":             uid,
            "qualification":    _infer_qual(qual),
            "aps":              _int(aps, 0),
            "aps_unknown":      aps is None,
            "duration":         _dur(r.get("duration_years",3)),
            "nqf":              _qual_nqf(qual),
            "streams":          [],
            "subjects":         subjects,
            "selection_test":   False,
            "access_programme": False,
            "raw_admission_text":(
                f"English: {r.get('english_requirement','')}. "
                f"Mathematics: {r.get('maths_requirement','')}"
            ),
        })
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  LOADER: FCSS
# ══════════════════════════════════════════════════════════════════════════════
def _fcss_subjects(admission_text, degree):
    """
    Extract subject requirements from FCSS free-text admission strings.
    Returns list of {name, min_level, min_pct}.
    """
    t   = str(admission_text)
    out = []
    seen = set()

    def add(name, lvl):
        k = name.lower()
        if k not in seen:
            seen.add(k)
            out.append({"name":name,"min_level":lvl,"min_pct":lvl*10})

    eng_lvl = _english_level_from_admission(t)
    add("English", eng_lvl)

    # Geography-specific
    if re.search(r"geography", t, re.I) and "geography" not in str(degree).lower():
        m = re.search(r"geography[^)]*?(\d)", t, re.I)
        add("Geography", int(m.group(1)) if m else 4)

    # History-specific (e.g. Political Science entry)
    if re.search(r"history\s+level\s+(\d)", t, re.I):
        m = re.search(r"history\s+level\s+(\d)", t, re.I)
        add("History", int(m.group(1)))

    # Economics / Maths Literacy (Political Science entry)
    if re.search(r"economics or mathematical literacy", t, re.I):
        add("Economics or Mathematical Literacy", 4)

    # Visual Arts / Dramatic Arts (Drama entry)
    if re.search(r"visual arts|dramatic arts", t, re.I):
        add("Visual Arts or Dramatic Arts", 4)

    # Tourism degree-specific
    if "tourism" in str(degree).lower():
        add("Geography or Tourism", 4)

    return out

def _fcss_selection(admission_text):
    return bool(re.search(r"interview|audition|selection test|shortlist", str(admission_text), re.I))

def load_fcss():
    rows = _load("fcss_output.json")
    out  = []
    for r in rows:
        aps   = r.get("minimum_points")
        deg   = r.get("degree","")
        # Fix garbled degree name
        if deg.strip() == "Bachelor of Arts shall apply.":
            deg = "Diploma in Tourism Management"
        adm   = r.get("admission_requirements","")
        code  = r.get("unizulu_code", _slug(deg)[:8].upper())

        out.append({
            "id":               code,
            "faculty":          "Faculty of Humanities & Social Sciences",
            "department":       r.get("department","").split("(")[0].strip(),
            "programme":        deg,
            "code":             code,
            "qualification":    _infer_qual(deg),
            "aps":              _int(aps, 0),
            "aps_unknown":      aps is None,
            "duration":         _dur(r.get("duration_years",3)),
            "nqf":              _int(r.get("nqf_level"),7),
            "streams":          r.get("streams",[]),
            "subjects":         _fcss_subjects(adm, deg),
            "selection_test":   _fcss_selection(adm),
            "access_programme": False,
            "raw_admission_text": adm,
        })
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  LOADER: SCIENCE (output.json)
# ══════════════════════════════════════════════════════════════════════════════
_SUBJ_CLEAN = {
    "physical science or info": "Physical Science or Information Technology",
    "physical science or":      "Physical Science",   # truncated in data
    "physical sciences":        "Physical Science",
}

def _clean_science_subject(name):
    k = str(name).strip().lower()
    if k in _SUBJ_CLEAN:
        return _SUBJ_CLEAN[k]
    return _canon(name)

def _science_prog_name(row):
    """Build a clean programme name from science row."""
    prog_field = row.get("programme", "")
    qual = row.get("qualification", "Bachelor Of Science")
    # Strip code prefix (e.g. "4BSC01 ") and "FACULTY..." suffix
    raw = re.sub(r"^\w+\d+\w*\s+", "", prog_field)
    raw = re.sub(r"\s+FACULTY.*$", "", raw).strip()
    # Replace AND with &
    name = re.sub(r"\bAND\b", "&", raw).title()
    return f"{qual.title()} – {name}"

def load_science():
    rows = _load("output.json")
    out  = []
    seen_ids = set()

    for r in rows:
        prog_field = r.get("programme","")
        code_match = re.match(r"(\w+\d+\w*)", prog_field)
        code = code_match.group(1) if code_match else _slug(prog_field)[:8].upper()

        # Skip duplicate IDs (4FSC entries that duplicate 4FBS)
        if code in seen_ids:
            continue
        seen_ids.add(code)

        aps = r.get("aps_required")
        is_access = code.startswith("4FBS") or code.startswith("4FSC")

        adm = r.get("admission_requirements", [])
        subjects = []
        for req in adm:
            sname = _clean_science_subject(req.get("subject",""))
            if not sname:
                continue
            subjects.append({
                "name":      sname,
                "min_level": _int(req.get("level"),4),
                "min_pct":   _int(req.get("percentage"),40),
            })

        out.append({
            "id":               code,
            "faculty":          "Faculty of Science, Agriculture & Engineering",
            "department":       r.get("department","").strip(),
            "programme":        _science_prog_name(r),
            "code":             code,
            "qualification":    r.get("qualification","Bachelor Of Science").title(),
            "aps":              _int(aps, 0),
            "aps_unknown":      aps is None,
            "duration":         _dur(r.get("duration_years",3)),
            "nqf":              7,
            "streams":          [],
            "subjects":         subjects,
            "selection_test":   False,
            "access_programme": is_access,
            "raw_admission_text": "; ".join(
                f"{req.get('subject')}: {req.get('percentage')}% (L{req.get('level')})"
                for req in adm
            ),
        })
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _infer_qual(name):
    n = str(name).lower()
    if "higher certificate" in n:   return "Higher Certificate"
    if "diploma"            in n:   return "Diploma"
    if "bachelor of laws"   in n:   return "Bachelor of Laws"
    if "bachelor of social" in n:   return "Bachelor of Social Work"
    if "bachelor of library"in n:   return "Bachelor of Library & Information Science"
    if "bachelor of tourism"in n:   return "Bachelor of Tourism Studies"
    if "bachelor of arts"   in n:   return "Bachelor of Arts"
    if "bachelor of science"in n:   return "Bachelor of Science"
    if "bachelor of commerce"in n:  return "Bachelor of Commerce"
    if "bachelor of admin"  in n:   return "Bachelor of Administration"
    if "b ed"               in n:   return "Bachelor of Education"
    if "social science"     in n:   return "Bachelor of Social Science"
    return "Degree"


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════
def load_all_programmes():
    progs = []
    progs.extend(load_education())   #  3
    progs.extend(load_fcal())        # 12
    progs.extend(load_fcss())        # 15
    progs.extend(load_science())     # 72 (after dedup)

    # Global dedup by id
    seen, unique = set(), []
    for p in progs:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique.append(p)
    return unique


if __name__ == "__main__":
    progs = load_all_programmes()
    by_fac = {}
    for p in progs:
        by_fac.setdefault(p["faculty"],[]).append(p)
    print(f"\nTotal: {len(progs)} programmes\n")
    for fac, ps in by_fac.items():
        print(f"  {fac} ({len(ps)})")
        for p in ps[:3]:
            subj = ", ".join(f"{s['name']} L{s['min_level']}" for s in p["subjects"])
            aps_str = "?" if p["aps_unknown"] else str(p["aps"])
            acc = " [ACCESS]" if p.get("access_programme") else ""
            print(f"    [{p['code']:10s}] {p['programme'][:50]:50s}  APS:{aps_str:3s}{acc}")
        if len(ps) > 3:
            print(f"    ... and {len(ps)-3} more")
