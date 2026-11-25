"""SmartStudy Knowledge Center UI: Upload/Detect/Review, Searchable Library, Edit/Replace & Semantic Lookup."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
import db
import knowledge
from ui import render_header


def render() -> None:
    user = auth.require_role("student", "teacher", "admin")
    role = user["role"]
    username = user["username"]

    render_header(
        "📚 SmartStudy Knowledge Center",
        "Central document intelligence hub — upload notes, question papers, manuals & syllabi to power AI tutoring, quizzes, and revision.",
    )

    if role in ("teacher", "admin"):
        tab_lib, tab_up, tab_search = st.tabs(
            ["📖 Document Library & Permissions", "⬆️ Upload & Auto-Detect Document", "🔍 Semantic Knowledge Search"]
        )
    else:
        tab_lib, tab_search = st.tabs(
            ["📖 Permitted Course Materials", "🔍 Semantic Knowledge Search"]
        )
        tab_up = None

    # ------------------------------------------------------------------
    # TAB 1: SEARCHABLE DOCUMENT LIBRARY
    # ------------------------------------------------------------------
    with tab_lib:
        docs = db.get_knowledge_documents(role=role, username=username, include_archived=(role in ("teacher", "admin")))
        subjects = ["All"] + db.get_subject_names()
        cats = ["All"] + knowledge.DOC_CATEGORIES

        f1, f2, f3, f4 = st.columns([1.5, 1, 1, 0.9])
        with f1:
            q_search = st.text_input("🔎 Search library (title, topic, tags, content)", placeholder="Search keywords...")
        with f2:
            f_subj = st.selectbox("Subject", subjects, key="kb_lib_subj")
        with f3:
            f_cat = st.selectbox("Category", cats, key="kb_lib_cat")
        with f4:
            f_sem = st.selectbox("Semester", ["All", 1, 2, 3, 4, 5, 6, 7, 8], key="kb_lib_sem")

        shown = docs
        if f_subj != "All":
            shown = [d for d in shown if d["subject"] == f_subj]
        if f_cat != "All":
            shown = [d for d in shown if d["category"] == f_cat]
        if f_sem != "All":
            shown = [d for d in shown if d["semester"] == f_sem]
        if q_search.strip():
            ql = q_search.strip().lower()
            shown = [
                d
                for d in shown
                if ql in (d["title"] + d["subject"] + d["topic"] + d["tags"] + d["description"] + d["extracted_text"]).lower()
            ]

        st.caption(f"Showing **{len(shown)}** document(s) accessible to `{role.title()}`.")
        if not shown:
            st.info("No documents match the selected filters.")

        for doc in shown:
            sem_lbl = f"Sem {doc['semester']}" if doc["semester"] else "Sem N/A"
            with st.expander(
                f"📄 [{doc['category']}] {doc['title']} · {doc['subject'] or 'General'} ({sem_lbl}) · {doc['visibility']} · {doc['status']}"
            ):
                c_meta, c_act = st.columns([3, 1.2])
                with c_meta:
                    st.markdown(
                        f"**File:** `{doc['file_name']}` ({doc['doc_type']}) | **Topic:** {doc['topic'] or '—'} | "
                        f"**Uploader:** {doc['uploader_name']} | **Updated:** {doc['updated_at']}"
                    )
                    if doc["description"]:
                        st.write(doc["description"])
                    if doc["tags"]:
                        st.caption("Tags: " + doc["tags"])
                    missing = json.loads(doc.get("missing_fields_json") or "[]")
                    if missing:
                        st.caption("⚠️ Unfilled metadata fields: " + ", ".join(missing))
                with c_act:
                    file_bytes = db.read_file_bytes(doc.get("file_path", ""))
                    if file_bytes is not None:
                        st.download_button(
                            "📥 Download File",
                            data=file_bytes,
                            file_name=doc["file_name"],
                            key=f"kb_dl_{doc['id']}",
                            width="stretch",
                        )
                    else:
                        st.download_button(
                            "📥 Export Text",
                            data=doc["extracted_text"].encode("utf-8"),
                            file_name=f"{doc['title'][:30].replace(' ', '_')}.txt",
                            key=f"kb_dl_txt_{doc['id']}",
                            width="stretch",
                        )

                st.text_area("Extracted Content Preview", value=doc["extracted_text"][:2500], height=140, disabled=True, key=f"kb_prev_{doc['id']}")

                can_edit = role == "admin" or (role == "teacher" and doc["uploader_username"] == username)
                if can_edit:
                    with st.expander("✏️ Edit / Replace / History"):
                        with st.form(f"kb_edit_form_{doc['id']}"):
                            e1, e2 = st.columns(2)
                            with e1:
                                ed_title = st.text_input("Title", value=doc["title"])
                                ed_subj = st.text_input("Subject", value=doc["subject"])
                                ed_topic = st.text_input("Topic", value=doc["topic"])
                                ed_tags = st.text_input("Tags", value=doc["tags"])
                            with e2:
                                ed_cat = st.selectbox("Category", knowledge.DOC_CATEGORIES, index=knowledge.DOC_CATEGORIES.index(doc["category"]) if doc["category"] in knowledge.DOC_CATEGORIES else 0)
                                ed_vis = st.selectbox("Visibility", knowledge.DOC_VISIBILITIES, index=knowledge.DOC_VISIBILITIES.index(doc["visibility"]) if doc["visibility"] in knowledge.DOC_VISIBILITIES else 0)
                                ed_stat = st.selectbox("Status", knowledge.DOC_STATUSES, index=knowledge.DOC_STATUSES.index(doc["status"]) if doc["status"] in knowledge.DOC_STATUSES else 0)
                                ed_sem = st.number_input("Semester (0 if N/A)", 0, 8, int(doc["semester"] or 0))
                            ed_desc = st.text_area("Description", value=doc["description"], height=65)
                            ed_text = st.text_area("Extracted Text", value=doc["extracted_text"], height=130)
                            repl_file = st.file_uploader("Replace Source File (optional)", type=["pdf", "txt", "md", "docx", "csv", "xlsx", "json"], key=f"kb_repl_{doc['id']}")
                            b_save, b_del = st.columns(2)
                            save_clicked = b_save.form_submit_button("💾 Save Changes", type="primary", width="stretch")
                            del_clicked = b_del.form_submit_button("🗑️ Delete Document", width="stretch")

                        if save_clicked:
                            try:
                                fpath, fname = (None, None)
                                text_to_save = ed_text
                                if repl_file is not None:
                                    parsed = knowledge.extract_document_content(repl_file, "")
                                    fpath, fname, _ = knowledge.save_knowledge_file(repl_file)
                                    text_to_save = parsed["extracted_text"]
                                chunks = knowledge.chunk_text(text_to_save)
                                db.update_knowledge_document(
                                    doc["id"],
                                    ed_title,
                                    ed_subj,
                                    doc["subject_code"],
                                    ed_sem if ed_sem > 0 else None,
                                    ed_topic,
                                    ed_cat,
                                    ed_desc,
                                    text_to_save,
                                    ed_tags,
                                    ed_vis,
                                    ed_stat,
                                    username,
                                    chunks,
                                    fpath,
                                    fname,
                                )
                                db.log_activity(username, role, "KB_EDIT", f"Updated document #{doc['id']} ({ed_title})")
                                st.toast("Document updated!", icon="✅")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                        if del_clicked:
                            db.delete_knowledge_document(doc["id"])
                            db.log_activity(username, role, "KB_DELETE", f"Deleted document #{doc['id']} ({doc['title']})")
                            st.toast("Document deleted.", icon="🗑️")
                            st.rerun()

                        hist = db.get_document_history(doc["id"])
                        if hist:
                            st.markdown("**Modification History:**")
                            for h in hist:
                                st.caption(f"• {h['created_at']} — `{h['actor_username']}` **{h['action']}**: {h['summary']}")

    # ------------------------------------------------------------------
    # TAB 2: UPLOAD & AUTO-DETECT (TEACHER / ADMIN ONLY)
    # ------------------------------------------------------------------
    if tab_up is not None:
        with tab_up:
            st.markdown("### ⬆️ Upload & Analyze Document")
            st.caption("Supports PDF, DOCX, TXT, MD, CSV, Excel (.xlsx), JSON, or pasted text. Auto-detects metadata, sections, tables, and candidate questions without inventing missing values.")

            up_file = st.file_uploader("Upload Document (max 8 MB)", type=["pdf", "txt", "md", "docx", "csv", "xlsx", "json"], key="kb_upload_file")
            pasted = st.text_area("Or Paste Document / Notes / Question Paper Text", height=140, key="kb_paste_text")

            if st.button("🔍 Extract & Detect Metadata", type="primary"):
                try:
                    extracted = knowledge.extract_document_content(up_file, pasted)
                    saved_path, saved_name, saved_ext = ("", extracted["file_name"], extracted["ext"])
                    if up_file is not None:
                        saved_path, saved_name, saved_ext = knowledge.save_knowledge_file(up_file)
                    st.session_state["kb_preview_doc"] = {
                        **extracted,
                        "file_path": saved_path,
                        "file_name": saved_name,
                        "ext": saved_ext,
                    }
                    st.toast("Document parsed! Review detected metadata below before saving.", icon="🔍")
                except Exception as exc:
                    st.error(str(exc))

            prev = st.session_state.get("kb_preview_doc")
            if prev:
                st.markdown("---")
                st.markdown(f"#### Review & Confirm: `{prev['file_name']}` ({prev['doc_type']})")
                if prev["missing_fields"]:
                    st.warning("Missing fields (not invented — fill manually if known): **" + ", ".join(prev["missing_fields"]) + "**")
                if prev["detected_sections"]:
                    st.info("Detected Sections: " + " | ".join(prev["detected_sections"][:6]))
                if prev["tables"]:
                    st.caption(f"Detected **{len(prev['tables'])}** table(s) inside the document.")
                if prev["detected_questions"]:
                    st.success(f"Detected **{len(prev['detected_questions'])}** candidate question(s)! You can import them into the Question Bank after saving.")

                subj_opts = [""] + db.get_subject_names()
                with st.form("kb_confirm_save"):
                    c1, c2 = st.columns(2)
                    with c1:
                        in_title = st.text_input("Document Title *", value=Path(prev["file_name"]).stem.replace("_", " ").title())
                        det_s = prev["detected_subject"]
                        in_subj = st.selectbox("Subject", subj_opts, index=subj_opts.index(det_s) if det_s in subj_opts else 0)
                        in_topic = st.text_input("Topic", value=prev["detected_topic"])
                        in_tags = st.text_input("Tags (comma-separated)", value=(in_subj or "study").lower())
                    with c2:
                        det_cat = prev["detected_category"]
                        in_cat = st.selectbox("Document Category *", knowledge.DOC_CATEGORIES, index=knowledge.DOC_CATEGORIES.index(det_cat) if det_cat in knowledge.DOC_CATEGORIES else 0)
                        in_sem = st.number_input("Semester (0 = unspecified)", 0, 8, int(prev["detected_semester"] or 0))
                        default_vis = "Teachers Only" if in_cat in ("Question banks", "Question papers") else "Students & Teachers"
                        in_vis = st.selectbox("Visibility / Permissions", knowledge.DOC_VISIBILITIES, index=knowledge.DOC_VISIBILITIES.index(default_vis))
                        in_stat = st.selectbox("Status", knowledge.DOC_STATUSES, index=0)
                    in_desc = st.text_area("Description", height=65, placeholder="Brief summary for students or faculty...")
                    in_text = st.text_area("Extracted Content (Editable)", value=prev["extracted_text"], height=190)

                    also_import_qb = st.checkbox(
                        f"Also send {len(prev['detected_questions'])} detected question(s) to Question Bank Review",
                        value=bool(prev["detected_questions"]),
                        disabled=not bool(prev["detected_questions"]),
                    )
                    if st.form_submit_button("💾 Save to Knowledge Center", type="primary"):
                        if not in_title.strip() or not in_text.strip():
                            st.error("Title and extracted content cannot be empty.")
                        else:
                            chunks = knowledge.chunk_text(in_text)
                            missing_now = [f for f, v in [("subject", in_subj), ("semester", in_sem or None), ("topic", in_topic)] if not v]
                            subj_code = ""
                            for s in db.get_subjects():
                                if s["name"] == in_subj:
                                    subj_code = s["code"]
                                    break
                            doc_id = db.add_knowledge_document(
                                title=in_title,
                                file_name=prev["file_name"],
                                file_path=prev["file_path"],
                                file_ext=prev["ext"],
                                doc_type=prev["doc_type"],
                                subject=in_subj,
                                subject_code=subj_code,
                                semester=in_sem if in_sem > 0 else None,
                                topic=in_topic,
                                category=in_cat,
                                description=in_desc,
                                extracted_text=in_text,
                                detected_sections=prev["detected_sections"],
                                detected_tables=prev["tables"],
                                missing_fields=missing_now,
                                tags=in_tags,
                                visibility=in_vis,
                                status=in_stat,
                                uploader_username=username,
                                uploader_name=user["full_name"],
                                uploader_role=role,
                                chunks=chunks,
                            )
                            db.log_activity(username, role, "KB_UPLOAD", f"Saved document #{doc_id} ({in_title})")
                            if also_import_qb and prev["detected_questions"]:
                                for q in prev["detected_questions"]:
                                    q["subject"] = q.get("subject") or in_subj
                                    q["subject_code"] = q.get("subject_code") or subj_code
                                    q["semester"] = q.get("semester") or (in_sem if in_sem > 0 else None)
                                    q["topic"] = q.get("topic") or in_topic
                                st.session_state["qb_extract_preview"] = {
                                    "source_doc_id": doc_id,
                                    "source_doc_name": in_title,
                                    "questions": prev["detected_questions"],
                                }
                            st.session_state.pop("kb_preview_doc", None)
                            st.toast(f"Saved '{in_title}' ({len(chunks)} searchable chunks indexed)!", icon="📚")
                            st.rerun()

    # ------------------------------------------------------------------
    # TAB 3: SEMANTIC KNOWLEDGE SEARCH
    # ------------------------------------------------------------------
    with tab_search:
        st.markdown("### 🔍 Search Across Chunked Course Knowledge")
        c1, c2 = st.columns([2, 1])
        with c1:
            sem_q = st.text_input("Ask or search a concept", placeholder="e.g., How does BCNF differ from 3NF? or Kirchhoff loop law")
        with c2:
            sem_subj = st.selectbox("Subject Filter", ["All"] + db.get_subject_names(), key="kb_sem_subj")
        if sem_q.strip():
            hits = knowledge.retrieve_relevant_chunks(sem_q.strip(), role=role, subject=sem_subj, top_k=5)
            if not hits:
                st.info("No matching chunks found in permitted documents.")
            else:
                for h in hits:
                    with st.container(border=True):
                        st.markdown(f"**📄 {h['doc_title']}** · `{h['subject'] or 'General'}` · § *{h['section_title']}* (Relevance: `{h['relevance_score']}`)")
                        st.write(h["content"])
