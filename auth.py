"""Authentication & Role-Based Access Control (RBAC) helpers (Student, Teacher, Parent, Admin)."""

from __future__ import annotations

from typing import Any

import streamlit as st

import db


def current_user() -> dict[str, Any] | None:
    return st.session_state.get("auth_user")


def authenticate(username: str, password: str) -> tuple[bool, str]:
    user = db.get_user_by_username(username)
    if not user:
        return False, "Invalid username or password."
    if not user.get("is_active"):
        return False, "This account has been deactivated by an administrator."
    if not db.verify_password(password, user["password_hash"]):
        return False, "Invalid username or password."
    st.session_state["auth_user"] = user
    db.log_activity(user["username"], user["role"], "LOGIN", f"Signed in as {user['role']}")
    return True, "Signed in successfully."


def login_demo_user(username: str) -> bool:
    user = db.get_user_by_username(username)
    if not user or not user.get("is_active"):
        return False
    st.session_state["auth_user"] = user
    db.log_activity(user["username"], user["role"], "DEMO_LOGIN", f"Quick demo sign-in ({user['role']})")
    return True


def logout() -> None:
    user = current_user()
    if user:
        db.log_activity(user["username"], user["role"], "LOGOUT", "User signed out")
    for key in [
        "auth_user",
        "latest_doubt",
        "active_quiz",
        "active_exam",
        "weak_sig",
        "weak_rec",
        "ml_bundle",
        "kb_preview_doc",
        "qb_extract_preview",
    ]:
        st.session_state.pop(key, None)


def require_role(*allowed_roles: str) -> dict[str, Any]:
    """Enforce RBAC in application logic (not only hiding UI)."""
    user = current_user()
    if not user:
        st.error("Authentication required. Please sign in.")
        st.stop()
    if user["role"] not in allowed_roles:
        db.log_activity(user["username"], user["role"], "ACCESS_DENIED", f"Attempted access requiring {allowed_roles}")
        st.error(f"Access denied: your role (`{user['role']}`) is not permitted to access this module.")
        st.stop()
    return user


def teacher_authorized_subjects(user: dict[str, Any]) -> list[str]:
    """Return subjects assigned to a teacher (Admins have access to all)."""
    if user["role"] == "admin":
        return db.get_subject_names()
    assigned = db.get_teacher_assignments(user["username"])
    if not assigned:
        return db.get_subject_names()
    return sorted({a["subject_name"] for a in assigned})


def teacher_authorized_students(user: dict[str, Any]) -> list[dict[str, Any]]:
    """Return students belonging to sections assigned to the teacher (Admins see all)."""
    all_students = db.get_all_students()
    if user["role"] == "admin":
        return all_students
    assigned = db.get_teacher_assignments(user["username"])
    if not assigned:
        return all_students
    allowed_sections = {a["section"] for a in assigned}
    return [s for s in all_students if s["section"] in allowed_sections or "All" in allowed_sections]
