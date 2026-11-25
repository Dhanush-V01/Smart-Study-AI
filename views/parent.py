"""Parent / Guardian Portal — strictly scoped to authorized linked student(s)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

import auth
import db
from ui import INDIGO, TEAL, apply_plotly_theme, build_printable_report_html, render_header, render_kpi_card


def render() -> None:
    user = auth.require_role("parent")
    linked = db.get_parent_linked_students(user["username"])

    render_header(
        "👨‍👩‍👧 Parent & Guardian Portal",
        f"Signed in as {user['full_name']} — View attendance alerts, assignments, upcoming exams, and academic progress for your linked student(s).",
    )

    if not linked:
        st.warning("No students are currently linked to this parent account. Please contact the Administrator.")
        return

    sel_idx = st.selectbox(
        "Authorized Student",
        list(range(len(linked))),
        format_func=lambda i: f"{linked[i]['avatar_emoji']} {linked[i]['name']} ({linked[i]['usn']} • {linked[i]['relationship']})",
    )
    student = linked[sel_idx]
    sid = student["id"]

    settings = db.get_settings()
    att_threshold = float(settings.get("attendance_threshold", 75))

    att_sum = db.get_attendance_summary(sid)
    overall_att = round(sum(a["pct"] for a in att_sum) / len(att_sum), 1) if att_sum else 100.0
    assigns = db.get_assignments(sid)
    pending_cnt = sum(1 for a in assigns if a["status"] in ("Pending", "Overdue"))
    assessments = db.get_assessments(sid)
    ia_avg = round(sum(100.0 * a["score"] / a["max_score"] for a in assessments) / len(assessments), 1) if assessments else 0.0
    quizzes = db.get_quiz_attempts(sid)
    quiz_avg = round(sum(q["score"] for q in quizzes) / len(quizzes), 1) if quizzes else 0.0

    # Absence / Low Attendance Alerts
    low_att = [a for a in att_sum if a["pct"] < att_threshold]
    for row in low_att:
        st.error(
            f"🚨 **Attendance Shortage Alert ({row['subject']}):** {row['pct']:.1f}% "
            f"({row['attended_classes']}/{row['total_classes']} classes) — below the {att_threshold:.0f}% institutional minimum."
        )
    if student.get("guardian_alerts_enabled", 1):
        abs_notifs = [n for n in db.get_notifications(sid, "student") if n["category"] == "Absence Alert" and not n["is_read"]]
        for an in abs_notifs[:3]:
            st.warning(f"📩 **{an['title']}** — {an['message']}")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card("📅 Overall Attendance", f"{overall_att:.1f}%", f"Threshold: {att_threshold:.0f}%", "amber" if low_att else "teal")
    with c2:
        render_kpi_card("📌 Pending/Overdue Work", str(pending_cnt), f"Out of {len(assigns)} assignments", "indigo")
    with c3:
        render_kpi_card("📊 Internal Assessment", f"{ia_avg:.1f}%", f"{len(assessments)} graded components", "teal")
    with c4:
        render_kpi_card("📝 Practice Quiz Avg", f"{quiz_avg:.1f}%" if quizzes else "—", f"{len(quizzes)} attempts", "indigo")

    t_att, t_prog, t_cal = st.tabs(["📅 Attendance & Absence Log", "📊 Progress & Assignments", "📢 Announcements & Upcoming Exams"])

    with t_att:
        if att_sum:
            df_att = pd.DataFrame(att_sum)
            fig = px.bar(df_att, x="subject", y="pct", title="Subject-Wise Attendance (%)", text="pct", color_discrete_sequence=[TEAL])
            fig.add_hline(y=att_threshold, line_dash="dash", line_color="#E11D48")
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_yaxes(range=[0, 112])
            fig.update_xaxes(title="")
            st.plotly_chart(apply_plotly_theme(fig, height=300), width="stretch")

        absences = [a for a in db.get_attendance(sid) if a["status"] != "Present"]
        if absences:
            st.markdown("#### Recent Absences / Late Marks")
            st.dataframe(pd.DataFrame(absences)[["att_date", "subject", "status"]].rename(columns={"att_date": "Date", "subject": "Subject", "status": "Status"}), hide_index=True, width="stretch")
        else:
            st.success("No recent absences recorded.")

    with t_prog:
        c_a, c_m = st.columns(2)
        with c_a:
            st.markdown("#### 📌 Assignments")
            if assigns:
                st.dataframe(pd.DataFrame(assigns)[["due_date", "subject", "title", "status", "marks"]], hide_index=True, width="stretch")
            else:
                st.info("No assignments assigned.")
        with c_m:
            st.markdown("#### 📈 Subject IA Summary")
            if assessments:
                ia_df = pd.DataFrame(assessments)
                ia_df["pct"] = (100.0 * ia_df["score"] / ia_df["max_score"]).round(1)
                subj_ia = ia_df.groupby("subject", as_index=False)["pct"].mean().round(1)
                fig_ia = px.bar(subj_ia, x="subject", y="pct", title="Average IA Score (%)", color_discrete_sequence=[INDIGO])
                fig_ia.update_yaxes(range=[0, 108])
                fig_ia.update_xaxes(title="")
                st.plotly_chart(apply_plotly_theme(fig_ia, height=280), width="stretch")

        feedback_rows = db.get_feedback_for_student(sid)
        st.markdown("#### 👩‍🏫 Teacher Progress Feedback")
        for fb in feedback_rows:
            st.info(f"**{fb['teacher_name']}** ({fb['created_at']}): **Strengths:** {fb['strengths']} | **Next Action:** {fb['next_action']}")

        report_html = build_printable_report_html(student, att_sum, assessments, quizzes, db.get_skills(sid), feedback_rows)
        st.download_button(
            "🖨️ Download Printable Student Report Card (.html)",
            data=report_html.encode("utf-8"),
            file_name=f"{student['usn']}_parent_report_card.html",
            mime="text/html",
        )

    with t_cal:
        c_ev, c_ann = st.columns(2)
        with c_ev:
            st.markdown("#### 🗓️ Upcoming Exams & Academic Milestones")
            evs = [e for e in db.get_calendar_events(sid) if e["event_type"] in ("Exam", "Assignment", "College Event")]
            if evs:
                st.dataframe(pd.DataFrame(evs)[["event_date", "event_type", "subject", "title"]], hide_index=True, width="stretch")
        with c_ann:
            st.markdown("#### 📢 College & Class Announcements")
            for ann in db.get_announcements():
                st.info(f"**{ann['title']}** ({ann['teacher_name']} • {ann['created_at']})\n\n{ann['message']}")
            st.markdown("#### 🔔 Academic Notifications")
            for n in db.get_notifications(sid, "student")[:5]:
                st.caption(f"• [{n['category']}] **{n['title']}** — {n['message']} ({n['created_at']})")
