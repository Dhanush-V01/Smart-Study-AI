"""Skills & Talent Discovery, Portfolio Showcase, Career Readiness & Teacher Feedback."""

from __future__ import annotations

import html
import json
import uuid
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import auth
import db
from ui import CAREER_ROLES, INDIGO, TEAL, apply_plotly_theme, render_header, type_badge_html

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


def _save_uploaded_file(uploaded_file) -> tuple[str, str]:
    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Only PNG, JPG, JPEG, or PDF files are allowed.")
    raw = uploaded_file.getvalue()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds 2 MB limit.")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOADS_DIR / safe_name
    dest.write_bytes(raw)
    db.save_file_blob(str(dest), uploaded_file.name, raw)
    return str(dest), uploaded_file.name


def _render_feedback_cards(feedback_list: list[dict]) -> None:
    for fb in feedback_list:
        st.markdown(
            f"""
            <div class="ss-feedback-box">
                <div style="font-weight:700;color:#0F766E;margin-bottom:0.2rem;">
                    👩‍🏫 {html.escape(fb['teacher_name'])} • <span style="font-weight:400;color:#64748B;">{html.escape(fb['created_at'])}</span>
                </div>
                <div><strong>Strengths:</strong> {html.escape(fb['strengths'])}</div>
                <div><strong>Improvement Area:</strong> {html.escape(fb['improvement_area'])}</div>
                <div><strong>Next Action:</strong> {html.escape(fb['next_action'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _build_resume_markdown(student: dict, skills: list[dict], portfolio: list[dict], career_profile: dict | None) -> str:
    lines = [
        f"# {student['name']}",
        f"**USN:** {student['usn']} | **Program:** {student['course']} {student['branch']} ({student['grade']}) | **Email:** {student['email']}",
        "",
    ]
    if career_profile:
        lines += [f"## Target Role: {career_profile['target_role']}", f"**Interests:** {career_profile['interests']}", ""]
    lines += ["## Technical & Holistic Skills"]
    for s in skills:
        lines.append(f"- **{s['name']}** ({s['category']}) — Level {s['current_level']}/5 | Evidence: {s['evidence'] or 'In progress'}")
    lines += ["", "## Projects, Certificates & Achievements"]
    for p in portfolio:
        lines.append(f"- **{p['title']}** ({p['item_type']}, {p['issuer']}, {p['item_date']}): {p['description']}")
    return "\n".join(lines)


def render(student: dict) -> None:
    auth.require_role("student")
    student_id = student["id"]
    render_header(
        "🌟 Skills, Portfolio & Career Readiness",
        "Track skill growth over time, manage portfolio visibility, map career skill gaps, and export your resume.",
    )

    skills = db.get_skills(student_id)
    portfolio = db.get_portfolio_items(student_id, include_private=True)
    all_feedback = db.get_feedback_for_student(student_id)

    skill_fb: dict[int, list[dict]] = {}
    port_fb: dict[int, list[dict]] = {}
    general_fb: list[dict] = []
    for fb in all_feedback:
        if fb["target_type"] == "skill" and fb["target_id"]:
            skill_fb.setdefault(fb["target_id"], []).append(fb)
        elif fb["target_type"] == "portfolio" and fb["target_id"]:
            port_fb.setdefault(fb["target_id"], []).append(fb)
        else:
            general_fb.append(fb)

    tab_skills, tab_port, tab_career, tab_fb = st.tabs(
        ["🎯 Skills & Radar", "🗂️ Portfolio Showcase", "🚀 Career & Resume", "💬 Teacher Feedback"]
    )

    # 1. SKILLS & RADAR
    with tab_skills:
        c_radar, c_form = st.columns([1.3, 1])
        with c_radar:
            if skills:
                names = [s["name"] for s in skills]
                curr = [s["current_level"] for s in skills]
                targ = [s["target_level"] for s in skills]
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(r=targ + [targ[0]], theta=names + [names[0]], fill="toself", name="Target", line=dict(color=TEAL, dash="dot"), fillcolor="rgba(13,148,136,0.12)"))
                fig.add_trace(go.Scatterpolar(r=curr + [curr[0]], theta=names + [names[0]], fill="toself", name="Current", line=dict(color=INDIGO, width=2.5), fillcolor="rgba(79,70,229,0.25)"))
                fig.update_layout(title="🕸️ Holistic Skill Radar (1–5)", polar=dict(radialaxis=dict(visible=True, range=[0, 5], dtick=1)))
                st.plotly_chart(apply_plotly_theme(fig, height=380), width="stretch")
            else:
                st.info("Add your first skill to render the holistic radar.")

        with c_form:
            st.markdown("### ➕ Add Skill")
            with st.form("add_skill_form", clear_on_submit=True):
                sk_name = st.text_input("Skill Name *")
                sk_cat = st.selectbox("Category", db.SKILL_CATEGORIES)
                c1, c2, c3 = st.columns(3)
                with c1:
                    sk_curr = st.slider("Current", 1, 5, 3)
                with c2:
                    sk_targ = st.slider("Target", 1, 5, 5)
                with c3:
                    sk_int = st.slider("Interest", 1, 5, 4)
                sk_ev = st.text_input("Evidence (optional)", placeholder="e.g., NPTEL Cert, GitHub repo")
                sk_next = st.text_input("Next Practice Action", placeholder="e.g., Build 2 mini projects")
                if st.form_submit_button("💾 Save Skill", type="primary", width="stretch"):
                    if not sk_name.strip():
                        st.error("Skill name is required.")
                    elif sk_targ < sk_curr:
                        st.error("Target level must be >= current level.")
                    else:
                        db.add_skill(student_id, sk_name, sk_cat, sk_curr, sk_targ, sk_int, "", date.today().isoformat(), sk_ev, sk_next)
                        st.toast(f"Skill '{sk_name}' added!", icon="🎯")
                        st.rerun()

        st.markdown("### 📋 Skills & Progress History")
        for sk in skills:
            with st.container(border=True):
                l_col, r_col = st.columns([4, 1.5])
                with l_col:
                    st.markdown(f"**{sk['name']}** · `{sk['category']}` · Interest: {sk['interest_level']}/5 · Current: **{sk['current_level']}/{sk['target_level']}**")
                    st.progress(sk["current_level"] / 5.0)
                    if sk.get("evidence") or sk.get("next_action"):
                        st.caption(f"Evidence: {sk.get('evidence') or '—'} | Next: {sk.get('next_action') or '—'}")
                with r_col:
                    new_lvl = st.selectbox("Update Lvl", [1, 2, 3, 4, 5], index=sk["current_level"] - 1, key=f"lvl_sel_{sk['id']}")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("Save", key=f"lvl_btn_{sk['id']}", width="stretch"):
                            if new_lvl != sk["current_level"]:
                                db.update_skill_level(sk["id"], new_lvl)
                                st.toast("Skill level updated!", icon="📈")
                                st.rerun()
                    with b2:
                        if st.button("🗑️", key=f"del_sk_{sk['id']}", width="stretch"):
                            db.delete_skill(sk["id"])
                            st.rerun()
                hist = db.get_skill_history(sk["id"])
                if len(hist) > 1:
                    st.caption("History: " + " → ".join(f"L{h['level']} ({h['recorded_at']})" for h in hist))
                if sk["id"] in skill_fb:
                    _render_feedback_cards(skill_fb[sk["id"]])

    # 2. PORTFOLIO SHOWCASE
    with tab_port:
        with st.expander("➕ Add Portfolio Item"):
            with st.form("add_port_form", clear_on_submit=True):
                p1, p2 = st.columns(2)
                with p1:
                    p_title = st.text_input("Title *")
                    p_issuer = st.text_input("Issuer / Organizer *")
                    p_skills = st.text_input("Skills Demonstrated", placeholder="Python & DSA, Public Speaking")
                with p2:
                    p_type = st.selectbox("Type", db.PORTFOLIO_TYPES)
                    p_date = st.date_input("Date", value=date.today(), max_value=date.today())
                    p_vis = st.selectbox("Visibility", db.PORTFOLIO_VISIBILITIES)
                p_desc = st.text_area("Description", height=75)
                p_file = st.file_uploader("Attachment (PNG/JPG/PDF, max 2 MB)", type=["png", "jpg", "jpeg", "pdf"])
                if st.form_submit_button("💾 Add Portfolio Item", type="primary"):
                    if not p_title.strip() or not p_issuer.strip():
                        st.error("Title and Issuer are required.")
                    else:
                        try:
                            fpath, fname = _save_uploaded_file(p_file) if p_file else ("", "")
                            db.add_portfolio_item(student_id, p_title, p_type, p_issuer, p_date.isoformat(), p_desc, fpath, fname, p_skills, p_vis)
                            st.toast("Added to portfolio!", icon="🏆")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

        f1, f2, f3 = st.columns([1.4, 1, 1])
        with f1:
            p_search = st.text_input("🔎 Search portfolio", placeholder="Search title, issuer, or skill...")
        with f2:
            p_filter_type = st.selectbox("Filter Type", ["All"] + db.PORTFOLIO_TYPES)
        with f3:
            if portfolio:
                exp_df = pd.DataFrame(portfolio)[["title", "item_type", "issuer", "item_date", "skills_demonstrated", "visibility", "description", "file_name"]]
                st.download_button("📥 Download portfolio summary", data=exp_df.to_csv(index=False).encode("utf-8"), file_name=f"{student['usn']}_portfolio.csv", mime="text/csv", width="stretch")

        shown = portfolio
        if p_filter_type != "All":
            shown = [x for x in shown if x["item_type"] == p_filter_type]
        if p_search.strip():
            q = p_search.strip().lower()
            shown = [x for x in shown if q in (x["title"] + x["issuer"] + x.get("skills_demonstrated", "") + x["description"]).lower()]

        if not shown:
            st.info("No portfolio items match your filters.")
        else:
            for i in range(0, len(shown), 2):
                cols = st.columns(2)
                for col, item in zip(cols, shown[i : i + 2]):
                    with col:
                        badge = type_badge_html(item["item_type"])
                        st.markdown(
                            f"""
                            <div class="ss-card">
                                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem;">
                                    {badge}
                                    <span style="font-size:0.76rem;color:#64748B;">🔒 {html.escape(item.get('visibility', 'Teacher-Visible'))} • {html.escape(item['item_date'])}</span>
                                </div>
                                <h4 style="margin:0.1rem 0;color:#0F172A;">{html.escape(item['title'])}</h4>
                                <div style="font-size:0.83rem;color:#4F46E5;font-weight:600;margin-bottom:0.3rem;">🏛️ {html.escape(item['issuer'])}</div>
                                <p style="font-size:0.86rem;color:#334155;margin:0;">{html.escape(item['description'] or '')}</p>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        a1, a2, a3 = st.columns([1.4, 1.2, 0.8])
                        with a1:
                            new_vis = st.selectbox("Visibility", db.PORTFOLIO_VISIBILITIES, index=db.PORTFOLIO_VISIBILITIES.index(item.get("visibility", "Teacher-Visible")), key=f"vis_{item['id']}", label_visibility="collapsed")
                            if new_vis != item.get("visibility", "Teacher-Visible"):
                                db.update_portfolio_visibility(item["id"], new_vis)
                                st.toast("Visibility updated!", icon="🔒")
                                st.rerun()
                        with a2:
                            p_bytes = db.read_file_bytes(item.get("file_path", ""))
                            if p_bytes is not None:
                                st.download_button(f"📎 {item.get('file_name') or 'File'}", data=p_bytes, file_name=item.get("file_name") or "file", key=f"dl_p_{item['id']}", width="stretch")
                        with a3:
                            if st.button("🗑️", key=f"del_p_{item['id']}", width="stretch"):
                                db.delete_portfolio_item(item["id"])
                                st.rerun()
                        if item["id"] in port_fb:
                            _render_feedback_cards(port_fb[item["id"]])

    # 3. CAREER READINESS & RESUME EXPORT (PDF §12)
    with tab_career:
        st.caption("ℹ️ *Caution (PDF §12): Career readiness indicators are guidance for learning roadmaps — not hiring predictions or authoritative scores.*")
        cp = db.get_career_profile(student_id)
        role_names = list(CAREER_ROLES.keys())
        default_role = cp["target_role"] if cp and cp["target_role"] in role_names else role_names[0]
        checklist = json.loads(cp["checklist_json"]) if cp else []

        c_left, c_right = st.columns([1.2, 1])
        with c_left:
            target_role = st.selectbox("Target Career Role", role_names, index=role_names.index(default_role))
            interests = st.text_input("Career Interests", value=cp["interests"] if cp else "Applied AI, Systems")
            if st.button("💾 Save Career Target"):
                db.upsert_career_profile(student_id, target_role, interests, checklist)
                st.toast("Career target saved!", icon="🚀")
                st.rerun()

            role_spec = CAREER_ROLES[target_role]
            skill_map = {s["name"].lower(): s["current_level"] for s in skills}
            gap_rows = []
            for req_name, req_lvl in role_spec["required_skills"].items():
                # Partial match if student has similar skill name
                curr_lvl = skill_map.get(req_name.lower(), 0)
                if curr_lvl == 0:
                    for k, v in skill_map.items():
                        if req_name.split()[0].lower() in k:
                            curr_lvl = v
                            break
                gap_rows.append({"Skill": req_name, "Current": curr_lvl, "Required": req_lvl, "Gap": max(0, req_lvl - curr_lvl)})

            gap_df = pd.DataFrame(gap_rows)
            fig_gap = px.bar(gap_df.melt(id_vars="Skill", value_vars=["Current", "Required"]), x="Skill", y="value", color="variable", barmode="group", title=f"🧭 Skill Gap Analysis — {target_role}", color_discrete_sequence=[INDIGO, TEAL])
            fig_gap.update_yaxes(range=[0, 5.5], title="Level (1–5)")
            fig_gap.update_xaxes(title="")
            st.plotly_chart(apply_plotly_theme(fig_gap, height=320), width="stretch")

        with c_right:
            st.markdown("### ✅ Career Readiness Checklist")
            updated_chk = []
            for idx, item in enumerate(checklist):
                val = st.checkbox(item["task"], value=bool(item.get("done")), key=f"car_chk_{idx}")
                updated_chk.append({"task": item["task"], "done": val})
            if updated_chk != checklist:
                db.upsert_career_profile(student_id, target_role, interests, updated_chk)
                st.rerun()

            st.markdown("### 🛠️ Recommended Projects")
            for proj in role_spec["recommended_projects"]:
                st.markdown(f"- {proj}")

            resume_md = _build_resume_markdown(student, skills, portfolio, cp)
            st.download_button(
                "📄 Download Resume Summary (.md)",
                data=resume_md.encode("utf-8"),
                file_name=f"{student['usn']}_resume.md",
                mime="text/markdown",
                type="primary",
                width="stretch",
            )

    # 4. ALL TEACHER FEEDBACK
    with tab_fb:
        if not all_feedback:
            st.info("No teacher feedback yet.")
        else:
            _render_feedback_cards(all_feedback)
