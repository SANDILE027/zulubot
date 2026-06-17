import pdfplumber
import json
import os
import re

# ==========================
# ✅ PDF FILES (BOTH CAMPUS)
# ==========================
PDF_FILES = [
    os.path.join(os.path.dirname(__file__), "PDF_FILE", "rich_bay.pdf"),     # Richards Bay
    os.path.join(os.path.dirname(__file__), "PDF_FILE", "main_campus.pdf")    # Main Campus
]

# ==========================
# ✅ SMART CLEANING
# ==========================
def clean_text(value, field="generic"):

    if not value:
        return ""

    value = str(value)

    # -------------------------
    # ✅ SITE FIX
    # -------------------------
    if field == "site":
        val = value.upper()

        if "RICH" in val or "BAY" in val:
            return "RICHARDS BAY"

        if "MAIN" in val or "CAMPUS" in val:
            return "MAIN CAMPUS"

        return ""

    # -------------------------
    # ✅ DATE FIX
    # -------------------------
    if field == "date":
        match = re.search(r"20\d{2}/\d{2}/\d{2}", value)
        return match.group(0) if match else ""

    # -------------------------
    # ✅ TIME FIX
    # -------------------------
    if field == "time":
        match = re.search(r"\d{2}:\d{2}", value)
        return match.group(0) if match else ""

    # -------------------------
    # ✅ CODE FIX
    # -------------------------
    if field == "code":
        raw = value.replace(" ", "")
        match = re.search(r"[0-9A-Z]+_?P_?\d+_?\d+", raw)
        if match:
            code = match.group(0)

            # Force correct format: XXXXXX_P_1_15
            code = re.sub(r"(_?P_?)", "_P_", code)
            code = re.sub(r"_{2,}", "_", code)

            return code.upper()

        return raw

    # -------------------------
    # ✅ ROOM CODE FIX
    # -------------------------
    if field == "room":
        match = re.search(r"1900[_A-Z0-9\-]+", value)
        return match.group(0) if match else ""

    # -------------------------
    # ✅ NAME / GENERAL TEXT
    # -------------------------
    value = re.sub(r"[^A-Za-z0-9\s\-/()]", "", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


# ==========================
# ✅ DE-INTERLEAVING HELPERS
# ==========================
def de_interleave(s, target):
    if not s:
        return "", ""
    matched = []
    remaining = []
    t_idx = 0
    t_len = len(target)
    for char in s:
        if t_idx < t_len and char.upper() == target[t_idx].upper():
            matched.append(char)
            t_idx += 1
        else:
            remaining.append(char)
    if t_idx == t_len:
        return target, "".join(remaining)
    return "", s


def de_interleave_date(s):
    if not s:
        return "", ""
    # Try with year 2026 first (safest and avoids false matches like 2021)
    for year_pattern in [('2', '0', '2', '6'), ('2', '0', None, None)]:
        matched = []
        remaining = []
        state = 0
        for char in s:
            is_match = False
            if state == 0 and char == '2': is_match = True
            elif state == 1 and char == '0': is_match = True
            elif state == 2:
                if year_pattern[2] is not None:
                    is_match = (char == year_pattern[2])
                else:
                    is_match = char.isdigit()
            elif state == 3:
                if year_pattern[3] is not None:
                    is_match = (char == year_pattern[3])
                else:
                    is_match = char.isdigit()
            elif state == 4 and char == '/': is_match = True
            elif state == 5 and char.isdigit(): is_match = True
            elif state == 6 and char.isdigit(): is_match = True
            elif state == 7 and char == '/': is_match = True
            elif state == 8 and char.isdigit(): is_match = True
            elif state == 9 and char.isdigit(): is_match = True
            
            if is_match:
                matched.append(char)
                state += 1
            else:
                remaining.append(char)
                
        if state == 10:
            return "".join(matched), "".join(remaining)
    return "", s


def de_interleave_time(s):
    if not s:
        return "", ""
    matched = []
    remaining = []
    state = 0
    for char in s:
        is_match = False
        if state == 0 and char.isdigit(): is_match = True
        elif state == 1 and char.isdigit(): is_match = True
        elif state == 2 and char == ':': is_match = True
        elif state == 3 and char.isdigit(): is_match = True
        elif state == 4 and char.isdigit(): is_match = True
        
        if is_match:
            matched.append(char)
            state += 1
        else:
            remaining.append(char)
            
    if state == 5:
        return "".join(matched), "".join(remaining)
    return "", s


# ==========================
# ✅ EXTRACT TABLE
# ==========================
def extract_from_pdf(pdf_file):

    exams = []
    expected_site = "RICHARDS BAY" if "rich_bay" in pdf_file.lower() else "MAIN CAMPUS"

    with pdfplumber.open(pdf_file) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables()

            for table in tables:

                if not table or len(table) < 2:
                    continue

                for row in table[1:]:

                    if not row or len(row) < 9:
                        continue

                    try:
                        _, site_rem = de_interleave(str(row[2] or ""), expected_site)
                        date_matched, date_rem = de_interleave_date(str(row[3] or ""))
                        time_matched, time_rem = de_interleave_time(str(row[4] or ""))
                        
                        # De-interleave "CAMPUS" noise from date and time remaining strings
                        _, date_rem_clean = de_interleave(date_rem, "CAMPUS")
                        _, time_rem_clean = de_interleave(time_rem, "CAMPUS")
                        
                        raw_name = str(row[1] or "")
                        full_exam_name = raw_name + " " + site_rem + " " + date_rem_clean + " " + time_rem_clean
                        full_exam_name = re.sub(r"\b(CAMPUS|MAIN|RICHARDS|BAY)\b", " ", full_exam_name, flags=re.IGNORECASE)
                        full_exam_name = re.sub(r"[^A-Za-z0-9\s\-/()]", "", full_exam_name)
                        full_exam_name = re.sub(r"\s+", " ", full_exam_name).strip()
                        
                        final_date = date_matched if date_matched else "2026/05/25"
                        final_time = time_matched if time_matched else "08:00"

                        exam = {
                            "exam_code": clean_text(row[0], "code"),
                            "exam_name": full_exam_name,
                            "site": expected_site,
                            "date": final_date,
                            "start_time": final_time,
                            "duration": int(re.sub(r"\D", "", str(row[5])) or 0),
                            "candidates": int(re.sub(r"\D", "", str(row[6])) or 0),
                            "room_code": clean_text(row[7], "room"),
                            "room_name": clean_text(row[8])
                        }

                        # ✅ REMOVE BAD ROWS
                        if len(exam["exam_name"]) < 5:
                            continue

                        exams.append(exam)

                    except Exception as e:
                        print("⚠️ Skipped row:", row, "due to", e)

    return exams


# ==========================
# ✅ REMOVE DUPLICATES
# ==========================
def remove_duplicates(exams):

    unique = {}

    for e in exams:
        key = (e["exam_code"], e["date"], e["start_time"])
        unique[key] = e

    return list(unique.values())


# ==========================
# ✅ MAIN
# ==========================
def main():

    all_exams = []

    print("📄 Processing PDFs...")

    for pdf in PDF_FILES:

        if not os.path.exists(pdf):
            print(f"❌ Missing: {pdf}")
            continue

        print(f"📘 {os.path.basename(pdf)}")

        data = extract_from_pdf(pdf)
        print(f"   ✅ Extracted: {len(data)}")

        all_exams.extend(data)

    print(f"\n🔍 Total before cleaning: {len(all_exams)}")

    all_exams = remove_duplicates(all_exams)

    print(f"✅ After cleaning: {len(all_exams)}")

    # SAVE JSON
    with open("exam_timetable.json", "w", encoding="utf-8") as f:
        json.dump(all_exams, f, indent=4)

    print("✅ Saved to exam_timetable.json ✅")


# ==========================
if __name__ == "__main__":
    main()