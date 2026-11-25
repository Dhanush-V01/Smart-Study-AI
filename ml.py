"""Scikit-learn Performance Analysis & ML Engine (Baseline vs. Comparison Models)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    precision_score,
    r2_score,
    recall_score,
    root_mean_squared_error,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import db

FEATURE_COLUMNS = [
    "attendance_pct",
    "study_hours_weekly",
    "assignment_completion_pct",
    "ia_avg_pct",
    "quiz_avg_pct",
    "habit_consistency_pct",
]

FEATURE_LABELS = {
    "attendance_pct": "Attendance (%)",
    "study_hours_weekly": "Weekly Study Hours",
    "assignment_completion_pct": "Assignment Completion (%)",
    "ia_avg_pct": "Internal Assessment Avg (%)",
    "quiz_avg_pct": "Practice Quiz Avg (%)",
    "habit_consistency_pct": "Habit Consistency (%)",
}


def build_benchmark_dataset(n_samples: int = 240, seed: int = 42) -> pd.DataFrame:
    """Generate a transparent synthetic academic benchmark dataset (with realistic noise)."""
    rng = np.random.default_rng(seed)
    attendance = np.clip(rng.normal(82, 11, n_samples), 45, 100)
    study_hrs = np.clip(rng.normal(7.5, 3.0, n_samples), 1.0, 20.0)
    assign_pct = np.clip(rng.normal(78, 16, n_samples), 20, 100)
    ia_avg = np.clip(0.35 * attendance + 1.8 * study_hrs + rng.normal(32, 9, n_samples), 25, 100)
    quiz_avg = np.clip(0.55 * ia_avg + 0.25 * assign_pct + rng.normal(12, 8, n_samples), 25, 100)
    habit_pct = np.clip(0.45 * assign_pct + 2.0 * study_hrs + rng.normal(18, 12, n_samples), 15, 100)

    final_score = np.clip(
        0.16 * attendance
        + 0.75 * study_hrs
        + 0.14 * assign_pct
        + 0.34 * ia_avg
        + 0.24 * quiz_avg
        + 0.08 * habit_pct
        + rng.normal(0, 3.8, n_samples),
        20,
        99,
    )
    support_tier = np.where(final_score >= 65.0, 1, 0)  # 1 = On Track, 0 = Needs Attention

    return pd.DataFrame(
        {
            "attendance_pct": np.round(attendance, 1),
            "study_hours_weekly": np.round(study_hrs, 2),
            "assignment_completion_pct": np.round(assign_pct, 1),
            "ia_avg_pct": np.round(ia_avg, 1),
            "quiz_avg_pct": np.round(quiz_avg, 1),
            "habit_consistency_pct": np.round(habit_pct, 1),
            "final_score": np.round(final_score, 1),
            "on_track": support_tier,
        }
    )


def train_and_evaluate_models() -> dict[str, Any]:
    """Train baseline & comparison regression + classification models with strict train/test split."""
    df = build_benchmark_dataset()
    X = df[FEATURE_COLUMNS]
    y_reg = df["final_score"]
    y_clf = df["on_track"]

    X_train, X_test, yr_train, yr_test, yc_train, yc_test = train_test_split(
        X, y_reg, y_clf, test_size=0.20, random_state=42, stratify=y_clf
    )

    # Regression: Baseline LinearRegression vs. RandomForestRegressor
    reg_base = make_pipeline(StandardScaler(), LinearRegression())
    reg_base.fit(X_train, yr_train)
    pred_rb = reg_base.predict(X_test)

    reg_rf = RandomForestRegressor(n_estimators=120, max_depth=6, random_state=42)
    reg_rf.fit(X_train, yr_train)
    pred_rrf = reg_rf.predict(X_test)

    # Classification: Baseline LogisticRegression vs. RandomForestClassifier
    clf_base = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, random_state=42))
    clf_base.fit(X_train, yc_train)
    pred_cb = clf_base.predict(X_test)

    clf_rf = RandomForestClassifier(n_estimators=120, max_depth=6, random_state=42)
    clf_rf.fit(X_train, yc_train)
    pred_crf = clf_rf.predict(X_test)

    reg_metrics = pd.DataFrame(
        [
            {
                "Model": "Linear Regression (Baseline)",
                "MAE": round(float(mean_absolute_error(yr_test, pred_rb)), 2),
                "RMSE": round(float(root_mean_squared_error(yr_test, pred_rb)), 2),
                "R²": round(float(r2_score(yr_test, pred_rb)), 3),
            },
            {
                "Model": "Random Forest Regressor",
                "MAE": round(float(mean_absolute_error(yr_test, pred_rrf)), 2),
                "RMSE": round(float(root_mean_squared_error(yr_test, pred_rrf)), 2),
                "R²": round(float(r2_score(yr_test, pred_rrf)), 3),
            },
        ]
    )

    clf_metrics = pd.DataFrame(
        [
            {
                "Model": "Logistic Regression (Baseline)",
                "Accuracy": round(float(accuracy_score(yc_test, pred_cb)), 3),
                "Precision": round(float(precision_score(yc_test, pred_cb, zero_division=0)), 3),
                "Recall": round(float(recall_score(yc_test, pred_cb, zero_division=0)), 3),
                "F1": round(float(f1_score(yc_test, pred_cb, zero_division=0)), 3),
            },
            {
                "Model": "Random Forest Classifier",
                "Accuracy": round(float(accuracy_score(yc_test, pred_crf)), 3),
                "Precision": round(float(precision_score(yc_test, pred_crf, zero_division=0)), 3),
                "Recall": round(float(recall_score(yc_test, pred_crf, zero_division=0)), 3),
                "F1": round(float(f1_score(yc_test, pred_crf, zero_division=0)), 3),
            },
        ]
    )

    importances = pd.DataFrame(
        {
            "Feature": [FEATURE_LABELS[c] for c in FEATURE_COLUMNS],
            "Importance": np.round(reg_rf.feature_importances_, 3),
        }
    ).sort_values("Importance", ascending=False)

    return {
        "n_train": len(X_train),
        "n_test": len(X_test),
        "reg_base": reg_base,
        "reg_rf": reg_rf,
        "clf_base": clf_base,
        "clf_rf": clf_rf,
        "reg_metrics": reg_metrics,
        "clf_metrics": clf_metrics,
        "importances": importances,
        "dataset_preview": df.head(10),
    }


def extract_student_features(student_id: int) -> tuple[dict[str, float], list[str]]:
    """Aggregate live SQLite metrics for a student and report any missing data fields."""
    missing: list[str] = []

    att_summary = db.get_attendance_summary(student_id)
    if att_summary:
        att_pct = float(np.mean([a["pct"] for a in att_summary]))
    else:
        att_pct = 80.0
        missing.append("Attendance records (defaulted to 80%)")

    sessions = db.get_study_sessions(student_id)
    if sessions:
        total_min = sum(s["duration_minutes"] for s in sessions)
        unique_days = max(1, len({s["session_date"] for s in sessions}))
        weekly_hrs = round((total_min / 60.0) * (7.0 / max(7, unique_days)), 2)
    else:
        weekly_hrs = 2.0
        missing.append("Study sessions (defaulted to 2h/wk)")

    assigns = db.get_assignments(student_id)
    if assigns:
        done = sum(1 for a in assigns if a["status"] in ("Submitted", "Completed"))
        assign_pct = round(100.0 * done / len(assigns), 1)
    else:
        assign_pct = 75.0
        missing.append("Assignments (defaulted to 75%)")

    assessments = db.get_assessments(student_id)
    if assessments:
        ia_avg = round(float(np.mean([100.0 * a["score"] / max(1.0, a["max_score"]) for a in assessments])), 1)
    else:
        ia_avg = 70.0
        missing.append("Internal assessments (defaulted to 70%)")

    quizzes = db.get_quiz_attempts(student_id)
    if quizzes:
        quiz_avg = round(float(np.mean([q["score"] for q in quizzes])), 1)
    else:
        quiz_avg = 70.0
        missing.append("Quiz attempts (defaulted to 70%)")

    habits = db.get_habits(student_id)
    h_logs = db.get_habit_logs(student_id, days=7)
    if habits:
        target_total = sum(max(1, h["target_per_week"]) for h in habits)
        habit_pct = round(min(100.0, 100.0 * len(h_logs) / target_total), 1)
    else:
        habit_pct = 65.0
        missing.append("Habit logs (defaulted to 65%)")

    features = {
        "attendance_pct": round(att_pct, 1),
        "study_hours_weekly": weekly_hrs,
        "assignment_completion_pct": assign_pct,
        "ia_avg_pct": ia_avg,
        "quiz_avg_pct": quiz_avg,
        "habit_consistency_pct": habit_pct,
    }
    return features, missing


def predict_student_performance(student_id: int, bundle: dict[str, Any]) -> dict[str, Any]:
    """Produce score estimate, support tier, and plain-language explanations for a student."""
    features, missing = extract_student_features(student_id)
    X_row = pd.DataFrame([features])[FEATURE_COLUMNS]

    est_base = float(bundle["reg_base"].predict(X_row)[0])
    est_rf = float(bundle["reg_rf"].predict(X_row)[0])
    est_score = round(0.5 * est_base + 0.5 * est_rf, 1)

    prob_on_track = float(bundle["clf_rf"].predict_proba(X_row)[0][1])
    tier = "On Track" if prob_on_track >= 0.6 else "Needs Attention"

    reasons: list[str] = []
    if features["attendance_pct"] < 75:
        reasons.append(f"Attendance is {features['attendance_pct']}% (below 75% threshold) — catching up on classes boosts expected score.")
    if features["assignment_completion_pct"] < 70:
        reasons.append(f"Assignment completion is {features['assignment_completion_pct']}% — clearing pending/overdue tasks improves consistency.")
    if features["quiz_avg_pct"] < 70:
        reasons.append(f"Quiz average is {features['quiz_avg_pct']}% — targeted 5-question drills on weak subjects can raise readiness.")
    if features["study_hours_weekly"] >= 6.0 and features["ia_avg_pct"] >= 75:
        reasons.append(f"Consistent {features['study_hours_weekly']}h/wk study rhythm and {features['ia_avg_pct']}% IA average strongly support your trajectory.")
    if not reasons:
        reasons.append("Balanced study metrics across attendance, quizzes, and internal assessments.")

    return {
        "features": features,
        "missing_fields": missing,
        "estimate_linear": round(est_base, 1),
        "estimate_rf": round(est_rf, 1),
        "estimate_combined": est_score,
        "on_track_prob": round(prob_on_track * 100, 1),
        "support_tier": tier,
        "explanations": reasons,
    }
