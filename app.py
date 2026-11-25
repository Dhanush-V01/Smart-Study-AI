"""SmartStudy AI — Main Entry Point, RBAC Authentication & Multi-Portal Routing."""

from __future__ import annotations

import importlib
import streamlit as st

import ai
import auth
import db
from ui import demo_badge_html, inject_custom_css, render_header

if not hasattr(db, "get_knowledge_documents") or not hasattr(db, "get_departments") or not hasattr(db, "verify_and_reset_credentials") or not hasattr(db, "read_file_bytes"):
    importlib.reload(db)
from views import (
    academics,
    admin,
    dashboard,
    doubt_solver,
    exams_ml,
    knowledge_center,
    parent,
    skills_portfolio,
    study_tracker,
    teacher,
)

st.set_page_config(
    page_title="SmartStudy AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

db.init_db()
inject_custom_css()


def _render_login_screen() -> None:
    render_header(
        "🎓 SmartStudy AI — Learning & Holistic Development System",
        "Sign in with your role account or launch a 1-click demo portal.",
        demo_badge_html(not ai.has_api_key()),
    )

    col_demo, col_login = st.columns([1.25, 1])

    with col_demo:
        st.markdown("### ⚡ 1-Click Demo Portals")
        st.caption("Explore each role with preserved records, Knowledge Center documents, Question Bank, ML analytics, and portals.")
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            if st.button("🎓 Student\n(Aarav)", width="stretch", type="primary"):
                auth.login_demo_user("aarav")
                st.rerun()
        with d2:
            if st.button("👩‍🏫 Teacher\n(Ms. Priya)", width="stretch"):
                auth.login_demo_user("priya")
                st.rerun()
        with d3:
            if st.button("👨‍👩‍👧 Parent\n(Mr. Sharma)", width="stretch"):
                auth.login_demo_user("parent_sharma")
                st.rerun()
        with d4:
            if st.button("🛡️ Admin\n(Dr. Rajesh)", width="stretch"):
                auth.login_demo_user("admin")
                st.rerun()

        with st.container(border=True):
            st.markdown("**Demo Credentials (for manual sign-in testing):**")
            st.markdown(
                "- **Student:** `aarav` / `student123`\n"
                "- **Teacher:** `priya` / `teacher123`\n"
                "- **Parent / Guardian:** `parent_sharma` / `parent123`\n"
                "- **Admin:** `admin` / `admin123`"
            )

    with col_login:
        t_in, t_reg, t_rec = st.tabs(["🔐 Sign In", "📝 Student Sign Up", "🔑 Forgot / Reset"])
        with t_in:
            with st.form("login_form"):
                uname = st.text_input("Username (or Full Name for bulk-created logins)", placeholder="aarav / Diya Nair / priya / admin")
                pwd = st.text_input("Password (or USN / Teacher ID for initial login)", type="password")
                if st.form_submit_button("Sign In", type="primary", width="stretch"):
                    ok, msg = auth.authenticate(uname, pwd)
                    if ok:
                        st.toast(msg, icon="✅")
                        st.rerun()
                    else:
                        st.error(msg)
                        st.caption("Forgot your password or initial USN/Teacher ID isn't working? Use the **🔑 Forgot / Reset** tab or ask your Administrator.")
        with t_reg:
            with st.form("register_form", clear_on_submit=True):
                r_usn = st.text_input("USN *", placeholder="1SI24CS099")
                r_name = st.text_input("Full Name *")
                r_email = st.text_input("Email")
                r_uname = st.text_input("Choose Username *")
                r_pwd = st.text_input("Password (min 4 chars) *", type="password")
                if st.form_submit_button("Create Student Account", width="stretch"):
                    if not r_usn.strip() or not r_name.strip() or not r_uname.strip() or len(r_pwd) < 4:
                        st.error("Complete all required fields (password >= 4 chars).")
                    elif db.get_user_by_username(r_uname):
                        st.error("Username already taken.")
                    else:
                        try:
                            sid = db.upsert_student(r_usn, r_name, r_email, "B.Tech", "CSE", 5, "Section A")
                            db.create_user(r_uname, r_pwd, "student", r_name, "CSE", sid, employee_id=r_usn.strip().upper())
                            auth.authenticate(r_uname, r_pwd)
                            st.toast("Welcome to SmartStudy AI!", icon="🎓")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not register: {exc}")
        with t_rec:
            st.caption("Verify your identity using your **USN** (Students) or **Teacher ID** (Teachers) + Full Name to reset your password or change your username.")
            with st.form("self_reset_form", clear_on_submit=True):
                rec_role = st.selectbox("Account Type", ["student", "teacher"], format_func=lambda r: "🎓 Student" if r == "student" else "👩‍🏫 Teacher")
                rec_id = st.text_input("USN (Student) or Teacher ID (Teacher) *", placeholder="e.g., 1SI24CS001 or TCH001")
                rec_name = st.text_input("Full Name *", placeholder="e.g., Aarav Sharma or Ms. Priya Nair")
                rec_new_uname = st.text_input("New Username (optional — leave blank to keep current)")
                rec_new_pwd = st.text_input("New Password (min 4 chars) *", type="password")
                if st.form_submit_button("🔄 Verify & Update Credentials", type="primary", width="stretch"):
                    ok, msg = db.verify_and_reset_credentials(
                        rec_role,
                        rec_id,
                        rec_name,
                        rec_new_pwd,
                        rec_new_uname.strip() or None,
                    )
                    if ok:
                        st.success(msg + " You can now sign in on the Sign In tab.")
                        st.toast("Credentials updated!", icon="🔑")
                    else:
                        st.error(msg)


user = auth.current_user()
if not user:
    _render_login_screen()
    st.stop()

with st.sidebar:
    st.markdown("## 🎓 SmartStudy AI")
    st.markdown(demo_badge_html(not ai.has_api_key()), unsafe_allow_html=True)
    st.markdown("---")

    role_emoji = {"student": "🎓", "teacher": "👩‍🏫", "parent": "👨‍👩‍👧", "admin": "🛡️"}.get(user["role"], "👤")
    st.markdown(f"**{role_emoji} {user['full_name']}**")
    st.caption(f"Role: `{user['role'].title()}` • Dept: {user.get('department', 'CSE')}")

    if user["role"] == "student":
        page = st.radio(
            "Student Modules",
            options=[
                "📊 Overview & Analytics",
                "📚 Academics & Calendar",
                "📖 Knowledge Center",
                "🤖 AI Assistant & Notes",
                "⏱️ Study Planner & Habits",
                "📝 Exams & ML Insights",
                "🌟 Skills, Portfolio & Career",
            ],
        )
    elif user["role"] == "teacher":
        page = st.radio(
            "Teacher Modules",
            options=[
                "🏫 Class Overview & Alerts",
                "📖 Knowledge Center",
                "📝 Exam & Question Bank",
                "🔎 Student Review & Feedback",
                "📥 Academic Records & Bulk Ops",
            ],
        )
    elif user["role"] == "parent":
        page = st.radio(
            "Parent Modules",
            options=["👨‍👩‍👧 Student Progress & Alerts"],
        )
    else:
        page = st.radio(
            "Admin Modules",
            options=[
                "👥 Users, Students & Subjects",
                "👨‍👩‍👧 Parents, Permissions & Events",
                "📖 Knowledge Center",
                "📥 Universal Bulk Import/Export",
                "⚙️ Settings, Logs & Backup",
            ],
        )

    st.markdown("---")
    with st.expander("🔑 Change Username / Password"):
        with st.form("sidebar_change_creds", clear_on_submit=True):
            cur_p = st.text_input("Current Password *", type="password")
            new_u = st.text_input("New Username (optional)", value=user["username"])
            new_p = st.text_input("New Password (optional, min 4 chars)", type="password")
            if st.form_submit_button("Save Credentials", width="stretch"):
                if not db.verify_password(cur_p, user["password_hash"]):
                    st.error("Current password is incorrect.")
                else:
                    u_arg = new_u.strip() if new_u.strip() and new_u.strip() != user["username"] else None
                    p_arg = new_p.strip() if new_p.strip() else None
                    if not u_arg and not p_arg:
                        st.info("No changes entered.")
                    else:
                        ok, msg = db.update_user_credentials(user["id"], new_username=u_arg, new_password=p_arg)
                        if ok:
                            updated = db.get_user_by_username(u_arg or user["username"])
                            if updated:
                                st.session_state["auth_user"] = updated
                            db.log_activity(user["username"], user["role"], "CHANGE_CREDENTIALS", "Updated own username/password")
                            st.toast("Account credentials updated!", icon="🔑")
                            st.rerun()
                        else:
                            st.error(msg)

    if st.button("🚪 Sign Out", width="stretch"):
        auth.logout()
        st.rerun()

# Route to Protected Portal Views
if page == "📖 Knowledge Center":
    knowledge_center.render()
elif user["role"] == "student":
    student = (
        db.get_student_by_id(user["linked_student_id"])
        if user.get("linked_student_id")
        else db.get_student_by_name(db.PRIMARY_STUDENT_NAME)
    )
    if not student:
        st.error("Linked student record not found.")
    elif page == "📊 Overview & Analytics":
        dashboard.render(student)
    elif page == "📚 Academics & Calendar":
        academics.render(student)
    elif page == "🤖 AI Assistant & Notes":
        doubt_solver.render(student)
    elif page == "⏱️ Study Planner & Habits":
        study_tracker.render(student)
    elif page == "📝 Exams & ML Insights":
        exams_ml.render(student)
    elif page == "🌟 Skills, Portfolio & Career":
        skills_portfolio.render(student)
elif user["role"] == "teacher":
    teacher.render(page)
elif user["role"] == "parent":
    parent.render()
elif user["role"] == "admin":
    admin.render(page)
