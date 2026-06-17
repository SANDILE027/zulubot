"""
registration_kb.py  —  Registration & Admissions Knowledge Base
=================================================================
Loads registration_info.json (extracted from the registration PDF) and
answers natural-language student questions by scoring keyword overlap
against each content block's section title, query text, and items.

Structure handled:
[
  {
    "topic": str,
    "keywords": [str, ...],
    "content": [
      { "section": str, "items": [str,...], "note": str },
      { "section": str, "query": str, "solutions": [str,...] },
      { "section": str, "items": [...], "notes": [...], "contact": str },
      ...
    ]
  },
  ...
]
"""

import json
import os
import re

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
INFO_FILE = os.path.join(CACHE_DIR, "registration_info.json")


# ══════════════════════════════════════════════════════════════════════════════
#  LOAD
# ══════════════════════════════════════════════════════════════════════════════

def load_registration_info():
    if not os.path.exists(INFO_FILE):
        print(f"⚠️  registration_info.json not found at {INFO_FILE}")
        return []
    with open(INFO_FILE, encoding="utf-8") as f:
        data = json.load(f)
    print(f"✅ Loaded {len(data)} registration topics")
    return data


# ══════════════════════════════════════════════════════════════════════════════
#  FORMAT ANSWERS
# ══════════════════════════════════════════════════════════════════════════════

def _format_block(block):
    """Format a single content block (section) into readable text."""
    lines = []
    section = block.get("section")
    if section:
        lines.append(f"**{section}**")

    if "query" in block:
        solutions = block.get("solutions", [])
        if solutions:
            lines.append("")
            lines.extend(f"  • {s}" for s in solutions)

    if "items" in block:
        items = block.get("items", [])
        if items:
            lines.append("")
            lines.extend(f"  • {item}" for item in items)

    if "note" in block:
        lines.append("")
        lines.append(f"⚠️ {block['note']}")

    if "notes" in block:
        notes = block.get("notes", [])
        if notes:
            lines.append("")
            lines.extend(f"📌 {n}" for n in notes)

    if "contact" in block:
        lines.append("")
        lines.append(f"📞 Contact: {block['contact']}")

    return "\n".join(lines)


def format_topic(topic_dict, section_filter=None):
    """Format a full topic, or just a specific section if section_filter is given."""
    topic_name = topic_dict.get("topic", "")
    blocks = topic_dict.get("content", [])

    if section_filter:
        matched = [b for b in blocks if b.get("section") == section_filter]
        if matched:
            blocks = matched

    if not blocks:
        return f"No information found for **{topic_name}**."

    formatted_blocks = [_format_block(b) for b in blocks]
    header = f"📋 **{topic_name}**\n\n"
    return header + "\n\n".join(formatted_blocks)


# ══════════════════════════════════════════════════════════════════════════════
#  SEARCH — keyword-overlap scoring (reliable, no fragile substring chains)
# ══════════════════════════════════════════════════════════════════════════════

_STOPWORDS = {
    "what", "where", "when", "how", "does", "this", "that", "with", "from",
    "have", "need", "want", "registration", "student", "about", "the", "for",
    "and", "are", "you", "your", "can", "will", "get", "got", "i", "a", "an",
    "is", "do", "to", "of", "in", "on", "or", "my", "me", "it", "am",
}


def _bigrams(text):
    """Extract adjacent word pairs, singularised, e.g. 'student card' from 'student cards'."""
    words = re.findall(r"\w+", text.lower())
    words = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words]
    return {f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)}


def _words(text):
    return set(re.findall(r"\w{3,}", text.lower())) - _STOPWORDS


def _score_block(q_text, q_words, block):
    """Score one content block against the question's keyword set."""
    section    = block.get("section", "") or ""
    query      = block.get("query", "") or ""
    items_text = " ".join(str(i) for i in block.get("items", []))

    section_words = _words(section)
    query_words    = _words(query)
    items_words    = _words(items_text)

    score = 0
    score += len(q_words & section_words) * 10   # section title = strongest signal
    score += len(q_words & query_words)    * 6    # structured Q&A blocks
    score += len(q_words & items_words)    * 2    # items text = weaker signal

    # Distinctive single-word boost: rare nouns like "passport", "visa" that
    # appear directly in items text deserve more weight than the generic x2.
    _DISTINCTIVE = {"passport", "visa", "permit", "asylum", "refugee", "saqa",
                     "embassy", "insurance", "orientation", "deposit", "card"}
    distinctive_hits = q_words & items_words & _DISTINCTIVE
    score += len(distinctive_hits) * 12

    # Bigram boost: catches phrases like "student card", "study permit"
    # where one word (e.g. "student") is normally stopworded out.
    q_bigrams = _bigrams(q_text)
    section_bigrams = _bigrams(section)
    items_bigrams   = _bigrams(items_text)
    score += len(q_bigrams & section_bigrams) * 20
    score += len(q_bigrams & items_bigrams) * 8

    return score


def search_registration_info(question, topics):
    """
    Score every content block in every topic against the question's keywords.
    Returns the formatted answer for the single best-scoring block/topic,
    or None if nothing scores high enough.
    """
    q = question.strip().lower()
    if not q:
        return None

    q_words = _words(q)
    if not q_words:
        return None

    best_score, best_topic, best_section = 0, None, None

    for t in topics:
        for block in t.get("content", []):
            score = _score_block(q, q_words, block)
            if score > best_score:
                best_score   = score
                best_topic   = t
                best_section = block.get("section")

    if best_topic and best_score >= 8:
        return format_topic(best_topic, section_filter=best_section)

    # ── Fallback: multi-word keyword phrase match at topic level ────────────
    for t in topics:
        for kw in t.get("keywords", []):
            kw_l = kw.lower()
            if len(kw_l.split()) >= 2 and kw_l in q:
                return format_topic(t)

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

_TOPICS = load_registration_info()


def get_registration_answer(question):
    """Returns (found: bool, answer: str)"""
    answer = search_registration_info(question, _TOPICS)
    if answer:
        return True, answer

    topic_list = "\n".join(f"  • {t['topic']}" for t in _TOPICS)
    msg = (
        f"😕 I couldn't find a specific answer for that.\n\n"
        f"I can help with:\n{topic_list}\n\n"
        f"Try rephrasing, or ask about one of these topics directly."
    )
    return False, msg


def list_topics():
    """Return topic names + their keywords for the frontend."""
    return [
        {"topic": t.get("topic", ""), "keywords": t.get("keywords", [])}
        for t in _TOPICS
    ]


def get_topic_by_name(topic_name):
    """Direct lookup — used when student clicks a topic from a list."""
    for t in _TOPICS:
        if t.get("topic", "").lower() == topic_name.lower():
            return format_topic(t)
    return None


if __name__ == "__main__":
    print(f"\nLoaded {len(_TOPICS)} topics:")
    for t in _TOPICS:
        print(f"  • {t['topic']} ({len(t.get('keywords',[]))} keywords)")

    print("\n--- Testing real student questions ---\n")
    test_questions = [
        "what documents do I need for registration",
        "my registration has been blocked for financial reasons",
        "I have a waiting for a decision status",
        "where do I get a student card",
        "when does orientation start",
        "I am an international student what do I need",
        "my biographical information is wrong",
        "some of my modules are not showing on my registration",
        "what is the registration schedule",
        "do I need a passport",
        "how do I apply for student housing",
        "completely unrelated nonsense question xyz123",
    ]

    for q in test_questions:
        found, ans = get_registration_answer(q)
        status = "✅" if found else "❌"
        print(f"{status} Q: {q}")
        print(f"   A: {ans[:180].replace(chr(10), ' | ')}")
        print()