"""Teacher Portal: Authorized Class Overview, Student Review/Feedback, Full Question Bank & Exam Builder, Attendance Edit & Events."""

from __future__ import annotations

import html
import json
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

import ai
import auth
import bulk
import db
import knowledge
import ml
from ui import INDIGO, TEAL, apply_plotly_theme, render_header, type_badge_html


def render(page: str) -> None:
    user = auth.require_role("teacher", "admin")
    teacher_name = user["full_name"]

    if page == "🏫 Class Overview & Alerts":
        _render_overview(user, teacher_name)
    elif page == "🔎 Student Review & Feedback":
        _render_student_review(user, teacher_name)
    elif page == "📝 Exam & Question Bank":
        _render_exam_builder(user, teacher_name)
    elif page == "📥 Academic Records & Bulk Ops":
        _render_academic_ops(user)


def _render_overview(user: dict, teacher_name: str) -> None:
    auth_subjs = auth.teacher_authorized_subjects(user)
    auth_students = auth.teacher_authorized_students(user)
    auth_ids = {s["id"] for s in auth_students}

    render_header(
        "👩‍🏫 Teacher Class Overview & Announcements",
        f"Signed in as {teacher_name} — Authorized Subjects: {', '.join(auth_subjs)}",
    )

    overview = [r for r in db.get_class_overview() if r["id"] in auth_ids]
    if not overview:
        st.info("No authorized students assigned yet.")
        return

    ov_df = pd.DataFrame(overview)
    table_df = ov_df[
        ["avatar_emoji", "usn", "name", "section", "attendance_pct", "avg_ia_pct", "avg_quiz_score", "weekly_study_hours", "skill_count", "portfolio_count"]
    ].rename(
        columns={
            "avatar_emoji": "",
            "usn": "USN",
            "name": "Student",
            "section": "Section",
            "attendance_pct": "Attendance %",
            "avg_ia_pct": "IA Avg %",
            "avg_quiz_score": "Quiz Avg %",
            "weekly_study_hours": "Study (hrs/wk)",
            "skill_count": "Skills",
            "portfolio_count": "Shared Portfolio",
        }
    )
    st.dataframe(table_df, hide_index=True, width="stretch")

    st.download_button(
        "📥 Download Class Overview Report (CSV)",
        data=table_df.to_csv(index=False).encode("utf-8"),
        file_name="class_overview_report.csv",
        mime="text/csv",
    )

    c1, c2 = st.columns(2)
    with c1:
        fig_q = px.bar(ov_df, x="name", y="avg_quiz_score", title="📝 Avg Quiz Score by Student", text="avg_quiz_score", color_discrete_sequence=[INDIGO])
        fig_q.update_traces(texttemplate="%{text:.1f}%", textposition="outside", marker_cornerradius=6)
        fig_q.update_yaxes(range=[0, 112], title="Score (%)")
        fig_q.update_xaxes(title="")
        st.plotly_chart(apply_plotly_theme(fig_q, height=310), width="stretch")
    with c2:
        fig_a = px.bar(ov_df, x="name", y="attendance_pct", title="📅 Attendance % by Student", text="attendance_pct", color_discrete_sequence=[TEAL])
        fig_a.update_traces(texttemplate="%{text:.1f}%", textposition="outside", marker_cornerradius=6)
        fig_a.update_yaxes(range=[0, 112], title="Attendance (%)")
        fig_a.update_xaxes(title="")
        st.plotly_chart(apply_plotly_theme(fig_a, height=310), width="stretch")

    st.markdown("---")
    c_ann, c_hist = st.columns([1, 1.2])
    with c_ann:
        st.markdown("### 📢 Send Announcement")
        with st.form("ann_form", clear_on_submit=True):
            a_title = st.text_input("Title *")
            a_sec = st.selectbox("Target Audience", ["All Sections", "Section A", "Section B"])
            a_msg = st.text_area("Message *", height=90)
            if st.form_submit_button("📣 Broadcast Announcement", type="primary", width="stretch"):
                if not a_title.strip() or not a_msg.strip():
                    st.error("Title and Message are required.")
                else:
                    db.add_announcement(teacher_name, a_title, a_msg, a_sec)
                    db.log_activity(user["username"], user["role"], "ANNOUNCEMENT", a_title)
                    st.toast("Announcement sent to students!", icon="📣")
                    st.rerun()
    with c_hist:
        st.markdown("### 📜 Recent Announcements")
        for ann in db.get_announcements()[:5]:
            st.info(f"**{ann['title']}** ({ann['target_section']} • {ann['created_at']})\n\n{ann['message']}")


def _render_student_review(user: dict, teacher_name: str) -> None:
    auth_ids = {s["id"] for s in auth.teacher_authorized_students(user)}
    overview = [r for r in db.get_class_overview() if r["id"] in auth_ids]

    render_header(
        "🔎 Student Review & Holistic Feedback",
        "Inspect authorized student academics, ML risk estimate, skills, and non-private portfolio items, then post feedback.",
    )
    if not overview:
        st.info("No authorized students available.")
        return

    sel_name = st.selectbox("Select Student", [s["name"] for s in overview])
    st_row = next(s for s in overview if s["name"] == sel_name)
    sid = st_row["id"]

    skills = db.get_skills(sid)
    portfolio = db.get_portfolio_items(sid, include_private=False)
    quizzes = db.get_quiz_attempts(sid)
    att_sum = db.get_attendance_summary(sid)
    assessments = db.get_assessments(sid)
    feedback_list = db.get_feedback_for_student(sid)

    if "ml_bundle" not in st.session_state:
        st.session_state["ml_bundle"] = ml.train_and_evaluate_models()
    ml_pred = ml.predict_student_performance(sid, st.session_state["ml_bundle"])
    st.caption(f"🧠 **ML Trajectory Estimate (not a guarantee):** {ml_pred['estimate_combined']}% • Tier: **{ml_pred['support_tier']}** ({ml_pred['on_track_prob']}% confidence)")

    t_acad, t_hol, t_fb = st.tabs(["📊 Attendance, Marks & Quizzes", "🌟 Skills & Portfolio", "✍️ Write Feedback"])

    with t_acad:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 📅 Attendance Summary")
            st.dataframe(pd.DataFrame(att_sum) if att_sum else pd.DataFrame(), hide_index=True, width="stretch")
        with c2:
            st.markdown("#### 📝 Recent Quizzes")
            if quizzes:
                st.dataframe(pd.DataFrame(quizzes)[["attempt_date", "subject", "topic", "score"]].iloc[::-1], hide_index=True, width="stretch")
            else:
                st.info("No quizzes taken.")
        if assessments:
            st.markdown("#### 📈 Internal Assessment Marks")
            st.dataframe(pd.DataFrame(assessments)[["recorded_date", "subject", "component", "score", "max_score"]], hide_index=True, width="stretch")

    with t_hol:
        st.markdown(f"#### 🎯 Skills ({len(skills)})")
        for sk in skills:
            st.markdown(f"- **{sk['name']}** (`{sk['category']}`) — Level **{sk['current_level']}/{sk['target_level']}**")
        st.markdown(f"#### 🏆 Portfolio ({len(portfolio)} teacher-visible/shared items)")
        for p in portfolio:
            st.markdown(
                f"<div class='ss-card' style='padding:0.8rem 1rem;'>{type_badge_html(p['item_type'])} "
                f"<strong>{html.escape(p['title'])}</strong> · {html.escape(p['issuer'])} ({html.escape(p['item_date'])})"
                f"<br><span style='font-size:0.85rem;color:#334155;'>{html.escape(p['description'] or '')}</span></div>",
                unsafe_allow_html=True,
            )

    with t_fb:
        target_opts: list[tuple[str, str, int | None]] = [("General (Overall Progress)", "general", None)]
        for sk in skills:
            target_opts.append((f"Skill: {sk['name']}", "skill", sk["id"]))
        for p in portfolio:
            target_opts.append((f"Portfolio: {p['title']}", "portfolio", p["id"]))

        with st.form("teacher_fb_form", clear_on_submit=True):
            t_idx = st.selectbox("Attach Feedback To", list(range(len(target_opts))), format_func=lambda i: target_opts[i][0])
            strengths = st.text_area("Strengths *")
            improvement = st.text_area("Improvement Area *")
            next_action = st.text_area("Next Action *")
            if st.form_submit_button("📨 Save Feedback", type="primary", width="stretch"):
                if not strengths.strip() or not improvement.strip() or not next_action.strip():
                    st.error("All 3 feedback fields are required.")
                else:
                    _, t_type, t_id = target_opts[t_idx]
                    db.add_feedback(sid, t_type, t_id, strengths.strip(), improvement.strip(), next_action.strip(), teacher_name)
                    db.log_activity(user["username"], user["role"], "FEEDBACK", f"Added feedback for {sel_name}")
                    st.toast(f"Feedback saved for {sel_name}!", icon="✅")
                    st.rerun()

        for fb in feedback_list:
            st.markdown(
                f"<div class='ss-feedback-box'><strong>👩‍🏫 {html.escape(fb['teacher_name'])}</strong> ({html.escape(fb['created_at'])})<br>"
                f"<b>Strengths:</b> {html.escape(fb['strengths'])}<br>"
                f"<b>Improvement:</b> {html.escape(fb['improvement_area'])}<br>"
                f"<b>Next Action:</b> {html.escape(fb['next_action'])}</div>",
                unsafe_allow_html=True,
            )


def _render_exam_builder(user: dict, teacher_name: str) -> None:
    render_header(
        "📝 Teacher Question Bank & Exam Builder",
        "Upload & auto-extract questions (PDF/DOCX/CSV/Excel/Text), review & edit in bulk, search/filter, and build multiple exams.",
    )
    subjects = auth.teacher_authorized_subjects(user)
    t_upload, t_bank, t_ai, t_exam = st.tabs(
        ["⬆️ Upload & Review Questions", "📚 Complete Question Bank", "🤖 AI Question Drafts", "🚀 Create & Manage Exams"]
    )

    # 1. UPLOAD & AUTOMATIC QUESTION EXTRACTION + EDITABLE REVIEW SCREEN
    with t_upload:
        st.markdown("### ⬆️ Upload Question Paper / Question Bank")
        st.caption("Supports PDF, DOCX, TXT, CSV, Excel (.xlsx), Pasted Text, or an existing Knowledge Center document. Missing fields are left blank (never invented).")

        src_mode = st.radio("Source", ["Upload File / Paste Text", "Import From Knowledge Center Document"], horizontal=True)
        if src_mode == "Upload File / Paste Text":
            qb_file = st.file_uploader("Upload Question File", type=["pdf", "txt", "md", "docx", "csv", "xlsx"], key="qb_up_file")
            qb_paste = st.text_area(
                "Or Paste Questions Text (e.g., `Q1. Question text? [2 marks]\\nA) opt1\\nB) opt2\\nAnswer: B`)",
                height=130,
                key="qb_paste_txt",
            )
            if st.button("🔍 Extract Questions for Review", type="primary"):
                try:
                    parsed = knowledge.extract_document_content(qb_file, qb_paste)
                    doc_id = None
                    if qb_file is not None or qb_paste.strip():
                        fpath, fname, fext = knowledge.save_knowledge_file(qb_file) if qb_file else ("", parsed["file_name"], ".txt")
                        doc_id = db.add_knowledge_document(
                            title=f"QB Source: {Path_stem(fname)}",
                            file_name=fname,
                            file_path=fpath,
                            file_ext=fext,
                            doc_type=parsed["doc_type"],
                            subject=parsed["detected_subject"],
                            subject_code=parsed["detected_code"],
                            semester=parsed["detected_semester"],
                            topic=parsed["detected_topic"],
                            category="Question banks",
                            description="Uploaded via Teacher Question Bank",
                            extracted_text=parsed["extracted_text"],
                            detected_sections=parsed["detected_sections"],
                            detected_tables=parsed["tables"],
                            missing_fields=parsed["missing_fields"],
                            tags="question-bank",
                            visibility="Teachers Only",
                            status="Active",
                            uploader_username=user["username"],
                            uploader_name=teacher_name,
                            uploader_role=user["role"],
                            chunks=knowledge.chunk_text(parsed["extracted_text"]),
                        )
                    st.session_state["qb_extract_preview"] = {
                        "source_doc_id": doc_id,
                        "source_doc_name": fname if qb_file else "Pasted Questions",
                        "questions": parsed["detected_questions"],
                    }
                    if not parsed["detected_questions"]:
                        st.warning("No structured numbered/tabular questions detected automatically — you can add rows manually in the review table below!")
                    else:
                        st.toast(f"Detected {len(parsed['detected_questions'])} question(s)! Review and confirm below.", icon="🔍")
                except Exception as exc:
                    st.error(str(exc))
        else:
            kb_docs = db.get_knowledge_documents(role=user["role"], username=user["username"])
            if not kb_docs:
                st.info("No Knowledge Center documents uploaded yet.")
            else:
                doc_labels = [f"#{d['id']} [{d['category']}] {d['title']} ({d['subject'] or 'General'})" for d in kb_docs]
                d_idx = st.selectbox("Select Knowledge Center Document", list(range(len(kb_docs))), format_func=lambda i: doc_labels[i])
                if st.button("🔍 Extract Questions from Selected Document", type="primary"):
                    doc = kb_docs[d_idx]
                    tbls = json.loads(doc.get("detected_tables_json") or "[]")
                    qs = knowledge.extract_questions_from_text(
                        doc["extracted_text"],
                        default_subject=doc["subject"],
                        default_code=doc["subject_code"],
                        default_semester=doc["semester"],
                        default_topic=doc["topic"],
                        tables=tbls,
                    )
                    st.session_state["qb_extract_preview"] = {
                        "source_doc_id": doc["id"],
                        "source_doc_name": doc["title"],
                        "questions": qs,
                    }
                    st.toast(f"Extracted {len(qs)} question(s) from '{doc['title']}'!", icon="🔍")

        # Editable Upload Review Screen
        prev = st.session_state.get("qb_extract_preview")
        if prev is not None:
            st.markdown("---")
            st.markdown(f"### ✅ Editable Question Review Screen — Source: `{prev['source_doc_name']}`")
            st.caption("Edit any cell, fill missing fields, uncheck rows to skip, or add new rows with `+` at the bottom.")

            rows_for_editor = []
            for idx, q in enumerate(prev["questions"], 1):
                q_txt = q.get("question", "")
                subj_val = q.get("subject", "")
                is_dup = db.question_exists_duplicate(q_txt, subj_val) if (q_txt and subj_val) else False
                rows_for_editor.append(
                    {
                        "Import": not is_dup,
                        "Q#": str(q.get("question_number") or idx),
                        "Subject": subj_val if subj_val in subjects else (subjects[0] if subjects else ""),
                        "Subject Code": q.get("subject_code", ""),
                        "Semester": int(q["semester"]) if q.get("semester") else 5,
                        "Topic": q.get("topic", ""),
                        "Unit": q.get("unit", ""),
                        "Difficulty": q.get("difficulty") if q.get("difficulty") in ("Easy", "Medium", "Hard") else "",
                        "Type": q.get("q_type") if q.get("q_type") in ("MCQ", "True/False", "Short Answer") else "MCQ",
                        "Marks": float(q["marks"]) if q.get("marks") is not None else 1.0,
                        "Question": q_txt,
                        "Options (|)": "|".join(q.get("options") or []),
                        "Correct Answer": q.get("correct_answer", ""),
                        "Explanation": q.get("explanation", ""),
                        "Duplicate?": "⚠️ Yes" if is_dup else "No",
                    }
                )
            if not rows_for_editor:
                rows_for_editor.append(
                    {
                        "Import": True,
                        "Q#": "1",
                        "Subject": subjects[0] if subjects else "DSA",
                        "Subject Code": "",
                        "Semester": 5,
                        "Topic": "",
                        "Unit": "",
                        "Difficulty": "",
                        "Type": "MCQ",
                        "Marks": 1.0,
                        "Question": "",
                        "Options (|)": "",
                        "Correct Answer": "",
                        "Explanation": "",
                        "Duplicate?": "No",
                    }
                )

            rev_df = pd.DataFrame(rows_for_editor)
            edited_rev = st.data_editor(
                rev_df,
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                disabled=["Duplicate?"],
                column_config={
                    "Import": st.column_config.CheckboxColumn("Import?", default=True),
                    "Subject": st.column_config.SelectboxColumn("Subject", options=subjects),
                    "Difficulty": st.column_config.SelectboxColumn("Difficulty", options=["", "Easy", "Medium", "Hard"]),
                    "Type": st.column_config.SelectboxColumn("Type", options=["MCQ", "True/False", "Short Answer"]),
                    "Marks": st.column_config.NumberColumn("Marks", min_value=0.5, max_value=100.0, step=0.5),
                    "Semester": st.column_config.NumberColumn("Sem", min_value=1, max_value=8, step=1),
                },
                key="qb_review_editor",
            )

            c_imp, c_clr = st.columns([2, 1])
            with c_imp:
                if st.button("✅ Confirm & Import Selected Questions to Permanent Question Bank", type="primary", width="stretch"):
                    imported = 0
                    skipped = 0
                    for _, row in edited_rev.iterrows():
                        if not bool(row.get("Import", True)):
                            continue
                        q_text = str(row.get("Question") or "").strip()
                        ans_text = str(row.get("Correct Answer") or "").strip()
                        subj_text = str(row.get("Subject") or "").strip()
                        if not q_text or not subj_text:
                            skipped += 1
                            continue
                        opts = [o.strip() for o in str(row.get("Options (|)") or "").split("|") if o.strip()]
                        db.add_question_to_bank(
                            subject=subj_text,
                            topic=str(row.get("Topic") or "").strip() or "General",
                            difficulty=str(row.get("Difficulty") or "").strip() or "Medium",
                            q_type=str(row.get("Type") or "MCQ").strip(),
                            question=q_text,
                            options=opts,
                            correct_answer=ans_text or "Pending Verification",
                            explanation=str(row.get("Explanation") or "").strip(),
                            marks=float(row.get("Marks") or 1.0),
                            source=f"Doc: {prev['source_doc_name'][:30]}",
                            approved_by_teacher=True,
                            question_number=str(row.get("Q#") or ""),
                            subject_code=str(row.get("Subject Code") or ""),
                            semester=int(row.get("Semester") or 5),
                            unit=str(row.get("Unit") or ""),
                            source_doc_id=prev.get("source_doc_id"),
                            source_doc_name=prev["source_doc_name"],
                            uploader_username=user["username"],
                        )
                        imported += 1
                    db.log_activity(user["username"], user["role"], "QB_IMPORT", f"Imported {imported} questions from {prev['source_doc_name']}")
                    st.session_state.pop("qb_extract_preview", None)
                    st.toast(f"Imported {imported} question(s)! ({skipped} skipped missing text)", icon="📚")
                    st.rerun()
            with c_clr:
                if st.button("Discard Preview", width="stretch"):
                    st.session_state.pop("qb_extract_preview", None)
                    st.rerun()

    # 2. COMPLETE SEARCHABLE, FILTERABLE, EDITABLE QUESTION BANK
    with t_bank:
        with st.expander("➕ Add Single Question Manually"):
            with st.form("add_q_form", clear_on_submit=True):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    q_subj = st.selectbox("Subject", subjects)
                with c2:
                    q_topic = st.text_input("Topic *", value="General")
                with c3:
                    q_diff = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"])
                with c4:
                    q_type = st.selectbox("Type", ["MCQ", "True/False", "Short Answer"])
                u1, u2, u3 = st.columns(3)
                with u1:
                    q_unit = st.text_input("Unit", placeholder="e.g., Unit 2")
                with u2:
                    q_sem = st.number_input("Semester", 1, 8, 5)
                with u3:
                    q_mks = st.number_input("Marks", 0.5, 50.0, 1.0, step=0.5)
                q_txt = st.text_area("Question Text *")
                q_opts = st.text_input("Options (pipe `|` separated)", value="Option A|Option B|Option C|Option D")
                q_ans = st.text_input("Correct Answer *")
                q_exp = st.text_input("Explanation")
                if st.form_submit_button("💾 Save Question", type="primary"):
                    if not q_txt.strip() or not q_ans.strip():
                        st.error("Question and Correct Answer are required.")
                    else:
                        opts = [o.strip() for o in q_opts.split("|") if o.strip()] if q_type != "Short Answer" else []
                        db.add_question_to_bank(q_subj, q_topic, q_diff, q_type, q_txt, opts, q_ans, q_exp, q_mks, source="Manual", approved_by_teacher=True, unit=q_unit, semester=int(q_sem), uploader_username=user["username"])
                        st.toast("Question saved to Question Bank!", icon="✅")
                        st.rerun()

        all_qb = db.get_question_bank("All", approved_only=False)
        # Filter bar
        f1, f2, f3, f4, f5 = st.columns([1.4, 1, 1, 1, 1])
        with f1:
            qb_search = st.text_input("🔎 Search Question Bank", placeholder="Search question, topic, unit, source...")
        with f2:
            f_subj = st.selectbox("Subject", ["All"] + subjects, key="qb_f_subj")
        with f3:
            f_diff = st.selectbox("Difficulty", ["All", "Easy", "Medium", "Hard"], key="qb_f_diff")
        with f4:
            f_type = st.selectbox("Type", ["All", "MCQ", "True/False", "Short Answer"], key="qb_f_type")
        with f5:
            sources_avail = ["All"] + sorted({(q.get("source_doc_name") or q.get("source") or "Manual") for q in all_qb})
            f_src = st.selectbox("Source", sources_avail, key="qb_f_src")

        f6, f7, f8 = st.columns([1, 1, 1])
        with f6:
            f_sem = st.selectbox("Semester", ["All", 1, 2, 3, 4, 5, 6, 7, 8], key="qb_f_sem")
        with f7:
            topics_avail = ["All"] + sorted({q["topic"] for q in all_qb if q["topic"]})
            f_top = st.selectbox("Topic", topics_avail, key="qb_f_top")
        with f8:
            sort_by = st.selectbox("Sort By", ["Newest", "Marks (High→Low)", "Subject", "Difficulty"], key="qb_sort")

        shown = all_qb
        if f_subj != "All":
            shown = [q for q in shown if q["subject"] == f_subj]
        if f_diff != "All":
            shown = [q for q in shown if q["difficulty"] == f_diff]
        if f_type != "All":
            shown = [q for q in shown if q["q_type"] == f_type]
        if f_sem != "All":
            shown = [q for q in shown if q.get("semester") == f_sem]
        if f_top != "All":
            shown = [q for q in shown if q["topic"] == f_top]
        if f_src != "All":
            shown = [q for q in shown if (q.get("source_doc_name") or q.get("source") or "Manual") == f_src]
        if qb_search.strip():
            ql = qb_search.strip().lower()
            shown = [q for q in shown if ql in (q["question"] + q["topic"] + (q.get("unit") or "") + (q.get("source_doc_name") or "")).lower()]

        if sort_by == "Marks (High→Low)":
            shown = sorted(shown, key=lambda x: x["marks"], reverse=True)
        elif sort_by == "Subject":
            shown = sorted(shown, key=lambda x: x["subject"])
        elif sort_by == "Difficulty":
            shown = sorted(shown, key=lambda x: x["difficulty"])

        st.caption(f"Showing **{len(shown)}** of {len(all_qb)} total question(s).")

        if shown:
            qb_rows = []
            for q in shown:
                opts = json.loads(q["options_json"] or "[]")
                qb_rows.append(
                    {
                        "id": q["id"],
                        "Delete": False,
                        "Approved": bool(q["approved_by_teacher"]),
                        "Subject": q["subject"],
                        "Sem": int(q.get("semester") or 5),
                        "Topic": q["topic"],
                        "Unit": q.get("unit") or "",
                        "Difficulty": q["difficulty"] or "Medium",
                        "Type": q["q_type"],
                        "Marks": float(q["marks"]),
                        "Question": q["question"],
                        "Options (|)": "|".join(opts),
                        "Correct Answer": q["correct_answer"],
                        "Explanation": q.get("explanation") or "",
                        "Source": q.get("source_doc_name") or q.get("source") or "Manual",
                    }
                )
            qb_df = pd.DataFrame(qb_rows)
            edited_qb = st.data_editor(
                qb_df,
                hide_index=True,
                width="stretch",
                disabled=["id", "Source"],
                column_config={
                    "Delete": st.column_config.CheckboxColumn("🗑️", default=False, width="small"),
                    "Approved": st.column_config.CheckboxColumn("✅", default=True, width="small"),
                    "Subject": st.column_config.SelectboxColumn("Subject", options=subjects),
                    "Difficulty": st.column_config.SelectboxColumn("Diff", options=["Easy", "Medium", "Hard"]),
                    "Type": st.column_config.SelectboxColumn("Type", options=["MCQ", "True/False", "Short Answer"]),
                },
                key="qb_bulk_editor",
            )
            b1, b2, b3 = st.columns([1.3, 1, 1])
            with b1:
                if st.button("💾 Save Question Bank Edits / Deletions", type="primary", width="stretch"):
                    changes = 0
                    for _, row in edited_qb.iterrows():
                        qid = int(row["id"])
                        if bool(row["Delete"]):
                            db.delete_question_from_bank(qid)
                            changes += 1
                            continue
                        opts = [o.strip() for o in str(row["Options (|)"] or "").split("|") if o.strip()]
                        db.update_question_in_bank(
                            qid,
                            str(row["Subject"]),
                            str(row["Topic"] or "General"),
                            str(row["Difficulty"] or "Medium"),
                            str(row["Type"] or "MCQ"),
                            str(row["Question"]),
                            opts,
                            str(row["Correct Answer"]),
                            str(row["Explanation"] or ""),
                            float(row["Marks"] or 1.0),
                            bool(row["Approved"]),
                            str(row["Unit"] or ""),
                            int(row["Sem"] or 5),
                        )
                        changes += 1
                    db.log_activity(user["username"], user["role"], "QB_BULK_EDIT", f"Saved/deleted {changes} questions")
                    st.toast("Question Bank updated!", icon="✅")
                    st.rerun()
            with b2:
                st.download_button("📥 Export CSV", data=qb_df.drop(columns=["Delete"]).to_csv(index=False).encode("utf-8"), file_name="question_bank.csv", mime="text/csv", width="stretch")
            with b3:
                st.download_button("📥 Export Excel", data=bulk.df_to_excel_bytes(qb_df.drop(columns=["Delete"])), file_name="question_bank.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")

    # 3. AI QUESTION BANK DRAFTS (WITH KNOWLEDGE CENTER GROUNDING)
    with t_ai:
        st.markdown("### 🤖 AI Question Bank Generator (Grounded in Knowledge Center)")
        c1, c2, c3 = st.columns(3)
        with c1:
            ai_subj = st.selectbox("Subject", subjects, key="tb_ai_s")
        with c2:
            ai_top = st.text_input("Topic", value="Binary Search & Trees", key="tb_ai_t")
        with c3:
            ai_diff = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], key="tb_ai_d")
        if st.button("✨ Generate 5 AI Draft Questions (Require Teacher Approval)", type="primary"):
            kb_hits = knowledge.retrieve_relevant_chunks(f"{ai_subj} {ai_top}", role=user["role"], subject=ai_subj, top_k=3)
            qs, _ = ai.generate_quiz(ai_subj, ai_top, ai_diff, knowledge_chunks=kb_hits)
            for q in qs:
                db.add_question_to_bank(ai_subj, ai_top, ai_diff, "MCQ", q["question"], q["options"], q["options"][q["correct_index"]], q["explanation"], 1.0, source="AI Draft", approved_by_teacher=False, uploader_username=user["username"])
            st.toast("5 AI drafts added! Approve them in 'Complete Question Bank' before publishing.", icon="🤖")
            st.rerun()

    # 4. CREATE MULTIPLE EXAMS FROM STORED QUESTION BANK
    with t_exam:
        approved = db.get_question_bank("All", approved_only=True)
        c_create, c_list = st.columns([1.2, 1])
        with c_create:
            st.markdown("### ⚡ 1-Click Auto-Build Exam")
            with st.form("auto_exam_form", clear_on_submit=True):
                ae_title = st.text_input("Auto Exam Title *", placeholder="e.g., DSA Medium Mock Test")
                ac1, ac2, ac3 = st.columns(3)
                with ac1:
                    ae_subj = st.selectbox("Subject", subjects, key="ae_s")
                with ac2:
                    ae_diff = st.selectbox("Difficulty", ["All", "Easy", "Medium", "Hard"], key="ae_d")
                with ac3:
                    ae_cnt = st.number_input("Questions", 1, 50, 5, key="ae_c")
                ac4, ac5, ac6 = st.columns(3)
                with ac4:
                    ae_mode = st.selectbox("Mode", ["Practice", "Timed"], key="ae_m")
                with ac5:
                    ae_dur = st.number_input("Duration (m)", 5, 180, 15, key="ae_dur")
                with ac6:
                    ae_neg = st.number_input("Neg Marks", 0.0, 2.0, 0.0, step=0.25, key="ae_neg")
                topics_for_s = ["All Topics"] + sorted({q["topic"] for q in approved if q["subject"] == ae_subj and q["topic"]})
                ae_topic = st.selectbox("Topic Filter", topics_for_s, key="ae_t")
                if st.form_submit_button("⚡ Auto-Build & Publish Exam", type="primary", width="stretch"):
                    matches = [
                        q for q in approved
                        if q["subject"] == ae_subj
                        and (ae_diff == "All" or (q["difficulty"] or "").lower() == ae_diff.lower())
                        and (ae_topic == "All Topics" or q["topic"] == ae_topic)
                    ]
                    if not ae_title.strip():
                        st.error("Provide an Auto Exam Title.")
                    elif not matches:
                        st.error("No approved questions match those filters in the Question Bank.")
                    else:
                        chosen_ids = [q["id"] for q in matches[: int(ae_cnt)]]
                        db.create_exam(ae_title, ae_subj, ae_topic, int(ae_dur), float(ae_neg), ae_mode, teacher_name, chosen_ids, True)
                        db.log_activity(user["username"], user["role"], "AUTO_PUBLISH_EXAM", f"{ae_title} ({len(chosen_ids)} Qs)")
                        st.toast(f"Published '{ae_title}' with {len(chosen_ids)} question(s)!", icon="⚡")
                        st.rerun()

            st.markdown("---")
            st.markdown("### 🚀 Manual Exam Builder (Combine Across Files)")
            st.caption("Combine approved questions across multiple uploaded files & topics.")
            with st.form("pub_exam_form", clear_on_submit=True):
                e_title = st.text_input("Exam Title *", placeholder="e.g., Unit 2–3 Combined Assessment")
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    e_subj = st.selectbox("Subject", subjects)
                with c2:
                    e_mode = st.selectbox("Mode", ["Practice", "Timed"])
                with c3:
                    e_dur = st.number_input("Duration (m)", 5, 180, 15)
                with c4:
                    e_neg = st.number_input("Neg Marks", 0.0, 2.0, 0.25, step=0.25)
                e_topic = st.text_input("Topic Coverage", value="Multi-Unit")
                q_choices = {
                    f"#{q['id']} [{q['subject']} · {q['difficulty']} · {q.get('source_doc_name') or q['source']}] {q['question'][:50]}": q["id"]
                    for q in approved
                }
                picked_labels = st.multiselect("Select Questions *", list(q_choices.keys()))
                if st.form_submit_button("🚀 Publish Exam", type="primary", width="stretch"):
                    if not e_title.strip() or not picked_labels:
                        st.error("Provide an Exam Title and select at least 1 question.")
                    else:
                        q_ids = [q_choices[lbl] for lbl in picked_labels]
                        db.create_exam(e_title, e_subj, e_topic, int(e_dur), float(e_neg), e_mode, teacher_name, q_ids, True)
                        db.log_activity(user["username"], user["role"], "PUBLISH_EXAM", e_title)
                        st.toast("Exam published to students!", icon="🚀")
                        st.rerun()
        with c_list:
            st.markdown("### 📋 Published Examinations")
            for ex in db.get_exams(published_only=False):
                with st.container(border=True):
                    st.markdown(f"**{ex['title']}** · `{ex['subject']}` · `{ex['mode']}`")
                    st.caption(f"{ex['question_count']} Qs | {ex['total_marks']} marks | {ex['duration_minutes']} min | -{ex['negative_marks']} neg")


def _render_academic_ops(user: dict) -> None:
    render_header(
        "📥 Attendance Correction, IA Marks, Class Events & Bulk Ops",
        "Take or correct attendance, enter marks, create assignments/events, and bulk-import spreadsheets.",
    )
    students = auth.teacher_authorized_students(user)
    subjects = auth.teacher_authorized_subjects(user)
    t_att, t_edit_att, t_ia, t_asg, t_ev, t_bulk = st.tabs(
        ["📅 Take Attendance", "✏️ Edit/Correct Attendance", "📊 Enter IA Marks", "📌 Assignments", "🗓️ Class Events", "📥 Bulk Import"]
    )

    with t_att:
        st.markdown("### 📅 Class Attendance Sheet (Side-by-Side P / A / L)")
        c1, c2, c3 = st.columns(3)
        with c1:
            a_subj = st.selectbox("Subject *", subjects, key="att_sheet_subj")
        with c2:
            sec_opts = ["All Sections"] + sorted({s["section"] for s in students})
            a_sec = st.selectbox("Class / Section", sec_opts, key="att_sheet_sec")
        with c3:
            a_dt = st.date_input("Class Date", value=date.today(), key="att_sheet_dt")

        class_students = [s for s in students if a_sec == "All Sections" or s["section"] == a_sec]
        if not class_students:
            st.info("No students in this section.")
        else:
            dt_iso = a_dt.isoformat()
            sheet_key = f"att_sheet_{a_subj}_{a_sec}_{dt_iso}"
            if sheet_key not in st.session_state:
                existing_rows = db.get_class_attendance(a_subj, dt_iso)
                existing_map = {r["student_id"]: r["status"] for r in existing_rows}
                st.session_state[sheet_key] = {
                    s["id"]: existing_map.get(s["id"], "Present") for s in class_students
                }

            status_map: dict[int, str] = st.session_state[sheet_key]
            for s in class_students:
                status_map.setdefault(s["id"], "Present")

            q1, q2, q3 = st.columns([1, 1, 2.5])
            with q1:
                if st.button("✅ Mark All P", width="stretch", key=f"all_p_{sheet_key}"):
                    for s in class_students:
                        status_map[s["id"]] = "Present"
                    st.rerun()
            with q2:
                if st.button("❌ Mark All A", width="stretch", key=f"all_a_{sheet_key}"):
                    for s in class_students:
                        status_map[s["id"]] = "Absent"
                    st.rerun()
            with q3:
                p_cnt = sum(1 for s in class_students if status_map[s["id"]] == "Present")
                a_cnt = sum(1 for s in class_students if status_map[s["id"]] == "Absent")
                l_cnt = sum(1 for s in class_students if status_map[s["id"]] == "Late")
                st.caption(f"Live Tally — **P:** {p_cnt} · **A:** {a_cnt} · **L:** {l_cnt}")

            for s in class_students:
                cur_st = status_map[s["id"]]
                r_info, r_p, r_a, r_l = st.columns([3.2, 0.8, 0.8, 0.8])
                with r_info:
                    badge_icon = {"Present": "🟢", "Absent": "🔴", "Late": "🟡"}.get(cur_st, "🟢")
                    st.markdown(f"{badge_icon} **`{s['usn']}`** {s['name']} · *{s['section']}* — **{cur_st}**")
                with r_p:
                    if st.button("P", key=f"att_p_{sheet_key}_{s['id']}", type="primary" if cur_st == "Present" else "secondary", width="stretch"):
                        status_map[s["id"]] = "Present"
                        st.rerun()
                with r_a:
                    if st.button("A", key=f"att_a_{sheet_key}_{s['id']}", type="primary" if cur_st == "Absent" else "secondary", width="stretch"):
                        status_map[s["id"]] = "Absent"
                        st.rerun()
                with r_l:
                    if st.button("L", key=f"att_l_{sheet_key}_{s['id']}", type="primary" if cur_st == "Late" else "secondary", width="stretch"):
                        status_map[s["id"]] = "Late"
                        st.rerun()

            if st.button("💾 Save Class Attendance", type="primary", width="stretch", key=f"save_att_{sheet_key}"):
                alerts_sent = 0
                for s in class_students:
                    st_val = status_map[s["id"]]
                    db.upsert_attendance(s["id"], a_subj, dt_iso, st_val)
                    if st_val == "Absent":
                        if db.add_absence_notification(s["id"], a_subj, dt_iso, user["full_name"]):
                            alerts_sent += 1
                db.log_activity(user["username"], user["role"], "ATTENDANCE_MARK", f"{a_subj} ({a_sec}) {dt_iso}: P={p_cnt}, A={a_cnt}, L={l_cnt}")
                msg = f"Saved attendance for {len(class_students)} students in {a_subj}!"
                if alerts_sent:
                    msg += f" Sent {alerts_sent} absence alert(s) to student/parent portals."
                st.toast(msg, icon="📅")

    with t_edit_att:
        st.markdown("### ✏️ Edit / Correct Recorded Attendance")
        c1, c2 = st.columns(2)
        with c1:
            ed_subj = st.selectbox("Filter Subject", ["All"] + subjects, key="att_ed_s")
        with c2:
            ed_date_on = st.checkbox("Filter by specific date")
            ed_dt = st.date_input("Date", value=date.today(), disabled=not ed_date_on, key="att_ed_d")
        att_rows = db.get_class_attendance(ed_subj, ed_dt.isoformat() if ed_date_on else None)
        if not att_rows:
            st.info("No attendance records match this filter.")
        else:
            att_df = pd.DataFrame(att_rows)
            edited_att = st.data_editor(
                att_df,
                hide_index=True,
                width="stretch",
                disabled=["id", "student_id", "usn", "student_name", "section", "subject", "att_date"],
                column_config={"status": st.column_config.SelectboxColumn("Status", options=["Present", "Absent", "Late"], required=True)},
                key="att_corr_editor",
            )
            if st.button("💾 Save Attendance Corrections", type="primary"):
                orig = {r["id"]: r["status"] for r in att_rows}
                upd = 0
                for _, row in edited_att.iterrows():
                    aid = int(row["id"])
                    if row["status"] != orig.get(aid):
                        db.update_attendance_by_id(aid, str(row["status"]))
                        upd += 1
                if upd:
                    db.log_activity(user["username"], user["role"], "ATTENDANCE_CORRECT", f"Updated {upd} records")
                    st.toast(f"Updated {upd} attendance record(s)!", icon="✅")
                    st.rerun()
                else:
                    st.info("No changes detected.")

    with t_ia:
        with st.form("enter_ia_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                st_nm = st.selectbox("Student", [s["name"] for s in students])
                subj = st.selectbox("Subject", subjects)
            with c2:
                comp = st.selectbox("Component", ["IA 1", "IA 2", "IA 3", "Assignment", "Lab", "Practical", "Exam"])
                rec_dt = st.date_input("Date", value=date.today())
            with c3:
                score = st.number_input("Score", 0.0, 100.0, 20.0, step=0.5)
                max_s = st.number_input("Max Score", 1.0, 100.0, 25.0, step=1.0)
            if st.form_submit_button("💾 Record Marks", type="primary"):
                if score > max_s:
                    st.error("Score cannot exceed Max Score.")
                else:
                    sid = next(s["id"] for s in students if s["name"] == st_nm)
                    db.add_assessment(sid, subj, comp, score, max_s, 0.35, rec_dt.isoformat())
                    st.toast("Marks recorded!", icon="📊")

    with t_asg:
        with st.form("teacher_asg_form", clear_on_submit=True):
            as_subj = st.selectbox("Subject", subjects)
            as_title = st.text_input("Assignment Title *")
            as_due = st.date_input("Due Date", value=date.today())
            as_desc = st.text_area("Instructions")
            targets = st.multiselect("Assign To", [s["name"] for s in students], default=[s["name"] for s in students])
            if st.form_submit_button("📌 Assign to Students", type="primary"):
                if not as_title.strip():
                    st.error("Title is required.")
                else:
                    name_map = {s["name"]: s["id"] for s in students}
                    for nm in targets:
                        db.add_assignment(name_map[nm], as_subj, as_title, as_desc, as_due.isoformat(), "Pending")
                    st.toast(f"Assigned to {len(targets)} students!", icon="📌")

    with t_ev:
        st.markdown("### 🗓️ Manage Class Events")
        with st.form("teacher_ev_form", clear_on_submit=True):
            ev_t = st.text_input("Event Title *")
            c1, c2, c3 = st.columns(3)
            with c1:
                ev_type = st.selectbox("Type", ["Exam", "Assignment", "College Event"])
            with c2:
                ev_subj = st.selectbox("Subject", subjects)
            with c3:
                ev_dt = st.date_input("Date", value=date.today())
            ev_desc = st.text_input("Details")
            if st.form_submit_button("➕ Publish Class Event", type="primary"):
                if not ev_t.strip():
                    st.error("Title required.")
                else:
                    db.add_calendar_event(None, ev_t, ev_type, ev_dt.isoformat(), ev_subj, ev_desc)
                    st.toast("Class event added!", icon="🗓️")
                    st.rerun()
        st.dataframe(pd.DataFrame(db.get_calendar_events()), hide_index=True, width="stretch")

    with t_bulk:
        _render_bulk_widget(["Attendance", "IA Marks", "Question Bank"], user)


def Path_stem(name: str) -> str:
    from pathlib import Path

    return Path(name).stem.replace("_", " ").title() or "Uploaded Document"


def _render_bulk_widget(allowed_modules: list[str], user: dict) -> None:
    mod = st.selectbox("Target Module", allowed_modules, key=f"bulk_mod_{user['role']}")
    tmpl_df = bulk.BULK_TEMPLATES[mod]
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(f"📥 Download {mod} Template (.csv)", data=tmpl_df.to_csv(index=False).encode("utf-8"), file_name=f"{mod.lower().replace(' ', '_')}_template.csv", mime="text/csv")
    with c2:
        st.download_button(f"📥 Download {mod} Template (.xlsx)", data=bulk.df_to_excel_bytes(tmpl_df), file_name=f"{mod.lower().replace(' ', '_')}_template.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    up_file = st.file_uploader(
        "Upload .csv, .xlsx, .json, .pdf, .docx, .txt, or .md",
        type=["csv", "xlsx", "json", "pdf", "docx", "txt", "md"],
        key=f"bulk_up_{user['role']}",
    )
    pasted = st.text_area("Or paste CSV / Tab-separated / Text rows", height=100, key=f"bulk_paste_{user['role']}")
    if st.button("🔍 Preview & Validate", key=f"bulk_val_{user['role']}"):
        try:
            raw_df = bulk.parse_uploaded_or_pasted(up_file, pasted, module=mod)
            valid, errs = bulk.validate_bulk_rows(mod, raw_df)
            st.session_state["bulk_preview"] = (mod, valid, errs)
        except Exception as exc:
            st.error(str(exc))

    prev = st.session_state.get("bulk_preview")
    if prev and prev[0] == mod:
        _, valid, errs = prev
        st.write(f"**Validation Summary:** ✅ {len(valid)} valid rows | ❌ {len(errs)} invalid rows")
        if valid:
            st.dataframe(pd.DataFrame(valid), hide_index=True, width="stretch")
            if st.button(f"🚀 Commit {len(valid)} Valid Rows", type="primary", key=f"bulk_commit_{user['role']}"):
                if mod == "Student Logins":
                    res_rows = db.bulk_create_student_logins(valid, user["username"])
                    st.session_state["last_generated_logins"] = res_rows
                    cnt = len(res_rows)
                elif mod == "Teacher Logins":
                    res_rows = db.bulk_create_teacher_logins(valid, user["username"])
                    st.session_state["last_generated_logins"] = res_rows
                    cnt = len(res_rows)
                else:
                    cnt = bulk.commit_bulk_rows(mod, valid, user["username"], user["role"])
                st.session_state.pop("bulk_preview", None)
                st.toast(f"Imported {cnt} records into {mod}!", icon="✅")
                st.rerun()
        gen_logins = st.session_state.get("last_generated_logins")
        if gen_logins and mod in ("Student Logins", "Teacher Logins"):
            gen_df = pd.DataFrame(gen_logins)
            st.success("Generated Login Credentials:")
            st.dataframe(gen_df, hide_index=True, width="stretch")
            st.download_button("📥 Download Generated Logins (.csv)", data=gen_df.to_csv(index=False).encode("utf-8"), file_name="generated_logins.csv", mime="text/csv")
        if errs:
            err_df = pd.DataFrame(errs)
            st.error("Invalid rows detected:")
            st.dataframe(err_df, hide_index=True, width="stretch")
            st.download_button("📥 Download Error Report (.csv)", data=err_df.to_csv(index=False).encode("utf-8"), file_name="import_errors.csv", mime="text/csv")
