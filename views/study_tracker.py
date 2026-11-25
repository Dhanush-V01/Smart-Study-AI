"""Smart Study Planner, Pomodoro & Stopwatch Timer, Tasks, Goals & Habits."""

from __future__ import annotations

import json
import time
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

import ai
import auth
import db
from ui import TEAL, apply_plotly_theme, demo_badge_html, render_header


def _init_timer_state() -> None:
    defaults = {
        "timer_kind": "Pomodoro",
        "pomo_focus_min": 25,
        "pomo_break_min": 5,
        "pomo_mode": "Focus",
        "pomo_running": False,
        "pomo_remaining": 25 * 60,
        "sw_elapsed": 0,
        "pomo_last_tick": None,
        "pomo_subject": db.SUBJECTS[0],
        "pomo_topic": "Focused Practice",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _sync_timer(student_id: int) -> None:
    if not st.session_state["pomo_running"]:
        st.session_state["pomo_last_tick"] = None
        return
    now = time.time()
    last = st.session_state.get("pomo_last_tick")
    if last is None:
        st.session_state["pomo_last_tick"] = now
        return
    elapsed = int(now - last)
    if elapsed >= 1:
        if st.session_state["timer_kind"] == "Stopwatch":
            st.session_state["sw_elapsed"] += elapsed
        else:
            st.session_state["pomo_remaining"] = max(0, st.session_state["pomo_remaining"] - elapsed)
        st.session_state["pomo_last_tick"] = now

    if st.session_state["timer_kind"] == "Pomodoro" and st.session_state["pomo_remaining"] <= 0:
        st.session_state["pomo_running"] = False
        st.session_state["pomo_last_tick"] = None
        if st.session_state["pomo_mode"] == "Focus":
            mins = int(st.session_state["pomo_focus_min"])
            db.add_study_session(
                student_id=student_id,
                subject=st.session_state["pomo_subject"],
                topic=st.session_state["pomo_topic"].strip() or "Pomodoro Focus Block",
                duration_minutes=mins,
                session_date=date.today().isoformat(),
                notes="Auto-logged from completed Pomodoro focus timer",
                source="Pomodoro",
            )
            st.toast(f"Pomodoro complete! Logged {mins}m.", icon="🍅")
            st.session_state["pomo_mode"] = "Break"
            st.session_state["pomo_remaining"] = int(st.session_state["pomo_break_min"]) * 60
        else:
            st.toast("Break complete! Ready for Focus.", icon="⚡")
            st.session_state["pomo_mode"] = "Focus"
            st.session_state["pomo_remaining"] = int(st.session_state["pomo_focus_min"]) * 60


@st.fragment(run_every=1)
def _render_timer_clock(student_id: int) -> None:
    _sync_timer(student_id)
    if st.session_state["timer_kind"] == "Stopwatch":
        mins, secs = divmod(int(st.session_state["sw_elapsed"]), 60)
        label = "⏱️ Stopwatch • " + ("Running" if st.session_state["pomo_running"] else "Paused")
    else:
        mins, secs = divmod(int(st.session_state["pomo_remaining"]), 60)
        mode_lbl = "🍅 Focus" if st.session_state["pomo_mode"] == "Focus" else "☕ Break"
        label = f"{mode_lbl} • " + ("Running" if st.session_state["pomo_running"] else "Paused")

    st.markdown(
        f"""
        <div class="ss-timer-box">
            <div style="font-weight:700;color:#4338CA;font-size:0.94rem;">{label}</div>
            <div class="ss-timer-clock">{mins:02d}:{secs:02d}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render(student: dict) -> None:
    auth.require_role("student")
    student_id = student["id"]
    subjects = db.get_subject_names()
    _init_timer_state()

    render_header(
        "⏱️ Study Planner, Timer & Habits",
        "Run live Pomodoro/Stopwatch blocks, build an AI weekly timetable, and track goals & daily habits.",
    )

    tab_timer, tab_history, tab_plan, tab_habits = st.tabs(
        ["🍅 Timer & Manual Log", "📋 Session History", "📅 Tasks & AI Timetable", "🔥 Goals, Habits & Reflection"]
    )

    # 1. TIMER & MANUAL LOG
    with tab_timer:
        st.caption("ℹ️ *Note: Study timers record session duration to build consistency—focus quality comes from active recall and quiz checks, not clock time alone.*")
        col_t, col_m = st.columns(2)

        with col_t:
            st.markdown("### 🍅 Pomodoro & Stopwatch")
            kind = st.radio("Timer Mode", ["Pomodoro", "Stopwatch"], horizontal=True, index=0 if st.session_state["timer_kind"] == "Pomodoro" else 1)
            if kind != st.session_state["timer_kind"]:
                st.session_state["timer_kind"] = kind
                st.session_state["pomo_running"] = False
                st.session_state["pomo_last_tick"] = None

            if kind == "Pomodoro":
                c1, c2 = st.columns(2)
                with c1:
                    f_min = st.number_input("Focus (min)", 1, 90, int(st.session_state["pomo_focus_min"]))
                with c2:
                    b_min = st.number_input("Break (min)", 1, 30, int(st.session_state["pomo_break_min"]))
                if f_min != st.session_state["pomo_focus_min"]:
                    st.session_state["pomo_focus_min"] = int(f_min)
                    if not st.session_state["pomo_running"] and st.session_state["pomo_mode"] == "Focus":
                        st.session_state["pomo_remaining"] = int(f_min) * 60
                if b_min != st.session_state["pomo_break_min"]:
                    st.session_state["pomo_break_min"] = int(b_min)
                    if not st.session_state["pomo_running"] and st.session_state["pomo_mode"] == "Break":
                        st.session_state["pomo_remaining"] = int(b_min) * 60

            st.session_state["pomo_subject"] = st.selectbox("Subject", subjects, key="timer_subj")
            st.session_state["pomo_topic"] = st.text_input("Topic", value=st.session_state["pomo_topic"], key="timer_topic")
            _render_timer_clock(student_id)

            b1, b2, b3, b4 = st.columns(4)
            with b1:
                if not st.session_state["pomo_running"]:
                    if st.button("▶️ Start", width="stretch", type="primary"):
                        st.session_state["pomo_running"] = True
                        st.session_state["pomo_last_tick"] = time.time()
                        st.rerun()
                else:
                    if st.button("⏸️ Pause", width="stretch"):
                        _sync_timer(student_id)
                        st.session_state["pomo_running"] = False
                        st.session_state["pomo_last_tick"] = None
                        st.rerun()
            with b2:
                if st.button("🔄 Reset", width="stretch"):
                    st.session_state["pomo_running"] = False
                    st.session_state["pomo_last_tick"] = None
                    st.session_state["sw_elapsed"] = 0
                    t_min = st.session_state["pomo_focus_min"] if st.session_state["pomo_mode"] == "Focus" else st.session_state["pomo_break_min"]
                    st.session_state["pomo_remaining"] = int(t_min) * 60
                    st.rerun()
            with b3:
                if st.button("🔁 Focus/Brk", width="stretch", disabled=(kind == "Stopwatch")):
                    st.session_state["pomo_running"] = False
                    st.session_state["pomo_mode"] = "Break" if st.session_state["pomo_mode"] == "Focus" else "Focus"
                    t_min = st.session_state["pomo_focus_min"] if st.session_state["pomo_mode"] == "Focus" else st.session_state["pomo_break_min"]
                    st.session_state["pomo_remaining"] = int(t_min) * 60
                    st.rerun()
            with b4:
                if st.button("✅ Log Now", width="stretch"):
                    if kind == "Stopwatch":
                        mins = max(1, int(st.session_state["sw_elapsed"]) // 60)
                    else:
                        mins = max(1, int(st.session_state["pomo_focus_min"]) - (int(st.session_state["pomo_remaining"]) // 60))
                        if st.session_state["pomo_remaining"] == int(st.session_state["pomo_focus_min"]) * 60:
                            mins = int(st.session_state["pomo_focus_min"])
                    db.add_study_session(student_id, st.session_state["pomo_subject"], st.session_state["pomo_topic"].strip() or "Study Block", mins, date.today().isoformat(), f"Logged via {kind}", kind)
                    st.session_state["pomo_running"] = False
                    st.session_state["sw_elapsed"] = 0
                    st.session_state["pomo_remaining"] = int(st.session_state["pomo_focus_min"]) * 60
                    st.toast(f"Logged {mins}m ({st.session_state['pomo_subject']})!", icon="✅")
                    st.rerun()

        with col_m:
            st.markdown("### ✍️ Manual Session Log")
            with st.form("manual_log_form", clear_on_submit=True):
                m_subj = st.selectbox("Subject", subjects)
                m_topic = st.text_input("Topic *", placeholder="e.g., Gauss Law Numericals")
                c_d, c_dt = st.columns(2)
                with c_d:
                    m_dur = st.number_input("Duration (min)", 5, 480, 45, step=5)
                with c_dt:
                    m_date = st.date_input("Date", value=date.today(), max_value=date.today())
                c_st, c_et = st.columns(2)
                with c_st:
                    m_start = st.text_input("Start Time (optional)", value="17:00")
                with c_et:
                    m_end = st.text_input("End Time (optional)", value="17:45")
                m_notes = st.text_area("Notes", height=70)
                if st.form_submit_button("💾 Log Study Session", type="primary", width="stretch"):
                    if not m_topic.strip():
                        st.error("Please enter the topic studied.")
                    else:
                        db.add_study_session(student_id, m_subj, m_topic.strip(), int(m_dur), m_date.isoformat(), m_notes.strip(), "Manual", m_start.strip(), m_end.strip())
                        st.toast("Study session logged!", icon="📚")
                        st.rerun()

    # 2. SESSION HISTORY (EDITABLE & DELETABLE)
    with tab_history:
        sessions = db.get_study_sessions(student_id)
        if not sessions:
            st.info("No study sessions logged yet.")
        else:
            df = pd.DataFrame(sessions)
            df["Delete"] = False
            df["session_date_dt"] = pd.to_datetime(df["session_date"]).dt.date
            edit_df = df[["id", "Delete", "session_date_dt", "subject", "topic", "duration_minutes", "notes", "source"]]
            edited = st.data_editor(
                edit_df,
                hide_index=True,
                width="stretch",
                disabled=["id", "source"],
                column_config={
                    "Delete": st.column_config.CheckboxColumn("🗑️ Delete", default=False),
                    "session_date_dt": st.column_config.DateColumn("Date", required=True),
                    "subject": st.column_config.SelectboxColumn("Subject", options=subjects, required=True),
                    "duration_minutes": st.column_config.NumberColumn("Minutes", min_value=1, max_value=600, step=5),
                },
                key="study_hist_editor",
            )
            if st.button("💾 Save Table Changes", type="primary"):
                orig_map = {r["id"]: r for r in sessions}
                changed = 0
                for _, row in edited.iterrows():
                    sid = int(row["id"])
                    if bool(row["Delete"]):
                        db.delete_study_session(sid)
                        changed += 1
                        continue
                    t_val = str(row["topic"] or "").strip()
                    d_val = int(row["duration_minutes"])
                    dt_str = row["session_date_dt"].isoformat() if hasattr(row["session_date_dt"], "isoformat") else str(row["session_date_dt"])
                    n_val = str(row["notes"] or "").strip()
                    s_val = str(row["subject"])
                    orig = orig_map.get(sid, {})
                    if t_val and d_val > 0 and (s_val != orig.get("subject") or t_val != orig.get("topic") or d_val != int(orig.get("duration_minutes", 0)) or dt_str != orig.get("session_date") or n_val != (orig.get("notes") or "")):
                        db.update_study_session(sid, s_val, t_val, d_val, dt_str, n_val)
                        changed += 1
                if changed:
                    st.toast(f"Saved {changed} change(s)!", icon="✅")
                    st.rerun()

    # 3. TASKS & AI WEEKLY TIMETABLE
    with tab_plan:
        col_tasks, col_tt = st.columns([1, 1.25])
        with col_tasks:
            st.markdown("### ✅ Study Tasks")
            with st.form("add_task_form", clear_on_submit=True):
                tk_subj = st.selectbox("Subject", subjects)
                tk_title = st.text_input("Task Title *")
                t1, t2, t3 = st.columns(3)
                with t1:
                    tk_prio = st.selectbox("Priority", ["High", "Medium", "Low"])
                with t2:
                    tk_est = st.number_input("Est. Min", 10, 240, 45, step=5)
                with t3:
                    tk_due = st.date_input("Due", value=date.today())
                if st.form_submit_button("➕ Add Task", type="primary", width="stretch"):
                    if not tk_title.strip():
                        st.error("Task title required.")
                    else:
                        db.add_study_task(student_id, tk_subj, tk_title, tk_prio, int(tk_est), tk_due.isoformat())
                        st.toast("Task added!", icon="✅")
                        st.rerun()

            tasks = db.get_study_tasks(student_id)
            for tk in tasks:
                c1, c2, c3 = st.columns([0.5, 4, 0.7])
                with c1:
                    checked = st.checkbox("Done", value=bool(tk["is_completed"]), key=f"tk_chk_{tk['id']}", label_visibility="collapsed")
                    if checked != bool(tk["is_completed"]):
                        db.toggle_study_task(tk["id"], checked)
                        st.rerun()
                with c2:
                    style = "~~" if tk["is_completed"] else ""
                    st.markdown(f"{style}**[{tk['subject']}] {tk['title']}**{style} · `{tk['priority']}` · {tk['estimated_minutes']}m (Due {tk['due_date']})")
                with c3:
                    if st.button("🗑️", key=f"tk_del_{tk['id']}"):
                        db.delete_study_task(tk["id"])
                        st.rerun()

        with col_tt:
            st.markdown("### 🗓️ Personalized AI Weekly Timetable")
            daily_mins = st.slider("Target Daily Study Time (minutes)", 30, 240, 90, step=15)
            if st.button("✨ Generate / Refresh Timetable", type="primary", width="stretch"):
                weak = [w["subject"] for w in db.get_weak_subjects(student_id, limit=2)]
                pending = [t["title"] for t in db.get_study_tasks(student_id) if not t["is_completed"]]
                plan, tt_demo = ai.generate_study_timetable(weak, pending, daily_mins)
                st.session_state["weekly_timetable"] = (plan, tt_demo)

            if "weekly_timetable" not in st.session_state:
                weak = [w["subject"] for w in db.get_weak_subjects(student_id, limit=2)]
                pending = [t["title"] for t in db.get_study_tasks(student_id) if not t["is_completed"]]
                st.session_state["weekly_timetable"] = ai.generate_study_timetable(weak, pending, daily_mins)

            plan_rows, tt_demo = st.session_state["weekly_timetable"]
            st.markdown(f"{demo_badge_html(tt_demo)} &nbsp; *Editable timetable — prioritize weak areas & unfinished tasks*", unsafe_allow_html=True)
            tt_df = pd.DataFrame(plan_rows)
            st.data_editor(tt_df, hide_index=True, width="stretch", key="timetable_editor")
            st.markdown('<div class="ss-ai-note">⚠️ AI-generated recommendation, adjust to your schedule</div>', unsafe_allow_html=True)

            # Link Knowledge Center revision materials for priority subjects
            weak_list = [w["subject"] for w in db.get_weak_subjects(student_id, limit=2)]
            kb_docs = [d for d in db.get_knowledge_documents(role="student") if not weak_list or d["subject"] in weak_list]
            if kb_docs:
                st.markdown("#### 📚 Recommended Knowledge Center Materials")
                for kd in kb_docs[:3]:
                    st.caption(f"• **[{kd['subject'] or 'General'} · {kd['category']}] {kd['title']}** — {kd['topic'] or 'Study Guide'} (Open in *Knowledge Center*)")

    # 4. GOALS, HABITS & WEEKLY REFLECTION
    with tab_habits:
        col_g, col_h = st.columns(2)
        with col_g:
            st.markdown("### 🎯 Personal & Academic Goals")
            with st.expander("➕ Add New Goal"):
                with st.form("add_goal_form", clear_on_submit=True):
                    g_title = st.text_input("Goal Title *")
                    g_cat = st.selectbox("Category", ["Academic", "Skill", "Career", "Fitness", "Personal"])
                    g_prio = st.selectbox("Priority", ["High", "Medium", "Low"])
                    g_due = st.date_input("Target Date", value=date.today())
                    g_desc = st.text_area("Description", height=60)
                    if st.form_submit_button("💾 Save Goal", type="primary"):
                        if not g_title.strip():
                            st.error("Goal title required.")
                        else:
                            db.add_goal(student_id, g_title, g_desc, g_cat, g_due.isoformat(), g_prio, [])
                            st.toast("Goal created!", icon="🎯")
                            st.rerun()

            for g in db.get_goals(student_id):
                overdue = g["target_date"] < date.today().isoformat() and g["progress"] < 100
                badge = "🔴 Overdue" if overdue else ("✅ Completed" if g["progress"] >= 100 else "🟢 Active")
                with st.container(border=True):
                    st.markdown(f"**{g['title']}** · `{g['category']}` · {badge} (Target: `{g['target_date']}`)")
                    new_prog = st.slider("Progress (%)", 0, 100, int(g["progress"]), key=f"g_prog_{g['id']}")
                    c_u, c_ai, c_d = st.columns(3)
                    with c_u:
                        if st.button("Update", key=f"g_upd_{g['id']}", width="stretch"):
                            db.update_goal_progress(g["id"], new_prog, "Completed" if new_prog >= 100 else "In Progress")
                            st.toast("Goal updated!", icon="✅")
                            st.rerun()
                    with c_ai:
                        if st.button("🤖 AI Steps", key=f"g_ai_{g['id']}", width="stretch"):
                            steps_txt, _ = ai.generate_goal_steps(g["title"], g["category"])
                            st.session_state[f"g_tip_{g['id']}"] = steps_txt
                    with c_d:
                        if st.button("🗑️", key=f"g_del_{g['id']}", width="stretch"):
                            db.delete_goal(g["id"])
                            st.rerun()
                    if f"g_tip_{g['id']}" in st.session_state:
                        st.info(st.session_state[f"g_tip_{g['id']}"])

        with col_h:
            st.markdown("### 🔥 Daily Habit Tracker")
            with st.form("add_habit_form", clear_on_submit=True):
                h_name = st.text_input("New Habit", placeholder="e.g., 20-min Flashcard Review")
                h_tgt = st.slider("Weekly Target (days)", 1, 7, 5)
                if st.form_submit_button("➕ Add Habit"):
                    if h_name.strip():
                        db.add_habit(student_id, h_name.strip(), "Daily", h_tgt)
                        st.toast("Habit added!", icon="🔥")
                        st.rerun()

            habits = db.get_habits(student_id)
            logs_14 = db.get_habit_logs(student_id, days=14)
            today_str = date.today().isoformat()
            done_today = {l["habit_id"] for l in logs_14 if l["log_date"] == today_str}
            for h in habits:
                cnt_7 = sum(1 for l in logs_14 if l["habit_id"] == h["id"] and l["log_date"] >= date.fromordinal(date.today().toordinal() - 6).isoformat())
                chk = st.checkbox(f"**{h['name']}** ({cnt_7}/{h['target_per_week']} this week)", value=(h["id"] in done_today), key=f"hab_{h['id']}")
                if chk != (h["id"] in done_today):
                    db.toggle_habit_log(h["id"], today_str, chk)
                    st.rerun()

            if logs_14:
                hdf = pd.DataFrame(logs_14).groupby("log_date", as_index=False)["completed"].sum()
                fig_h = px.bar(hdf, x="log_date", y="completed", title="Habits Completed (Last 14 Days)", color_discrete_sequence=[TEAL])
                fig_h.update_yaxes(title="Count", dtick=1)
                fig_h.update_xaxes(title="")
                st.plotly_chart(apply_plotly_theme(fig_h, height=240), width="stretch")

            st.markdown("### 🪞 Weekly Reflection")
            with st.form("refl_form", clear_on_submit=True):
                r_wins = st.text_input("Key Wins This Week *")
                r_block = st.text_input("Blockers / Challenges *")
                r_next = st.text_input("Top Focus Next Week *")
                if st.form_submit_button("💾 Save Reflection"):
                    if r_wins.strip() and r_block.strip() and r_next.strip():
                        db.add_study_reflection(student_id, f"Week of {date.today().isoformat()}", r_wins, r_block, r_next)
                        st.toast("Reflection saved!", icon="🪞")
                        st.rerun()
                    else:
                        st.error("Complete all 3 reflection fields.")
            for rf in db.get_study_reflections(student_id)[:2]:
                st.caption(f"**{rf['week_label']}** — Wins: {rf['wins']} | Next: {rf['next_focus']}")
