"""Shared CSS, visual cards, Plotly theme, gamification badges, and career role profiles."""

from __future__ import annotations

import html
from typing import Any

import plotly.graph_objects as go
import streamlit as st

INDIGO = "#4F46E5"
INDIGO_DARK = "#3730A3"
TEAL = "#0D9488"
TEAL_LIGHT = "#14B8A6"
AMBER = "#F59E0B"
ROSE = "#E11D48"

CHART_COLORS = ["#4F46E5", "#0D9488", "#6366F1", "#14B8A6", "#F59E0B", "#0EA5E9"]

TYPE_BADGE_COLORS = {
    "Project": ("#EEF2FF", "#4338CA"),
    "Certificate": ("#CCFBF1", "#0F766E"),
    "Hackathon": ("#FEF3C7", "#B45309"),
    "Internship": ("#E0F2FE", "#0369A1"),
    "Award": ("#FCE7F3", "#BE185D"),
    "Workshop": ("#EDE9FE", "#6D28D9"),
    "Competition": ("#FFEDD5", "#C2410C"),
    "Research": ("#DCFCE7", "#15803D"),
    "Sports": ("#E0E7FF", "#3730A3"),
    "Volunteering": ("#F1F5F9", "#334155"),
}

CAREER_ROLES: dict[str, dict[str, Any]] = {
    "Software & AI Engineer": {
        "required_skills": {
            "Python & DSA": 4,
            "SQL & Database Design": 4,
            "System Design / Projects": 3,
            "Public Speaking": 3,
            "UI/UX Prototyping": 3,
        },
        "recommended_projects": [
            "Build a REST API + SQLite/PostgreSQL backend with automated input validation.",
            "Deploy an LLM-powered study assistant with offline graceful degradation.",
        ],
    },
    "Data Scientist / ML Analyst": {
        "required_skills": {
            "Python & DSA": 4,
            "SQL & Database Design": 4,
            "Applied Statistics & ML": 4,
            "Data Visualization": 4,
            "Public Speaking": 3,
        },
        "recommended_projects": [
            "Train and benchmark baseline vs. ensemble Scikit-learn models with RMSE/F1 reports.",
            "Create an interactive Plotly KPI dashboard summarizing feature importance.",
        ],
    },
    "Product / UX Designer": {
        "required_skills": {
            "UI/UX Prototyping": 5,
            "Public Speaking": 4,
            "User Research": 4,
            "Frontend Basics": 3,
            "Robotics Club Lead": 3,
        },
        "recommended_projects": [
            "Conduct a 5-user usability test and document before/after wireframe iterations.",
            "Design an accessible mobile-first academic planner component library.",
        ],
    },
    "Embedded / IoT Systems Engineer": {
        "required_skills": {
            "Python & DSA": 4,
            "Hardware & Sensors": 4,
            "SQL & Database Design": 3,
            "Robotics Club Lead": 4,
            "Technical Writing": 3,
        },
        "recommended_projects": [
            "Publish sensor calibration & power-draw benchmarks for an ESP32 telemetry node.",
            "Build a real-time MQTT/HTTP monitoring dashboard.",
        ],
    },
}


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.25rem; padding-bottom: 2.5rem; max-width: 1240px; }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #F8FAFC 0%, #EEF2FF 100%);
            border-right: 1px solid #E2E8F0;
        }
        .ss-hero {
            background: linear-gradient(135deg, #3730A3 0%, #4F46E5 55%, #0D9488 100%);
            color: #FFFFFF;
            padding: 1.25rem 1.65rem;
            border-radius: 18px;
            box-shadow: 0 10px 28px rgba(79, 70, 229, 0.18);
            margin-bottom: 1.15rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.75rem;
        }
        .ss-hero h1 { margin: 0; font-size: 1.55rem; font-weight: 700; letter-spacing: -0.02em; color: #FFFFFF; }
        .ss-hero p { margin: 0.22rem 0 0 0; font-size: 0.92rem; color: rgba(255, 255, 255, 0.9); }

        .ss-demo-badge {
            display: inline-flex; align-items: center; gap: 0.35rem;
            background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A;
            padding: 0.2rem 0.62rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600;
        }
        .ss-live-badge {
            display: inline-flex; align-items: center; gap: 0.35rem;
            background: #CCFBF1; color: #115E59; border: 1px solid #99F6E4;
            padding: 0.2rem 0.62rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600;
        }
        .ss-badge {
            display: inline-block; padding: 0.18rem 0.6rem; border-radius: 999px;
            font-size: 0.74rem; font-weight: 600;
        }
        .ss-kpi-card {
            background: #FFFFFF; border: 1px solid #E2E8F0; border-top: 4px solid #4F46E5;
            border-radius: 16px; padding: 0.95rem 1.1rem;
            box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
            margin-bottom: 0.55rem;
        }
        .ss-kpi-card.teal { border-top-color: #0D9488; }
        .ss-kpi-card.amber { border-top-color: #F59E0B; }
        .ss-kpi-card:hover { transform: translateY(-3px); box-shadow: 0 10px 24px rgba(79, 70, 229, 0.12); }
        .ss-kpi-label { font-size: 0.8rem; font-weight: 600; color: #64748B; margin-bottom: 0.25rem; }
        .ss-kpi-value { font-size: 1.62rem; font-weight: 700; color: #0F172A; line-height: 1.15; }
        .ss-kpi-sub { font-size: 0.76rem; color: #0D9488; margin-top: 0.3rem; font-weight: 500; }

        .ss-card {
            background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px;
            padding: 1rem 1.2rem; box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
            margin-bottom: 0.8rem;
        }
        .ss-card:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(15, 23, 42, 0.08); border-color: #C7D2FE; }
        .ss-weak-card {
            background: linear-gradient(135deg, #EEF2FF 0%, #F0FDFA 100%);
            border: 1px solid #C7D2FE; border-left: 5px solid #4F46E5;
            border-radius: 14px; padding: 1rem 1.15rem; margin-top: 0.45rem;
        }
        .ss-feedback-box {
            background: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #0D9488;
            border-radius: 12px; padding: 0.75rem 0.95rem; margin-top: 0.5rem; font-size: 0.87rem;
        }
        .ss-ai-note {
            display: inline-block; background: #F1F5F9; color: #475569;
            border-radius: 8px; padding: 0.24rem 0.6rem; font-size: 0.77rem; font-weight: 500; margin-top: 0.4rem;
        }
        .ss-timer-box {
            background: linear-gradient(135deg, #EEF2FF 0%, #CCFBF1 100%);
            border: 1px solid #C7D2FE; border-radius: 18px; padding: 1.15rem; text-align: center; margin-bottom: 0.75rem;
        }
        .ss-timer-clock {
            font-size: 2.85rem; font-weight: 800; color: #1E1B4B;
            font-variant-numeric: tabular-nums; letter-spacing: 0.03em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str, badge_html: str = "") -> None:
    st.markdown(
        f"""
        <div class="ss-hero">
            <div>
                <h1>{html.escape(title)}</h1>
                <p>{html.escape(subtitle)}</p>
            </div>
            <div>{badge_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def demo_badge_html(is_demo: bool) -> str:
    if is_demo:
        return '<span class="ss-demo-badge">✨ Demo mode</span>'
    return '<span class="ss-live-badge">⚡ Gemini AI</span>'


def render_kpi_card(label: str, value: str, sub: str, variant: str = "indigo") -> None:
    cls = "" if variant == "indigo" else variant
    st.markdown(
        f"""
        <div class="ss-kpi-card {cls}">
            <div class="ss-kpi-label">{html.escape(label)}</div>
            <div class="ss-kpi-value">{html.escape(value)}</div>
            <div class="ss-kpi-sub">{html.escape(sub)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def type_badge_html(item_type: str) -> str:
    bg, fg = TYPE_BADGE_COLORS.get(item_type, ("#F1F5F9", "#334155"))
    return f'<span class="ss-badge" style="background:{bg};color:{fg};">{html.escape(item_type)}</span>'


def apply_plotly_theme(fig: go.Figure, height: int = 330) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=20, r=20, t=42, b=24),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", color="#1E293B", size=12),
        title_font=dict(size=14, color="#0F172A"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(showgrid=False, linecolor="#CBD5E1")
    fig.update_yaxes(gridcolor="#E2E8F0", zerolinecolor="#CBD5E1")
    return fig


def compute_gamification(sessions: list[dict], quizzes: list[dict], skills: list[dict], portfolio: list[dict], streak: int) -> dict[str, Any]:
    """Calculate Study XP, Scholar Level, and unlocked achievement badges."""
    xp = (
        len(sessions) * 20
        + len(quizzes) * 30
        + sum(1 for q in quizzes if q["score"] >= 80) * 20
        + len(skills) * 25
        + len(portfolio) * 40
        + streak * 15
    )
    level = max(1, (xp // 250) + 1)
    badges: list[str] = []
    if streak >= 5:
        badges.append("🔥 5-Day Streak")
    if sum(s["duration_minutes"] for s in sessions) >= 300:
        badges.append("⏱️ 5h+ Focus Club")
    if any(q["score"] >= 90 for q in quizzes):
        badges.append("🏆 Quiz Ace (90%+)")
    if len(portfolio) >= 3:
        badges.append("🌟 Portfolio Builder")
    if len(skills) >= 5:
        badges.append("🕸️ Holistic Learner")
    return {"xp": xp, "level": level, "badges": badges}


def build_printable_report_html(
    student: dict[str, Any],
    att_summary: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    quizzes: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    feedback_list: list[dict[str, Any]],
) -> str:
    """Build a crisp print-ready HTML student progress report card."""
    overall_att = round(sum(a["pct"] for a in att_summary) / len(att_summary), 1) if att_summary else 100.0
    ia_avg = round(sum(100.0 * a["score"] / max(1.0, a["max_score"]) for a in assessments) / len(assessments), 1) if assessments else 0.0
    quiz_avg = round(sum(q["score"] for q in quizzes) / len(quizzes), 1) if quizzes else 0.0

    att_rows_html = "".join(
        f"<tr><td>{html.escape(a['subject'])}</td><td>{a['attended_classes']}/{a['total_classes']}</td><td>{a['pct']:.1f}%</td></tr>"
        for a in att_summary
    ) or "<tr><td colspan='3'>No attendance records</td></tr>"

    skill_rows_html = "".join(
        f"<tr><td>{html.escape(s['name'])}</td><td>{html.escape(s['category'])}</td><td>{s['current_level']} / {s['target_level']}</td></tr>"
        for s in skills
    ) or "<tr><td colspan='3'>No skills recorded</td></tr>"

    fb_html = "".join(
        f"<div class='fb'><strong>{html.escape(f['teacher_name'])}</strong> ({html.escape(f['created_at'])})<br>"
        f"<b>Strengths:</b> {html.escape(f['strengths'])}<br>"
        f"<b>Next Action:</b> {html.escape(f['next_action'])}</div>"
        for f in feedback_list[:5]
    ) or "<p>No teacher feedback recorded yet.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SmartStudy AI Report Card — {html.escape(student['name'])}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #0F172A; margin: 28px; background: #F8FAFC; }}
  .wrap {{ max-width: 820px; margin: auto; background: #fff; padding: 28px; border-radius: 14px; border: 1px solid #E2E8F0; }}
  .hero {{ background: linear-gradient(135deg, #3730A3, #4F46E5, #0D9488); color: #fff; padding: 18px 22px; border-radius: 12px; }}
  .hero h1 {{ margin: 0; font-size: 22px; }}
  .hero p {{ margin: 4px 0 0; opacity: 0.92; font-size: 13px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 18px 0; }}
  .kpi {{ border: 1px solid #E2E8F0; border-top: 4px solid #4F46E5; border-radius: 10px; padding: 12px; text-align: center; }}
  .kpi strong {{ display: block; font-size: 20px; color: #1E1B4B; }}
  h2 {{ font-size: 15px; color: #3730A3; border-bottom: 1px solid #E2E8F0; padding-bottom: 4px; margin-top: 20px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 7px 10px; border-bottom: 1px solid #E2E8F0; }}
  th {{ background: #EEF2FF; color: #312E81; }}
  .fb {{ background: #F8FAFC; border-left: 4px solid #0D9488; padding: 8px 12px; margin-bottom: 8px; border-radius: 6px; font-size: 13px; }}
  @media print {{ body {{ background: #fff; margin: 0; }} .wrap {{ border: none; }} }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>SmartStudy AI — Student Holistic Progress Report</h1>
    <p>{html.escape(student['name'])} ({html.escape(student['usn'])}) • {html.escape(student['course'])} {html.escape(student['branch'])} • {html.escape(student['grade'])} ({html.escape(student['section'])})</p>
  </div>
  <div class="kpis">
    <div class="kpi"><span>Overall Attendance</span><strong>{overall_att:.1f}%</strong></div>
    <div class="kpi"><span>IA Marks Average</span><strong>{ia_avg:.1f}%</strong></div>
    <div class="kpi"><span>Quiz Average</span><strong>{quiz_avg:.1f}%</strong></div>
  </div>
  <h2>Subject-Wise Attendance</h2>
  <table><thead><tr><th>Subject</th><th>Attended</th><th>Percentage</th></tr></thead><tbody>{att_rows_html}</tbody></table>
  <h2>Holistic Skills & Growth</h2>
  <table><thead><tr><th>Skill</th><th>Category</th><th>Current / Target</th></tr></thead><tbody>{skill_rows_html}</tbody></table>
  <h2>Teacher Mentorship Feedback</h2>
  {fb_html}
</div>
</body>
</html>"""
