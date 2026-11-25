"""AI Doubt Solver (with follow-up chat), Summarizer, Flashcards & Digital Notes."""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import ai
import auth
import db
import knowledge
from ui import demo_badge_html, render_header

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".txt", ".md"}


def _save_note_file(uploaded_file) -> tuple[str, str]:
    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("Allowed formats: PNG, JPG, PDF, TXT, MD.")
    raw = uploaded_file.getvalue()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("File exceeds 2 MB limit.")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"note_{uuid.uuid4().hex}{ext}"
    dest = UPLOADS_DIR / safe_name
    dest.write_bytes(raw)
    db.save_file_blob(str(dest), uploaded_file.name, raw)
    return str(dest), uploaded_file.name


def render(student: dict) -> None:
    auth.require_role("student")
    student_id = student["id"]
    subjects = db.get_subject_names()

    render_header(
        "🤖 AI Study Assistant & Digital Notes",
        "Ask doubts with follow-up chat, summarize notes, generate flashcards, and organize study resources.",
        demo_badge_html(not ai.has_api_key()),
    )

    tab_doubt, tab_hist, tab_tools, tab_notes = st.tabs(
        ["💡 AI Doubt Solver", "🕘 Doubt History", "✨ Summarizer & Flashcards", "📒 Digital Notes"]
    )

    # 1. DOUBT SOLVER + FOLLOW-UP CHAT
    with tab_doubt:
        c_ask, c_info = st.columns([1.45, 1])
        with c_ask:
            with st.form("doubt_form", clear_on_submit=False):
                subject = st.selectbox("Subject", subjects, key="doubt_subject")
                question = st.text_area(
                    "Ask a Concept Doubt",
                    placeholder="e.g., Why does Binary Search run in O(log n)? or Explain 3NF with an example.",
                    height=105,
                )
                submitted = st.form_submit_button("✨ Solve My Doubt", type="primary", width="stretch")

            if submitted:
                if not question.strip():
                    st.error("Please type your doubt first.")
                else:
                    with st.spinner("Searching Knowledge Center & generating step-by-step explanation..."):
                        kb_hits = knowledge.retrieve_relevant_chunks(question.strip(), role="student", subject=subject, semester=student.get("semester"), top_k=3)
                        ans, is_demo = ai.solve_doubt(subject, question.strip(), knowledge_chunks=kb_hits)
                    doubt_id = db.add_doubt(student_id, subject, question.strip(), ans, is_demo)
                    st.session_state["latest_doubt"] = {
                        "id": doubt_id,
                        "subject": subject,
                        "question": question.strip(),
                        "answer": ans,
                        "is_demo": is_demo,
                    }
                    st.toast("Doubt solved and saved!", icon="✅")

        with c_info:
            st.markdown(
                """
                <div class="ss-card">
                    <h4 style="margin:0 0 0.4rem 0;color:#1E1B4B;">💬 Conversational Learning</h4>
                    <p style="margin:0;color:#475569;font-size:0.88rem;">
                        Every doubt includes a step-by-step breakdown, an example or analogy, and follow-up Q&A.
                        Ready to test mastery? Jump to <b>Exams & ML Insights</b> to generate a 5-question quiz!
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        latest = st.session_state.get("latest_doubt")
        if latest:
            st.markdown("---")
            st.markdown(f"#### 💡 Explanation — `{latest['subject']}` {demo_badge_html(latest['is_demo'])}", unsafe_allow_html=True)
            st.markdown(f"**Question:** {latest['question']}")
            st.markdown(latest["answer"])
            st.markdown('<div class="ss-ai-note">⚠️ AI-generated, please verify</div>', unsafe_allow_html=True)

            # Follow-up thread
            followups = db.get_doubt_followups(latest["id"])
            for msg in followups:
                if msg["sender"] == "student":
                    st.markdown(f"**🧑‍🎓 Follow-up:** {msg['content']}")
                else:
                    st.info(f"🤖 {msg['content']}\n\n⚠️ *AI-generated, please verify*")

            with st.form("followup_form", clear_on_submit=True):
                fu_q = st.text_input("Ask a follow-up question on this answer...")
                if st.form_submit_button("💬 Send Follow-up"):
                    if not fu_q.strip():
                        st.error("Enter a follow-up question.")
                    else:
                        db.add_doubt_followup(latest["id"], "student", fu_q.strip())
                        fu_ans, _ = ai.follow_up_doubt(latest["subject"], latest["question"], latest["answer"], fu_q.strip())
                        db.add_doubt_followup(latest["id"], "ai", fu_ans)
                        st.rerun()

    # 2. DOUBT HISTORY
    with tab_hist:
        f_subj = st.selectbox("Filter by Subject", ["All"] + subjects, key="doubt_hist_filter")
        doubts = db.get_doubts(student_id, f_subj)
        if not doubts:
            st.info("No saved doubts for this filter yet.")
        for d in doubts:
            with st.expander(f"📘 [{d['subject']}] {d['question']} — {d['created_at']}"):
                st.markdown(d["answer"])
                for msg in db.get_doubt_followups(d["id"]):
                    st.caption(f"{'🧑‍🎓 You' if msg['sender'] == 'student' else '🤖 AI'}: {msg['content']}")
                st.markdown(f'<div class="ss-ai-note">⚠️ AI-generated, please verify</div> {demo_badge_html(bool(d["is_demo"]))}', unsafe_allow_html=True)

    # 3. SUMMARIZER & FLASHCARDS
    with tab_tools:
        c_sum, c_fc = st.columns(2)
        with c_sum:
            st.markdown("### 📝 AI Notes & Knowledge Summarizer")
            notes_list = db.get_notes(student_id)
            kb_docs = db.get_knowledge_documents(role="student", username=student["name"])
            note_choices = (
                ["(Paste custom text)"]
                + [f"[My Note] {n['subject']}: {n['title']}" for n in notes_list]
                + [f"[Knowledge Center] {d['subject'] or 'General'}: {d['title']}" for d in kb_docs]
            )
            picked = st.selectbox("Source", note_choices)
            default_txt = ""
            sum_subj = subjects[0]
            if picked.startswith("[My Note]"):
                idx = note_choices.index(picked) - 1
                default_txt = notes_list[idx]["content"]
                sum_subj = notes_list[idx]["subject"]
            elif picked.startswith("[Knowledge Center]"):
                idx = note_choices.index(picked) - 1 - len(notes_list)
                default_txt = kb_docs[idx]["extracted_text"]
                sum_subj = kb_docs[idx]["subject"] or subjects[0]
            s_subj = st.selectbox("Subject", subjects, index=subjects.index(sum_subj) if sum_subj in subjects else 0, key="sum_subj")
            raw_text = st.text_area("Notes Content to Summarize", value=default_txt, height=150)
            if st.button("✨ Summarize Key Points", type="primary", width="stretch"):
                if not raw_text.strip():
                    st.error("Paste notes or select a saved note first.")
                else:
                    summary, s_demo = ai.summarize_notes(s_subj, raw_text.strip())
                    st.session_state["last_summary"] = (summary, s_demo)
            if "last_summary" in st.session_state:
                s_txt, s_demo = st.session_state["last_summary"]
                st.markdown(s_txt)
                st.markdown(f'<div class="ss-ai-note">⚠️ AI-generated, please verify</div> {demo_badge_html(s_demo)}', unsafe_allow_html=True)

        with c_fc:
            st.markdown("### 🃏 Revision Flashcard Generator")
            fc_subj = st.selectbox("Subject", subjects, key="fc_subj")
            fc_topic = st.text_input("Topic or Concept", value="Normalization & SQL Joins")
            if st.button("🃏 Generate Flashcards", width="stretch"):
                cards, fc_demo = ai.generate_flashcards(fc_subj, fc_topic)
                st.session_state["last_flashcards"] = (cards, fc_demo)
            if "last_flashcards" in st.session_state:
                cards, fc_demo = st.session_state["last_flashcards"]
                st.markdown(demo_badge_html(fc_demo), unsafe_allow_html=True)
                for idx, card in enumerate(cards, 1):
                    with st.expander(f"Card {idx}: {card['front']}"):
                        st.success(card["back"])
                st.markdown('<div class="ss-ai-note">⚠️ AI-generated, please verify</div>', unsafe_allow_html=True)

    # 4. DIGITAL NOTES & RESOURCES
    with tab_notes:
        with st.expander("➕ Add New Digital Note / Resource"):
            with st.form("add_note_form", clear_on_submit=True):
                n1, n2 = st.columns(2)
                with n1:
                    n_subj = st.selectbox("Subject", subjects)
                    n_title = st.text_input("Note Title *")
                    n_tags = st.text_input("Tags (comma-separated)", placeholder="exam-prep,formulas")
                with n2:
                    n_topic = st.text_input("Topic *")
                    n_url = st.text_input("Reference Link (optional)", placeholder="https://...")
                    n_rev_date = st.date_input("Revision Date", value=date.today())
                n_content = st.text_area("Note Content *", height=110)
                n_rev = st.checkbox("Mark as Needs Revision")
                n_file = st.file_uploader("Optional Resource File (≤2 MB)", type=["png", "jpg", "jpeg", "pdf", "txt", "md"])
                if st.form_submit_button("💾 Save Note", type="primary"):
                    if not n_title.strip() or not n_topic.strip() or not n_content.strip():
                        st.error("Title, Topic, and Content are required.")
                    else:
                        try:
                            fpath, fname = _save_note_file(n_file) if n_file else ("", "")
                            db.add_note(student_id, n_subj, n_topic, n_title, n_content, n_tags, n_url, fpath, fname, n_rev, n_rev_date.isoformat())
                            st.toast("Note saved!", icon="📒")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

        search_q = st.text_input("🔎 Search notes by title, subject, or tag", placeholder="Type keyword...")
        notes = db.get_notes(student_id)
        if search_q.strip():
            q_low = search_q.strip().lower()
            notes = [n for n in notes if q_low in (n["title"] + n["subject"] + n["tags"] + n["content"]).lower()]

        if notes:
            export_df = pd.DataFrame(notes)[["subject", "topic", "title", "tags", "needs_revision", "revision_date", "content"]]
            st.download_button("📥 Export Notes (CSV)", data=export_df.to_csv(index=False).encode("utf-8"), file_name="my_notes.csv", mime="text/csv")
        else:
            st.info("No notes match your search.")

        for n in notes:
            with st.container(border=True):
                c_left, c_right = st.columns([4, 1])
                with c_left:
                    rev_tag = "🔁 Needs Revision" if n["needs_revision"] else "✅ Reviewed"
                    st.markdown(f"**[{n['subject']}] {n['title']}** · `{n['topic']}` · {rev_tag}")
                    st.write(n["content"])
                    if n["tags"]:
                        st.caption("Tags: " + n["tags"])
                    if n["resource_url"]:
                        st.caption(f"Link: {n['resource_url']}")
                with c_right:
                    if st.button("🔁 Toggle Rev", key=f"tog_rev_{n['id']}", width="stretch"):
                        db.toggle_note_revision(n["id"], not bool(n["needs_revision"]))
                        st.rerun()
                    if st.button("🗑️ Delete", key=f"del_note_{n['id']}", width="stretch"):
                        db.delete_note(n["id"])
                        st.rerun()
