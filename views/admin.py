"""Administrator & System Management Portal."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

import auth
import bulk
import cloud_sync
import db
from ui import render_header
from views.teacher import _render_bulk_widget


def render(page: str) -> None:
    user = auth.require_role("admin")
    if page == "👥 Users, Students & Subjects":
        _render_users_and_academics(user)
    elif page == "👨‍👩‍👧 Parents, Permissions & Events":
        _render_parents_permissions_events(user)
    elif page == "📥 Universal Bulk Import/Export":
        render_header(
            "📥 Universal Bulk Import & Export",
            "Import or export Students, Attendance, IA Marks, Questions, and Skills via CSV, Excel, JSON, PDF, DOCX, TXT, or pasted text.",
        )
        _render_bulk_widget(list(bulk.BULK_TEMPLATES.keys()), user)
    elif page == "⚙️ Settings, Logs & Backup":
        _render_settings_and_backup(user)


def _render_users_and_academics(admin_user: dict) -> None:
    render_header(
        "🛡️ Admin: Users, Departments, Students & Curriculum",
        "Manage accounts (Student/Teacher/Parent/Admin), departments & sections, student directory, and subjects.",
    )
    depts = db.get_department_names()
    secs = db.get_section_names()

    t_users, t_stud, t_dept, t_subj = st.tabs(
        ["👤 Users & Teachers", "🎓 Student Directory", "🏢 Departments & Sections", "📚 Subjects & Curriculum"]
    )

    # 1. USERS & TEACHERS
    with t_users:
        users = db.get_all_users()
        st.dataframe(pd.DataFrame(users), hide_index=True, width="stretch")

        c_create, c_reset, c_toggle = st.columns([1.3, 1.2, 0.9])
        with c_create:
            with st.form("admin_create_user", clear_on_submit=True):
                st.markdown("#### ➕ Create User Account")
                c1, c2 = st.columns(2)
                with c1:
                    u_name = st.text_input("Username *")
                    u_full = st.text_input("Full Name *")
                    u_emp = st.text_input("USN / Teacher ID", placeholder="e.g., TCH105 or 1SI24CS020")
                with c2:
                    u_role = st.selectbox("Role", ["teacher", "student", "parent", "admin"])
                    u_pass = st.text_input("Password *", type="password")
                    u_dept = st.selectbox("Department", depts + ["Administration", "Parent Portal"])
                students = db.get_all_students()
                st_opts = {"None": None, **{f"{s['usn']} - {s['name']}": s["id"] for s in students}}
                u_link = st.selectbox("Linked Student (for student/parent)", list(st_opts.keys()))
                if st.form_submit_button("👤 Create Account", type="primary", width="stretch"):
                    if not u_name.strip() or not u_full.strip() or len(u_pass) < 4:
                        st.error("Username, Full Name, and Password (>= 4 chars) required.")
                    elif db.get_user_by_username(u_name):
                        st.error("Username already exists.")
                    else:
                        linked_id = st_opts[u_link]
                        db.create_user(u_name, u_pass, u_role, u_full, u_dept, linked_id, employee_id=u_emp)
                        if u_role == "parent" and linked_id:
                            db.link_parent_student(u_name, linked_id, "Guardian")
                        db.log_activity(admin_user["username"], "admin", "CREATE_USER", f"Created {u_role} user {u_name}")
                        st.toast(f"User '{u_name}' ({u_role}) created!", icon="👤")
                        st.rerun()

        with c_reset:
            st.markdown("#### 🔑 Reset Password / Change Username")
            if users:
                pick_r = st.selectbox(
                    "Target Account",
                    [f"{u['id']}: {u['username']} ({u['role']} • {u['full_name']})" for u in users],
                    key="adm_reset_pick",
                )
                r_uid = int(pick_r.split(":")[0])
                r_obj = next(u for u in users if u["id"] == r_uid)
                with st.form("admin_reset_creds", clear_on_submit=True):
                    new_uname = st.text_input("New Username (leave same to keep)", value=r_obj["username"])
                    new_pwd = st.text_input("New Password (optional, min 4 chars)", type="password")
                    if st.form_submit_button("💾 Update Username / Password", type="primary", width="stretch"):
                        u_arg = new_uname.strip() if new_uname.strip() and new_uname.strip() != r_obj["username"] else None
                        p_arg = new_pwd.strip() if new_pwd.strip() else None
                        if not u_arg and not p_arg:
                            st.info("Enter a new username or password.")
                        else:
                            ok, msg = db.update_user_credentials(r_uid, new_username=u_arg, new_password=p_arg)
                            if ok:
                                db.log_activity(admin_user["username"], "admin", "ADMIN_RESET_CREDS", f"Updated credentials for user #{r_uid}")
                                st.toast(msg, icon="🔑")
                                st.rerun()
                            else:
                                st.error(msg)

        with c_toggle:
            st.markdown("#### 🔒 Status & Quick Logins")
            editable_users = [u for u in users if u["username"] != admin_user["username"]]
            if editable_users:
                pick_u = st.selectbox(
                    "Select User",
                    [f"{u['id']}: {u['username']} ({u['role']}) — {'Active' if u['is_active'] else 'Disabled'}" for u in editable_users],
                )
                uid = int(pick_u.split(":")[0])
                u_obj = next(u for u in editable_users if u["id"] == uid)
                if u_obj["is_active"]:
                    if st.button("🚫 Deactivate", width="stretch"):
                        db.toggle_user_active(uid, False)
                        db.log_activity(admin_user["username"], "admin", "DEACTIVATE_USER", u_obj["username"])
                        st.rerun()
                else:
                    if st.button("✅ Activate", width="stretch"):
                        db.toggle_user_active(uid, True)
                        db.log_activity(admin_user["username"], "admin", "ACTIVATE_USER", u_obj["username"])
                        st.rerun()
            if st.button("⚡ Generate Missing Student Logins (Name/USN)", width="stretch"):
                created = db.generate_missing_student_logins(admin_user["username"])
                if created:
                    st.session_state["last_generated_logins"] = created
                    st.toast(f"Created {len(created)} student login(s)!", icon="🎓")
                    st.rerun()
                else:
                    st.info("All active students already have user logins.")

        st.markdown("---")
        with st.expander("📥 Bulk Generate Logins from File (Student Name + USN, or Teacher Name + Teacher ID)", expanded=False):
            st.caption("Upload a CSV, Excel, PDF, DOCX, TXT file (or paste lines) with just `name, usn` for students (`username=name, password=usn`) or `teacher_name, teacher_id` for teachers (`username=teacher_name, password=teacher_id`).")
            _render_bulk_widget(["Student Logins", "Teacher Logins"], admin_user)

    # 2. STUDENT DIRECTORY
    with t_stud:
        show_arch = st.checkbox("Include archived students")
        q = st.text_input("🔎 Search students by USN, name, branch, or section")
        students = db.get_all_students(include_archived=show_arch)
        if q.strip():
            ql = q.strip().lower()
            students = [s for s in students if ql in (s["usn"] + s["name"] + s["branch"] + s["section"]).lower()]

        if students:
            s_df = pd.DataFrame(students)[["id", "usn", "name", "email", "course", "branch", "semester", "section", "guardian_name", "is_archived"]]
            st.dataframe(s_df, hide_index=True, width="stretch")
            st.download_button("📥 Export Students (CSV)", data=s_df.to_csv(index=False).encode("utf-8"), file_name="students_export.csv", mime="text/csv")

        c_add, c_arch = st.columns(2)
        with c_add:
            with st.form("admin_add_student", clear_on_submit=True):
                st.markdown("#### ➕ Add Student Record")
                s_usn = st.text_input("USN *")
                s_name = st.text_input("Name *")
                s_email = st.text_input("Email")
                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    s_branch = st.selectbox("Department / Branch", depts)
                with sc2:
                    s_sem = st.number_input("Semester", 1, 8, 5)
                with sc3:
                    s_sec = st.selectbox("Section", secs)
                if st.form_submit_button("💾 Save Student", type="primary", width="stretch"):
                    if not s_usn.strip() or not s_name.strip():
                        st.error("USN and Name required.")
                    else:
                        try:
                            db.upsert_student(s_usn, s_name, s_email, "B.Tech", s_branch, int(s_sem), s_sec)
                            db.log_activity(admin_user["username"], "admin", "ADD_STUDENT", f"Added {s_usn}")
                            st.toast("Student added!", icon="🎓")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not save student: {exc}")
        with c_arch:
            st.markdown("#### 📦 Archive / Restore Student")
            if students:
                pick = st.selectbox("Select Student", [f"{s['id']}: {s['usn']} - {s['name']}" for s in students])
                pick_id = int(pick.split(":")[0])
                pick_obj = next(s for s in students if s["id"] == pick_id)
                if pick_obj["is_archived"]:
                    if st.button("♻️ Restore Student", width="stretch"):
                        db.set_student_archived(pick_id, False)
                        st.rerun()
                else:
                    if st.button("📦 Archive Student", width="stretch"):
                        db.set_student_archived(pick_id, True)
                        st.rerun()

    # 3. DEPARTMENTS & SECTIONS
    with t_dept:
        c_d, c_s = st.columns(2)
        with c_d:
            st.markdown("### 🏢 Departments")
            dept_rows = db.get_departments()
            if dept_rows:
                st.dataframe(pd.DataFrame(dept_rows)[["code", "name", "hod_name", "description"]], hide_index=True, width="stretch")
            with st.form("add_dept_form", clear_on_submit=True):
                d_code = st.text_input("Department Code *", placeholder="e.g., ECE, BT, CIVIL")
                d_name = st.text_input("Department Name *", placeholder="e.g., Biotechnology")
                d_hod = st.text_input("Head of Department (HOD)", placeholder="e.g., Dr. Anitha Rao")
                d_desc = st.text_input("Description")
                if st.form_submit_button("➕ Add Department", type="primary", width="stretch"):
                    if not d_code.strip() or not d_name.strip():
                        st.error("Department Code and Name are required.")
                    else:
                        try:
                            db.add_department(d_code, d_name, d_hod, d_desc)
                            db.log_activity(admin_user["username"], "admin", "ADD_DEPARTMENT", f"Added {d_code.upper()}")
                            st.toast(f"Department '{d_code.upper()}' added!", icon="🏢")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not add department: {exc}")
            if dept_rows:
                del_d = st.selectbox("Remove Department", [f"{d['id']}: {d['code']} - {d['name']}" for d in dept_rows])
                if st.button("🗑️ Delete Selected Department"):
                    db.delete_department(int(del_d.split(":")[0]))
                    st.toast("Department deleted.", icon="🗑️")
                    st.rerun()

        with c_s:
            st.markdown("### 🏷️ Semesters & Sections")
            sec_rows = db.get_sections()
            if sec_rows:
                st.dataframe(pd.DataFrame(sec_rows)[["department_code", "semester", "name"]], hide_index=True, width="stretch")
            with st.form("add_sec_form", clear_on_submit=True):
                sc_dept = st.selectbox("Department", depts, key="add_sec_dept")
                sc_sem = st.number_input("Semester", 1, 8, 5, key="add_sec_sem")
                sc_name = st.text_input("Section Name *", placeholder="e.g., Section D")
                if st.form_submit_button("➕ Add Section", type="primary", width="stretch"):
                    if not sc_name.strip():
                        st.error("Section name required.")
                    else:
                        db.add_section(sc_name, int(sc_sem), sc_dept)
                        db.log_activity(admin_user["username"], "admin", "ADD_SECTION", f"{sc_dept} Sem {sc_sem} {sc_name}")
                        st.toast(f"Added {sc_name}!", icon="🏷️")
                        st.rerun()
            if sec_rows:
                del_s = st.selectbox("Remove Section", [f"{s['id']}: {s['department_code']} Sem {s['semester']} - {s['name']}" for s in sec_rows])
                if st.button("🗑️ Delete Selected Section"):
                    db.delete_section(int(del_s.split(":")[0]))
                    st.toast("Section deleted.", icon="🗑️")
                    st.rerun()

    # 4. SUBJECTS & CURRICULUM
    with t_subj:
        st.dataframe(pd.DataFrame(db.get_subjects()), hide_index=True, width="stretch")
        teachers = [u["full_name"] for u in db.get_all_users() if u["role"] == "teacher"] or ["Ms. Priya Nair"]
        with st.form("admin_add_subj", clear_on_submit=True):
            st.markdown("#### ➕ Add Subject")
            c1, c2, c3 = st.columns(3)
            with c1:
                code = st.text_input("Code *", placeholder="CS506")
                name = st.text_input("Subject Name *", placeholder="Machine Learning")
                dept = st.selectbox("Department", depts, key="subj_dept")
            with c2:
                credits = st.number_input("Credits", 1, 6, 4)
                sem = st.number_input("Semester", 1, 8, 5)
                teacher = st.selectbox("Assigned Faculty", teachers)
            with c3:
                cat = st.selectbox("Category", ["Core", "Science", "Humanities", "Elective", "Lab"])
                topics = st.text_input("Topics (comma-separated)", value="Supervised Learning, Evaluation Metrics")
            if st.form_submit_button("➕ Add Subject", type="primary"):
                if not code.strip() or not name.strip():
                    st.error("Code and Name are required.")
                else:
                    try:
                        db.add_subject(code, name, int(credits), int(sem), dept, teacher, cat, [t.strip() for t in topics.split(",") if t.strip()])
                        db.log_activity(admin_user["username"], "admin", "ADD_SUBJECT", f"Added {code} {name}")
                        st.toast("Subject added!", icon="📚")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed: {exc}")


def _render_parents_permissions_events(admin_user: dict) -> None:
    render_header(
        "👨‍👩‍👧 Parents, Teacher Permissions & College Events",
        "Manage parent/guardian accounts & absence alerts, teacher class-subject permissions, and institution-wide events.",
    )
    depts = db.get_department_names()
    secs = db.get_section_names()
    t_par, t_perm, t_ev = st.tabs(
        ["👨‍👩‍👧 Parent Accounts, Contacts & Links", "🔐 Teacher Class/Subject Permissions", "🗓️ College Events"]
    )

    with t_par:
        students = db.get_all_students()
        parent_users = [u for u in db.get_all_users() if u["role"] == "parent"]
        links = db.get_all_parent_links()

        st.markdown("### 📋 Active Parent / Guardian Directory & Linked Students")
        if links:
            st.dataframe(
                pd.DataFrame(links)[["id", "parent_username", "student_name", "usn", "relationship"]],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No parent-student links yet. Create or link a parent account below.")

        if students:
            g_rows = [
                {
                    "USN": s["usn"],
                    "Student": s["name"],
                    "Guardian Name": s.get("guardian_name") or "—",
                    "Phone": s.get("guardian_phone") or "—",
                    "Email": s.get("guardian_email") or "—",
                    "Alerts Enabled": "✅ Yes" if s.get("guardian_alerts_enabled", 1) else "❌ No",
                }
                for s in students
            ]
            st.dataframe(pd.DataFrame(g_rows), hide_index=True, width="stretch")

        c_create_p, c_edit_g, c_link_p = st.columns(3)
        with c_create_p:
            with st.form("create_parent_quick", clear_on_submit=True):
                st.markdown("#### ➕ Create Parent Account")
                p_user = st.text_input("Username *", placeholder="e.g., parent_verma")
                p_name = st.text_input("Parent Full Name *", placeholder="e.g., Mrs. Sunita Verma")
                p_pwd = st.text_input("Password *", type="password")
                p_st_opts = [f"{s['id']}: {s['name']} ({s['usn']})" for s in students]
                p_st = st.selectbox("Link to Student *", p_st_opts) if p_st_opts else None
                p_rel = st.selectbox("Relationship", ["Father", "Mother", "Guardian"])
                if st.form_submit_button("👨‍👩‍👧 Create & Link Parent", type="primary", width="stretch"):
                    if not p_st or not p_user.strip() or not p_name.strip() or len(p_pwd) < 4:
                        st.error("Complete all fields (password >= 4 chars).")
                    elif db.get_user_by_username(p_user):
                        st.error("Username already exists.")
                    else:
                        sid = int(p_st.split(":")[0])
                        db.create_user(p_user, p_pwd, "parent", p_name, "Parent Portal", sid)
                        db.link_parent_student(p_user, sid, p_rel)
                        db.log_activity(admin_user["username"], "admin", "CREATE_PARENT", f"Created {p_user} -> student #{sid}")
                        st.toast(f"Parent '{p_user}' created and linked!", icon="👨‍👩‍👧")
                        st.rerun()

        with c_edit_g:
            st.markdown("#### 📞 Guardian Contact & Alerts")
            if students:
                sel_s = st.selectbox("Student", [f"{s['id']}: {s['usn']} - {s['name']}" for s in students], key="g_sel_st")
                sid = int(sel_s.split(":")[0])
                st_obj = next(s for s in students if s["id"] == sid)
                with st.form("guardian_contact_form"):
                    g_name = st.text_input("Guardian Name", value=st_obj.get("guardian_name", ""))
                    g_phone = st.text_input("Guardian Phone", value=st_obj.get("guardian_phone", ""))
                    g_email = st.text_input("Guardian Email", value=st_obj.get("guardian_email", ""))
                    g_alert = st.checkbox("Enable Absence & Low-Attendance Alerts", value=bool(st_obj.get("guardian_alerts_enabled", 1)))
                    if st.form_submit_button("💾 Save Guardian Info", type="primary", width="stretch"):
                        db.update_student_guardian(sid, g_name, g_phone, g_email, g_alert)
                        db.log_activity(admin_user["username"], "admin", "UPDATE_GUARDIAN", f"Updated guardian for {st_obj['usn']}")
                        st.toast("Guardian contact settings saved!", icon="✅")
                        st.rerun()

        with c_link_p:
            st.markdown("#### 🔗 Manage Existing Parent Links")
            if parent_users and students:
                with st.form("link_parent_form"):
                    p_u = st.selectbox("Parent Account", [u["username"] for u in parent_users], key="lp_u")
                    p_st = st.selectbox("Authorize Student", [f"{s['id']}: {s['name']} ({s['usn']})" for s in students], key="lp_s")
                    p_rel = st.selectbox("Relationship", ["Father", "Mother", "Guardian"], key="lp_r")
                    if st.form_submit_button("🔗 Link Parent to Student", width="stretch"):
                        db.link_parent_student(p_u, int(p_st.split(":")[0]), p_rel)
                        db.log_activity(admin_user["username"], "admin", "LINK_PARENT", f"{p_u} -> {p_st}")
                        st.toast("Parent link saved!", icon="🔗")
                        st.rerun()
            if links:
                del_l = st.selectbox("Unlink Record", [f"{l['id']}: {l['parent_username']} -> {l['student_name']}" for l in links])
                if st.button("🗑️ Remove Link", width="stretch"):
                    db.delete_parent_link(int(del_l.split(":")[0]))
                    st.toast("Link removed.", icon="🗑️")
                    st.rerun()

    with t_perm:
        st.markdown("### 🔐 Teacher Subject & Section Assignments")
        teachers = [u for u in db.get_all_users() if u["role"] == "teacher"]
        subjects = db.get_subject_names()
        if teachers:
            with st.form("assign_teacher_form"):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    t_u = st.selectbox("Teacher", [t["username"] for t in teachers])
                with c2:
                    t_s = st.selectbox("Subject", subjects)
                with c3:
                    t_sec = st.selectbox("Section", secs + ["All"])
                with c4:
                    t_sem = st.number_input("Semester", 1, 8, 5)
                if st.form_submit_button("➕ Grant Class/Subject Access", type="primary"):
                    db.add_teacher_assignment(t_u, t_s, t_sec, int(t_sem))
                    db.log_activity(admin_user["username"], "admin", "ASSIGN_TEACHER", f"{t_u}: {t_s} ({t_sec})")
                    st.toast("Assignment saved!", icon="🔐")
                    st.rerun()
        assigns = db.get_all_teacher_assignments()
        for a in assigns:
            ca, cb = st.columns([4, 1])
            with ca:
                st.markdown(f"- `{a['teacher_username']}` → **{a['subject_name']}** · {a['section']} (Sem {a['semester']})")
            with cb:
                if st.button("Revoke", key=f"rev_ta_{a['id']}"):
                    db.delete_teacher_assignment(a["id"])
                    st.rerun()

    with t_ev:
        st.markdown("### 🗓️ College-Wide Events")
        with st.form("admin_ev_form", clear_on_submit=True):
            ev_t = st.text_input("Event Title *")
            c1, c2, c3 = st.columns(3)
            with c1:
                ev_type = st.selectbox("Type", ["College Event", "Exam", "Assignment"])
            with c2:
                ev_subj = st.selectbox("Department / Scope", ["All"] + depts)
            with c3:
                ev_dt = st.date_input("Date", value=date.today())
            ev_desc = st.text_area("Description", height=65)
            if st.form_submit_button("➕ Publish College Event", type="primary"):
                if not ev_t.strip():
                    st.error("Event title required.")
                else:
                    db.add_calendar_event(None, ev_t, ev_type, ev_dt.isoformat(), ev_subj, ev_desc)
                    db.log_activity(admin_user["username"], "admin", "ADD_EVENT", ev_t)
                    st.toast("College event published!", icon="🗓️")
                    st.rerun()
        st.dataframe(pd.DataFrame(db.get_calendar_events()), hide_index=True, width="stretch")


def _render_settings_and_backup(admin_user: dict) -> None:
    render_header("⚙️ System Settings, Activity Logs & DB Backup", "Configure academic thresholds, inspect audit logs, and manage SQLite backups.")
    settings = db.get_settings()

    t_set, t_logs, t_bak = st.tabs(["⚙️ Threshold Settings", "📜 Activity Logs", "💾 Backup & Restore"])

    with t_set:
        with st.form("settings_form"):
            inst = st.text_input("Institution Name", value=settings.get("institution_name", "SmartStudy Institute"))
            term = st.text_input("Academic Term", value=settings.get("academic_term", "2026-27 • Semester 5"))
            att_th = st.number_input("Minimum Attendance Threshold (%)", 50, 95, int(float(settings.get("attendance_threshold", 75))))
            pass_m = st.number_input("Passing Marks (%)", 20, 75, int(float(settings.get("passing_marks", 40))))
            if st.form_submit_button("💾 Save Settings", type="primary"):
                db.update_setting("institution_name", inst)
                db.update_setting("academic_term", term)
                db.update_setting("attendance_threshold", str(att_th))
                db.update_setting("passing_marks", str(pass_m))
                db.log_activity(admin_user["username"], "admin", "UPDATE_SETTINGS", f"att_threshold={att_th}")
                st.toast("Settings updated!", icon="⚙️")

    with t_logs:
        logs = db.get_activity_logs(100)
        st.dataframe(pd.DataFrame(logs), hide_index=True, width="stretch")

    with t_bak:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 📥 Download SQLite Backup")
            st.download_button(
                "💾 Download smartstudy.db Backup",
                data=db.export_db_bytes(),
                file_name="smartstudy_backup.db",
                mime="application/octet-stream",
                type="primary",
                width="stretch",
            )
        with c2:
            st.markdown("### ♻️ Restore Database / Reset Demo")
            up_db = st.file_uploader("Upload `.db` backup file", type=["db", "sqlite"])
            confirm_res = st.checkbox("I confirm restoring/resetting overwrites current database state.")
            if st.button("Restore Uploaded DB", disabled=not (up_db and confirm_res)):
                try:
                    db.restore_db_bytes(up_db.getvalue())
                    db.log_activity(admin_user["username"], "admin", "DB_RESTORE", "Restored database backup")
                    st.toast("Database restored!", icon="✅")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if st.button("🔄 Reset All Demo Data (Admin)", disabled=not confirm_res):
                db.reset_demo_data()
                st.toast("Demo dataset restored!", icon="🔄")
                st.rerun()

        st.markdown("---")
        st.markdown("### ☁️ Permanent Free Cloud Persistence Status")
        sync_stat = cloud_sync.get_sync_status()
        st.info(f"**Storage Mode:** {sync_stat['mode']}")
        if sync_stat.get("last_sync"):
            st.caption(f"Last Cloud Sync: `{sync_stat['last_sync']}`")
        if sync_stat.get("last_error"):
            st.warning(f"Last Sync Notice: {sync_stat['last_error']}")

        if cloud_sync.is_configured():
            sc1, sc2 = st.columns(2)
            with sc1:
                if st.button("☁️ Force Push DB to Cloud Now", type="primary", width="stretch"):
                    if cloud_sync.push_db(db.DB_PATH):
                        st.toast("Pushed latest database & file blobs to GitHub Cloud!", icon="☁️")
                        st.rerun()
                    else:
                        st.error("Cloud push failed — check GITHUB_TOKEN permissions.")
            with sc2:
                if st.button("⬇️ Pull Latest DB from Cloud", width="stretch"):
                    if cloud_sync.pull_db_on_startup(db.DB_PATH, force=True):
                        st.toast("Pulled latest database from GitHub Cloud!", icon="⬇️")
                        st.rerun()
                    else:
                        st.warning("No remote DB snapshot found yet or pull failed.")
        else:
            st.caption(
                "To make data & uploaded PDFs persist permanently across free Streamlit Community Cloud restarts, "
                "add `GITHUB_TOKEN` and `GITHUB_DATA_REPO` (a private GitHub repo like `username/smartstudy-data`) to Streamlit Secrets."
            )
