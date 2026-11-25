"""Online Examinations, AI Practice Quizzes & Scikit-learn ML Performance Insights."""

from __future__ import annotations

import json
import time

import pandas as pd
import plotly.express as px
import streamlit as st

import ai
import auth
import db
import knowledge
import ml
from ui import INDIGO, TEAL, apply_plotly_theme, demo_badge_html, render_header


def render(student: dict) -> None:
    auth.require_role("student")
    student_id = student["id"]
    subjects = db.get_subject_names()

    render_header(
        "📝 Examinations & ML Performance Predictor",
        "Take quick AI quizzes, sit timed teacher assessments, and explore Scikit-learn performance estimates.",
        demo_badge_html(not ai.has_api_key()),
    )

    tab_ai_quiz, tab_exams, tab_hist, tab_ml = st.tabs(
        ["🎯 Quick AI 5-Q Quiz", "📝 Teacher Published Exams", "📈 Attempt History", "🧠 ML Performance Insights"]
    )

    # 1. QUICK AI 5-QUESTION QUIZ
    with tab_ai_quiz:
        c1, c2, c3, c4 = st.columns([1, 1.3, 0.8, 1])
        with c1:
            q_subj = st.selectbox("Subject", subjects, key="aiq_subj")
        with c2:
            q_topic = st.text_input("Topic", value="Core Concepts", key="aiq_topic")
        with c3:
            q_diff = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=1, key="aiq_diff")
        with c4:
            q_src = st.selectbox("Source", ["AI + Knowledge Docs", "Stored Question Bank"], key="aiq_src")

        if st.button("🎯 Generate 5-question MCQ quiz", type="primary"):
            if not q_topic.strip():
                st.error("Enter a topic first.")
            elif q_src == "Stored Question Bank":
                bank_qs = [
                    b
                    for b in db.get_question_bank(q_subj, approved_only=True)
                    if len(json.loads(b["options_json"] or "[]")) >= 2
                    and (q_diff == "All" or not b["difficulty"] or b["difficulty"].lower() == q_diff.lower())
                ]
                if not bank_qs:
                    bank_qs = [b for b in db.get_question_bank(q_subj, approved_only=True) if len(json.loads(b["options_json"] or "[]")) >= 2]
                if not bank_qs:
                    st.warning("No approved MCQ questions in Question Bank for this subject yet — switching to AI + Knowledge Docs.")
                    kb_hits = knowledge.retrieve_relevant_chunks(f"{q_subj} {q_topic}", role="student", subject=q_subj, top_k=3)
                    qs, q_demo = ai.generate_quiz(q_subj, q_topic.strip(), q_diff, knowledge_chunks=kb_hits)
                else:
                    qs = []
                    for b in bank_qs[:5]:
                        opts = json.loads(b["options_json"] or "[]")
                        while len(opts) < 4:
                            opts.append("None of the above")
                        c_idx = opts.index(b["correct_answer"]) if b["correct_answer"] in opts else 0
                        qs.append({"question": b["question"], "options": opts[:4], "correct_index": c_idx, "explanation": b.get("explanation") or "From Question Bank."})
                    q_demo = False
                    st.session_state["active_quiz"] = {"subject": q_subj, "topic": q_topic.strip(), "questions": qs, "is_demo": q_demo, "submitted": False, "answers": {}, "score_pct": None, "correct": None, "started_at": time.time()}
                    st.toast(f"Loaded {len(qs)} question(s) from Question Bank!", icon="🎯")
            else:
                with st.spinner("Retrieving Knowledge Center materials & generating 5 MCQs..."):
                    kb_hits = knowledge.retrieve_relevant_chunks(f"{q_subj} {q_topic}", role="student", subject=q_subj, top_k=3)
                    qs, q_demo = ai.generate_quiz(q_subj, q_topic.strip(), q_diff, knowledge_chunks=kb_hits)
                st.session_state["active_quiz"] = {
                    "subject": q_subj,
                    "topic": q_topic.strip(),
                    "questions": qs,
                    "is_demo": q_demo,
                    "submitted": False,
                    "answers": {},
                    "score_pct": None,
                    "correct": None,
                    "started_at": time.time(),
                }
                st.toast("Quiz generated!", icon="🎯")

        quiz = st.session_state.get("active_quiz")
        if quiz:
            st.markdown(f"#### {quiz['subject']} — *{quiz['topic']}* {demo_badge_html(quiz['is_demo'])}", unsafe_allow_html=True)
            if not quiz["submitted"]:
                with st.form("ai_mcq_form"):
                    choices: dict[int, int] = {}
                    for idx, q in enumerate(quiz["questions"]):
                        st.markdown(f"**Q{idx + 1}. {q['question']}**")
                        choices[idx] = st.radio(
                            f"Q{idx + 1}",
                            options=list(range(4)),
                            format_func=lambda i, opts=q["options"]: opts[i],
                            key=f"ai_mcq_{idx}",
                            label_visibility="collapsed",
                        )
                    if st.form_submit_button("✅ Submit Quiz", type="primary"):
                        elapsed = max(1, int(time.time() - quiz["started_at"]))
                        correct = sum(1 for i, q in enumerate(quiz["questions"]) if choices[i] == q["correct_index"])
                        pct = round(100.0 * correct / len(quiz["questions"]), 1)
                        db.add_quiz_attempt(student_id, quiz["subject"], quiz["topic"], pct, correct, len(quiz["questions"]), time_taken_sec=elapsed, mode="Practice")
                        quiz["submitted"] = True
                        quiz["answers"] = choices
                        quiz["score_pct"] = pct
                        quiz["correct"] = correct
                        st.toast(f"Scored {correct}/5 ({pct:.0f}%)!", icon="🎉")
                        st.rerun()
            else:
                st.success(f"Score: **{quiz['correct']}/{len(quiz['questions'])} ({quiz['score_pct']:.0f}%)** — saved to history & dashboard.")
                for idx, q in enumerate(quiz["questions"]):
                    picked = quiz["answers"].get(idx, 0)
                    right = q["correct_index"]
                    with st.container(border=True):
                        st.markdown(f"**{'✅' if picked == right else '❌'} Q{idx + 1}. {q['question']}**")
                        st.write(f"Your answer: **{q['options'][picked]}** | Correct: **{q['options'][right]}**")
                        st.caption(q["explanation"])
                if st.button("🔄 Clear Quiz"):
                    st.session_state.pop("active_quiz", None)
                    st.rerun()

    # 2. PUBLISHED TEACHER EXAMS (PRACTICE & TIMED MODES + NEGATIVE MARKING)
    with tab_exams:
        exams = db.get_exams(published_only=True)
        if not exams:
            st.info("No teacher-published exams available yet.")
        else:
            exam_labels = [f"{e['title']} ({e['subject']} • {e['mode']} • {e['duration_minutes']}m • -{e['negative_marks']} neg)" for e in exams]
            sel_idx = st.selectbox("Select Assessment", list(range(len(exams))), format_func=lambda i: exam_labels[i])
            exam = exams[sel_idx]

            if st.button("🚀 Start Selected Exam", type="primary"):
                qs = db.get_exam_questions(exam["id"])
                if not qs:
                    st.error("This exam has no questions attached yet.")
                else:
                    st.session_state["active_exam"] = {
                        "exam": exam,
                        "questions": qs,
                        "started_at": time.time(),
                        "submitted": False,
                        "result": None,
                    }

            act = st.session_state.get("active_exam")
            if act and act["exam"]["id"] == exam["id"]:
                qs = act["questions"]
                elapsed = int(time.time() - act["started_at"])
                limit_sec = exam["duration_minutes"] * 60
                if exam["mode"] == "Timed" and not act["submitted"]:
                    rem_sec = max(0, limit_sec - elapsed)
                    m, s = divmod(rem_sec, 60)
                    st.warning(f"⏱️ **Timed Mode** — Time Remaining: `{m:02d}:{s:02d}` | Negative marking: `-{exam['negative_marks']}` per wrong answer")

                if not act["submitted"]:
                    with st.form("teacher_exam_form"):
                        user_ans: dict[int, str] = {}
                        for idx, q in enumerate(qs):
                            st.markdown(f"**Q{idx + 1}. [{q['q_type']} • {q['marks']} pts] {q['question']}**")
                            opts = json.loads(q["options_json"] or "[]")
                            if opts:
                                user_ans[idx] = st.radio(f"Ans {idx}", opts, key=f"ex_q_{exam['id']}_{idx}", label_visibility="collapsed")
                            else:
                                user_ans[idx] = st.text_input(f"Short answer Q{idx + 1}", key=f"ex_q_{exam['id']}_{idx}")
                        if st.form_submit_button("📩 Submit Assessment", type="primary"):
                            earned = 0.0
                            total_m = 0.0
                            correct_cnt = 0
                            reviews = []
                            for idx, q in enumerate(qs):
                                m_val = float(q["marks"])
                                total_m += m_val
                                resp = str(user_ans.get(idx, "")).strip()
                                exp = str(q["correct_answer"]).strip()
                                is_ok = resp.lower() == exp.lower()
                                if is_ok:
                                    earned += m_val
                                    correct_cnt += 1
                                elif resp:
                                    earned -= float(exam["negative_marks"])
                                reviews.append((q, resp, exp, is_ok))
                            earned = max(0.0, round(earned, 2))
                            pct = round(100.0 * earned / max(1.0, total_m), 1)
                            db.add_quiz_attempt(student_id, exam["subject"], exam["title"], pct, correct_cnt, len(qs), exam_id=exam["id"], time_taken_sec=elapsed, mode=exam["mode"])
                            act["submitted"] = True
                            act["result"] = {"earned": earned, "total": total_m, "pct": pct, "correct": correct_cnt, "reviews": reviews}
                            st.toast(f"Exam submitted! {pct:.1f}%", icon="📝")
                            st.rerun()
                else:
                    res = act["result"]
                    st.success(f"Exam Score: **{res['earned']} / {res['total']} ({res['pct']}%)** • Correct: {res['correct']}/{len(qs)}")
                    for idx, (q, resp, exp, is_ok) in enumerate(res["reviews"], 1):
                        with st.container(border=True):
                            st.markdown(f"**{'✅' if is_ok else '❌'} Q{idx}. {q['question']}**")
                            st.write(f"Your answer: `{resp or '—'}` | Correct: `{exp}`")
                            if q.get("explanation"):
                                st.caption(q["explanation"])

    # 3. ATTEMPT HISTORY
    with tab_hist:
        attempts = db.get_quiz_attempts(student_id)
        if not attempts:
            st.info("No exam or quiz attempts yet.")
        else:
            df = pd.DataFrame(attempts)[["attempt_date", "subject", "topic", "mode", "correct_count", "total_questions", "score", "time_taken_sec"]].iloc[::-1]
            df = df.rename(columns={"attempt_date": "Date", "subject": "Subject", "topic": "Topic/Exam", "mode": "Mode", "correct_count": "Correct", "total_questions": "Total", "score": "Score (%)", "time_taken_sec": "Time (s)"})
            st.dataframe(df, hide_index=True, width="stretch")

    # 4. SCIKIT-LEARN ML PERFORMANCE PREDICTOR (PDF §8)
    with tab_ml:
        st.markdown("### 🧠 Academic Performance Analysis & ML Predictor")
        st.info(
            "📌 **Model Disclosure & Caveats (PDF §8):** Models are trained on a 240-record synthetic academic engagement dataset "
            "(80% train / 20% held-out test split, zero data leakage) and evaluated against your live SQLite records. "
            "**Outputs are statistical estimates to guide study priorities — not guaranteed final grades.**"
        )

        if "ml_bundle" not in st.session_state:
            st.session_state["ml_bundle"] = ml.train_and_evaluate_models()
        bundle = st.session_state["ml_bundle"]
        pred = ml.predict_student_performance(student_id, bundle)

        # Student Prediction Summary
        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric("Estimated Final Score", f"{pred['estimate_combined']}%", f"Linear: {pred['estimate_linear']}% | RF: {pred['estimate_rf']}%")
        with k2:
            st.metric("Support Tier", pred["support_tier"], f"{pred['on_track_prob']}% On-Track confidence")
        with k3:
            st.metric("Dataset Split", f"{bundle['n_train']} / {bundle['n_test']}", "Train / Held-out Test rows")

        if pred["missing_fields"]:
            st.warning("Data coverage notice (missing fields used defaults): " + ", ".join(pred["missing_fields"]))
        else:
            st.success("Full 6/6 live data coverage from Attendance, Study Sessions, Assignments, IA Marks, Quizzes, and Habits.")

        st.markdown("#### 🔍 Why This Estimate? (Explainability & Next Actions)")
        for ex in pred["explanations"]:
            st.markdown(f"- {ex}")

        st.markdown("---")
        c_m1, c_m2 = st.columns(2)
        with c_m1:
            st.markdown("#### 📉 Regression Model Comparison (Test Set)")
            st.dataframe(bundle["reg_metrics"], hide_index=True, width="stretch")
        with c_m2:
            st.markdown("#### 🎯 Classification Model Comparison (Test Set)")
            st.dataframe(bundle["clf_metrics"], hide_index=True, width="stretch")

        fig_imp = px.bar(
            bundle["importances"],
            x="Importance",
            y="Feature",
            orientation="h",
            title="📊 Random Forest Feature Importance (What Drives Performance)",
            color_discrete_sequence=[TEAL],
        )
        fig_imp.update_yaxes(autorange="reversed", title="")
        fig_imp.update_xaxes(title="Relative Importance")
        st.plotly_chart(apply_plotly_theme(fig_imp, height=300), width="stretch")
