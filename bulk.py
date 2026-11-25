"""Universal Bulk Import, Template Generation, Validation, and Error Report helpers."""

from __future__ import annotations

import io
import json
from datetime import date
from typing import Any

import pandas as pd

import db

BULK_TEMPLATES: dict[str, pd.DataFrame] = {
    "Students": pd.DataFrame(
        [
            {
                "usn": "1SI24CS010",
                "name": "Diya Nair",
                "email": "diya.nair@smartstudy.edu",
                "course": "B.Tech",
                "branch": "CSE",
                "semester": 5,
                "section": "Section A",
                "academic_year": "2026-27",
            }
        ]
    ),
    "Student Logins": pd.DataFrame(
        [
            {"name": "Diya Nair", "usn": "1SI24CS010"},
            {"name": "Vikram Rao", "usn": "1SI24CS011"},
        ]
    ),
    "Teacher Logins": pd.DataFrame(
        [
            {"teacher_name": "Prof. Arvind Rao", "teacher_id": "TCH101", "department": "CSE"},
            {"teacher_name": "Dr. Kavita Menon", "teacher_id": "TCH102", "department": "Physics"},
        ]
    ),
    "Attendance": pd.DataFrame(
        [
            {
                "usn": "1SI24CS001",
                "subject": "Physics",
                "att_date": date.today().isoformat(),
                "status": "Present",
            }
        ]
    ),
    "IA Marks": pd.DataFrame(
        [
            {
                "usn": "1SI24CS001",
                "subject": "DSA",
                "component": "IA 3",
                "score": 23,
                "max_score": 25,
                "weightage": 0.35,
                "recorded_date": date.today().isoformat(),
            }
        ]
    ),
    "Question Bank": pd.DataFrame(
        [
            {
                "subject": "DSA",
                "topic": "Sorting",
                "difficulty": "Easy",
                "q_type": "MCQ",
                "question": "Which sorting algorithm has O(n log n) worst-case time?",
                "options_pipe": "Bubble Sort|Merge Sort|Insertion Sort|Selection Sort",
                "correct_answer": "Merge Sort",
                "explanation": "Merge Sort guarantees O(n log n) across all cases.",
                "marks": 1,
            }
        ]
    ),
    "Skills": pd.DataFrame(
        [
            {
                "usn": "1SI24CS001",
                "name": "Docker & Containers",
                "category": "Technical",
                "current_level": 2,
                "target_level": 4,
                "interest_level": 4,
            }
        ]
    ),
}


def df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Template")
    return buf.getvalue()


def parse_uploaded_or_pasted(uploaded_file, pasted_text: str, module: str = "") -> pd.DataFrame:
    """Read CSV, Excel (.xlsx), JSON, PDF, DOCX, TXT, or pasted text into a DataFrame."""
    import knowledge

    if uploaded_file is not None:
        name = uploaded_file.name.lower()
        if name.endswith(".xlsx"):
            return pd.read_excel(uploaded_file, engine="openpyxl")
        if name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        if name.endswith(".json"):
            return pd.read_json(uploaded_file)
        if name.endswith((".pdf", ".docx", ".txt", ".md")):
            parsed = knowledge.extract_document_content(uploaded_file, "")
            # If Question Bank, use structured Q&A extraction directly
            if module == "Question Bank" and parsed["detected_questions"]:
                return pd.DataFrame(
                    [
                        {
                            "subject": q.get("subject") or "DSA",
                            "topic": q.get("topic") or "General",
                            "difficulty": q.get("difficulty") or "Medium",
                            "q_type": q.get("q_type") or "MCQ",
                            "question": q.get("question") or "",
                            "options_pipe": "|".join(q.get("options") or []),
                            "correct_answer": q.get("correct_answer") or "",
                            "explanation": q.get("explanation") or "",
                            "marks": q.get("marks") or 1.0,
                        }
                        for q in parsed["detected_questions"]
                    ]
                )
            # If DOCX/PDF contained a table with headers, use first table
            if parsed["tables"] and parsed["tables"][0].get("rows"):
                rows = parsed["tables"][0]["rows"]
                if len(rows) >= 2:
                    return pd.DataFrame(rows[1:], columns=rows[0])
            # Fallback: try parsing extracted text lines as CSV/TSV
            txt_clean = (parsed["extracted_text"] or "").strip()
            if not txt_clean:
                raise ValueError("No readable text or table found inside the uploaded document.")
            first_line = txt_clean.splitlines()[0]
            sep = "\t" if "\t" in first_line else ("," if "," in first_line else "|")
            df_out = pd.read_csv(io.StringIO(txt_clean), sep=sep)
            cols_low = [str(c).strip().lower() for c in df_out.columns]
            if module == "Student Logins" and not any(c in cols_low for c in ("name", "student_name", "usn")):
                df_out = pd.read_csv(io.StringIO(txt_clean), sep=sep, header=None, names=["name", "usn"][: len(df_out.columns)])
            elif module == "Teacher Logins" and not any(c in cols_low for c in ("teacher_name", "name", "teacher_id")):
                names_pool = ["teacher_name", "teacher_id", "department"]
                df_out = pd.read_csv(io.StringIO(txt_clean), sep=sep, header=None, names=names_pool[: len(df_out.columns)])
            return df_out
        raise ValueError("Unsupported file type. Upload .csv, .xlsx, .json, .pdf, .docx, .txt, or .md.")

    raw = (pasted_text or "").strip()
    if not raw:
        raise ValueError("Upload a file (CSV/Excel/PDF/DOCX/TXT) or paste text first.")
    if module == "Question Bank" and ("," not in raw.splitlines()[0] and "\t" not in raw.splitlines()[0]):
        parsed = knowledge.extract_document_content(None, raw)
        if parsed["detected_questions"]:
            return pd.DataFrame(
                [
                    {
                        "subject": q.get("subject") or "DSA",
                        "topic": q.get("topic") or "General",
                        "difficulty": q.get("difficulty") or "Medium",
                        "q_type": q.get("q_type") or "MCQ",
                        "question": q.get("question") or "",
                        "options_pipe": "|".join(q.get("options") or []),
                        "correct_answer": q.get("correct_answer") or "",
                        "explanation": q.get("explanation") or "",
                        "marks": q.get("marks") or 1.0,
                    }
                    for q in parsed["detected_questions"]
                ]
            )
    sep = "\t" if "\t" in raw.splitlines()[0] else ("," if "," in raw.splitlines()[0] else "|")
    df_out = pd.read_csv(io.StringIO(raw), sep=sep)
    cols_low = [str(c).strip().lower() for c in df_out.columns]
    if module == "Student Logins" and not any(c in cols_low for c in ("name", "student_name", "usn")):
        df_out = pd.read_csv(io.StringIO(raw), sep=sep, header=None, names=["name", "usn"][: len(df_out.columns)])
    elif module == "Teacher Logins" and not any(c in cols_low for c in ("teacher_name", "name", "teacher_id")):
        names_pool = ["teacher_name", "teacher_id", "department"]
        df_out = pd.read_csv(io.StringIO(raw), sep=sep, header=None, names=names_pool[: len(df_out.columns)])
    return df_out


def validate_bulk_rows(module: str, df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate rows for a target module, returning `(valid_rows, error_rows)`."""
    if df.empty:
        return [], [{"row": 0, "error": "Input table has 0 rows."}]

    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    valid: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    students = db.get_all_students(include_archived=True)
    usn_to_id = {s["usn"].upper(): s["id"] for s in students}
    existing_names = {s["name"].lower() for s in students}
    valid_subjects = set(db.get_subject_names())

    if module == "Student Logins":
        seen_usns: set[str] = set()
        for idx, row in df.iterrows():
            name = str(row.get("name") or row.get("student_name") or "").strip()
            usn = str(row.get("usn") or row.get("student_id") or row.get("roll_no") or "").strip().upper()
            if not name or not usn or name.lower() == "nan" or usn == "NAN":
                errors.append({"row": idx + 1, "error": "Missing required 'name' or 'usn'."})
                continue
            if usn in seen_usns:
                errors.append({"row": idx + 1, "error": f"Duplicate USN '{usn}' in upload."})
                continue
            seen_usns.add(usn)
            valid.append(
                {
                    "name": name,
                    "usn": usn,
                    "branch": str(row.get("branch") or row.get("department") or "CSE").strip() if str(row.get("branch") or row.get("department") or "").lower() != "nan" else "CSE",
                    "section": str(row.get("section") or "Section A").strip() if str(row.get("section") or "").lower() != "nan" else "Section A",
                }
            )

    elif module == "Teacher Logins":
        seen_ids: set[str] = set()
        for idx, row in df.iterrows():
            t_name = str(row.get("teacher_name") or row.get("name") or "").strip()
            t_id = str(row.get("teacher_id") or row.get("id") or row.get("emp_id") or "").strip().upper()
            dept = str(row.get("department") or "CSE").strip()
            if not t_name or not t_id or t_name.lower() == "nan" or t_id == "NAN":
                errors.append({"row": idx + 1, "error": "Missing required 'teacher_name' (or 'name') or 'teacher_id'."})
                continue
            if t_id in seen_ids:
                errors.append({"row": idx + 1, "error": f"Duplicate Teacher ID '{t_id}' in upload."})
                continue
            seen_ids.add(t_id)
            valid.append({"teacher_name": t_name, "teacher_id": t_id, "department": "CSE" if dept.lower() == "nan" or not dept else dept})

    elif module == "Students":
        seen_usns: set[str] = set()
        for idx, row in df.iterrows():
            usn = str(row.get("usn", "")).strip().upper()
            name = str(row.get("name", "")).strip()
            email = str(row.get("email", "")).strip()
            if not usn or not name or usn == "NAN" or name.lower() == "nan":
                errors.append({"row": idx + 1, "error": "Missing required 'usn' or 'name'."})
                continue
            if usn in usn_to_id or usn in seen_usns:
                errors.append({"row": idx + 1, "error": f"Duplicate USN '{usn}'."})
                continue
            if name.lower() in existing_names:
                errors.append({"row": idx + 1, "error": f"Duplicate student name '{name}'."})
                continue
            try:
                sem = int(row.get("semester", 5))
            except Exception:
                errors.append({"row": idx + 1, "error": "Invalid semester integer."})
                continue
            seen_usns.add(usn)
            valid.append(
                {
                    "usn": usn,
                    "name": name,
                    "email": "" if email.lower() == "nan" else email,
                    "course": str(row.get("course", "B.Tech")).strip() or "B.Tech",
                    "branch": str(row.get("branch", "CSE")).strip() or "CSE",
                    "semester": sem,
                    "section": str(row.get("section", "Section A")).strip() or "Section A",
                    "academic_year": str(row.get("academic_year", "2026-27")).strip() or "2026-27",
                }
            )

    elif module == "Attendance":
        for idx, row in df.iterrows():
            usn = str(row.get("usn", "")).strip().upper()
            subj = str(row.get("subject", "")).strip()
            att_date = str(row.get("att_date", "")).strip()[:10]
            status = str(row.get("status", "")).strip().title()
            if usn not in usn_to_id:
                errors.append({"row": idx + 1, "error": f"Unknown student USN '{usn}'."})
                continue
            if subj not in valid_subjects:
                errors.append({"row": idx + 1, "error": f"Unknown subject '{subj}'."})
                continue
            if status not in ("Present", "Absent", "Late"):
                errors.append({"row": idx + 1, "error": f"Invalid status '{status}' (use Present/Absent/Late)."})
                continue
            try:
                date.fromisoformat(att_date)
            except Exception:
                errors.append({"row": idx + 1, "error": f"Invalid ISO date '{att_date}'."})
                continue
            valid.append({"student_id": usn_to_id[usn], "usn": usn, "subject": subj, "att_date": att_date, "status": status})

    elif module == "IA Marks":
        for idx, row in df.iterrows():
            usn = str(row.get("usn", "")).strip().upper()
            subj = str(row.get("subject", "")).strip()
            comp = str(row.get("component", "IA 1")).strip()
            rec_date = str(row.get("recorded_date", date.today().isoformat())).strip()[:10]
            if usn not in usn_to_id:
                errors.append({"row": idx + 1, "error": f"Unknown student USN '{usn}'."})
                continue
            if subj not in valid_subjects:
                errors.append({"row": idx + 1, "error": f"Unknown subject '{subj}'."})
                continue
            try:
                score = float(row.get("score"))
                max_score = float(row.get("max_score", 25))
                weightage = float(row.get("weightage", 0.35))
                if score < 0 or max_score <= 0 or score > max_score:
                    raise ValueError
            except Exception:
                errors.append({"row": idx + 1, "error": "Invalid score/max_score range."})
                continue
            valid.append(
                {
                    "student_id": usn_to_id[usn],
                    "usn": usn,
                    "subject": subj,
                    "component": comp,
                    "score": score,
                    "max_score": max_score,
                    "weightage": weightage,
                    "recorded_date": rec_date,
                }
            )

    elif module == "Question Bank":
        for idx, row in df.iterrows():
            subj = str(row.get("subject", "")).strip()
            topic = str(row.get("topic", "General")).strip()
            diff = str(row.get("difficulty", "Medium")).strip().title()
            q_type = str(row.get("q_type", "MCQ")).strip()
            q_text = str(row.get("question", "")).strip()
            opts_raw = str(row.get("options_pipe", "")).strip()
            ans = str(row.get("correct_answer", "")).strip()
            if subj not in valid_subjects or not q_text or not ans or q_text.lower() == "nan":
                errors.append({"row": idx + 1, "error": "Invalid subject, empty question, or missing correct_answer."})
                continue
            opts = [o.strip() for o in opts_raw.split("|") if o.strip()] if opts_raw and opts_raw.lower() != "nan" else []
            if q_type == "MCQ" and len(opts) < 2:
                errors.append({"row": idx + 1, "error": "MCQ requires pipe-separated options in 'options_pipe'."})
                continue
            valid.append(
                {
                    "subject": subj,
                    "topic": topic,
                    "difficulty": diff if diff in ("Easy", "Medium", "Hard") else "Medium",
                    "q_type": q_type,
                    "question": q_text,
                    "options": opts,
                    "correct_answer": ans,
                    "explanation": str(row.get("explanation", "")).strip(),
                    "marks": float(row.get("marks", 1.0) or 1.0),
                }
            )

    elif module == "Skills":
        for idx, row in df.iterrows():
            usn = str(row.get("usn", "")).strip().upper()
            name = str(row.get("name", "")).strip()
            cat = str(row.get("category", "Technical")).strip()
            if usn not in usn_to_id or not name or name.lower() == "nan":
                errors.append({"row": idx + 1, "error": f"Unknown USN '{usn}' or empty skill name."})
                continue
            try:
                curr = int(row.get("current_level", 2))
                targ = int(row.get("target_level", 4))
                inter = int(row.get("interest_level", 4))
                if not (1 <= curr <= 5 and 1 <= targ <= 5):
                    raise ValueError
            except Exception:
                errors.append({"row": idx + 1, "error": "Levels must be integers 1–5."})
                continue
            valid.append(
                {
                    "student_id": usn_to_id[usn],
                    "usn": usn,
                    "name": name,
                    "category": cat,
                    "current_level": curr,
                    "target_level": max(curr, targ),
                    "interest_level": max(1, min(5, inter)),
                }
            )
    return valid, errors


def commit_bulk_rows(module: str, valid_rows: list[dict[str, Any]], actor_username: str, actor_role: str) -> int:
    if module == "Student Logins":
        res = db.bulk_create_student_logins(valid_rows, actor_username)
        return len(res)
    if module == "Teacher Logins":
        res = db.bulk_create_teacher_logins(valid_rows, actor_username)
        return len(res)
    count = 0
    for r in valid_rows:
        if module == "Students":
            db.upsert_student(r["usn"], r["name"], r["email"], r["course"], r["branch"], r["semester"], r["section"], r["academic_year"])
        elif module == "Attendance":
            db.upsert_attendance(r["student_id"], r["subject"], r["att_date"], r["status"])
        elif module == "IA Marks":
            db.add_assessment(r["student_id"], r["subject"], r["component"], r["score"], r["max_score"], r["weightage"], r["recorded_date"])
        elif module == "Question Bank":
            db.add_question_to_bank(r["subject"], r["topic"], r["difficulty"], r["q_type"], r["question"], r["options"], r["correct_answer"], r["explanation"], r["marks"], source="Bulk Import", approved_by_teacher=True)
        elif module == "Skills":
            db.add_skill(r["student_id"], r["name"], r["category"], r["current_level"], r["target_level"], r["interest_level"])
        count += 1
    db.log_activity(actor_username, actor_role, "BULK_IMPORT", f"Imported {count} rows into {module}")
    return count
