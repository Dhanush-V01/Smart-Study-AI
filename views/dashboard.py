"""Student Overview & Performance Analytics Dashboard."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import ai
import auth
import db
from ui import (
    CHART_COLORS,
    INDIGO,
    TEAL,
    apply_plotly_theme,
    build_printable_report_html,
    compute_gamification,
    demo_badge_html,
    render_header,
    render_kpi_card,
)


def _fmt_minutes(minutes: int) -> str:
    if minutes <= 0:
        return "0m"
    hrs, mins = divmod(int(minutes), 60)
    if hrs and mins:
        return f"{hrs}h {mins}m"
    return f"{hrs}h" if hrs else f"{mins}m"


def render(student: dict) -> None:
    auth.require_role("student")
    student_id = student["id"]
    settings = db.get_settings()
    att_threshold = float(settings.get("attendance_threshold", 75))

    render_header(
        f"📊 Welcome back, {student['name']}!",
        f"{student['usn']} • {student['course']} {student['branch']} • {student['grade']} ({student['section']})",
        demo_badge_html(not ai.has_api_key()),
    )

    sessions = db.get_study_sessions(student_id)
    quizzes = db.get_quiz_attempts(student_id)
    skills = db.get_skills(student_id)
    portfolio = db.get_portfolio_items(student_id)
    att_summary = db.get_attendance_summary(student_id)
    assignments = db.get_assignments(student_id)
    streak = db.compute_study_streak(student_id)
    gami = compute_gamification(sessions, quizzes, skills, portfolio, streak)

    today_iso = date.today().isoformat()
    week_start_iso = (date.today() - timedelta(days=6)).isoformat()

    today_mins = sum(s["duration_minutes"] for s in sessions if s["session_date"] == today_iso)
    weekly_mins = sum(s["duration_minutes"] for s in sessions if s["session_date"] >= week_start_iso)
    avg_quiz = round(sum(q["score"] for q in quizzes) / len(quizzes), 1) if quizzes else 0.0
    overall_att = round(sum(a["pct"] for a in att_summary) / len(att_summary), 1) if att_summary else 100.0

    # 5 KPI Cards
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card("⏱️ Today's Study", _fmt_minutes(today_mins), "Logged today", "indigo")
    with c2:
        render_kpi_card("📅 Weekly Study", f"{round(weekly_mins / 60, 1)} hrs", f"{weekly_mins} mins (7d)", "teal")
    with c3:
        render_kpi_card("🏫 Attendance", f"{overall_att:.1f}%", f"Min target: {att_threshold:.0f}%", "amber" if overall_att < att_threshold else "teal")
    with c4:
        render_kpi_card("🔥 Study Streak", f"{streak}d", f"Level {gami['level']} • {gami['xp']} XP", "indigo")
    with c5:
        render_kpi_card("🎯 Avg Quiz", f"{avg_quiz:.1f}%" if quizzes else "—", f"{len(quizzes)} attempts", "teal")

    if gami["badges"]:
        st.markdown("**🏅 Unlocked Badges:** " + " &nbsp;•&nbsp; ".join(gami["badges"]))

    # Charts Row 1
    col_bar, col_donut = st.columns([1.35, 1])
    with col_bar:
        last_7 = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        totals = {d: 0.0 for d in last_7}
        for s in sessions:
            if s["session_date"] in totals:
                totals[s["session_date"]] += s["duration_minutes"] / 60.0
        bar_df = pd.DataFrame({"Date": [date.fromisoformat(d).strftime("%b %d") for d in last_7], "Hours": [round(totals[d], 2) for d in last_7]})
        fig_bar = px.bar(bar_df, x="Date", y="Hours", title="📈 Study Hours Per Day (Last 7 Days)", text="Hours", color_discrete_sequence=[INDIGO])
        fig_bar.update_traces(texttemplate="%{text:.1f}h", textposition="outside", marker_cornerradius=6)
        fig_bar.update_yaxes(title="Hours", rangemode="tozero")
        fig_bar.update_xaxes(title="")
        st.plotly_chart(apply_plotly_theme(fig_bar, height=330), width="stretch")

    with col_donut:
        if sessions:
            sess_df = pd.DataFrame(sessions)
            subj_df = sess_df.groupby("subject", as_index=False)["duration_minutes"].sum().sort_values("duration_minutes", ascending=False)
            subj_df["Hours"] = (subj_df["duration_minutes"] / 60.0).round(2)
            fig_donut = px.pie(subj_df, names="subject", values="Hours", hole=0.55, title="📚 Time by Subject", color_discrete_sequence=CHART_COLORS)
            fig_donut.update_traces(textinfo="percent+label", hovertemplate="%{label}: %{value:.1f} hrs<extra></extra>")
            st.plotly_chart(apply_plotly_theme(fig_donut, height=330), width="stretch")
        else:
            st.info("Log study sessions in **Study Planner** to view your subject breakdown.")

    # Charts Row 2
    col_line, col_weak = st.columns([1.35, 1])
    with col_line:
        if quizzes:
            q_df = pd.DataFrame(quizzes)
            fig_line = go.Figure()
            fig_line.add_trace(
                go.Scatter(
                    x=list(range(1, len(q_df) + 1)),
                    y=q_df["score"],
                    mode="lines+markers",
                    name="Quiz Score (%)",
                    line=dict(color=TEAL, width=3),
                    marker=dict(size=9, color=INDIGO, line=dict(width=2, color="#FFFFFF")),
                    text=q_df["subject"] + ": " + q_df["topic"] + " (" + q_df["attempt_date"] + ")",
                    hovertemplate="<b>%{text}</b><br>Score: %{y:.0f}%<extra></extra>",
                )
            )
            fig_line.update_layout(title="📝 Quiz Score Trend", xaxis_title="Attempt #", yaxis_title="Score (%)", yaxis=dict(range=[0, 108]))
            st.plotly_chart(apply_plotly_theme(fig_line, height=320), width="stretch")
        else:
            st.info("Take a practice quiz in **Exams & ML Insights** or **AI Assistant**.")

    with col_weak:
        st.markdown("### 🎯 Weak Areas")
        weak_subjects = db.get_weak_subjects(student_id, limit=2)
        for item in weak_subjects:
            bg = "#FEE2E2" if item["avg_score"] < 65 else "#FEF3C7"
            fg = "#991B1B" if item["avg_score"] < 65 else "#92400E"
            st.markdown(
                f"""
                <div class="ss-card" style="padding:0.75rem 1rem; margin-bottom:0.5rem;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-weight:700;color:#0F172A;">📘 {item['subject']}</span>
                        <span class="ss-badge" style="background:{bg};color:{fg};">{item['avg_score']:.1f}% avg ({item['attempts']} attempts)</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        sig = tuple((w["subject"], w["avg_score"]) for w in weak_subjects)
        if st.session_state.get("weak_sig") != sig:
            st.session_state["weak_sig"] = sig
            st.session_state["weak_rec"] = ai.get_weak_area_recommendation(weak_subjects)
        rec_text, rec_demo = st.session_state["weak_rec"]
        st.markdown(
            f"""
            <div class="ss-weak-card">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem;">
                    <span style="font-weight:700;color:#3730A3;">🤖 AI suggestion</span>
                    {demo_badge_html(rec_demo)}
                </div>
                <div style="color:#1E293B;font-size:0.9rem;">{rec_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Row 3: Alerts, Pending Assignments & Weekly Report Export
    st.markdown("---")
    c_alert, c_rep = st.columns([1.4, 1])
    with c_alert:
        st.markdown("### 🔔 Recent Alerts & Announcements")
        notifs = [n for n in db.get_notifications(student_id, "student") if not n["is_read"]][:4]
        if not notifs:
            st.success("All caught up! No unread alerts.")
        for n in notifs:
            nl, nr = st.columns([4.5, 1])
            with nl:
                st.warning(f"**{n['title']}** — {n['message']}")
            with nr:
                if st.button("✓ Read", key=f"dash_read_{n['id']}"):
                    db.mark_notification_read(n["id"], True)
                    st.rerun()

    with c_rep:
        st.markdown("### 📄 Weekly Student Report")
        pending_cnt = sum(1 for a in assignments if a["status"] in ("Pending", "Overdue"))
        low_att = [a["subject"] for a in att_summary if a["pct"] < att_threshold]
        st.write(f"- **Pending/Overdue Assignments:** {pending_cnt}")
        st.write(f"- **Attendance Warnings (<{att_threshold:.0f}%):** {', '.join(low_att) if low_att else 'None'}")
        st.write(f"- **Active Skills / Portfolio:** {len(skills)} skills, {len(portfolio)} items")

        report_df = pd.DataFrame(
            [
                {
                    "Student": student["name"],
                    "USN": student["usn"],
                    "Weekly_Study_Hours": round(weekly_mins / 60, 2),
                    "Study_Streak_Days": streak,
                    "Overall_Attendance_Pct": overall_att,
                    "Avg_Quiz_Pct": avg_quiz,
                    "Pending_Assignments": pending_cnt,
                    "Skills_Count": len(skills),
                    "Portfolio_Count": len(portfolio),
                    "XP": gami["xp"],
                    "Scholar_Level": gami["level"],
                    "Recommended_Action": rec_text,
                }
            ]
        )
        st.download_button(
            "📥 Download Weekly Report (CSV)",
            data=report_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{student['usn']}_weekly_report.csv",
            mime="text/csv",
            width="stretch",
        )
        report_html = build_printable_report_html(
            student,
            att_summary,
            db.get_assessments(student_id),
            quizzes,
            skills,
            db.get_feedback_for_student(student_id),
        )
        st.download_button(
            "🖨️ Printable Report Card (.html)",
            data=report_html.encode("utf-8"),
            file_name=f"{student['usn']}_report_card.html",
            mime="text/html",
            width="stretch",
        )
