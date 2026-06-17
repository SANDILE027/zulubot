"""
db_init.py
==========
Initialises the MySQL database used by the chatbot for registration / FAQ
responses. Run this once (or whenever you edit the responses below):

    python db_init.py
"""

from db_config import get_db_connection


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # ── Drop old tables ─────────────────────────────────────────────────────
    cursor.execute("DROP TABLE IF EXISTS responses")
    cursor.execute("DROP TABLE IF EXISTS modules")

    # ── Create tables ───────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE responses (
            keyword VARCHAR(100) PRIMARY KEY,
            intro TEXT,
            response TEXT,
            suggestions TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE modules (
            code VARCHAR(20) PRIMARY KEY,
            name VARCHAR(255),
            faculty VARCHAR(255),
            description TEXT
        )
    """)

    # ── Responses ───────────────────────────────────────────────────────────
    responses = [
        ("registration",
         "Ohh, I see you have a problem with registration.",
         "📝 You can follow these steps:\n\n"
         "1️⃣ Go to [Registration Portal](https://jasper.unizulu.ac.za/pls/prodi41/w99pkg.mi_login)\n"
         "2️⃣ Log in with student number & PIN.\n"
         "3️⃣ Accept Rules & Regulations.\n"
         "4️⃣ Select subjects (compulsory + electives).\n"
         "5️⃣ Save & Continue.\n"
         "6️⃣ Accept Registration.\n"
         "7️⃣ Print Proof of Registration.\n\n"
         "📺 Tutorial 👇\n"
         "[youtube:https://www.youtube.com/embed/k4IRZ9NxwpQ]\n"
         "[link:https://reg.unizulu.ac.za/registration-steps/|Registration Steps]\n",
         "after registration, registration problems, modules, password reset"),

        ("after registration",
         "What happens after registration?",
         "🎉 Congrats, you're registered!\n\n"
         "📅 Check timetable in Student Enabler.\n"
         "🏠 Confirm accommodation.\n"
         "📘 Lectures start soon.\n"
         "👉 Orientation will guide you further.",
         "registration problems, contact support, programmes"),

        ("registration problems",
         "Common Registration Problems",
         "⚠️ Issues & solutions:\n\n"
         "🔹 System down → Wait & retry.\n"
         "🔹 Can't upload docs → Try another device, check network.\n"
         "🔹 Course full → Contact Faculty Admin.\n"
         "🔹 Login issues → Reset PIN or ICT support.\n"
         "🔹 NSFAS/Fees related issues → Visit Financial Aid.\n",
         "documents, password reset, contact support"),

        ("password reset",
         "Password reset help",
         "🔑 Forgot password?\n\n"
         "1️⃣ Go to Student Enabler login.\n"
         "2️⃣ Click *Forgot PIN*.\n"
         "3️⃣ Enter student number.\n"
         "4️⃣ Follow reset instructions via email.\n",
         "registration, student number, contact support"),

        ("documents",
         "Required Documents",
         "📂 For registration you'll need:\n"
         "- Certified ID\n"
         "- Matric certificate\n"
         "- Proof of residence\n"
         "- Proof of payment (if applicable)\n"
         "- Any other documents requested by your faculty",
         "registration, modules, password reset"),

        ("contact support",
         "UniZulu Support Contacts",
         "📞 Need more help?\n\n"
         "🏢 Student Enrolment Centre (SEC): walk-in or call the main switchboard.\n"
         "💻 ICT Helpdesk: for login / PIN issues.\n"
         "💰 Financial Aid Office: for NSFAS & fee queries.\n"
         "🌐 Or visit unizulu.ac.za for department contact details.",
         "registration, documents, programmes"),

        ("aps",
         "What is APS?",
         "📊 APS (Admission Point Score) is calculated from your top 6 NSC "
         "subjects (excluding Life Orientation, which is capped at 4 points).\n\n"
         "Each subject's achievement level (1–7) counts directly toward your "
         "total — Level 7 = 7 points, Level 1 = 1 point.\n\n"
         "👉 Use the **Programme Finder** tab to enter your subjects and see "
         "your APS plus which programmes you qualify for!",
         "programmes, registration"),

        ("programmes",
         "Programme Information",
         "🎓 UniZulu offers programmes across 4 faculties:\n\n"
         "📘 Education\n"
         "💼 Commerce, Administration & Law\n"
         "📚 Humanities & Social Sciences\n"
         "🔬 Science, Agriculture & Engineering\n\n"
         "👉 Switch to the **Programme Finder** tab, enter your matric "
         "subjects and levels, and I'll show you exactly which programmes "
         "you qualify for!",
         "aps, registration, documents"),
    ]

    cursor.executemany(
        "INSERT INTO responses (keyword, intro, response, suggestions) "
        "VALUES (%s, %s, %s, %s)",
        responses
    )

    # ── Modules (optional reference table — currently empty) ────────────────
    modules = [
        # ("3BFPT1", "B Ed in Foundation Phase Teaching", "Faculty of Education", "..."),
    ]
    if modules:
        cursor.executemany(
            "INSERT INTO modules (code, name, faculty, description) "
            "VALUES (%s, %s, %s, %s)",
            modules
        )

    conn.commit()
    conn.close()
    print("✅ Database initialized.")


if __name__ == "__main__":
    init_db()
