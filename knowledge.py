"""SmartStudy Knowledge Center: document parsing, metadata detection, chunking, TF-IDF retrieval & Q&A extraction."""

from __future__ import annotations

import io
import json
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import db

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "uploads" / "knowledge"
DOC_CATEGORIES = [
    "Notes",
    "Question papers",
    "Question banks",
    "Assignments",
    "Syllabus",
    "Reference materials",
    "Lab manuals",
    "Tutorials",
    "Exam preparation",
    "Announcements",
    "Other",
]
DOC_VISIBILITIES = ["Students & Teachers", "Teachers Only", "Admin Only"]
DOC_STATUSES = ["Active", "Draft", "Archived"]
MAX_DOC_BYTES = 8 * 1024 * 1024  # 8 MB


def save_knowledge_file(uploaded_file) -> tuple[str, str, str]:
    """Validate and persist an uploaded document safely under uploads/knowledge/."""
    raw = uploaded_file.getvalue()
    if len(raw) > MAX_DOC_BYTES:
        raise ValueError("Document exceeds the 8 MB limit.")
    ext = Path(uploaded_file.name).suffix.lower() or ".txt"
    allowed = {".pdf", ".txt", ".md", ".docx", ".csv", ".xlsx", ".json"}
    if ext not in allowed:
        raise ValueError(f"Unsupported format '{ext}'. Supported: {', '.join(sorted(allowed))}.")
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"doc_{uuid.uuid4().hex}{ext}"
    dest = KNOWLEDGE_DIR / safe_name
    dest.write_bytes(raw)
    db.save_file_blob(str(dest), uploaded_file.name, raw)
    return str(dest), uploaded_file.name, ext


def extract_document_content(uploaded_file=None, pasted_text: str = "") -> dict[str, Any]:
    """Extract raw text, tables, sections, Q&A candidates, and metadata from uploaded file or pasted text."""
    text = ""
    tables: list[dict[str, Any]] = []
    file_name = "pasted_document.txt"
    ext = ".txt"
    doc_type = "Pasted Text"

    if uploaded_file is not None:
        file_name = uploaded_file.name
        ext = Path(file_name).suffix.lower()
        raw = uploaded_file.getvalue()

        if ext == ".pdf":
            doc_type = "PDF Document"
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            pages_txt = []
            for i, page in enumerate(reader.pages, 1):
                p_txt = (page.extract_text() or "").strip()
                if p_txt:
                    pages_txt.append(f"--- Page {i} ---\n{p_txt}")
            text = "\n\n".join(pages_txt)

        elif ext == ".docx":
            doc_type = "Word Document (DOCX)"
            import docx

            document = docx.Document(io.BytesIO(raw))
            paras = [p.text.strip() for p in document.paragraphs if p.text.strip()]
            text = "\n".join(paras)
            for t_idx, tbl in enumerate(document.tables, 1):
                rows = [[cell.text.strip() for cell in row.cells] for row in tbl.rows]
                if rows:
                    tables.append({"table_index": t_idx, "rows": rows[:25]})
                    text += "\n\n" + "\n".join(" | ".join(r) for r in rows)

        elif ext == ".csv":
            doc_type = "CSV Table"
            df = pd.read_csv(io.BytesIO(raw))
            tables.append({"table_index": 1, "columns": list(df.columns), "rows": df.head(25).astype(str).values.tolist()})
            text = df.to_csv(index=False)

        elif ext == ".xlsx":
            doc_type = "Excel Workbook"
            xls = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
            parts = []
            for s_idx, sheet in enumerate(xls.sheet_names, 1):
                df = xls.parse(sheet)
                tables.append({"sheet": sheet, "table_index": s_idx, "columns": list(df.columns), "rows": df.head(25).astype(str).values.tolist()})
                parts.append(f"### Sheet: {sheet}\n" + df.to_csv(index=False))
            text = "\n\n".join(parts)

        elif ext in {".txt", ".md", ".json"}:
            doc_type = "Text / Markdown" if ext != ".json" else "JSON Document"
            text = raw.decode("utf-8", errors="replace")
        else:
            raise ValueError(f"Unsupported format '{ext}'.")
    else:
        text = (pasted_text or "").strip()
        if not text:
            raise ValueError("Please upload a file or paste text content.")

    metadata = detect_metadata(text, file_name, doc_type, tables)
    return {
        "file_name": file_name,
        "ext": ext,
        "doc_type": doc_type,
        "extracted_text": text.strip(),
        "tables": tables,
        **metadata,
    }


def detect_metadata(text: str, file_name: str, doc_type: str, tables: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect subject, semester, topic, sections, candidate questions, and missing fields without inventing."""
    haystack = f"{file_name}\n{text[:4000]}".lower()
    subjects = db.get_subjects()

    detected_subject = ""
    detected_code = ""
    for s in subjects:
        if s["name"].lower() in haystack or s["code"].lower() in haystack:
            detected_subject = s["name"]
            detected_code = s["code"]
            break

    # Detect semester if explicitly mentioned
    sem_match = re.search(r"\bsem(?:ester)?\s*[-:]?\s*([1-8])\b", haystack)
    detected_semester: int | None = int(sem_match.group(1)) if sem_match else None

    # Detect sections from headings or numbered headers
    sections: list[str] = []
    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        if re.match(r"^(#{1,3}\s+|unit\s+\d+|module\s+\d+|chapter\s+\d+|\d+\.\s+[A-Z])", ln, flags=re.IGNORECASE):
            sections.append(ln.lstrip("#").strip()[:100])
        if len(sections) >= 12:
            break

    # Detect topic from first heading or topic: line (or leave blank if absent)
    topic_match = re.search(r"(?:topic|unit|chapter)\s*[:\-]\s*([^\n\r]{3,80})", text, flags=re.IGNORECASE)
    detected_topic = topic_match.group(1).strip() if topic_match else (sections[0] if sections else "")

    # Guess category from text cues
    detected_category = "Notes"
    if "question bank" in haystack or "mcq" in haystack or "multiple choice" in haystack:
        detected_category = "Question banks"
    elif "question paper" in haystack or "max marks" in haystack or "part a" in haystack:
        detected_category = "Question papers"
    elif "syllabus" in haystack or "course outcomes" in haystack:
        detected_category = "Syllabus"
    elif "lab manual" in haystack or "experiment" in haystack:
        detected_category = "Lab manuals"
    elif "assignment" in haystack or "due date" in haystack:
        detected_category = "Assignments"

    # Extract candidate Q&A items without inventing missing fields
    detected_questions = extract_questions_from_text(
        text=text,
        default_subject=detected_subject,
        default_code=detected_code,
        default_semester=detected_semester,
        default_topic=detected_topic,
        tables=tables,
    )

    missing_fields: list[str] = []
    if not detected_subject:
        missing_fields.append("subject")
    if detected_semester is None:
        missing_fields.append("semester")
    if not detected_topic:
        missing_fields.append("topic")
    if not text.strip():
        missing_fields.append("extracted_text")

    return {
        "detected_subject": detected_subject,
        "detected_code": detected_code,
        "detected_semester": detected_semester,
        "detected_topic": detected_topic,
        "detected_category": detected_category,
        "detected_sections": sections,
        "detected_questions": detected_questions,
        "missing_fields": missing_fields,
    }


def extract_questions_from_text(
    text: str,
    default_subject: str = "",
    default_code: str = "",
    default_semester: int | None = None,
    default_topic: str = "",
    tables: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Parse structured questions (CSV/Excel rows or numbered Q1/1. text blocks). Never invents missing answers."""
    items: list[dict[str, Any]] = []

    # 1. Try tabular extraction if CSV/Excel columns look like questions
    if tables:
        for tbl in tables:
            cols = [str(c).strip().lower() for c in tbl.get("columns", [])]
            if "question" in cols:
                col_idx = {c: i for i, c in enumerate(cols)}
                for r_idx, row in enumerate(tbl.get("rows", []), 1):
                    def _get(key: str, fallback: str = "") -> str:
                        idx = col_idx.get(key)
                        if idx is not None and idx < len(row):
                            val = str(row[idx]).strip()
                            return "" if val.lower() in ("nan", "none") else val
                        return fallback

                    q_txt = _get("question")
                    if not q_txt:
                        continue
                    opts_raw = _get("options_pipe") or _get("options")
                    opts = [o.strip() for o in re.split(r"[|;]", opts_raw) if o.strip()] if opts_raw else []
                    if not opts:
                        # Check option_a..option_d columns
                        for opt_col in ("option_a", "option_b", "option_c", "option_d", "a", "b", "c", "d"):
                            v = _get(opt_col)
                            if v:
                                opts.append(v)
                    marks_raw = _get("marks")
                    try:
                        marks_val = float(marks_raw) if marks_raw else None
                    except ValueError:
                        marks_val = None
                    sem_raw = _get("semester")
                    try:
                        sem_val = int(float(sem_raw)) if sem_raw else default_semester
                    except ValueError:
                        sem_val = default_semester

                    items.append(
                        {
                            "question_number": _get("question_number") or _get("q_no") or str(r_idx),
                            "subject": _get("subject") or default_subject,
                            "subject_code": _get("subject_code") or default_code,
                            "semester": sem_val,
                            "topic": _get("topic") or default_topic,
                            "unit": _get("unit"),
                            "difficulty": _get("difficulty"),
                            "q_type": _get("q_type") or _get("type") or ("MCQ" if len(opts) >= 2 else "Short Answer"),
                            "marks": marks_val,
                            "question": q_txt,
                            "options": opts,
                            "correct_answer": _get("correct_answer") or _get("answer"),
                            "explanation": _get("explanation"),
                        }
                    )
                if items:
                    return items

    # 2. Parse numbered question blocks from PDF/DOCX/TXT
    lines = [ln.rstrip() for ln in text.splitlines()]
    blocks: list[tuple[str, list[str]]] = []
    cur_num = ""
    cur_lines: list[str] = []

    q_start_re = re.compile(r"^\s*(?:Q\.?\s*(\d+)\s*[.):]?|(\d{1,3})\s*[.)])\s+(.+)$", re.IGNORECASE)
    for ln in lines:
        m = q_start_re.match(ln)
        if m:
            if cur_lines:
                blocks.append((cur_num, cur_lines))
            cur_num = m.group(1) or m.group(2) or ""
            cur_lines = [m.group(3).strip()]
        elif cur_lines:
            cur_lines.append(ln.strip())
    if cur_lines:
        blocks.append((cur_num, cur_lines))

    opt_re = re.compile(r"^\s*(?:\(?([A-Da-d])\)?[.)]|[A-Da-d]:)\s+(.+)$")
    ans_re = re.compile(r"^\s*(?:Ans(?:wer)?|Correct\s*Answer)\s*[:\-]\s*(.+)$", re.IGNORECASE)
    exp_re = re.compile(r"^\s*(?:Explanation|Exp)\s*[:\-]\s*(.+)$", re.IGNORECASE)
    marks_re = re.compile(r"\[(\d+(?:\.\d+)?)\s*(?:marks?|pts?|m)?\]|\((\d+(?:\.\d+)?)\s*(?:marks?|pts?)\)", re.IGNORECASE)
    diff_re = re.compile(r"\b(Easy|Medium|Hard)\b", re.IGNORECASE)

    for q_num, b_lines in blocks:
        q_parts: list[str] = []
        opts_map: dict[str, str] = {}
        ans_raw = ""
        exp_raw = ""
        for bl in b_lines:
            if not bl:
                continue
            om = opt_re.match(bl)
            am = ans_re.match(bl)
            em = exp_re.match(bl)
            if am:
                ans_raw = am.group(1).strip()
            elif em:
                exp_raw = em.group(1).strip()
            elif om and not ans_raw:
                opts_map[om.group(1).upper()] = om.group(2).strip()
            elif not opts_map and not ans_raw:
                q_parts.append(bl)

        q_text = " ".join(q_parts).strip()
        if len(q_text) < 8:
            continue

        marks_val = None
        mm = marks_re.search(q_text)
        if mm:
            marks_val = float(mm.group(1) or mm.group(2))
            q_text = marks_re.sub("", q_text).strip()

        diff_val = ""
        dm = diff_re.search(q_text)
        if dm:
            diff_val = dm.group(1).title()

        opts = [opts_map[k] for k in sorted(opts_map.keys())]
        # Map letter answer like "B" or "b)" to option text if present
        resolved_ans = ans_raw
        letter_m = re.match(r"^([A-Da-d])(?:[.)])?$", ans_raw)
        if letter_m and letter_m.group(1).upper() in opts_map:
            resolved_ans = opts_map[letter_m.group(1).upper()]

        q_type = "MCQ" if len(opts) >= 2 else ("True/False" if resolved_ans.lower() in ("true", "false") else "Short Answer")

        items.append(
            {
                "question_number": q_num,
                "subject": default_subject,
                "subject_code": default_code,
                "semester": default_semester,
                "topic": default_topic,
                "unit": "",
                "difficulty": diff_val,
                "q_type": q_type,
                "marks": marks_val,
                "question": q_text,
                "options": opts,
                "correct_answer": resolved_ans,
                "explanation": exp_raw,
            }
        )
    return items


def chunk_text(text: str, chunk_size: int = 600, overlap: int = 100) -> list[dict[str, str]]:
    """Split extracted text into searchable overlapping chunks preserving section headers."""
    clean = (text or "").strip()
    if not clean:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", clean) if p.strip()]
    chunks: list[dict[str, str]] = []
    cur_section = "Overview"
    buf = ""

    for para in paragraphs:
        first_line = para.splitlines()[0].strip()
        if len(first_line) < 90 and (first_line.startswith("#") or first_line.startswith("--- Page") or re.match(r"^(unit|module|chapter|\d+\.)\b", first_line, re.I)):
            cur_section = first_line.lstrip("#- ").strip()[:80]

        if len(buf) + len(para) + 2 <= chunk_size:
            buf = f"{buf}\n\n{para}".strip()
        else:
            if buf:
                chunks.append({"section_title": cur_section, "content": buf})
            if len(para) > chunk_size:
                step = max(100, chunk_size - overlap)
                for start in range(0, len(para), step):
                    piece = para[start : start + chunk_size].strip()
                    if piece:
                        chunks.append({"section_title": cur_section, "content": piece})
                buf = ""
            else:
                buf = para
    if buf:
        chunks.append({"section_title": cur_section, "content": buf})
    return chunks


def retrieve_relevant_chunks(
    query: str,
    role: str,
    subject: str | None = None,
    semester: int | None = None,
    top_k: int = 4,
) -> list[dict[str, Any]]:
    """Retrieve the top-K relevant knowledge chunks permitted for the caller's role using TF-IDF + keyword fallback."""
    chunks = db.get_permitted_knowledge_chunks(role=role, subject=subject, semester=semester)
    if not chunks:
        # Broaden across subjects if subject-specific had none
        chunks = db.get_permitted_knowledge_chunks(role=role, subject=None, semester=semester)
    if not chunks or not query.strip():
        return []

    corpus = [f"{c['doc_title']} {c['subject']} {c['topic']} {c['section_title']} {c['content']}" for c in chunks]
    scored: list[tuple[float, dict[str, Any]]] = []
    try:
        vec = TfidfVectorizer(stop_words="english", max_features=3000)
        mat = vec.fit_transform(corpus + [query])
        sims = cosine_similarity(mat[-1], mat[:-1]).flatten()
        for sim, chunk in zip(sims, chunks):
            if sim > 0.03:
                scored.append((float(sim), chunk))
    except Exception:
        pass

    # Keyword overlap fallback if TF-IDF yields nothing
    if not scored:
        q_words = {w for w in re.findall(r"[a-z0-9]{3,}", query.lower())}
        for chunk in chunks:
            c_words = set(re.findall(r"[a-z0-9]{3,}", f"{chunk['doc_title']} {chunk['topic']} {chunk['content']}".lower()))
            overlap = len(q_words & c_words)
            if overlap > 0:
                scored.append((float(overlap), chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, chunk in scored[:top_k]:
        c_copy = dict(chunk)
        c_copy["relevance_score"] = round(score, 3)
        results.append(c_copy)
    return results
