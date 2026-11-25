"""Academics & Calendar view: Subjects, Attendance, IA Marks, Assignments, Calendar & Notifications."""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import auth
import db
from ui import INDIGO, TEAL, apply_plotly_theme, render_header

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".txt"}


def _save_assignment_file(uploaded_file) -> tuple[str, str]:
    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("Allowed file types: PNG, JPG, PDF, TXT.")
    raw = uploaded_file.getvalue()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("File must be <= 2 MB.")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"assign_{uuid.uuid4().hex}{ext}"
    dest = UPLOADS_DIR / safe_name
    dest.write_bytes(raw)
    db.save_file_blob(str(dest), uploaded_file.name, raw)
    return str(dest), uploaded_file.name


def render(student: dict) -> None:
    auth.require_role("student")
    student_id = student["id"]
    settings = db.get_settings()
    att_threshold = float(settings.get("attendance_threshold", 75))

    render_header(
        "📚 Academics, Attendance & Calendar",
        "Monitor subjects, attendance warnings, internal assessment marks, assignments, and academic events.",
    )

    tab_subj, tab_att, tab_ia, tab_assign, tab_cal = st.tabs(
        ["📖 Subjects", "📅 Attendance", "📊 IA Marks", "📌 Assignments", "🗓️ Calendar & Alerts"]
    )

    # 1. SUBJECTS & CURRICULUM
    with tab_subj:
        subjects = db.get_subjects()
        att_map = {a["subject"]: a for a in db.get_attendance_summary(student_id)}
        assessments = db.get_assessments(student_id)
        for s in subjects:
            topics = json.loads(s.get("topics_json") or "[]")
            att_info = att_map.get(s["name"], {})
            subj_ia = [a for a in assessments if a["subject"] == s["name"]]
            ia_avg = round(sum(100.0 * a["score"] / a["max_score"] for a in subj_ia) / len(subj_ia), 1) if subj_ia else 0.0
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**`{s['code']}` {s['name']}** · {s['credits']} Credits · `{s['category']}` · Faculty: *{s['teacher_name']}*")
                    st.caption("Chapters / Topics: " + (", ".join(topics) if topics else "Standard syllabus"))
                with c2:
                    st.metric("Attendance", f"{att_info.get('pct', 100.0):.1f}%")
                    st.caption(f"IA Avg: {ia_avg:.1f}%")

    # 2. ATTENDANCE
    with tab_att:
        att_sum = db.get_attendance_summary(student_id)
        if att_sum:
            att_df = pd.DataFrame(att_sum)
            for row in att_sum:
                if row["pct"] < att_threshold:
                    st.error(
                        f"⚠️ **Attendance Warning in {row['subject']}:** {row['pct']:.1f}% "
                        f"({row['attended_classes']}/{row['total_classes']} classes) — below the {att_threshold:.0f}% requirement!"
                    )
            fig_att = px.bar(
                att_df,
                x="subject",
                y="pct",
                title="📅 Attendance Percentage by Subject",
                text="pct",
                color="pct",
                color_continuous_scale=["#E11D48", "#F59E0B", "#0D9488"],
                range_color=[50, 100],
            )
            fig_att.add_hline(y=att_threshold, line_dash="dash", line_color="#4F46E5", annotation_text=f"Min {att_threshold:.0f}%")
            fig_att.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig_att.update_yaxes(range=[0, 112], title="Attendance (%)")
            fig_att.update_xaxes(title="")
            st.plotly_chart(apply_plotly_theme(fig_att, height=330), width="stretch")

        att_rows = db.get_attendance(student_id)
        if att_rows:
            st.markdown("#### Detailed Attendance Log")
            df_log = pd.DataFrame(att_rows)[["att_date", "subject", "status"]].rename(
                columns={"att_date": "Date", "subject": "Subject", "status": "Status"}
            )
            st.dataframe(df_log, hide_index=True, width="stretch")
        else:
            st.info("No attendance records logged yet.")

    # 3. INTERNAL ASSESSMENT & MARKS
    with tab_ia:
        assessments = db.get_assessments(student_id)
        if not assessments:
            st.info("No IA or exam marks recorded yet.")
        else:
            ia_df = pd.DataFrame(assessments)
            ia_df["pct"] = (100.0 * ia_df["score"] / ia_df["max_score"]).round(1)
            subj_avg = ia_df.groupby("subject", as_index=False)["pct"].mean().round(1)
            fig_ia = px.bar(subj_avg, x="subject", y="pct", title="📊 Overall Subject Performance (%)", text="pct", color_discrete_sequence=[INDIGO])
            fig_ia.update_traces(texttemplate="%{text:.1f}%", textposition="outside", marker_cornerradius=6)
            fig_ia.update_yaxes(range=[0, 112], title="Score (%)")
            fig_ia.update_xaxes(title="")
            st.plotly_chart(apply_plotly_theme(fig_ia, height=310), width="stretch")

            st.dataframe(
                ia_df[["recorded_date", "subject", "component", "score", "max_score", "pct", "weightage"]].rename(
                    columns={"recorded_date": "Date", "subject": "Subject", "component": "Component", "score": "Score", "max_score": "Max", "pct": "Pct (%)", "weightage": "Weight"}
                ),
                hide_index=True,
                width="stretch",
            )
            st.download_button(
                "📥 Export Academic Marks (CSV)",
                data=ia_df.to_csv(index=False).encode("utf-8"),
                file_name=f"{student['usn']}_marks.csv",
                mime="text/csv",
            )

    # 4. ASSIGNMENTS & DEADLINES
    with tab_assign:
        assigns = db.get_assignments(student_id)
        status_filter = st.selectbox("Filter Status", ["All", "Pending", "Overdue", "Submitted", "Completed"])
        filtered = [a for a in assigns if status_filter == "All" or a["status"] == status_filter]
        if not filtered:
            st.info("No assignments match this filter.")
        for a in filtered:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1.3])
                with c1:
                    st.markdown(f"**[{a['subject']}] {a['title']}** — Due: `{a['due_date']}` · Status: **{a['status']}**")
                    st.caption(a["description"] or "No description.")
                    if a["marks"] is not None:
                        st.caption(f"Scored: **{a['marks']} / {a['max_marks']}**")
                with c2:
                    new_stat = st.selectbox(
                        "Update Status",
                        ["Pending", "Submitted", "Completed", "Overdue"],
                        index=["Pending", "Submitted", "Completed", "Overdue"].index(a["status"]),
                        key=f"asg_stat_{a['id']}",
                    )
                    if st.button("Save", key=f"asg_btn_{a['id']}", width="stretch"):
                        db.update_assignment_status(a["id"], new_stat)
                        st.toast("Assignment updated!", icon="📌")
                        st.rerun()

        with st.expander("➕ Add Personal Assignment / Submission"):
            with st.form("add_assign_form", clear_on_submit=True):
                a_subj = st.selectbox("Subject", db.get_subject_names())
                a_title = st.text_input("Assignment Title *")
                a_due = st.date_input("Due Date", value=date.today())
                a_desc = st.text_area("Notes / Description")
                a_file = st.file_uploader("Optional Attachment (≤2 MB)", type=["png", "jpg", "jpeg", "pdf", "txt"])
                if st.form_submit_button("💾 Save Assignment", type="primary"):
                    if not a_title.strip():
                        st.error("Title is required.")
                    else:
                        try:
                            fpath, fname = _save_assignment_file(a_file) if a_file else ("", "")
                            db.add_assignment(student_id, a_subj, a_title, a_desc, a_due.isoformat(), "Pending", None, 20.0, fpath, fname)
                            st.toast("Assignment added!", icon="✅")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

    # 5. CALENDAR & NOTIFICATIONS
    with tab_cal:
        c_events, c_notif = st.columns([1.2, 1])
        with c_events:
            st.markdown("### 🗓️ Academic Calendar")
            ev_filter = st.selectbox("Event Type", ["All", "Exam", "Assignment", "College Event", "Study", "Personal"])
            events = db.get_calendar_events(student_id)
            shown = [e for e in events if ev_filter == "All" or e["event_type"] == ev_filter]
            if shown:
                ev_df = pd.DataFrame(shown)[["event_date", "event_type", "subject", "title", "description"]].rename(
                    columns={"event_date": "Date", "event_type": "Type", "subject": "Subject", "title": "Event", "description": "Details"}
                )
                st.dataframe(ev_df, hide_index=True, width="stretch")
            with st.form("add_cal_event", clear_on_submit=True):
                ev_title = st.text_input("Add Personal Event / Reminder")
                e1, e2 = st.columns(2)
                with e1:
                    ev_type = st.selectbox("Type", ["Study", "Personal", "Exam", "Assignment"])
                with e2:
                    ev_date = st.date_input("Date", value=date.today())
                if st.form_submit_button("➕ Add to Calendar"):
                    if not ev_title.strip():
                        st.error("Enter an event title.")
                    else:
                        db.add_calendar_event(student_id, ev_title, ev_type, ev_date.isoformat(), "General", "")
                        st.toast("Event added to calendar!", icon="🗓️")
                        st.rerun()

        with c_notif:
            st.markdown("### 🔔 Notifications & Class Announcements")
            for ann in db.get_announcements()[:3]:
                st.info(f"📢 **{ann['title']}** ({ann['teacher_name']} • {ann['created_at']})\n\n{ann['message']}")
            for n in db.get_notifications(student_id, "student"):
                label = "✅ " if n["is_read"] else "🔴 "
                with st.expander(f"{label}{n['title']} ({n['created_at']})", expanded=not n["is_read"]):
                    st.write(n["message"])
                    if not n["is_read"]:
                        if st.button("Mark as read", key=f"cal_read_{n['id']}"):
                            db.mark_notification_read(n["id"], True)
                            st.rerun()
