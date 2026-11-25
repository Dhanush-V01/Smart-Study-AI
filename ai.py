"""Google Gemini integration (`google-genai`) with full offline Demo Mode fallbacks."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

GEMINI_MODEL = "gemini-2.5-flash"


def _get_api_key() -> str:
    """Resolve GEMINI_API_KEY from environment/.env first, then Streamlit secrets."""
    load_dotenv(dotenv_path=ENV_PATH, override=False)
    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        import streamlit as st

        sec_key = st.secrets.get("GEMINI_API_KEY", "")
        return str(sec_key).strip() if sec_key else ""
    except Exception:
        return ""


def has_api_key() -> bool:
    return bool(_get_api_key())


def _call_gemini(prompt: str) -> str | None:
    api_key = _get_api_key()
    if not api_key:
        return None
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = getattr(response, "text", None)
        return text.strip() if text and text.strip() else None
    except Exception:
        return None


def _strip_code_fences(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# 1. Doubt Solver + Follow-Up Conversation
# ---------------------------------------------------------------------------

_DEMO_DOUBT_BANK: dict[str, str] = {
    "Maths": (
        "### Step-by-Step Explanation\n\n"
        "1. **Identify givens & goal:** List known quantities, constraints, and the target expression.\n"
        "2. **Pick the theorem/technique:** Check algebra, differentiation, integration by parts, or identities.\n"
        "3. **Evaluate & sanity-check:** Verify signs, limits, and boundary values.\n\n"
        "**Example:** For $\\int x e^x\\,dx$, choose $u = x$ and $dv = e^x\\,dx$, yielding $x e^x - e^x + C$."
    ),
    "Physics": (
        "### Step-by-Step Explanation\n\n"
        "1. **Sketch the system:** Draw vectors, fields, or circuit loops with clear sign conventions.\n"
        "2. **Apply the physical law:** Use Gauss's Law, Kirchhoff's rules, or energy conservation.\n"
        "3. **Check limiting cases:** Confirm units and behavior when distance or resistance grows large.\n\n"
        "**Analogy (Kirchhoff's Voltage Law):** Walking around a closed loop trail and returning to camp means total net elevation gain equals **zero**."
    ),
    "DSA": (
        "### Step-by-Step Explanation\n\n"
        "1. **Inspect constraints (`N`):** Decide between `O(log n)`, `O(n)`, or `O(n log n)`.\n"
        "2. **Select structure:** Hash map for `O(1)` lookup, Stack for LIFO, Binary Search for monotonic conditions.\n"
        "3. **Dry-run edge cases:** Empty input, 1 element, and duplicates.\n\n"
        "**Analogy (Stack vs Queue):** A **Stack** is a pile of plates (LIFO); a **Queue** is a ticket line (FIFO)."
    ),
    "DBMS": (
        "### Step-by-Step Explanation\n\n"
        "1. **One entity per table:** Keep attributes atomic (1NF).\n"
        "2. **Remove partial & transitive dependencies:** Achieve 2NF and 3NF.\n"
        "3. **Link via Foreign Keys:** Use `INNER JOIN` for intersections, `LEFT JOIN` to preserve unmatched rows.\n\n"
        "**Example:** Moving `(DeptID, DeptHead)` out of `Student` avoids update anomalies and satisfies 3NF."
    ),
    "English": (
        "### Step-by-Step Explanation\n\n"
        "1. **Lead with a clear thesis:** State the central claim in sentence one.\n"
        "2. **Back with evidence + active voice:** Use concrete metrics and crisp verbs.\n"
        "3. **Synthesize:** Tie your closing line back to the core prompt.\n\n"
        "**Example:** Prefer *'Students discovered two calibration errors'* over *'Two calibration errors were discovered by students'*."
    ),
}


def solve_doubt(subject: str, question: str, knowledge_chunks: list[dict[str, Any]] | None = None) -> tuple[str, bool]:
    ctx_block = ""
    citations: list[str] = []
    if knowledge_chunks:
        snippets = []
        for ch in knowledge_chunks[:3]:
            cite = f"{ch['doc_title']} (§ {ch['section_title']})"
            if cite not in citations:
                citations.append(cite)
            snippets.append(f"[{cite}]\n{ch['content'][:450]}")
        ctx_block = "\n\nUploaded Class Reference Excerpts:\n" + "\n---\n".join(snippets)

    prompt = (
        f"You are SmartStudy AI, a supportive academic tutor.\n"
        f"Subject: {subject}\nStudent's doubt: {question}{ctx_block}\n\n"
        "Provide:\n"
        "1. A beginner-friendly step-by-step explanation (numbered markdown steps).\n"
        "2. One clear worked example or real-world analogy.\n"
        "Ground your explanation in the uploaded class reference excerpts when relevant. Keep it under 260 words."
    )
    ai_text = _call_gemini(prompt)
    if ai_text:
        if citations:
            ai_text += "\n\n**📚 Referenced Knowledge Materials:** " + " · ".join(f"`{c}`" for c in citations)
        return ai_text, False

    q_lower = question.lower()
    if any(k in q_lower for k in ("si unit", "unit of")) and any(k in q_lower for k in ("energy", "work", "heat")):
        ans = (
            "### Step-by-Step Explanation — SI Unit of Energy\n\n"
            "1. **Direct Answer:** The SI unit of energy (as well as work and heat) is the **Joule (J)**.\n"
            "2. **Derivation from Work:** $\\text{Work / Energy} = \\text{Force} \\times \\text{Displacement}$. "
            "Since force is measured in **Newtons (N)** and displacement in **metres (m)**, $1\\text{ J} = 1\\text{ N}\\cdot\\text{m}$.\n"
            "3. **In SI Base Units:** Since $1\\text{ N} = 1\\text{ kg}\\cdot\\text{m}/\\text{s}^2$, we get $1\\text{ J} = 1\\text{ kg}\\cdot\\text{m}^2/\\text{s}^2$.\n\n"
            "**Example:** Lifting a 100 g apple (weight $\\approx 1\\text{ N}$) straight up by $1\\text{ metre}$ uses about **1 Joule** of energy. "
            "*(Other common non-SI units: 1 calorie ≈ 4.184 J; 1 kWh = 3.6 × 10⁶ J.)*"
        )
    elif any(k in q_lower for k in ("si unit", "unit of")) and "force" in q_lower:
        ans = (
            "### Step-by-Step Explanation — SI Unit of Force\n\n"
            "1. **Direct Answer:** The SI unit of force is the **Newton (N)**.\n"
            "2. **From Newton's Second Law ($F = m \\cdot a$):** Mass is in $\\text{kg}$ and acceleration in $\\text{m/s}^2$, so $1\\text{ N} = 1\\text{ kg}\\cdot\\text{m/s}^2$.\n\n"
            "**Example:** Holding a 1 kg textbook steady against Earth's gravity ($g \\approx 9.8\\text{ m/s}^2$) requires about **9.8 N** of upward force."
        )
    elif any(k in q_lower for k in ("si unit", "unit of")) and "power" in q_lower:
        ans = (
            "### Step-by-Step Explanation — SI Unit of Power\n\n"
            "1. **Direct Answer:** The SI unit of power is the **Watt (W)**.\n"
            "2. **Formula ($P = W / t$):** Power is energy transferred per unit time, so $1\\text{ W} = 1\\text{ J/s} = 1\\text{ kg}\\cdot\\text{m}^2/\\text{s}^3$.\n\n"
            "**Example:** A 60 W LED bulb converts 60 Joules of electrical energy into light and heat every second."
        )
    elif any(k in q_lower for k in ("si unit", "unit of")) and any(k in q_lower for k in ("current", "voltage", "potential", "resistance", "charge")):
        ans = (
            "### Step-by-Step Reference — Key Electrical SI Units\n\n"
            "1. **Electric Charge:** **Coulomb (C)** ($1\\text{ C} = 1\\text{ A}\\cdot\\text{s}$)\n"
            "2. **Electric Current:** **Ampere (A)** (base SI unit)\n"
            "3. **Potential Difference (Voltage):** **Volt (V)** ($1\\text{ V} = 1\\text{ J/C}$)\n"
            "4. **Resistance:** **Ohm ($\\Omega$)** ($1\\,\\Omega = 1\\text{ V/A}$)\n\n"
            "**Analogy:** Voltage is water pressure, Current is flow rate, and Resistance is pipe narrowness."
        )
    elif "newton" in q_lower or ("law" in q_lower and "motion" in q_lower):
        ans = (
            "### Step-by-Step Explanation — Newton's Laws of Motion\n\n"
            "1. **First Law (Inertia):** An object stays at rest or constant velocity unless acted on by a non-zero net force.\n"
            "2. **Second Law ($F_{\\text{net}} = m a$):** Acceleration is proportional to net force and inversely proportional to mass.\n"
            "3. **Third Law:** Every action force has an equal and opposite reaction force acting on the *other* body.\n\n"
            "**Analogy:** Pushing an empty shopping cart accelerates it faster than pushing a full cart with the exact same push."
        )
    elif "ohm" in q_lower:
        ans = (
            "### Step-by-Step Explanation — Ohm's Law\n\n"
            "1. **Formula:** $V = I \\cdot R$ (at constant temperature).\n"
            "2. **Meaning:** Voltage ($V$, Volts) across a conductor equals Current ($I$, Amperes) times Resistance ($R$, Ohms).\n\n"
            "**Example:** A $12\\text{ V}$ battery across a $4\\,\\Omega$ resistor drives $I = 12 / 4 = 3\\text{ A}$ of current."
        )
    elif "recursion" in q_lower:
        ans = (
            "### Step-by-Step Explanation (Recursion)\n\n"
            "1. **Base Case:** Define the smallest input where the function stops recursing.\n"
            "2. **Recursive Case:** Reduce the problem to a smaller identical subproblem.\n"
            "3. **Call Stack Return:** Each waiting frame combines results on the way back up.\n\n"
            "**Analogy:** Russian nesting dolls—opening smaller dolls until the smallest solid one (base case), then closing them in reverse."
        )
    elif "binary search" in q_lower:
        ans = (
            "### Step-by-Step Explanation (Binary Search)\n\n"
            "1. **Requirement:** Array or search space must be **sorted** (monotonic).\n"
            "2. **Halving:** Compare target with `mid = lo + (hi - lo) // 2` and discard half the interval each step.\n"
            "3. **Complexity:** Takes at most $\\lceil \\log_2(n) \\rceil$ steps → **$O(\\log n)$ time, $O(1)$ space**.\n\n"
            "**Analogy:** Opening a 1,000-page dictionary in the middle takes ~10 flips instead of checking every page."
        )
    elif "join" in q_lower or "sql" in q_lower:
        ans = (
            "### Step-by-Step Explanation (SQL Joins)\n\n"
            "1. **INNER JOIN:** Keeps rows matching in **both** tables.\n"
            "2. **LEFT JOIN:** Keeps **all** left-table rows, filling unmatched right columns with `NULL`.\n"
            "3. **Join Key:** Match primary key to foreign key for speed and accuracy.\n\n"
            "**Example:** `Students LEFT JOIN QuizAttempts` lists every student, even those with zero quizzes yet."
        )
    elif any(k in q_lower for k in ("1nf", "2nf", "3nf", "bcnf", "normal")):
        ans = (
            "### Step-by-Step Explanation (Database Normalization)\n\n"
            "1. **1NF:** Atomic column values (no repeating groups).\n"
            "2. **2NF:** Every non-key attribute depends on the **whole** primary key (no partial dependencies).\n"
            "3. **3NF:** No transitive dependencies between non-key attributes ($A \\to B \\to C$).\n"
            "4. **BCNF:** Every determinant in a non-trivial functional dependency is a superkey.\n\n"
            "**Rule of Thumb:** Every non-key column depends on *the key, the whole key (2NF), and nothing but the key (3NF)*."
        )
    elif knowledge_chunks:
        top = knowledge_chunks[0]
        ans = (
            f"### 📚 Answer from Uploaded Knowledge Center (`{top['doc_title']}`)\n\n"
            f"**Section:** *{top['section_title']}*\n\n"
            f"{top['content']}\n\n"
            "*(Offline Demo Mode: Add `GEMINI_API_KEY` in `.env` for full conversational Gemini explanations.)*"
        )
        return ans, True
    else:
        ans = (
            f"**Question:** *{question.strip()}* ({subject})\n\n"
            "ℹ️ **Offline Demo Mode Notice:** No `GEMINI_API_KEY` is currently set in `.env`, and this exact question is not in the offline demo bank or uploaded Knowledge Center documents yet.\n\n"
            + _DEMO_DOUBT_BANK.get(subject, _DEMO_DOUBT_BANK["DSA"])
            + "\n\n*Tip: Add a free `GEMINI_API_KEY` in `.env` (or upload notes in **Knowledge Center**) to get tailored answers to any arbitrary question.*"
        )

    if knowledge_chunks:
        top = knowledge_chunks[0]
        ans += (
            f"\n\n---\n**📚 From Class Knowledge Center (`{top['doc_title']}` — {top['section_title']}):**\n"
            f"> {top['content'][:320].replace(chr(10), ' ')}..."
        )
    return ans, True


def follow_up_doubt(subject: str, original_q: str, original_a: str, follow_up_q: str) -> tuple[str, bool]:
    prompt = (
        f"Subject: {subject}\nOriginal Question: {original_q}\nPrevious Answer: {original_a}\n"
        f"Student Follow-up: {follow_up_q}\n"
        "Give a concise, helpful follow-up clarification (under 140 words)."
    )
    ai_text = _call_gemini(prompt)
    if ai_text:
        return ai_text, False
    return (
        f"Great follow-up on **{subject}**! To apply *{follow_up_q.strip()}* to your original question, "
        f"focus on checking one small concrete input by hand first, verify each intermediate step against the core rule, "
        f"and try a 5-question practice quiz right after to confirm mastery."
    ), True


# ---------------------------------------------------------------------------
# 2. Notes Summarizer & Flashcards
# ---------------------------------------------------------------------------

def summarize_notes(subject: str, content: str) -> tuple[str, bool]:
    prompt = (
        f"Summarize these {subject} study notes into: (1) 4-5 concise bulleted Key Takeaways, and "
        f"(2) 2 Quick Exam Revision Tips.\n\nNotes:\n{content[:4000]}"
    )
    ai_text = _call_gemini(prompt)
    if ai_text:
        return ai_text, False

    sentences = [s.strip() for s in re.split(r"[.\n]+", content) if len(s.strip()) > 12]
    bullets = "\n".join(f"- {s}." for s in sentences[:5]) or "- Review core definitions and worked examples from your notes."
    return (
        f"### 📌 Key Takeaways ({subject})\n{bullets}\n\n"
        f"### 🎯 Exam Revision Tips\n"
        f"- Rewrite these formulas/rules from memory without looking at your sheet.\n"
        f"- Practice 3 timed questions covering edge cases in {subject}."
    ), True


def generate_flashcards(subject: str, topic_or_text: str) -> tuple[list[dict[str, str]], bool]:
    prompt = (
        f"Generate 5 concise study flashcards for Subject '{subject}' based on: '{topic_or_text[:1500]}'.\n"
        "Return STRICT JSON ONLY: an array of 5 objects with keys 'front' and 'back'."
    )
    ai_text = _call_gemini(prompt)
    if ai_text:
        cleaned = _strip_code_fences(ai_text)
        m = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
        try:
            data = json.loads(m.group(0) if m else cleaned)
            if isinstance(data, list) and len(data) >= 3:
                cards = [
                    {"front": str(c["front"]).strip(), "back": str(c["back"]).strip()}
                    for c in data[:5]
                    if isinstance(c, dict) and c.get("front") and c.get("back")
                ]
                if cards:
                    return cards, False
        except Exception:
            pass

    fallback = {
        "Maths": [
            {"front": "Integration by Parts formula?", "back": "∫ u dv = uv - ∫ v du (LIATE rule helps choose u)."},
            {"front": "When is a square matrix singular?", "back": "When its determinant equals 0 (non-invertible)."},
            {"front": "Bayes' Theorem?", "back": "P(A|B) = P(B|A) * P(A) / P(B)."},
            {"front": "Chain Rule of differentiation?", "back": "d/dx[f(g(x))] = f'(g(x)) * g'(x)."},
        ],
        "Physics": [
            {"front": "Gauss's Law equation?", "back": "Φ_E = ∮ E·dA = Q_enclosed / ε₀."},
            {"front": "Kirchhoff's Voltage Law (KVL)?", "back": "Algebraic sum of potential differences around any closed loop is 0."},
            {"front": "Fringe width in Young's double-slit?", "back": "β = λD / d."},
            {"front": "Coulomb's Law scaling with distance r?", "back": "Inverse-square: F ∝ 1 / r²."},
        ],
        "DSA": [
            {"front": "Binary Search time & space complexity?", "back": "O(log n) time, O(1) iterative space."},
            {"front": "BST traversal giving sorted order?", "back": "Inorder traversal (Left → Root → Right)."},
            {"front": "Shortest path in unweighted graph?", "back": "Breadth-First Search (BFS)."},
            {"front": "LIFO vs FIFO?", "back": "Stack is LIFO; Queue is FIFO."},
        ],
        "DBMS": [
            {"front": "What does 2NF eliminate?", "back": "Partial dependencies on a composite primary key."},
            {"front": "What does 3NF eliminate?", "back": "Transitive dependencies between non-key attributes."},
            {"front": "WHERE vs HAVING?", "back": "WHERE filters rows before grouping; HAVING filters groups after GROUP BY."},
            {"front": "ACID stands for?", "back": "Atomicity, Consistency, Isolation, Durability."},
        ],
        "English": [
            {"front": "Active vs Passive voice?", "back": "In active voice, the subject performs the action; clearer and more direct."},
            {"front": "Role of a thesis statement?", "back": "States the central argument or claim of an essay."},
            {"front": "When to use a semicolon?", "back": "To join two closely related independent clauses without a conjunction."},
            {"front": "Analytical paragraph essentials?", "back": "Topic sentence, objective evidence/data, and concise synthesis."},
        ],
    }
    return fallback.get(subject, fallback["DSA"]), True


# ---------------------------------------------------------------------------
# 3. 5-Question MCQ Quiz Generator
# ---------------------------------------------------------------------------

_DEMO_QUIZ_BANK: dict[str, list[dict[str, Any]]] = {
    "Maths": [
        {"question": "What is the derivative of sin(2x) with respect to x?", "options": ["cos(2x)", "2 cos(2x)", "-2 cos(2x)", "2 sin(2x)"], "correct_index": 1, "explanation": "Chain rule: d/dx[sin(2x)] = 2 cos(2x)."},
        {"question": "Value of ∫ 2x dx from x = 1 to x = 3?", "options": ["4", "6", "8", "10"], "correct_index": 2, "explanation": "[x^2] from 1 to 3 = 9 - 1 = 8."},
        {"question": "If det(A) = 0 for a 2x2 matrix A, then A is:", "options": ["Orthogonal", "Singular (non-invertible)", "Identity", "Symmetric"], "correct_index": 1, "explanation": "A matrix is invertible iff its determinant is non-zero."},
        {"question": "For independent events P(A)=0.5, P(B)=0.4, P(A ∩ B) is:", "options": ["0.9", "0.2", "0.1", "0.45"], "correct_index": 1, "explanation": "P(A ∩ B) = P(A) * P(B) = 0.2."},
        {"question": "What is lim(x→0) sin(x)/x?", "options": ["0", "Infinity", "1", "-1"], "correct_index": 2, "explanation": "Standard trigonometric limit equals 1."},
    ],
    "Physics": [
        {"question": "Kirchhoff's Junction Rule reflects conservation of:", "options": ["Voltage", "Electric charge", "Resistance", "Magnetic flux"], "correct_index": 1, "explanation": "Charge cannot accumulate at a circuit junction."},
        {"question": "Doubling distance between two point charges makes force:", "options": ["Half", "Double", "One-fourth", "Four times"], "correct_index": 2, "explanation": "F ∝ 1/r² so 2r gives F/4."},
        {"question": "SI unit of electric potential difference?", "options": ["Ampere", "Coulomb", "Volt", "Ohm"], "correct_index": 2, "explanation": "Measured in Volts (J/C)."},
        {"question": "In YDSE, increasing wavelength λ causes fringe width to:", "options": ["Increase", "Decrease", "Stay same", "Drop to zero"], "correct_index": 0, "explanation": "β = λD/d is directly proportional to λ."},
        {"question": "Uniform circular motion has acceleration directed:", "options": ["Tangentially", "Outward", "Toward the center", "Zero"], "correct_index": 2, "explanation": "Centripetal acceleration always points radially inward."},
    ],
    "DSA": [
        {"question": "Worst-case time complexity of Binary Search on n items?", "options": ["O(1)", "O(log n)", "O(n)", "O(n log n)"], "correct_index": 1, "explanation": "Search interval halves every step."},
        {"question": "Which structure follows LIFO ordering?", "options": ["Queue", "Stack", "Min-Heap", "Hash Table"], "correct_index": 1, "explanation": "Stack pops the most recently pushed element."},
        {"question": "BST traversal returning sorted ascending order?", "options": ["Preorder", "Postorder", "Inorder", "Level-order"], "correct_index": 2, "explanation": "Inorder visits Left → Root → Right."},
        {"question": "Average-case lookup time in a Hash Table?", "options": ["O(1)", "O(log n)", "O(n)", "O(n^2)"], "correct_index": 0, "explanation": "Direct bucket indexing gives O(1) expected time."},
        {"question": "Shortest path in an unweighted graph uses:", "options": ["DFS", "BFS", "Prim's", "QuickSort"], "correct_index": 1, "explanation": "BFS visits vertices layer by layer."},
    ],
    "DBMS": [
        {"question": "Which normal form eliminates transitive dependencies?", "options": ["1NF", "2NF", "3NF", "UNF"], "correct_index": 2, "explanation": "3NF removes non-key transitive dependencies."},
        {"question": "SQL clause used to filter grouped rows after GROUP BY?", "options": ["WHERE", "HAVING", "ORDER BY", "DISTINCT"], "correct_index": 1, "explanation": "HAVING filters aggregated groups."},
        {"question": "The 'A' in ACID stands for:", "options": ["Availability", "Atomicity", "Authorization", "Aggregation"], "correct_index": 1, "explanation": "Transactions execute all-or-nothing."},
        {"question": "Join keeping all rows from the left table even if unmatched:", "options": ["INNER JOIN", "LEFT JOIN", "CROSS JOIN", "SELF JOIN"], "correct_index": 1, "explanation": "LEFT JOIN emits NULLs for unmatched right rows."},
        {"question": "Column(s) uniquely identifying every row without NULLs:", "options": ["Foreign Key", "Primary Key", "Check Constraint", "View"], "correct_index": 1, "explanation": "Primary Key enforces uniqueness and NOT NULL."},
    ],
    "English": [
        {"question": "Which sentence uses active voice?", "options": ["The report was submitted by Aarav.", "Aarav submitted the report before noon.", "The report had been written yesterday.", "Mistakes were found in the draft."], "correct_index": 1, "explanation": "Subject 'Aarav' directly performs 'submitted'."},
        {"question": "Primary purpose of a thesis statement?", "options": ["List citations", "State the central argument", "Add anecdotes", "Summarize bibliography"], "correct_index": 1, "explanation": "Communicates the essay's core claim."},
        {"question": "Word closest in meaning to 'concise':", "options": ["Verbose", "Brief and clear", "Ambiguous", "Repetitive"], "correct_index": 1, "explanation": "'Concise' means brief and clear."},
        {"question": "Punctuation joining two related independent clauses without a conjunction?", "options": ["Comma", "Semicolon", "Apostrophe", "Hyphen"], "correct_index": 1, "explanation": "A semicolon links two independent clauses."},
        {"question": "In analytical paragraphs, data is mainly used to:", "options": ["Replace the topic sentence", "Provide objective evidence", "Add dialogue", "Avoid a conclusion"], "correct_index": 1, "explanation": "Data substantiates claims objectively."},
    ],
}


def _parse_quiz_json(raw: str) -> list[dict[str, Any]] | None:
    cleaned = _strip_code_fences(raw)
    candidates = [cleaned]
    m = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            parsed = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list) or len(parsed) < 5:
            continue
        valid = []
        for item in parsed[:5]:
            if not isinstance(item, dict):
                break
            q, opts, idx = item.get("question"), item.get("options"), item.get("correct_index")
            expl = item.get("explanation", "Review this concept in your notes.")
            if (
                isinstance(q, str)
                and q.strip()
                and isinstance(opts, list)
                and len(opts) == 4
                and all(isinstance(o, str) and o.strip() for o in opts)
                and isinstance(idx, int)
                and 0 <= idx <= 3
            ):
                valid.append({"question": q.strip(), "options": [o.strip() for o in opts], "correct_index": idx, "explanation": str(expl).strip()})
        if len(valid) == 5:
            return valid
    return None


def generate_quiz(
    subject: str,
    topic: str,
    difficulty: str = "Medium",
    knowledge_chunks: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    topic_clean = topic.strip() or f"{subject} Fundamentals"
    ctx = ""
    if knowledge_chunks:
        ctx = "\nReference Material:\n" + "\n".join(c["content"][:350] for c in knowledge_chunks[:3])
    prompt = (
        f"Generate exactly 5 {difficulty}-level multiple-choice questions on Subject: '{subject}', Topic: '{topic_clean}'.{ctx}\n"
        "Return STRICT JSON ONLY (array of 5 objects with keys: 'question', 'options' [4 strings], 'correct_index' [0-3], 'explanation')."
    )
    ai_text = _call_gemini(prompt)
    if ai_text:
        parsed = _parse_quiz_json(ai_text)
        if parsed:
            return parsed, False
    return [dict(item) for item in _DEMO_QUIZ_BANK.get(subject, _DEMO_QUIZ_BANK["DSA"])], True


# ---------------------------------------------------------------------------
# 4. Weak-Area Recommendation, Study Timetable & Career/Goal Tips
# ---------------------------------------------------------------------------

def get_weak_area_recommendation(weak_subjects: list[dict[str, Any]]) -> tuple[str, bool]:
    if not weak_subjects:
        return "Take your first practice quiz to unlock personalized weak-area insights!", True
    summary = ", ".join(f"{w['subject']} ({w['avg_score']}% avg)" for w in weak_subjects)
    prompt = f"A student's lowest quiz subjects are: {summary}. Give a concise 2-sentence actionable study tip."
    ai_text = _call_gemini(prompt)
    if ai_text:
        return ai_text, False
    top_weak = weak_subjects[0]["subject"]
    return (
        f"Focus your next two 25-minute Pomodoro blocks on **{top_weak}**—review solved examples first, "
        f"then test yourself with a 5-question practice quiz to strengthen active recall."
    ), True


def generate_study_timetable(weak_subjects: list[str], pending_tasks: list[str], daily_minutes: int = 90) -> tuple[list[dict[str, Any]], bool]:
    prompt = (
        f"Create a balanced 7-day study timetable (Mon-Sun) with ~{daily_minutes} mins/day.\n"
        f"Priority weak subjects: {', '.join(weak_subjects) or 'Physics, DBMS'}.\n"
        f"Pending tasks: {', '.join(pending_tasks[:4]) or 'Revision & Practice'}.\n"
        "Return STRICT JSON array of 7 objects with keys: 'day', 'subject', 'focus', 'minutes'."
    )
    ai_text = _call_gemini(prompt)
    if ai_text:
        cleaned = _strip_code_fences(ai_text)
        m = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
        try:
            data = json.loads(m.group(0) if m else cleaned)
            if isinstance(data, list) and len(data) == 7:
                rows = [
                    {
                        "day": str(r.get("day", "")),
                        "subject": str(r.get("subject", "DSA")),
                        "focus": str(r.get("focus", "Revision")),
                        "minutes": int(r.get("minutes", daily_minutes)),
                    }
                    for r in data
                ]
                return rows, False
        except Exception:
            pass

    w1 = weak_subjects[0] if weak_subjects else "Physics"
    w2 = weak_subjects[1] if len(weak_subjects) > 1 else "DBMS"
    plan = [
        {"day": "Monday", "subject": w1, "focus": f"Core concepts + solved examples ({w1})", "minutes": daily_minutes},
        {"day": "Tuesday", "subject": w2, "focus": f"Worksheet & normalization drill ({w2})", "minutes": daily_minutes},
        {"day": "Wednesday", "subject": "DSA", "focus": "Timed coding + binary search edge cases", "minutes": daily_minutes},
        {"day": "Thursday", "subject": w1, "focus": f"5-question practice quiz + error review ({w1})", "minutes": daily_minutes},
        {"day": "Friday", "subject": "Maths", "focus": "Integration & definite integrals set", "minutes": daily_minutes},
        {"day": "Saturday", "subject": w2, "focus": f"Mock test + flashcard recall ({w2})", "minutes": daily_minutes},
        {"day": "Sunday", "subject": "English", "focus": "Weekly reflection + light revision", "minutes": max(45, daily_minutes // 2)},
    ]
    return plan, True


def generate_goal_steps(goal_title: str, category: str) -> tuple[str, bool]:
    prompt = f"Give 3 crisp, realistic next steps for a student goal '{goal_title}' ({category}). Keep under 90 words."
    ai_text = _call_gemini(prompt)
    if ai_text:
        return ai_text, False
    return (
        f"1. Break **{goal_title}** into a 25-minute starter milestone today.\n"
        f"2. Schedule 3 recurring weekly checkpoints in your Study Planner.\n"
        f"3. Log measurable evidence (quiz score, notes, or upload) once completed."
    ), True
