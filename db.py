"""SQLite database schema, safe migration, comprehensive demo seeding, and queries for SmartStudy AI."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import cloud_sync

_CUSTOM_DB_PATH = cloud_sync._get_secret("SMARTSTUDY_DB_PATH")
DB_PATH = Path(_CUSTOM_DB_PATH) if _CUSTOM_DB_PATH else (Path(__file__).resolve().parent / "smartstudy.db")
_AUTO_SYNC_SUSPEND = False
SUBJECTS = ["Maths", "Physics", "DSA", "DBMS", "English"]
SKILL_CATEGORIES = [
    "Technical",
    "Communication",
    "Leadership",
    "Creative",
    "Sports",
    "Business",
    "Research",
    "Social Impact",
    "Other",
]
PORTFOLIO_TYPES = [
    "Project",
    "Certificate",
    "Hackathon",
    "Internship",
    "Workshop",
    "Competition",
    "Research",
    "Award",
    "Sports",
    "Volunteering",
]
PORTFOLIO_VISIBILITIES = ["Teacher-Visible", "Shared", "Private"]
PRIMARY_STUDENT_NAME = "Aarav Sharma"


# ---------------------------------------------------------------------------
# Password Hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected_hex = stored_hash.split("$", 1)
    except ValueError:
        return False
    computed = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(computed, expected_hex)


# ---------------------------------------------------------------------------
# Connection & Schema Management
# ---------------------------------------------------------------------------

@contextmanager
def get_connection():
    """Yield a SQLite connection with foreign keys and auto-sync after real writes."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    before_changes = conn.total_changes
    changed = False
    try:
        yield conn
        conn.commit()
        changed = conn.total_changes > before_changes
    finally:
        conn.close()
    if changed and not _AUTO_SYNC_SUSPEND:
        cloud_sync.push_db(DB_PATH)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {r["name"] for r in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, col_def: str) -> None:
    cols = _table_columns(conn, table)
    if cols and col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")


def init_db() -> None:
    """Pull cloud DB if configured on cold start, then create/migrate tables & seed defaults."""
    global _AUTO_SYNC_SUSPEND
    cloud_sync.pull_db_on_startup(DB_PATH)
    _AUTO_SYNC_SUSPEND = True
    try:
        _init_db_inner()
    finally:
        _AUTO_SYNC_SUSPEND = False


def _init_db_inner() -> None:
    with get_connection() as conn:
        # Detect if upgrading from early v1 MVP schema (which lacked `users` and `usn` on `students`)
        existing_tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        upgrading_from_v1 = "students" in existing_tables and "users" not in existing_tables

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'teacher', 'admin', 'parent')),
                full_name TEXT NOT NULL,
                department TEXT DEFAULT 'CSE',
                linked_student_id INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usn TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL DEFAULT '',
                course TEXT NOT NULL DEFAULT 'B.Tech',
                branch TEXT NOT NULL DEFAULT 'CSE',
                semester INTEGER NOT NULL DEFAULT 5,
                section TEXT NOT NULL DEFAULT 'Section A',
                academic_year TEXT NOT NULL DEFAULT '2026-27',
                grade TEXT NOT NULL DEFAULT 'Sem 5',
                avatar_emoji TEXT NOT NULL DEFAULT '🎓',
                extra_json TEXT NOT NULL DEFAULT '{}',
                is_archived INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL UNIQUE,
                credits INTEGER NOT NULL DEFAULT 4,
                semester INTEGER NOT NULL DEFAULT 5,
                department TEXT NOT NULL DEFAULT 'CSE',
                teacher_name TEXT NOT NULL DEFAULT 'Ms. Priya Nair',
                category TEXT NOT NULL DEFAULT 'Core',
                topics_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                att_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Present', 'Absent', 'Late')),
                UNIQUE(student_id, subject, att_date)
            );

            CREATE TABLE IF NOT EXISTS assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                component TEXT NOT NULL,
                score REAL NOT NULL,
                max_score REAL NOT NULL DEFAULT 100,
                weightage REAL NOT NULL DEFAULT 1.0,
                recorded_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                due_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                marks REAL,
                max_marks REAL NOT NULL DEFAULT 20,
                attachment_path TEXT DEFAULT '',
                attachment_name TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS doubts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS doubt_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doubt_id INTEGER NOT NULL REFERENCES doubts(id) ON DELETE CASCADE,
                sender TEXT NOT NULL CHECK(sender IN ('student', 'ai')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                session_date TEXT NOT NULL,
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                source TEXT NOT NULL DEFAULT 'Manual'
            );

            CREATE TABLE IF NOT EXISTS study_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                title TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'Medium',
                estimated_minutes INTEGER NOT NULL DEFAULT 45,
                due_date TEXT NOT NULL,
                scheduled_day TEXT DEFAULT 'Unscheduled',
                is_completed INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS study_reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                week_label TEXT NOT NULL,
                wins TEXT NOT NULL,
                blockers TEXT NOT NULL,
                next_focus TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS question_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                difficulty TEXT NOT NULL DEFAULT 'Medium',
                q_type TEXT NOT NULL DEFAULT 'MCQ',
                question TEXT NOT NULL,
                options_json TEXT NOT NULL DEFAULT '[]',
                correct_answer TEXT NOT NULL,
                explanation TEXT DEFAULT '',
                marks REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'Manual',
                approved_by_teacher INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL DEFAULT 15,
                question_count INTEGER NOT NULL DEFAULT 5,
                total_marks REAL NOT NULL DEFAULT 5.0,
                negative_marks REAL NOT NULL DEFAULT 0.0,
                mode TEXT NOT NULL DEFAULT 'Practice',
                created_by TEXT NOT NULL DEFAULT 'Ms. Priya Nair',
                is_published INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exam_questions (
                exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
                question_id INTEGER NOT NULL REFERENCES question_bank(id) ON DELETE CASCADE,
                PRIMARY KEY (exam_id, question_id)
            );

            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                exam_id INTEGER,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                score REAL NOT NULL,
                correct_count INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                time_taken_sec INTEGER DEFAULT 0,
                mode TEXT NOT NULL DEFAULT 'Practice',
                attempt_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                interest_level INTEGER NOT NULL DEFAULT 4,
                current_level INTEGER NOT NULL,
                target_level INTEGER NOT NULL,
                experience_note TEXT DEFAULT '',
                started_date TEXT DEFAULT '',
                evidence TEXT DEFAULT '',
                next_action TEXT DEFAULT '',
                is_archived INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS skill_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
                level INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                note TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Academic',
                target_date TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'High',
                progress INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'In Progress',
                milestones_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                frequency TEXT NOT NULL DEFAULT 'Daily',
                target_per_week INTEGER NOT NULL DEFAULT 5
            );

            CREATE TABLE IF NOT EXISTS habit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                log_date TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 1,
                UNIQUE(habit_id, log_date)
            );

            CREATE TABLE IF NOT EXISTS portfolio_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                item_type TEXT NOT NULL,
                issuer TEXT NOT NULL,
                item_date TEXT NOT NULL,
                skills_demonstrated TEXT DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'Teacher-Visible',
                description TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                file_name TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS career_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL UNIQUE REFERENCES students(id) ON DELETE CASCADE,
                target_role TEXT NOT NULL DEFAULT 'Software & AI Engineer',
                interests TEXT DEFAULT 'Backend Systems, Applied AI, EdTech',
                checklist_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT DEFAULT '',
                resource_url TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                file_name TEXT DEFAULT '',
                needs_revision INTEGER NOT NULL DEFAULT 0,
                revision_date TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                target_type TEXT NOT NULL DEFAULT 'general',
                target_id INTEGER,
                teacher_name TEXT NOT NULL DEFAULT 'Ms. Priya Nair',
                strengths TEXT NOT NULL,
                improvement_area TEXT NOT NULL,
                next_action TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_role TEXT NOT NULL DEFAULT 'student',
                student_id INTEGER,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Reminder',
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                title TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'Exam',
                event_date TEXT NOT NULL,
                subject TEXT DEFAULT '',
                description TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_name TEXT NOT NULL DEFAULT 'Ms. Priya Nair',
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                target_section TEXT NOT NULL DEFAULT 'All Sections',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                file_name TEXT NOT NULL DEFAULT '',
                file_path TEXT NOT NULL DEFAULT '',
                file_ext TEXT NOT NULL DEFAULT '.txt',
                doc_type TEXT NOT NULL DEFAULT 'Text / Markdown',
                subject TEXT NOT NULL DEFAULT '',
                subject_code TEXT NOT NULL DEFAULT '',
                semester INTEGER,
                topic TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Notes',
                description TEXT NOT NULL DEFAULT '',
                extracted_text TEXT NOT NULL DEFAULT '',
                detected_sections_json TEXT NOT NULL DEFAULT '[]',
                detected_tables_json TEXT NOT NULL DEFAULT '[]',
                missing_fields_json TEXT NOT NULL DEFAULT '[]',
                tags TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'Students & Teachers',
                status TEXT NOT NULL DEFAULT 'Active',
                uploader_username TEXT NOT NULL DEFAULT 'priya',
                uploader_name TEXT NOT NULL DEFAULT 'Ms. Priya Nair',
                uploader_role TEXT NOT NULL DEFAULT 'teacher',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                section_title TEXT NOT NULL DEFAULT 'Overview',
                content TEXT NOT NULL,
                keywords TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS document_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
                actor_username TEXT NOT NULL,
                action TEXT NOT NULL,
                summary TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teacher_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_username TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                section TEXT NOT NULL DEFAULT 'Section A',
                semester INTEGER NOT NULL DEFAULT 5,
                UNIQUE(teacher_username, subject_name, section, semester)
            );

            CREATE TABLE IF NOT EXISTS parent_student_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_username TEXT NOT NULL,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                relationship TEXT NOT NULL DEFAULT 'Guardian',
                UNIQUE(parent_username, student_id)
            );

            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL UNIQUE,
                hod_name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                semester INTEGER NOT NULL DEFAULT 5,
                department_code TEXT NOT NULL DEFAULT 'CSE',
                UNIQUE(name, semester, department_code)
            );

            CREATE TABLE IF NOT EXISTS file_blobs (
                file_path TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                content BLOB NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        # Safe non-destructive migration for users table to allow 'parent' role
        users_ddl_row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if users_ddl_row and "'parent'" not in (users_ddl_row["sql"] or ""):
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.executescript(
                """
                CREATE TABLE users_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('student', 'teacher', 'admin', 'parent')),
                    full_name TEXT NOT NULL,
                    department TEXT DEFAULT 'CSE',
                    linked_student_id INTEGER,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                INSERT INTO users_new (id, username, password_hash, role, full_name, department, linked_student_id, is_active, created_at)
                SELECT id, username, password_hash, role, full_name, department, linked_student_id, is_active, created_at FROM users;
                DROP TABLE users;
                ALTER TABLE users_new RENAME TO users;
                """
            )
            conn.execute("PRAGMA foreign_keys = ON;")

        # Safe non-destructive column migrations on existing tables
        _ensure_column(conn, "users", "employee_id", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "students", "guardian_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "students", "guardian_phone", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "students", "guardian_email", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "students", "guardian_alerts_enabled", "INTEGER NOT NULL DEFAULT 1")

        _ensure_column(conn, "question_bank", "question_number", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "question_bank", "subject_code", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "question_bank", "semester", "INTEGER DEFAULT 5")
        _ensure_column(conn, "question_bank", "unit", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "question_bank", "source_doc_id", "INTEGER")
        _ensure_column(conn, "question_bank", "source_doc_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "question_bank", "uploader_username", "TEXT NOT NULL DEFAULT 'priya'")
        _ensure_column(conn, "question_bank", "created_at", "TEXT NOT NULL DEFAULT ''")

        # Safe column migrations for any older existing tables
        if upgrading_from_v1:
            _ensure_column(conn, "students", "usn", "TEXT DEFAULT ''")
            _ensure_column(conn, "students", "email", "TEXT DEFAULT ''")
            _ensure_column(conn, "students", "course", "TEXT DEFAULT 'B.Tech'")
            _ensure_column(conn, "students", "branch", "TEXT DEFAULT 'CSE'")
            _ensure_column(conn, "students", "semester", "INTEGER DEFAULT 5")
            _ensure_column(conn, "students", "academic_year", "TEXT DEFAULT '2026-27'")
            _ensure_column(conn, "students", "extra_json", "TEXT DEFAULT '{}'")
            _ensure_column(conn, "students", "is_archived", "INTEGER DEFAULT 0")
            _ensure_column(conn, "study_sessions", "start_time", "TEXT DEFAULT ''")
            _ensure_column(conn, "study_sessions", "end_time", "TEXT DEFAULT ''")
            _ensure_column(conn, "quiz_attempts", "exam_id", "INTEGER")
            _ensure_column(conn, "quiz_attempts", "time_taken_sec", "INTEGER DEFAULT 0")
            _ensure_column(conn, "quiz_attempts", "mode", "TEXT DEFAULT 'Practice'")
            _ensure_column(conn, "skills", "interest_level", "INTEGER DEFAULT 4")
            _ensure_column(conn, "skills", "experience_note", "TEXT DEFAULT ''")
            _ensure_column(conn, "skills", "started_date", "TEXT DEFAULT ''")
            _ensure_column(conn, "skills", "evidence", "TEXT DEFAULT ''")
            _ensure_column(conn, "skills", "next_action", "TEXT DEFAULT ''")
            _ensure_column(conn, "skills", "is_archived", "INTEGER DEFAULT 0")
            _ensure_column(conn, "portfolio_items", "skills_demonstrated", "TEXT DEFAULT ''")
            _ensure_column(conn, "portfolio_items", "visibility", "TEXT DEFAULT 'Teacher-Visible'")

            # Cleanly reset/upgrade v1 demo DB so new tables (users, attendance, subjects, exams, etc.) are fully populated
            _clear_all_tables(conn)

        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            _seed_demo_data(conn)
        _ensure_upgrade_seed_data(conn)


def _clear_all_tables(conn: sqlite3.Connection) -> None:
    tables = [
        "file_blobs",
        "document_history",
        "knowledge_chunks",
        "knowledge_documents",
        "parent_student_links",
        "teacher_assignments",
        "sections",
        "departments",
        "activity_logs",
        "announcements",
        "calendar_events",
        "notifications",
        "feedback",
        "notes",
        "career_profiles",
        "portfolio_items",
        "habit_logs",
        "habits",
        "goals",
        "skill_history",
        "skills",
        "quiz_attempts",
        "exam_questions",
        "exams",
        "question_bank",
        "study_reflections",
        "study_tasks",
        "study_sessions",
        "doubt_messages",
        "doubts",
        "assignments",
        "assessments",
        "attendance",
        "subjects",
        "users",
        "students",
        "app_settings",
    ]
    for tbl in tables:
        conn.execute(f"DELETE FROM {tbl}")
    conn.execute("DELETE FROM sqlite_sequence")


def reset_demo_data() -> None:
    """Clear all tables and re-seed realistic demo data across every module."""
    with get_connection() as conn:
        _clear_all_tables(conn)
        _seed_demo_data(conn)
        _ensure_upgrade_seed_data(conn)


def _ensure_upgrade_seed_data(conn: sqlite3.Connection) -> None:
    """Non-destructively seed Parent account, Teacher assignments, and Knowledge Center docs if absent."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Ensure guardian contact info on existing seeded students if blank
    aarav_row = conn.execute("SELECT id, guardian_name FROM students WHERE name = 'Aarav Sharma'").fetchone()
    if aarav_row:
        if not (aarav_row["guardian_name"] or "").strip():
            conn.execute(
                "UPDATE students SET guardian_name=?, guardian_phone=?, guardian_email=?, guardian_alerts_enabled=1 WHERE id=?",
                ("Mr. Rajesh Sharma", "+91-98450-11223", "rajesh.sharma.parent@example.com", aarav_row["id"]),
            )
        # Ensure parent demo account exists
        parent_row = conn.execute("SELECT id FROM users WHERE username = 'parent_sharma'").fetchone()
        if not parent_row:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, full_name, department, linked_student_id, created_at)
                VALUES (?, ?, 'parent', ?, 'Parent Portal', ?, ?)
                """,
                ("parent_sharma", hash_password("parent123"), "Mr. Rajesh Sharma (Parent)", aarav_row["id"], now_str),
            )
        conn.execute(
            "INSERT OR IGNORE INTO parent_student_links (parent_username, student_id, relationship) VALUES (?, ?, ?)",
            ("parent_sharma", aarav_row["id"], "Father"),
        )

    # Ensure default departments and sections exist
    dept_count = conn.execute("SELECT COUNT(*) FROM departments").fetchone()[0]
    if dept_count == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO departments (code, name, hod_name, description, created_at) VALUES (?, ?, ?, ?, ?)",
            [
                ("CSE", "Computer Science & Engineering", "Dr. Meenakshi Rao", "Core computing, AI, algorithms, and systems.", now_str),
                ("ECE", "Electronics & Communication", "Dr. Suresh Verma", "VLSI, embedded systems, and signal processing.", now_str),
                ("ISE", "Information Science & Engineering", "Prof. Kavita Hegde", "Software engineering and data platforms.", now_str),
                ("AIML", "Artificial Intelligence & ML", "Dr. Vikram Joshi", "Machine learning, deep learning, and data science.", now_str),
                ("ME", "Mechanical Engineering", "Dr. R. Subramanian", "Thermodynamics, robotics, and CAD/CAM.", now_str),
            ],
        )
    sec_count = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    if sec_count == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO sections (name, semester, department_code) VALUES (?, ?, ?)",
            [
                ("Section A", 5, "CSE"),
                ("Section B", 5, "CSE"),
                ("Section C", 5, "CSE"),
            ],
        )

    # Ensure default teacher employee_id for Ms. Priya Nair
    conn.execute("UPDATE users SET employee_id = 'TCH001' WHERE username = 'priya' AND (employee_id IS NULL OR employee_id = '')")

    # Ensure teacher assignments for Priya Nair
    ta_count = conn.execute("SELECT COUNT(*) FROM teacher_assignments").fetchone()[0]
    if ta_count == 0:
        for subj in SUBJECTS:
            for sec in ("Section A", "Section B"):
                conn.execute(
                    "INSERT OR IGNORE INTO teacher_assignments (teacher_username, subject_name, section, semester) VALUES (?, ?, ?, 5)",
                    ("priya", subj, sec),
                )

    # Ensure Knowledge Center starter documents exist
    kb_count = conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0]
    if kb_count == 0:
        starter_docs = [
            (
                "DSA Module 2: Binary Search & Trees Study Guide",
                "dsa_binary_search_trees.md",
                "",
                ".md",
                "Text / Markdown",
                "DSA",
                "CS503",
                5,
                "Binary Search & BST",
                "Notes",
                "Teacher-curated notes covering binary search invariants, lower/upper bounds, and BST traversals.",
                (
                    "# Binary Search & Binary Search Trees\n\n"
                    "## 1. Binary Search Invariant\n"
                    "Binary search works on any monotonic predicate over a sorted array. By checking the midpoint "
                    "`mid = lo + (hi - lo) // 2`, half of the remaining search space is eliminated at every comparison, "
                    "resulting in O(log n) worst-case time complexity and O(1) iterative space.\n\n"
                    "## 2. Binary Search Tree (BST) Traversals\n"
                    "An Inorder traversal (Left -> Root -> Right) visits all BST nodes in non-decreasing sorted ascending order. "
                    "Preorder is useful for serializing tree structure, and Postorder is ideal for deleting nodes bottom-up."
                ),
                json.dumps(["1. Binary Search Invariant", "2. Binary Search Tree (BST) Traversals"]),
                "[]",
                "[]",
                "dsa,binary-search,bst,exam-prep",
                "Students & Teachers",
                "Active",
                "priya",
                "Ms. Priya Nair",
                "teacher",
                now_str,
                now_str,
            ),
            (
                "DBMS Reference: 1NF to BCNF Normalization Rules",
                "dbms_normalization_guide.md",
                "",
                ".md",
                "Text / Markdown",
                "DBMS",
                "CS504",
                5,
                "Normalization (1NF–BCNF)",
                "Reference materials",
                "Step-by-step functional dependency rules and decomposition examples for 2NF, 3NF, and BCNF.",
                (
                    "# Database Normalization Reference\n\n"
                    "## 1. Second Normal Form (2NF)\n"
                    "A relation is in 2NF if it is in 1NF and has no partial dependencies—every non-prime attribute must depend on the whole candidate key.\n\n"
                    "## 2. Third Normal Form (3NF) & BCNF\n"
                    "3NF eliminates transitive dependencies (A -> B -> C where B is non-key). "
                    "BCNF requires that for every non-trivial functional dependency X -> Y, X must be a superkey."
                ),
                json.dumps(["1. Second Normal Form (2NF)", "2. Third Normal Form (3NF) & BCNF"]),
                "[]",
                "[]",
                "dbms,normalization,3nf,bcnf",
                "Students & Teachers",
                "Active",
                "priya",
                "Ms. Priya Nair",
                "teacher",
                now_str,
                now_str,
            ),
            (
                "Physics Lab Manual: Gauss Law & Kirchhoff Circuits",
                "physics_gauss_kirchhoff_manual.md",
                "",
                ".md",
                "Text / Markdown",
                "Physics",
                "CS502",
                5,
                "Electrostatics & Circuits",
                "Lab manuals",
                "Practical lab notes on Gaussian surfaces, electric flux, and KVL/KCL loop analysis.",
                (
                    "# Electrostatics & DC Circuit Laws\n\n"
                    "## 1. Gauss's Law\n"
                    "The net electric flux through any closed Gaussian surface equals Q_enclosed / epsilon_0. "
                    "Use spherical symmetry for point charges and cylindrical symmetry for infinite line charges.\n\n"
                    "## 2. Kirchhoff's Laws\n"
                    "Kirchhoff's Current Law (KCL) expresses conservation of electric charge at a junction. "
                    "Kirchhoff's Voltage Law (KVL) expresses conservation of energy around any closed circuit loop (sum of potential changes = 0)."
                ),
                json.dumps(["1. Gauss's Law", "2. Kirchhoff's Laws"]),
                "[]",
                "[]",
                "physics,gauss-law,kirchhoff,lab",
                "Students & Teachers",
                "Active",
                "priya",
                "Ms. Priya Nair",
                "teacher",
                now_str,
                now_str,
            ),
        ]
        for doc in starter_docs:
            cur = conn.execute(
                """
                INSERT INTO knowledge_documents
                (title, file_name, file_path, file_ext, doc_type, subject, subject_code, semester, topic, category,
                 description, extracted_text, detected_sections_json, detected_tables_json, missing_fields_json,
                 tags, visibility, status, uploader_username, uploader_name, uploader_role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                doc,
            )
            did = cur.lastrowid
            # Create searchable chunks
            sections = [p.strip() for p in doc[11].split("\n\n") if p.strip()]
            for idx, sec in enumerate(sections):
                sec_title = sec.splitlines()[0].lstrip("# ").strip()[:80]
                conn.execute(
                    "INSERT INTO knowledge_chunks (doc_id, chunk_index, section_title, content, keywords) VALUES (?, ?, ?, ?, ?)",
                    (did, idx, sec_title, sec, doc[15]),
                )
            conn.execute(
                "INSERT INTO document_history (doc_id, actor_username, action, summary, created_at) VALUES (?, ?, ?, ?, ?)",
                (did, "priya", "UPLOAD", f"Seeded knowledge document '{doc[0]}'", now_str),
            )


def _d(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _dfut(days_ahead: int) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


def _seed_demo_data(conn: sqlite3.Connection) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # App settings
    conn.executemany(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        [
            ("attendance_threshold", "75"),
            ("passing_marks", "40"),
            ("institution_name", "SmartStudy Institute of Technology"),
            ("academic_term", "2026-27 • Semester 5"),
        ],
    )

    # Students
    students_data = [
        ("1SI24CS001", "Aarav Sharma", "aarav.sharma@smartstudy.edu", "B.Tech", "CSE", 5, "Section A", "2026-27", "Sem 5", "🧑‍🎓"),
        ("1SI24CS002", "Ananya Verma", "ananya.verma@smartstudy.edu", "B.Tech", "CSE", 5, "Section A", "2026-27", "Sem 5", "👩‍🎓"),
        ("1SI24CS003", "Rohan Patel", "rohan.patel@smartstudy.edu", "B.Tech", "CSE", 5, "Section B", "2026-27", "Sem 5", "🧑‍💻"),
        ("1SI24CS004", "Meera Iyer", "meera.iyer@smartstudy.edu", "B.Tech", "CSE", 5, "Section A", "2026-27", "Sem 5", "👩‍🔬"),
        ("1SI24CS005", "Kabir Singh", "kabir.singh@smartstudy.edu", "B.Tech", "CSE", 5, "Section B", "2026-27", "Sem 5", "🧑‍🚀"),
    ]
    conn.executemany(
        """
        INSERT INTO students
        (usn, name, email, course, branch, semester, section, academic_year, grade, avatar_emoji)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        students_data,
    )
    rows = conn.execute("SELECT id, name FROM students").fetchall()
    sid = {r["name"]: r["id"] for r in rows}
    aarav = sid["Aarav Sharma"]

    # Users (with PBKDF2 hashed passwords)
    users_data = [
        ("aarav", hash_password("student123"), "student", "Aarav Sharma", "CSE", aarav, now_str),
        ("ananya", hash_password("student123"), "student", "Ananya Verma", "CSE", sid["Ananya Verma"], now_str),
        ("rohan", hash_password("student123"), "student", "Rohan Patel", "CSE", sid["Rohan Patel"], now_str),
        ("meera", hash_password("student123"), "student", "Meera Iyer", "CSE", sid["Meera Iyer"], now_str),
        ("kabir", hash_password("student123"), "student", "Kabir Singh", "CSE", sid["Kabir Singh"], now_str),
        ("priya", hash_password("teacher123"), "teacher", "Ms. Priya Nair", "CSE", None, now_str),
        ("admin", hash_password("admin123"), "admin", "Dr. Rajesh Kulkarni (Admin)", "Administration", None, now_str),
    ]
    conn.executemany(
        """
        INSERT INTO users (username, password_hash, role, full_name, department, linked_student_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        users_data,
    )

    # Subjects & Curriculum
    subjects_data = [
        ("CS501", "Maths", 4, 5, "CSE", "Prof. Arvind Rao", "Core", json.dumps(["Integration by Parts", "Definite Integrals", "Differential Equations", "Probability & Bayes"])),
        ("CS502", "Physics", 3, 5, "CSE", "Dr. Kavita Menon", "Science", json.dumps(["Electrostatics & Gauss Law", "Kirchhoff's Laws", "Wave Optics", "Quantum Tunneling"])),
        ("CS503", "DSA", 4, 5, "CSE", "Ms. Priya Nair", "Core", json.dumps(["Big-O & Recurrences", "Binary Search", "Stacks & Queues", "Trees & Graphs", "Dynamic Programming"])),
        ("CS504", "DBMS", 4, 5, "CSE", "Ms. Priya Nair", "Core", json.dumps(["ER Modeling", "SQL Joins", "1NF/2NF/3NF/BCNF", "ACID & Transactions", "B+ Tree Indexing"])),
        ("HS505", "English", 2, 5, "CSE", "Prof. Elena D'Souza", "Humanities", json.dumps(["Analytical Writing", "Active Voice", "Technical Reports", "Presentation Skills"])),
    ]
    conn.executemany(
        """
        INSERT INTO subjects (code, name, credits, semester, department, teacher_name, category, topics_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        subjects_data,
    )

    # Attendance (last 10 days; Aarav deliberately has 70% in Physics to trigger threshold alert)
    att_rows: list[tuple[int, str, str, str]] = []
    for day_off in range(10):
        dt = _d(day_off)
        for s_name, st_id in sid.items():
            for subj in SUBJECTS:
                status = "Present"
                if st_id == aarav and subj == "Physics" and day_off in (1, 4, 7):
                    status = "Absent"
                elif st_id == aarav and subj == "DBMS" and day_off == 6:
                    status = "Late"
                elif st_id == sid["Kabir Singh"] and day_off in (2, 5, 8) and subj in ("Maths", "Physics"):
                    status = "Absent"
                elif st_id == sid["Rohan Patel"] and day_off == 3 and subj == "DBMS":
                    status = "Absent"
                att_rows.append((st_id, subj, dt, status))
    conn.executemany(
        "INSERT INTO attendance (student_id, subject, att_date, status) VALUES (?, ?, ?, ?)",
        att_rows,
    )

    # Internal Assessments & Marks (IA 1, IA 2, Lab, Assignment)
    assess_rows: list[tuple[int, str, str, float, float, float, str]] = []
    base_marks = {
        "Aarav Sharma": {"Maths": (22, 24, 23), "Physics": (15, 16, 18), "DSA": (24, 25, 24), "DBMS": (17, 18, 20), "English": (21, 22, 23)},
        "Ananya Verma": {"Maths": (24, 24, 25), "Physics": (22, 23, 22), "DSA": (25, 25, 25), "DBMS": (24, 23, 24), "English": (23, 23, 24)},
        "Rohan Patel": {"Maths": (18, 19, 20), "Physics": (17, 16, 18), "DSA": (21, 22, 21), "DBMS": (16, 17, 18), "English": (19, 20, 19)},
        "Meera Iyer": {"Maths": (23, 22, 23), "Physics": (24, 25, 24), "DSA": (21, 20, 22), "DBMS": (20, 21, 21), "English": (24, 24, 25)},
        "Kabir Singh": {"Maths": (14, 15, 16), "Physics": (12, 13, 14), "DSA": (16, 17, 18), "DBMS": (15, 14, 16), "English": (18, 19, 20)},
    }
    for s_name, st_id in sid.items():
        for subj, (ia1, ia2, lab) in base_marks[s_name].items():
            assess_rows.append((st_id, subj, "IA 1", float(ia1), 25.0, 0.35, _d(20)))
            assess_rows.append((st_id, subj, "IA 2", float(ia2), 25.0, 0.35, _d(7)))
            assess_rows.append((st_id, subj, "Lab", float(lab), 25.0, 0.30, _d(3)))
    conn.executemany(
        """
        INSERT INTO assessments (student_id, subject, component, score, max_score, weightage, recorded_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        assess_rows,
    )

    # Assignments & Deadlines
    assign_rows = [
        (aarav, "DBMS", "ER Diagram & 3NF Schema Design", "Design a normalized library database up to BCNF.", _dfut(2), "Pending", None, 20.0, "", ""),
        (aarav, "Physics", "Gauss Law Numerical Set", "Solve 10 problems on cylindrical & planar symmetry.", _dfut(4), "Pending", None, 20.0, "", ""),
        (aarav, "DSA", "Binary Search & Trees Lab", "Implement lower_bound, upper_bound, and BST inorder.", _d(2), "Submitted", 18.0, 20.0, "", ""),
        (aarav, "Maths", "Integration Worksheet #4", "Submit worked solutions for definite integral properties.", _d(5), "Completed", 19.0, 20.0, "", ""),
        (aarav, "English", "Technical Abstract Draft", "Write a 300-word analytical abstract on IoT telemetry.", _d(1), "Overdue", None, 20.0, "", ""),
        (sid["Ananya Verma"], "DSA", "DP Knapsack Lab", "Submit top-down and bottom-up implementations.", _d(2), "Completed", 20.0, 20.0, "", ""),
        (sid["Kabir Singh"], "Physics", "Gauss Law Numerical Set", "Solve 10 problems on cylindrical symmetry.", _d(1), "Overdue", None, 20.0, "", ""),
    ]
    conn.executemany(
        """
        INSERT INTO assignments
        (student_id, subject, title, description, due_date, status, marks, max_marks, attachment_path, attachment_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        assign_rows,
    )

    # Study Sessions (2 weeks for Aarav + peers)
    aarav_sessions = [
        (aarav, "DSA", "Binary Search & Bounds", 50, _d(0), "17:00", "17:50", "Solved 4 LeetCode problems", "Pomodoro"),
        (aarav, "Maths", "Integration by Parts", 45, _d(0), "18:10", "18:55", "Completed exercise 7.6", "Manual"),
        (aarav, "Physics", "Electrostatics & Gauss Law", 40, _d(1), "16:30", "17:10", "Derived field due to sheet", "Pomodoro"),
        (aarav, "DBMS", "3NF & BCNF Normalization", 35, _d(1), "19:00", "19:35", "Functional dependency closures", "Manual"),
        (aarav, "English", "Analytical Paragraph Writing", 30, _d(2), "18:00", "18:30", "Drafted two sample essays", "Manual"),
        (aarav, "DSA", "Recursion & Backtracking", 55, _d(3), "17:15", "18:10", "N-Queens dry run on paper", "Pomodoro"),
        (aarav, "Maths", "Definite Integrals", 50, _d(4), "16:00", "16:50", "King's property problems", "Pomodoro"),
        (aarav, "Physics", "Kirchhoff's Voltage Law", 35, _d(5), "19:15", "19:50", "Loop equations practice", "Manual"),
        (aarav, "DSA", "Stacks & Monotonic Queue", 60, _d(7), "17:00", "18:00", "Next greater element", "Pomodoro"),
        (aarav, "DBMS", "SQL Joins & Subqueries", 45, _d(8), "18:00", "18:45", "8 SQLite queries", "Manual"),
        (aarav, "Maths", "Differential Equations", 40, _d(9), "17:30", "18:10", "Variable separable method", "Manual"),
        (aarav, "English", "Reading Comprehension", 25, _d(10), "20:00", "20:25", "Timed passage practice", "Pomodoro"),
        (aarav, "Physics", "Wave Optics Interference", 45, _d(11), "16:30", "17:15", "Double slit derivations", "Manual"),
        (aarav, "DSA", "Time Complexity & Big-O", 50, _d(13), "17:00", "17:50", "Master theorem notes", "Pomodoro"),
    ]
    peer_sessions = [
        (sid["Ananya Verma"], "Maths", "Vectors & 3D Geometry", 60, _d(0), "", "", "Solved PYQs", "Pomodoro"),
        (sid["Ananya Verma"], "DSA", "Dynamic Programming", 75, _d(1), "", "", "Knapsack variants", "Pomodoro"),
        (sid["Ananya Verma"], "DBMS", "Indexing & B+ Trees", 55, _d(4), "", "", "Tree order calculations", "Manual"),
        (sid["Rohan Patel"], "DSA", "Linked Lists", 45, _d(1), "", "", "Cycle detection", "Pomodoro"),
        (sid["Rohan Patel"], "DBMS", "ER Diagrams", 40, _d(3), "", "", "Library schema", "Manual"),
        (sid["Meera Iyer"], "Physics", "Thermodynamics", 65, _d(0), "", "", "Carnot cycle numericals", "Pomodoro"),
        (sid["Meera Iyer"], "Maths", "Probability", 55, _d(2), "", "", "Bayes theorem", "Pomodoro"),
        (sid["Kabir Singh"], "Physics", "Magnetism", 30, _d(2), "", "", "Biot-Savart law", "Manual"),
        (sid["Kabir Singh"], "Maths", "Trigonometry", 35, _d(6), "", "", "Identities drill", "Manual"),
    ]
    conn.executemany(
        """
        INSERT INTO study_sessions
        (student_id, subject, topic, duration_minutes, session_date, start_time, end_time, notes, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        aarav_sessions + peer_sessions,
    )

    # Study Tasks & Weekly Reflections
    conn.executemany(
        """
        INSERT INTO study_tasks
        (student_id, subject, title, priority, estimated_minutes, due_date, scheduled_day, is_completed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (aarav, "Physics", "Revise Gauss Law & solve 5 numericals", "High", 50, _dfut(1), "Tomorrow", 0),
            (aarav, "DBMS", "Finish 3NF decomposition worksheet", "High", 45, _dfut(2), "Thursday", 0),
            (aarav, "DSA", "Practice 3 rotated binary search problems", "Medium", 60, _dfut(3), "Friday", 0),
            (aarav, "English", "Submit Technical Abstract Draft", "High", 30, _dfut(0), "Today", 0),
            (aarav, "Maths", "Review Integration by Parts formulas", "Low", 30, _d(0), "Today", 1),
        ],
    )
    conn.execute(
        """
        INSERT INTO study_reflections (student_id, week_label, wins, blockers, next_focus, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            aarav,
            f"Week of {_d(6)}",
            "Maintained a 6-day study streak and scored 100% on Stacks & Integration quizzes.",
            "Missed 2 Physics classes; Kirchhoff loop sign conventions slowed me down.",
            "Dedicate 2 Pomodoro blocks to Physics numericals and catch up on DBMS normalization.",
            now_str,
        ),
    )

    # Question Bank + Teacher Published Exams
    qb_items = [
        ("DSA", "Binary Search", "Easy", "MCQ", "What is the worst-case time complexity of Binary Search on a sorted array of size n?", ["O(1)", "O(log n)", "O(n)", "O(n log n)"], "O(log n)", "Each step halves the search interval.", 1.0, "Teacher", 1),
        ("DSA", "Stacks", "Easy", "MCQ", "Which data structure follows LIFO ordering?", ["Queue", "Stack", "Heap", "Graph"], "Stack", "Last-In, First-Out is the defining Stack property.", 1.0, "Teacher", 1),
        ("DSA", "Trees", "Medium", "MCQ", "Which traversal of a Binary Search Tree yields keys in sorted order?", ["Preorder", "Inorder", "Postorder", "Level-order"], "Inorder", "Left -> Root -> Right visits BST nodes in ascending order.", 1.0, "Teacher", 1),
        ("DSA", "Graphs", "Medium", "True/False", "Breadth-First Search (BFS) finds the shortest path in an unweighted graph.", ["True", "False"], "True", "BFS explores vertices in non-decreasing distance from the source.", 1.0, "Teacher", 1),
        ("DSA", "Hashing", "Medium", "Short Answer", "What is the expected average-case lookup complexity in a well-sized hash table? (Write O(1), O(log n), or O(n))", [], "O(1)", "Direct bucket indexing gives O(1) expected time.", 2.0, "Teacher", 1),
        ("DBMS", "Normalization", "Medium", "MCQ", "Which normal form eliminates transitive dependencies of non-key attributes?", ["1NF", "2NF", "3NF", "UNF"], "3NF", "3NF removes transitive dependencies on candidate keys.", 1.0, "Teacher", 1),
        ("DBMS", "SQL", "Easy", "MCQ", "Which SQL clause filters groups after GROUP BY aggregation?", ["WHERE", "HAVING", "ORDER BY", "DISTINCT"], "HAVING", "HAVING filters grouped rows; WHERE filters individual rows.", 1.0, "Teacher", 1),
        ("DBMS", "Transactions", "Easy", "True/False", "Atomicity in ACID ensures a transaction executes either completely or not at all.", ["True", "False"], "True", "All-or-nothing execution is Atomicity.", 1.0, "Teacher", 1),
        ("DBMS", "Joins", "Medium", "MCQ", "Which join keeps all rows from the left table even when no right match exists?", ["INNER JOIN", "LEFT JOIN", "CROSS JOIN", "SELF JOIN"], "LEFT JOIN", "Unmatched right columns become NULL.", 1.0, "Teacher", 1),
        ("DBMS", "Keys", "Easy", "MCQ", "Which constraint uniquely identifies each row and disallows NULL?", ["Foreign Key", "Primary Key", "Index", "Default"], "Primary Key", "Primary Keys enforce uniqueness and NOT NULL.", 1.0, "Teacher", 1),
        ("Physics", "Electrostatics", "Medium", "MCQ", "If distance between two point charges is doubled, electrostatic force becomes:", ["Half", "Double", "One-fourth", "Four times"], "One-fourth", "Coulomb force follows F ∝ 1/r^2.", 1.0, "AI Draft", 0),
        ("Maths", "Calculus", "Easy", "MCQ", "What is d/dx[sin(2x)]?", ["cos(2x)", "2 cos(2x)", "-2 cos(2x)", "2 sin(2x)"], "2 cos(2x)", "Apply chain rule: cos(2x) * 2.", 1.0, "Teacher", 1),
    ]
    conn.executemany(
        """
        INSERT INTO question_bank
        (subject, topic, difficulty, q_type, question, options_json, correct_answer, explanation, marks, source, approved_by_teacher)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (s, t, d, qt, q, json.dumps(opts), ca, exp, m, src, app)
            for (s, t, d, qt, q, opts, ca, exp, m, src, app) in qb_items
        ],
    )

    conn.execute(
        """
        INSERT INTO exams (title, subject, topic, duration_minutes, question_count, total_marks, negative_marks, mode, created_by, is_published, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("DSA Core Concepts Assessment", "DSA", "Search, Trees & Graphs", 10, 5, 6.0, 0.25, "Timed", "Ms. Priya Nair", 1, now_str),
    )
    dsa_exam_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    dsa_q_ids = [r["id"] for r in conn.execute("SELECT id FROM question_bank WHERE subject='DSA' AND approved_by_teacher=1 LIMIT 5").fetchall()]
    conn.executemany("INSERT INTO exam_questions (exam_id, question_id) VALUES (?, ?)", [(dsa_exam_id, qid) for qid in dsa_q_ids])

    conn.execute(
        """
        INSERT INTO exams (title, subject, topic, duration_minutes, question_count, total_marks, negative_marks, mode, created_by, is_published, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("DBMS Normalization & SQL Drill", "DBMS", "SQL & 3NF", 10, 5, 5.0, 0.0, "Practice", "Ms. Priya Nair", 1, now_str),
    )
    dbms_exam_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    dbms_q_ids = [r["id"] for r in conn.execute("SELECT id FROM question_bank WHERE subject='DBMS' AND approved_by_teacher=1 LIMIT 5").fetchall()]
    conn.executemany("INSERT INTO exam_questions (exam_id, question_id) VALUES (?, ?)", [(dbms_exam_id, qid) for qid in dbms_q_ids])

    # Quiz Attempts
    aarav_quizzes = [
        (aarav, None, "DSA", "Time Complexity & Big-O", 80.0, 4, 5, 190, "Practice", _d(13)),
        (aarav, None, "Physics", "Wave Optics Interference", 60.0, 3, 5, 220, "Practice", _d(11)),
        (aarav, None, "DBMS", "SQL Joins & Subqueries", 60.0, 3, 5, 210, "Practice", _d(8)),
        (aarav, None, "DSA", "Stacks & Monotonic Queue", 100.0, 5, 5, 165, "Practice", _d(7)),
        (aarav, None, "Physics", "Kirchhoff's Voltage Law", 40.0, 2, 5, 240, "Practice", _d(5)),
        (aarav, None, "Maths", "Definite Integrals", 80.0, 4, 5, 200, "Practice", _d(4)),
        (aarav, None, "English", "Analytical Writing", 80.0, 4, 5, 175, "Practice", _d(2)),
        (aarav, dbms_exam_id, "DBMS", "SQL & 3NF", 60.0, 3, 5, 205, "Practice", _d(1)),
        (aarav, None, "Maths", "Integration by Parts", 100.0, 5, 5, 150, "Practice", _d(0)),
        (aarav, dsa_exam_id, "DSA", "Search, Trees & Graphs", 80.0, 4, 5, 180, "Timed", _d(0)),
    ]
    peer_quizzes = [
        (sid["Ananya Verma"], dsa_exam_id, "DSA", "Dynamic Programming", 100.0, 5, 5, 140, "Timed", _d(1)),
        (sid["Ananya Verma"], None, "Maths", "Vectors", 80.0, 4, 5, 170, "Practice", _d(3)),
        (sid["Ananya Verma"], dbms_exam_id, "DBMS", "Indexing", 100.0, 5, 5, 155, "Practice", _d(5)),
        (sid["Rohan Patel"], None, "DSA", "Linked Lists", 80.0, 4, 5, 200, "Practice", _d(2)),
        (sid["Rohan Patel"], dbms_exam_id, "DBMS", "ER Diagrams", 60.0, 3, 5, 230, "Practice", _d(4)),
        (sid["Meera Iyer"], None, "Physics", "Thermodynamics", 100.0, 5, 5, 160, "Practice", _d(1)),
        (sid["Meera Iyer"], None, "Maths", "Probability", 80.0, 4, 5, 180, "Practice", _d(3)),
        (sid["Kabir Singh"], None, "Physics", "Magnetism", 40.0, 2, 5, 240, "Practice", _d(2)),
        (sid["Kabir Singh"], None, "Maths", "Trigonometry", 60.0, 3, 5, 210, "Practice", _d(5)),
    ]
    conn.executemany(
        """
        INSERT INTO quiz_attempts
        (student_id, exam_id, subject, topic, score, correct_count, total_questions, time_taken_sec, mode, attempt_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        aarav_quizzes + peer_quizzes,
    )

    # Skills + Skill History
    skills_data = [
        (aarav, "Python & DSA", "Technical", 5, 4, 5, "Solved 60+ algorithmic problems", _d(90), "LeetCode + NPTEL Cert", "Practice dynamic programming on trees"),
        (aarav, "SQL & Database Design", "Technical", 4, 3, 5, "Built SQLite schemas for 2 projects", _d(60), "DBMS Lab Project", "Master BCNF & query indexing"),
        (aarav, "Public Speaking", "Communication", 4, 3, 4, "Presented IoT project at STEM expo", _d(75), "Science Presenter Award", "Deliver a 5-min lightning talk without notes"),
        (aarav, "UI/UX Prototyping", "Creative", 4, 4, 5, "Designed interactive dashboards", _d(50), "Hackathon Prototype", "Conduct 3 peer usability reviews"),
        (aarav, "Robotics Club Lead", "Leadership", 5, 3, 4, "Mentored 8 junior members", _d(120), "Club Attendance Log", "Organize monthly hardware sprint"),
        (aarav, "Badminton", "Sports", 4, 4, 5, "College squad doubles player", _d(150), "Inter-House Semifinalist", "Improve backhand clear consistency"),
        (sid["Ananya Verma"], "Competitive Programming", "Technical", 5, 5, 5, "Top 2% regional finalist", _d(120), "Olympiad Gold", "Mentor peer study circle"),
        (sid["Ananya Verma"], "Technical Writing", "Communication", 4, 4, 5, "Open source docs contributor", _d(60), "PR links", "Publish system design blog post"),
        (sid["Rohan Patel"], "Web Development", "Technical", 4, 4, 5, "Full-stack club apps", _d(80), "Event Finder App", "Add automated API tests"),
        (sid["Meera Iyer"], "Physics Research", "Research", 5, 4, 5, "Solar thermal study", _d(100), "Research Grant", "Draft conference poster"),
        (sid["Kabir Singh"], "Football", "Sports", 5, 5, 5, "U-17 team captain", _d(180), "District Meet", "Lead fitness drills"),
    ]
    conn.executemany(
        """
        INSERT INTO skills
        (student_id, name, category, interest_level, current_level, target_level, experience_note, started_date, evidence, next_action)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        skills_data,
    )
    first_sk = conn.execute("SELECT id FROM skills WHERE student_id = ? ORDER BY id ASC LIMIT 1", (aarav,)).fetchone()
    if first_sk:
        conn.executemany(
            "INSERT INTO skill_history (skill_id, level, recorded_at, note) VALUES (?, ?, ?, ?)",
            [
                (first_sk["id"], 2, _d(90), "Started Python basics"),
                (first_sk["id"], 3, _d(45), "Completed trees & recursion"),
                (first_sk["id"], 4, _d(5), "Solved binary search & stack challenges"),
            ],
        )

    # Goals & Habits
    conn.executemany(
        """
        INSERT INTO goals (student_id, title, description, category, target_date, priority, progress, status, milestones_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (aarav, "Raise Physics Quiz Average above 80%", "Close gaps in Electrostatics and Kirchhoff's laws before IA 3.", "Academic", _dfut(14), "High", 55, "In Progress", json.dumps(["Review Gauss Law notes", "Solve 15 numericals", "Score 4/5 on Physics quiz"])),
            (aarav, "Complete 50 Medium DSA Problems", "Focus on binary search, sliding window, and DP.", "Skill", _dfut(25), "High", 72, "In Progress", json.dumps(["20 Array/Search problems", "15 Stack/Tree problems", "15 DP problems"])),
            (aarav, "Publish IoT Telemetry Case Study", "Write documentation and upload architecture PDF to portfolio.", "Career", _dfut(10), "Medium", 40, "In Progress", json.dumps(["Add calibration table", "Draw system diagram", "Share with mentor"])),
        ],
    )
    conn.executemany(
        "INSERT INTO habits (student_id, name, frequency, target_per_week) VALUES (?, ?, ?, ?)",
        [
            (aarav, "45-min Deep Study Block", "Daily", 6),
            (aarav, "Solve 2 Coding / Maths Problems", "Daily", 5),
            (aarav, "Revise Class Notes Before Sleep", "Daily", 5),
        ],
    )
    habit_ids = [r["id"] for r in conn.execute("SELECT id FROM habits WHERE student_id = ?", (aarav,)).fetchall()]
    h_logs = []
    for hid in habit_ids:
        for d_off in range(10):
            if (hid + d_off) % 4 != 0:
                h_logs.append((hid, _d(d_off), 1))
    conn.executemany("INSERT OR IGNORE INTO habit_logs (habit_id, log_date, completed) VALUES (?, ?, ?)", h_logs)

    # Portfolio Items (with skills_demonstrated and visibility)
    portfolio_data = [
        (aarav, "Smart Campus Air-Quality Monitor", "Project", "School STEM Innovation Lab", _d(18), "Python & DSA, UI/UX Prototyping", "Shared", "Built an ESP32 + Python dashboard tracking classroom CO2 and humidity in real time.", "", ""),
        (aarav, "National Youth Hackathon Finalist", "Hackathon", "TechSpark India", _d(32), "UI/UX Prototyping, Public Speaking", "Teacher-Visible", "Led a 3-student team to prototype an accessible study planner in 24 hours.", "", ""),
        (aarav, "Python Data Structures & Algorithms", "Certificate", "NPTEL / IIT Madras", _d(45), "Python & DSA", "Shared", "Completed 8-week coursework covering trees, graphs, and dynamic programming.", "", ""),
        (aarav, "Best Inter-House Science Presenter", "Award", "SmartStudy Institute", _d(60), "Public Speaking", "Teacher-Visible", "Awarded 1st place for explaining quantum tunneling with interactive visuals.", "", ""),
        (sid["Ananya Verma"], "Algorithmic Problem Solving Gold", "Award", "Regional Olympiad", _d(20), "Competitive Programming", "Shared", "Ranked top 2% across 400 participants.", "", ""),
        (sid["Ananya Verma"], "Open Source Docs Contributor", "Internship", "PyLearn Community", _d(35), "Technical Writing", "Teacher-Visible", "Authored beginner tutorials and fixed 12 documentation issues.", "", ""),
        (sid["Rohan Patel"], "Campus Event Finder App", "Project", "Self-Initiated", _d(25), "Web Development", "Shared", "Full-stack club calendar built with Python and SQLite.", "", ""),
        (sid["Meera Iyer"], "Solar Oven Efficiency Study", "Research", "Regional Science Fair", _d(15), "Physics Research", "Shared", "Measured thermal retention across three reflector geometries.", "", ""),
        (sid["Kabir Singh"], "Inter-School Football Captaincy", "Sports", "District Sports Meet", _d(28), "Football", "Teacher-Visible", "Captained U-17 squad to semi-finals.", "", ""),
    ]
    conn.executemany(
        """
        INSERT INTO portfolio_items
        (student_id, title, item_type, issuer, item_date, skills_demonstrated, visibility, description, file_path, file_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        portfolio_data,
    )

    # Career Profile
    conn.execute(
        """
        INSERT INTO career_profiles (student_id, target_role, interests, checklist_json, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            aarav,
            "Software & AI Engineer",
            "Distributed Backends, Applied Machine Learning, EdTech Products",
            json.dumps([
                {"task": "Complete 2 end-to-end SQL + Python projects", "done": True},
                {"task": "Practice 5 mock technical interviews", "done": False},
                {"task": "Publish clean GitHub README & architecture diagrams", "done": True},
                {"task": "Strengthen DBMS indexing & query optimization", "done": False},
            ]),
            now_str,
        ),
    )

    # Digital Notes
    conn.executemany(
        """
        INSERT INTO notes (student_id, subject, topic, title, content, tags, resource_url, needs_revision, revision_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (aarav, "Physics", "Gauss Law", "Gauss Law Gaussian Surfaces Cheat Sheet", "Total electric flux = Q_enclosed / epsilon_0. Choose spherical symmetry for point/shell, cylindrical for infinite line, pillbox for infinite sheet.", "electrostatics,exam-prep", "https://en.wikipedia.org/wiki/Gauss%27s_law", 1, _dfut(1), now_str),
            (aarav, "DBMS", "Normalization", "1NF to BCNF Quick Decision Rules", "1NF: atomic values. 2NF: no partial dependency on composite key. 3NF: no transitive dependency. BCNF: every determinant is a superkey.", "dbms,sql,3nf", "", 1, _dfut(2), now_str),
            (aarav, "DSA", "Binary Search", "Binary Search Invariant Template", "Use `lo <= hi` for exact match and `lo < hi` with `mid = lo + (hi - lo)//2` for lower_bound problems to avoid infinite loops.", "dsa,algorithms", "", 0, "", now_str),
        ],
    )

    # Teacher Feedback
    aarav_portfolio = conn.execute("SELECT id FROM portfolio_items WHERE student_id = ? ORDER BY id ASC LIMIT 1", (aarav,)).fetchone()
    conn.executemany(
        """
        INSERT INTO feedback
        (student_id, target_type, target_id, teacher_name, strengths, improvement_area, next_action, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (aarav, "skill", first_sk["id"] if first_sk else None, "Ms. Priya Nair", "Strong grasp of recursion trees and binary search invariants during class walkthroughs.", "Double-check edge cases with empty arrays and integer overflow bounds.", "Solve 3 boundary-condition problems on rotated sorted arrays this week.", now_str),
            (aarav, "portfolio", aarav_portfolio["id"] if aarav_portfolio else None, "Ms. Priya Nair", "Clear real-world sensor integration and crisp visual telemetry charts.", "Documentation lacks calibration methodology and battery life benchmarks.", "Add a 1-page testing log and upload a PDF architecture diagram to your portfolio.", now_str),
        ],
    )

    # Sample Doubts + Follow-up Thread
    conn.executemany(
        """
        INSERT INTO doubts (student_id, subject, question, answer, is_demo, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (aarav, "DSA", "Why is Binary Search O(log n) instead of O(n)?", "### Step-by-Step Explanation\n\n1. **Halving the search space:** Binary search checks the middle element of a sorted array.\n2. **Eliminating half every step:** Each comparison discards 50% of remaining candidates.\n3. **Logarithmic steps:** `n / 2^k = 1` gives `k = log2(n)`.\n\n**Analogy:** Looking up a word in a 1,000-page dictionary by opening at the middle takes ~10 flips instead of 1,000.", 1, (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")),
            (aarav, "DBMS", "What is the difference between 2NF and 3NF?", "### Step-by-Step Explanation\n\n1. **2NF:** Removes partial dependencies on part of a composite key.\n2. **3NF:** Removes transitive dependencies between non-key columns.\n\n**Example:** Moving `(DeptID, DeptHead)` out of `Student` eliminates transitive dependency `RollNo -> DeptID -> DeptHead`.", 1, (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")),
        ],
    )

    # Calendar Events, Announcements, Notifications & Audit Log
    conn.executemany(
        """
        INSERT INTO calendar_events (student_id, title, event_type, event_date, subject, description)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (None, "Internal Assessment 3 (IA 3)", "Exam", _dfut(6), "All", "Mid-semester assessment covering Modules 3 & 4."),
            (aarav, "DBMS Normalization Assignment Due", "Assignment", _dfut(2), "DBMS", "Submit ER diagram & BCNF decomposition."),
            (aarav, "Physics Gauss Law Numerical Due", "Assignment", _dfut(4), "Physics", "Submit 10 solved problems."),
            (None, "Annual TechSpark Hackathon", "College Event", _dfut(10), "DSA", "24-hour inter-department innovation challenge."),
            (aarav, "1:1 Mentor Portfolio Review", "Personal", _dfut(3), "General", "Discuss IoT calibration log with Ms. Priya Nair."),
        ],
    )
    conn.execute(
        """
        INSERT INTO announcements (teacher_name, title, message, target_section, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("Ms. Priya Nair", "IA 3 Syllabus & Practice Quiz Live", "Complete the published DSA & DBMS practice assessments before Friday. Students below 75% attendance must meet advisors.", "All Sections", now_str),
    )
    conn.executemany(
        """
        INSERT INTO notifications (user_role, student_id, title, message, category, is_read, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("student", aarav, "Attendance Alert: Physics (70%)", "Your Physics attendance is below the 75% threshold. Attend upcoming lectures to avoid shortage.", "Attendance Warning", 0, now_str),
            ("student", aarav, "Assignment Overdue: Technical Abstract Draft", "English assignment was due yesterday. Upload or update status in Academics.", "Deadline", 0, now_str),
            ("student", aarav, "New Teacher Feedback", "Ms. Priya Nair posted feedback on your Python & DSA skill and Smart Campus project.", "Feedback", 0, now_str),
        ],
    )
    conn.execute(
        """
        INSERT INTO activity_logs (username, role, action, details, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("system", "admin", "DEMO_SEED", "Initialized SmartStudy AI database with 5 students, academics, ML data, and holistic records.", now_str),
    )


# ---------------------------------------------------------------------------
# Auth, Users & Settings Queries
# ---------------------------------------------------------------------------

def get_user_by_username(username: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),)).fetchone()
        return dict(row) if row else None


def get_all_users() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role, full_name, department, employee_id, linked_student_id, is_active, created_at FROM users ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def create_user(
    username: str,
    password: str,
    role: str,
    full_name: str,
    department: str = "CSE",
    linked_student_id: int | None = None,
    employee_id: str = "",
) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, full_name, department, employee_id, linked_student_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (username.strip(), hash_password(password), role, full_name.strip(), department, employee_id.strip(), linked_student_id, now_str),
        )
        return cur.lastrowid


def toggle_user_active(user_id: int, is_active: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))


def log_activity(username: str, role: str, action: str, details: str = "") -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO activity_logs (username, role, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, role, action, details, now_str),
        )


def get_activity_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_settings() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def update_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, str(value)))


def export_db_bytes() -> bytes:
    return DB_PATH.read_bytes() if DB_PATH.exists() else b""


def restore_db_bytes(raw_bytes: bytes) -> None:
    if not raw_bytes.startswith(b"SQLite format 3"):
        raise ValueError("Invalid SQLite database file.")
    DB_PATH.write_bytes(raw_bytes)


# ---------------------------------------------------------------------------
# Students & Subjects Queries
# ---------------------------------------------------------------------------

def get_all_students(include_archived: bool = False) -> list[dict[str, Any]]:
    with get_connection() as conn:
        q = "SELECT * FROM students" + ("" if include_archived else " WHERE is_archived = 0") + " ORDER BY id ASC"
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_student_by_id(student_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(row) if row else None


def get_student_by_name(name: str = PRIMARY_STUDENT_NAME) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM students WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None


def upsert_student(
    usn: str,
    name: str,
    email: str,
    course: str,
    branch: str,
    semester: int,
    section: str,
    academic_year: str = "2026-27",
    student_id: int | None = None,
) -> int:
    with get_connection() as conn:
        if student_id:
            conn.execute(
                """
                UPDATE students
                SET usn=?, name=?, email=?, course=?, branch=?, semester=?, section=?, academic_year=?, grade=?
                WHERE id=?
                """,
                (usn.strip().upper(), name.strip(), email.strip(), course.strip(), branch.strip(), int(semester), section.strip(), academic_year.strip(), f"Sem {semester}", student_id),
            )
            return student_id
        cur = conn.execute(
            """
            INSERT INTO students (usn, name, email, course, branch, semester, section, academic_year, grade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usn.strip().upper(), name.strip(), email.strip(), course.strip(), branch.strip(), int(semester), section.strip(), academic_year.strip(), f"Sem {semester}"),
        )
        return cur.lastrowid


def set_student_archived(student_id: int, archived: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE students SET is_archived = ? WHERE id = ?", (1 if archived else 0, student_id))


def get_subjects() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM subjects ORDER BY code ASC").fetchall()
        return [dict(r) for r in rows]


def get_subject_names() -> list[str]:
    subs = [s["name"] for s in get_subjects()]
    return subs if subs else list(SUBJECTS)


def add_subject(code: str, name: str, credits: int, semester: int, department: str, teacher_name: str, category: str, topics: list[str]) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO subjects (code, name, credits, semester, department, teacher_name, category, topics_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (code.strip().upper(), name.strip(), int(credits), int(semester), department.strip(), teacher_name.strip(), category.strip(), json.dumps(topics)),
        )
        return cur.lastrowid


# ---------------------------------------------------------------------------
# Attendance, Assessments & Assignments
# ---------------------------------------------------------------------------

def upsert_attendance(student_id: int, subject: str, att_date: str, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO attendance (student_id, subject, att_date, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(student_id, subject, att_date) DO UPDATE SET status = excluded.status
            """,
            (student_id, subject, att_date, status),
        )


def get_attendance(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM attendance WHERE student_id = ? ORDER BY att_date DESC, subject ASC",
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_attendance_summary(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT subject,
                   COUNT(*) AS total_classes,
                   SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END) AS attended_classes,
                   ROUND(100.0 * SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct
            FROM attendance
            WHERE student_id = ?
            GROUP BY subject
            ORDER BY subject ASC
            """,
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_assessment(student_id: int, subject: str, component: str, score: float, max_score: float, weightage: float, recorded_date: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO assessments (student_id, subject, component, score, max_score, weightage, recorded_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, subject, component, float(score), float(max_score), float(weightage), recorded_date),
        )
        return cur.lastrowid


def get_assessments(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM assessments WHERE student_id = ? ORDER BY recorded_date DESC, subject ASC",
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_assignment(
    student_id: int,
    subject: str,
    title: str,
    description: str,
    due_date: str,
    status: str = "Pending",
    marks: float | None = None,
    max_marks: float = 20.0,
    attachment_path: str = "",
    attachment_name: str = "",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO assignments
            (student_id, subject, title, description, due_date, status, marks, max_marks, attachment_path, attachment_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, subject, title.strip(), description.strip(), due_date, status, marks, max_marks, attachment_path, attachment_name),
        )
        return cur.lastrowid


def get_assignments(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM assignments WHERE student_id = ? ORDER BY due_date ASC, id DESC",
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_assignment_status(assignment_id: int, status: str, marks: float | None = None) -> None:
    with get_connection() as conn:
        if marks is not None:
            conn.execute("UPDATE assignments SET status = ?, marks = ? WHERE id = ?", (status, float(marks), assignment_id))
        else:
            conn.execute("UPDATE assignments SET status = ? WHERE id = ?", (status, assignment_id))


# ---------------------------------------------------------------------------
# Doubts & Follow-up Thread
# ---------------------------------------------------------------------------

def add_doubt(student_id: int, subject: str, question: str, answer: str, is_demo: bool) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO doubts (student_id, subject, question, answer, is_demo, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, subject, question, answer, 1 if is_demo else 0, now_str),
        )
        return cur.lastrowid


def get_doubts(student_id: int, subject: str | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if subject and subject != "All":
            rows = conn.execute("SELECT * FROM doubts WHERE student_id = ? AND subject = ? ORDER BY id DESC", (student_id, subject)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM doubts WHERE student_id = ? ORDER BY id DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


def add_doubt_followup(doubt_id: int, sender: str, content: str) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO doubt_messages (doubt_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
            (doubt_id, sender, content, now_str),
        )
        return cur.lastrowid


def get_doubt_followups(doubt_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM doubt_messages WHERE doubt_id = ? ORDER BY id ASC", (doubt_id,)).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Study Sessions, Tasks & Reflections
# ---------------------------------------------------------------------------

def add_study_session(
    student_id: int,
    subject: str,
    topic: str,
    duration_minutes: int,
    session_date: str,
    notes: str = "",
    source: str = "Manual",
    start_time: str = "",
    end_time: str = "",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO study_sessions
            (student_id, subject, topic, duration_minutes, session_date, start_time, end_time, notes, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, subject, topic, duration_minutes, session_date, start_time, end_time, notes, source),
        )
        return cur.lastrowid


def get_study_sessions(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM study_sessions WHERE student_id = ? ORDER BY session_date DESC, id DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


def update_study_session(session_id: int, subject: str, topic: str, duration_minutes: int, session_date: str, notes: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE study_sessions SET subject=?, topic=?, duration_minutes=?, session_date=?, notes=? WHERE id=?",
            (subject, topic, duration_minutes, session_date, notes, session_id),
        )


def delete_study_session(session_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM study_sessions WHERE id = ?", (session_id,))


def compute_study_streak(student_id: int) -> int:
    with get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT session_date FROM study_sessions WHERE student_id = ?", (student_id,)).fetchall()
    if not rows:
        return 0
    logged_dates = {date.fromisoformat(r["session_date"]) for r in rows if r["session_date"]}
    cursor = date.today()
    if cursor not in logged_dates:
        cursor -= timedelta(days=1)
        if cursor not in logged_dates:
            return 0
    streak = 0
    while cursor in logged_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def add_study_task(student_id: int, subject: str, title: str, priority: str, estimated_minutes: int, due_date: str, scheduled_day: str = "Unscheduled") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO study_tasks (student_id, subject, title, priority, estimated_minutes, due_date, scheduled_day)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, subject, title.strip(), priority, int(estimated_minutes), due_date, scheduled_day),
        )
        return cur.lastrowid


def get_study_tasks(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM study_tasks WHERE student_id = ? ORDER BY is_completed ASC, due_date ASC, id DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


def toggle_study_task(task_id: int, is_completed: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE study_tasks SET is_completed = ? WHERE id = ?", (1 if is_completed else 0, task_id))


def delete_study_task(task_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM study_tasks WHERE id = ?", (task_id,))


def add_study_reflection(student_id: int, week_label: str, wins: str, blockers: str, next_focus: str) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO study_reflections (student_id, week_label, wins, blockers, next_focus, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, week_label, wins.strip(), blockers.strip(), next_focus.strip(), now_str),
        )
        return cur.lastrowid


def get_study_reflections(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM study_reflections WHERE student_id = ? ORDER BY id DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Question Bank, Exams & Quiz Attempts
# ---------------------------------------------------------------------------

def add_question_to_bank(
    subject: str,
    topic: str,
    difficulty: str,
    q_type: str,
    question: str,
    options: list[str],
    correct_answer: str,
    explanation: str = "",
    marks: float = 1.0,
    source: str = "Manual",
    approved_by_teacher: bool = True,
    question_number: str = "",
    subject_code: str = "",
    semester: int | None = 5,
    unit: str = "",
    source_doc_id: int | None = None,
    source_doc_name: str = "",
    uploader_username: str = "priya",
) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO question_bank
            (subject, topic, difficulty, q_type, question, options_json, correct_answer, explanation, marks, source, approved_by_teacher,
             question_number, subject_code, semester, unit, source_doc_id, source_doc_name, uploader_username, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subject.strip(),
                topic.strip(),
                difficulty.strip() if difficulty else "",
                q_type.strip() if q_type else "MCQ",
                question.strip(),
                json.dumps(options),
                correct_answer.strip(),
                explanation.strip(),
                float(marks),
                source,
                1 if approved_by_teacher else 0,
                str(question_number or "").strip(),
                subject_code.strip(),
                semester,
                unit.strip(),
                source_doc_id,
                source_doc_name.strip(),
                uploader_username.strip() or "priya",
                now_str,
            ),
        )
        return cur.lastrowid


def update_question_in_bank(
    question_id: int,
    subject: str,
    topic: str,
    difficulty: str,
    q_type: str,
    question: str,
    options: list[str],
    correct_answer: str,
    explanation: str,
    marks: float,
    approved_by_teacher: bool,
    unit: str = "",
    semester: int | None = 5,
    subject_code: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE question_bank
            SET subject=?, topic=?, difficulty=?, q_type=?, question=?, options_json=?, correct_answer=?, explanation=?,
                marks=?, approved_by_teacher=?, unit=?, semester=?, subject_code=?
            WHERE id=?
            """,
            (
                subject.strip(),
                topic.strip(),
                difficulty.strip(),
                q_type.strip(),
                question.strip(),
                json.dumps(options),
                correct_answer.strip(),
                explanation.strip(),
                float(marks),
                1 if approved_by_teacher else 0,
                unit.strip(),
                semester,
                subject_code.strip(),
                question_id,
            ),
        )


def delete_question_from_bank(question_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM question_bank WHERE id = ?", (question_id,))


def question_exists_duplicate(question_text: str, subject: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM question_bank WHERE LOWER(TRIM(question)) = LOWER(TRIM(?)) AND LOWER(TRIM(subject)) = LOWER(TRIM(?))",
            (question_text, subject),
        ).fetchone()
        return row is not None


def get_question_bank(subject: str | None = None, approved_only: bool = False) -> list[dict[str, Any]]:
    with get_connection() as conn:
        clauses = []
        params: list[Any] = []
        if subject and subject != "All":
            clauses.append("subject = ?")
            params.append(subject)
        if approved_only:
            clauses.append("approved_by_teacher = 1")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(f"SELECT * FROM question_bank{where} ORDER BY id DESC", params).fetchall()
        return [dict(r) for r in rows]


def approve_question(question_id: int, approved: bool = True) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE question_bank SET approved_by_teacher = ? WHERE id = ?", (1 if approved else 0, question_id))


def create_exam(
    title: str,
    subject: str,
    topic: str,
    duration_minutes: int,
    negative_marks: float,
    mode: str,
    created_by: str,
    question_ids: list[int],
    is_published: bool = True,
) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        total_marks = 0.0
        if question_ids:
            placeholders = ",".join("?" for _ in question_ids)
            total_marks = float(
                conn.execute(f"SELECT COALESCE(SUM(marks), 0) FROM question_bank WHERE id IN ({placeholders})", question_ids).fetchone()[0]
            )
        cur = conn.execute(
            """
            INSERT INTO exams (title, subject, topic, duration_minutes, question_count, total_marks, negative_marks, mode, created_by, is_published, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title.strip(), subject, topic.strip(), int(duration_minutes), len(question_ids), total_marks, float(negative_marks), mode, created_by, 1 if is_published else 0, now_str),
        )
        exam_id = cur.lastrowid
        conn.executemany("INSERT INTO exam_questions (exam_id, question_id) VALUES (?, ?)", [(exam_id, qid) for qid in question_ids])
        return exam_id


def get_exams(published_only: bool = True) -> list[dict[str, Any]]:
    with get_connection() as conn:
        q = "SELECT * FROM exams" + (" WHERE is_published = 1" if published_only else "") + " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_exam_questions(exam_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT qb.* FROM question_bank qb
            JOIN exam_questions eq ON qb.id = eq.question_id
            WHERE eq.exam_id = ?
            ORDER BY qb.id ASC
            """,
            (exam_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_quiz_attempt(
    student_id: int,
    subject: str,
    topic: str,
    score: float,
    correct_count: int,
    total_questions: int,
    attempt_date: str | None = None,
    exam_id: int | None = None,
    time_taken_sec: int = 0,
    mode: str = "Practice",
) -> int:
    attempt_date = attempt_date or date.today().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO quiz_attempts
            (student_id, exam_id, subject, topic, score, correct_count, total_questions, time_taken_sec, mode, attempt_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, exam_id, subject, topic, score, correct_count, total_questions, time_taken_sec, mode, attempt_date),
        )
        return cur.lastrowid


def get_quiz_attempts(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM quiz_attempts WHERE student_id = ? ORDER BY attempt_date ASC, id ASC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


def get_weak_subjects(student_id: int, limit: int = 2) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT subject, ROUND(AVG(score), 1) AS avg_score, COUNT(*) AS attempts
            FROM quiz_attempts
            WHERE student_id = ?
            GROUP BY subject
            ORDER BY avg_score ASC, attempts DESC
            LIMIT ?
            """,
            (student_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Skills, Goals, Habits, Portfolio, Career & Notes
# ---------------------------------------------------------------------------

def add_skill(
    student_id: int,
    name: str,
    category: str,
    current_level: int,
    target_level: int,
    interest_level: int = 4,
    experience_note: str = "",
    started_date: str = "",
    evidence: str = "",
    next_action: str = "",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO skills
            (student_id, name, category, interest_level, current_level, target_level, experience_note, started_date, evidence, next_action)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, name.strip(), category, interest_level, current_level, target_level, experience_note.strip(), started_date or date.today().isoformat(), evidence.strip(), next_action.strip()),
        )
        skill_id = cur.lastrowid
        conn.execute(
            "INSERT INTO skill_history (skill_id, level, recorded_at, note) VALUES (?, ?, ?, ?)",
            (skill_id, current_level, date.today().isoformat(), "Initial assessment"),
        )
        return skill_id


def update_skill_level(skill_id: int, new_level: int, note: str = "Progress update") -> None:
    with get_connection() as conn:
        conn.execute("UPDATE skills SET current_level = ? WHERE id = ?", (int(new_level), skill_id))
        conn.execute(
            "INSERT INTO skill_history (skill_id, level, recorded_at, note) VALUES (?, ?, ?, ?)",
            (skill_id, int(new_level), date.today().isoformat(), note),
        )


def get_skills(student_id: int, include_archived: bool = False) -> list[dict[str, Any]]:
    with get_connection() as conn:
        q = "SELECT * FROM skills WHERE student_id = ?" + ("" if include_archived else " AND is_archived = 0") + " ORDER BY id ASC"
        return [dict(r) for r in conn.execute(q, (student_id,)).fetchall()]


def get_skill_history(skill_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM skill_history WHERE skill_id = ? ORDER BY recorded_at ASC, id ASC", (skill_id,)).fetchall()
        return [dict(r) for r in rows]


def archive_skill(skill_id: int, archived: bool = True) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE skills SET is_archived = ? WHERE id = ?", (1 if archived else 0, skill_id))


def delete_skill(skill_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM feedback WHERE target_type = 'skill' AND target_id = ?", (skill_id,))
        conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))


def add_goal(student_id: int, title: str, description: str, category: str, target_date: str, priority: str, milestones: list[str]) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO goals (student_id, title, description, category, target_date, priority, progress, status, milestones_json)
            VALUES (?, ?, ?, ?, ?, ?, 0, 'In Progress', ?)
            """,
            (student_id, title.strip(), description.strip(), category, target_date, priority, json.dumps(milestones)),
        )
        return cur.lastrowid


def get_goals(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM goals WHERE student_id = ? ORDER BY target_date ASC, id DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


def update_goal_progress(goal_id: int, progress: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE goals SET progress = ?, status = ? WHERE id = ?", (int(progress), status, goal_id))


def delete_goal(goal_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))


def add_habit(student_id: int, name: str, frequency: str = "Daily", target_per_week: int = 5) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO habits (student_id, name, frequency, target_per_week) VALUES (?, ?, ?, ?)",
            (student_id, name.strip(), frequency, int(target_per_week)),
        )
        return cur.lastrowid


def get_habits(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM habits WHERE student_id = ? ORDER BY id ASC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


def toggle_habit_log(habit_id: int, log_date: str, completed: bool) -> None:
    with get_connection() as conn:
        if completed:
            conn.execute(
                "INSERT OR REPLACE INTO habit_logs (habit_id, log_date, completed) VALUES (?, ?, 1)",
                (habit_id, log_date),
            )
        else:
            conn.execute("DELETE FROM habit_logs WHERE habit_id = ? AND log_date = ?", (habit_id, log_date))


def get_habit_logs(student_id: int, days: int = 14) -> list[dict[str, Any]]:
    since = _d(days - 1)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT hl.*, h.name AS habit_name, h.target_per_week
            FROM habit_logs hl
            JOIN habits h ON hl.habit_id = h.id
            WHERE h.student_id = ? AND hl.log_date >= ?
            ORDER BY hl.log_date DESC
            """,
            (student_id, since),
        ).fetchall()
        return [dict(r) for r in rows]


def add_portfolio_item(
    student_id: int,
    title: str,
    item_type: str,
    issuer: str,
    item_date: str,
    description: str = "",
    file_path: str = "",
    file_name: str = "",
    skills_demonstrated: str = "",
    visibility: str = "Teacher-Visible",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO portfolio_items
            (student_id, title, item_type, issuer, item_date, skills_demonstrated, visibility, description, file_path, file_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, title.strip(), item_type, issuer.strip(), item_date, skills_demonstrated.strip(), visibility, description.strip(), file_path, file_name),
        )
        return cur.lastrowid


def get_portfolio_items(student_id: int, include_private: bool = True) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if include_private:
            rows = conn.execute(
                "SELECT * FROM portfolio_items WHERE student_id = ? ORDER BY item_date DESC, id DESC",
                (student_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM portfolio_items WHERE student_id = ? AND visibility != 'Private' ORDER BY item_date DESC, id DESC",
                (student_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def update_portfolio_visibility(item_id: int, visibility: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE portfolio_items SET visibility = ? WHERE id = ?", (visibility, item_id))


def delete_portfolio_item(item_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM feedback WHERE target_type = 'portfolio' AND target_id = ?", (item_id,))
        conn.execute("DELETE FROM portfolio_items WHERE id = ?", (item_id,))


def get_career_profile(student_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM career_profiles WHERE student_id = ?", (student_id,)).fetchone()
        return dict(row) if row else None


def upsert_career_profile(student_id: int, target_role: str, interests: str, checklist: list[dict[str, Any]]) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO career_profiles (student_id, target_role, interests, checklist_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(student_id) DO UPDATE SET
                target_role = excluded.target_role,
                interests = excluded.interests,
                checklist_json = excluded.checklist_json,
                updated_at = excluded.updated_at
            """,
            (student_id, target_role, interests.strip(), json.dumps(checklist), now_str),
        )


def add_note(
    student_id: int,
    subject: str,
    topic: str,
    title: str,
    content: str,
    tags: str = "",
    resource_url: str = "",
    file_path: str = "",
    file_name: str = "",
    needs_revision: bool = False,
    revision_date: str = "",
) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO notes
            (student_id, subject, topic, title, content, tags, resource_url, file_path, file_name, needs_revision, revision_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, subject, topic.strip(), title.strip(), content.strip(), tags.strip(), resource_url.strip(), file_path, file_name, 1 if needs_revision else 0, revision_date, now_str),
        )
        return cur.lastrowid


def get_notes(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM notes WHERE student_id = ? ORDER BY id DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


def toggle_note_revision(note_id: int, needs_revision: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE notes SET needs_revision = ? WHERE id = ?", (1 if needs_revision else 0, note_id))


def delete_note(note_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


# ---------------------------------------------------------------------------
# Feedback, Notifications, Calendar, Announcements & Class Overview
# ---------------------------------------------------------------------------

def add_feedback(
    student_id: int,
    target_type: str,
    target_id: int | None,
    strengths: str,
    improvement_area: str,
    next_action: str,
    teacher_name: str = "Ms. Priya Nair",
) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO feedback
            (student_id, target_type, target_id, teacher_name, strengths, improvement_area, next_action, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, target_type, target_id, teacher_name, strengths, improvement_area, next_action, now_str),
        )
        conn.execute(
            "INSERT INTO notifications (user_role, student_id, title, message, category, is_read, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            ("student", student_id, "New Teacher Feedback", f"{teacher_name} added feedback on your {target_type}.", "Feedback", now_str),
        )
        return cur.lastrowid


def get_feedback_for_student(student_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM feedback WHERE student_id = ? ORDER BY id DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]


def get_notifications(student_id: int | None, role: str = "student") -> list[dict[str, Any]]:
    with get_connection() as conn:
        if role == "student" and student_id:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE user_role='student' AND (student_id=? OR student_id IS NULL) ORDER BY is_read ASC, id DESC",
                (student_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notifications ORDER BY is_read ASC, id DESC LIMIT 30").fetchall()
        return [dict(r) for r in rows]


def mark_notification_read(notif_id: int, is_read: bool = True) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE notifications SET is_read = ? WHERE id = ?", (1 if is_read else 0, notif_id))


def add_calendar_event(student_id: int | None, title: str, event_type: str, event_date: str, subject: str = "", description: str = "") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO calendar_events (student_id, title, event_type, event_date, subject, description) VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, title.strip(), event_type, event_date, subject, description.strip()),
        )
        return cur.lastrowid


def get_calendar_events(student_id: int | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if student_id:
            rows = conn.execute(
                "SELECT * FROM calendar_events WHERE student_id = ? OR student_id IS NULL ORDER BY event_date ASC",
                (student_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM calendar_events ORDER BY event_date ASC").fetchall()
        return [dict(r) for r in rows]


def add_announcement(teacher_name: str, title: str, message: str, target_section: str = "All Sections") -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO announcements (teacher_name, title, message, target_section, created_at) VALUES (?, ?, ?, ?, ?)",
            (teacher_name, title.strip(), message.strip(), target_section, now_str),
        )
        # Notify all matching students
        students = conn.execute("SELECT id, section FROM students WHERE is_archived = 0").fetchall()
        for st_row in students:
            if target_section == "All Sections" or st_row["section"] == target_section:
                conn.execute(
                    "INSERT INTO notifications (user_role, student_id, title, message, category, is_read, created_at) VALUES ('student', ?, ?, ?, 'Announcement', 0, ?)",
                    (st_row["id"], f"📢 {title.strip()}", message.strip(), now_str),
                )
        return cur.lastrowid


def get_announcements() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def get_class_overview() -> list[dict[str, Any]]:
    week_start = (date.today() - timedelta(days=6)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id, s.usn, s.name, s.grade, s.section, s.avatar_emoji,
                ROUND(COALESCE((SELECT AVG(q.score) FROM quiz_attempts q WHERE q.student_id = s.id), 0), 1) AS avg_quiz_score,
                ROUND(COALESCE((
                    SELECT AVG(100.0 * a.score / a.max_score) FROM assessments a WHERE a.student_id = s.id
                ), 0), 1) AS avg_ia_pct,
                ROUND(COALESCE((
                    SELECT 100.0 * SUM(CASE WHEN att.status IN ('Present','Late') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
                    FROM attendance att WHERE att.student_id = s.id
                ), 100), 1) AS attendance_pct,
                ROUND(COALESCE((
                    SELECT SUM(ss.duration_minutes) / 60.0
                    FROM study_sessions ss
                    WHERE ss.student_id = s.id AND ss.session_date >= ?
                ), 0), 2) AS weekly_study_hours,
                (SELECT COUNT(*) FROM skills sk WHERE sk.student_id = s.id AND sk.is_archived = 0) AS skill_count,
                (SELECT COUNT(*) FROM portfolio_items p WHERE p.student_id = s.id AND p.visibility != 'Private') AS portfolio_count
            FROM students s
            WHERE s.is_archived = 0
            ORDER BY s.id ASC
            """,
            (week_start,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Knowledge Center Queries
# ---------------------------------------------------------------------------

def add_knowledge_document(
    title: str,
    file_name: str,
    file_path: str,
    file_ext: str,
    doc_type: str,
    subject: str,
    subject_code: str,
    semester: int | None,
    topic: str,
    category: str,
    description: str,
    extracted_text: str,
    detected_sections: list[str],
    detected_tables: list[dict[str, Any]],
    missing_fields: list[str],
    tags: str,
    visibility: str,
    status: str,
    uploader_username: str,
    uploader_name: str,
    uploader_role: str,
    chunks: list[dict[str, str]],
) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO knowledge_documents
            (title, file_name, file_path, file_ext, doc_type, subject, subject_code, semester, topic, category,
             description, extracted_text, detected_sections_json, detected_tables_json, missing_fields_json,
             tags, visibility, status, uploader_username, uploader_name, uploader_role, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title.strip(),
                file_name,
                file_path,
                file_ext,
                doc_type,
                subject.strip(),
                subject_code.strip(),
                semester,
                topic.strip(),
                category,
                description.strip(),
                extracted_text,
                json.dumps(detected_sections),
                json.dumps(detected_tables),
                json.dumps(missing_fields),
                tags.strip(),
                visibility,
                status,
                uploader_username,
                uploader_name,
                uploader_role,
                now_str,
                now_str,
            ),
        )
        doc_id = cur.lastrowid
        for idx, ch in enumerate(chunks):
            conn.execute(
                "INSERT INTO knowledge_chunks (doc_id, chunk_index, section_title, content, keywords) VALUES (?, ?, ?, ?, ?)",
                (doc_id, idx, ch.get("section_title", "Overview"), ch.get("content", ""), tags.strip()),
            )
        conn.execute(
            "INSERT INTO document_history (doc_id, actor_username, action, summary, created_at) VALUES (?, ?, ?, ?, ?)",
            (doc_id, uploader_username, "UPLOAD", f"Uploaded '{title.strip()}' ({category}, {visibility})", now_str),
        )
        return doc_id


def update_knowledge_document(
    doc_id: int,
    title: str,
    subject: str,
    subject_code: str,
    semester: int | None,
    topic: str,
    category: str,
    description: str,
    extracted_text: str,
    tags: str,
    visibility: str,
    status: str,
    actor_username: str,
    chunks: list[dict[str, str]],
    file_path: str | None = None,
    file_name: str | None = None,
) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        if file_path is not None and file_name is not None:
            conn.execute(
                """
                UPDATE knowledge_documents
                SET title=?, subject=?, subject_code=?, semester=?, topic=?, category=?, description=?, extracted_text=?,
                    tags=?, visibility=?, status=?, file_path=?, file_name=?, updated_at=?
                WHERE id=?
                """,
                (title.strip(), subject.strip(), subject_code.strip(), semester, topic.strip(), category, description.strip(), extracted_text, tags.strip(), visibility, status, file_path, file_name, now_str, doc_id),
            )
        else:
            conn.execute(
                """
                UPDATE knowledge_documents
                SET title=?, subject=?, subject_code=?, semester=?, topic=?, category=?, description=?, extracted_text=?,
                    tags=?, visibility=?, status=?, updated_at=?
                WHERE id=?
                """,
                (title.strip(), subject.strip(), subject_code.strip(), semester, topic.strip(), category, description.strip(), extracted_text, tags.strip(), visibility, status, now_str, doc_id),
            )
        conn.execute("DELETE FROM knowledge_chunks WHERE doc_id = ?", (doc_id,))
        for idx, ch in enumerate(chunks):
            conn.execute(
                "INSERT INTO knowledge_chunks (doc_id, chunk_index, section_title, content, keywords) VALUES (?, ?, ?, ?, ?)",
                (doc_id, idx, ch.get("section_title", "Overview"), ch.get("content", ""), tags.strip()),
            )
        conn.execute(
            "INSERT INTO document_history (doc_id, actor_username, action, summary, created_at) VALUES (?, ?, ?, ?, ?)",
            (doc_id, actor_username, "EDIT", f"Updated metadata/content ({category}, {visibility}, {status})", now_str),
        )


def delete_knowledge_document(doc_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM knowledge_documents WHERE id = ?", (doc_id,))


def get_knowledge_documents(role: str = "admin", username: str = "", include_archived: bool = False) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM knowledge_documents ORDER BY id DESC").fetchall()
        docs = [dict(r) for r in rows]

    filtered: list[dict[str, Any]] = []
    for d in docs:
        if not include_archived and d["status"] == "Archived":
            continue
        if role == "admin":
            filtered.append(d)
        elif role == "teacher":
            if d["visibility"] in ("Students & Teachers", "Teachers Only") or d["uploader_username"] == username:
                filtered.append(d)
        elif role == "student":
            if (
                d["status"] == "Active"
                and d["visibility"] == "Students & Teachers"
                and d["category"] != "Question banks"
            ):
                filtered.append(d)
        elif role == "parent":
            if d["status"] == "Active" and d["visibility"] == "Students & Teachers" and d["category"] in ("Syllabus", "Announcements"):
                filtered.append(d)
    return filtered


def get_knowledge_document_by_id(doc_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM knowledge_documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None


def get_permitted_knowledge_chunks(role: str, subject: str | None = None, semester: int | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        clauses = ["kd.status = 'Active'"]
        params: list[Any] = []
        if role == "student":
            clauses.append("kd.visibility = 'Students & Teachers'")
            clauses.append("kd.category != 'Question banks'")
        elif role == "teacher":
            clauses.append("kd.visibility IN ('Students & Teachers', 'Teachers Only')")
        if subject and subject != "All":
            clauses.append("(LOWER(kd.subject) = LOWER(?) OR kd.subject = '')")
            params.append(subject)
        if semester:
            clauses.append("(kd.semester = ? OR kd.semester IS NULL)")
            params.append(semester)
        where = " WHERE " + " AND ".join(clauses)
        rows = conn.execute(
            f"""
            SELECT kc.*, kd.title AS doc_title, kd.subject, kd.topic, kd.category, kd.semester, kd.uploader_name
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kc.doc_id = kd.id
            {where}
            ORDER BY kc.id DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_document_history(doc_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM document_history WHERE doc_id = ? ORDER BY id DESC", (doc_id,)).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Teacher Assignments, Parent Links & Attendance Editing
# ---------------------------------------------------------------------------

def get_teacher_assignments(teacher_username: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM teacher_assignments WHERE LOWER(teacher_username) = LOWER(?) ORDER BY subject_name, section",
            (teacher_username,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_teacher_assignments() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM teacher_assignments ORDER BY teacher_username, subject_name, section").fetchall()
        return [dict(r) for r in rows]


def add_teacher_assignment(teacher_username: str, subject_name: str, section: str, semester: int = 5) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO teacher_assignments (teacher_username, subject_name, section, semester) VALUES (?, ?, ?, ?)",
            (teacher_username.strip().lower(), subject_name.strip(), section.strip(), int(semester)),
        )


def delete_teacher_assignment(assignment_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM teacher_assignments WHERE id = ?", (assignment_id,))


def get_parent_linked_students(parent_username: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.*, psl.relationship
            FROM students s
            JOIN parent_student_links psl ON s.id = psl.student_id
            WHERE LOWER(psl.parent_username) = LOWER(?) AND s.is_archived = 0
            ORDER BY s.id ASC
            """,
            (parent_username,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_parent_links() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT psl.*, s.name AS student_name, s.usn
            FROM parent_student_links psl
            JOIN students s ON psl.student_id = s.id
            ORDER BY psl.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def link_parent_student(parent_username: str, student_id: int, relationship: str = "Guardian") -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO parent_student_links (parent_username, student_id, relationship) VALUES (?, ?, ?)",
            (parent_username.strip().lower(), int(student_id), relationship.strip()),
        )


def update_student_guardian(student_id: int, guardian_name: str, guardian_phone: str, guardian_email: str, alerts_enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE students SET guardian_name=?, guardian_phone=?, guardian_email=?, guardian_alerts_enabled=? WHERE id=?",
            (guardian_name.strip(), guardian_phone.strip(), guardian_email.strip(), 1 if alerts_enabled else 0, student_id),
        )


def get_class_attendance(subject: str | None = None, att_date: str | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        clauses = ["s.is_archived = 0"]
        params: list[Any] = []
        if subject and subject != "All":
            clauses.append("a.subject = ?")
            params.append(subject)
        if att_date:
            clauses.append("a.att_date = ?")
            params.append(att_date)
        where = " WHERE " + " AND ".join(clauses)
        rows = conn.execute(
            f"""
            SELECT a.id, a.student_id, s.usn, s.name AS student_name, s.section, a.subject, a.att_date, a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            {where}
            ORDER BY a.att_date DESC, s.name ASC, a.subject ASC
            LIMIT 250
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def update_attendance_by_id(attendance_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE attendance SET status = ? WHERE id = ?", (status, attendance_id))


# ---------------------------------------------------------------------------
# Departments, Sections & Parent Link Deletion
# ---------------------------------------------------------------------------

def get_departments() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM departments ORDER BY code ASC").fetchall()
        return [dict(r) for r in rows]


def get_department_names() -> list[str]:
    depts = [d["code"] for d in get_departments()]
    return depts if depts else ["CSE", "ECE", "ISE", "AIML", "ME"]


def add_department(code: str, name: str, hod_name: str = "", description: str = "") -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO departments (code, name, hod_name, description, created_at) VALUES (?, ?, ?, ?, ?)",
            (code.strip().upper(), name.strip(), hod_name.strip(), description.strip(), now_str),
        )
        return cur.lastrowid


def delete_department(dept_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM departments WHERE id = ?", (dept_id,))


def get_sections() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM sections ORDER BY department_code, semester, name").fetchall()
        return [dict(r) for r in rows]


def get_section_names() -> list[str]:
    secs = sorted({s["name"] for s in get_sections()})
    return secs if secs else ["Section A", "Section B"]


def add_section(name: str, semester: int = 5, department_code: str = "CSE") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO sections (name, semester, department_code) VALUES (?, ?, ?)",
            (name.strip(), int(semester), department_code.strip().upper()),
        )
        return cur.lastrowid


def delete_section(section_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))


def delete_parent_link(link_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM parent_student_links WHERE id = ?", (link_id,))


def add_absence_notification(student_id: int, subject: str, att_date: str, teacher_name: str = "Faculty") -> bool:
    """Create a deduplicated absence alert for a student & their parent/guardian if alerts are enabled."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"Absence Alert: {subject} ({att_date})"
    with get_connection() as conn:
        st_row = conn.execute(
            "SELECT name, guardian_alerts_enabled FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if not st_row:
            return False
        existing = conn.execute(
            "SELECT id FROM notifications WHERE student_id = ? AND title = ? AND category = 'Absence Alert'",
            (student_id, title),
        ).fetchone()
        if existing:
            return False
        msg = f"{st_row['name']} was marked Absent in {subject} on {att_date} by {teacher_name}."
        conn.execute(
            "INSERT INTO notifications (user_role, student_id, title, message, category, is_read, created_at) VALUES ('student', ?, ?, ?, 'Absence Alert', 0, ?)",
            (student_id, title, msg, now_str),
        )
        return bool(st_row["guardian_alerts_enabled"])


# ---------------------------------------------------------------------------
# Credential Management, Recovery & Bulk Login Generation
# ---------------------------------------------------------------------------

def update_user_credentials(
    user_id: int,
    new_username: str | None = None,
    new_password: str | None = None,
) -> tuple[bool, str]:
    """Update a user's username and/or password safely."""
    with get_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, "User account not found."
        if new_username is not None and new_username.strip():
            uname_clean = new_username.strip()
            conflict = conn.execute(
                "SELECT id FROM users WHERE LOWER(username) = LOWER(?) AND id != ?",
                (uname_clean, user_id),
            ).fetchone()
            if conflict:
                return False, f"Username '{uname_clean}' is already taken."
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (uname_clean, user_id))
        if new_password is not None and new_password.strip():
            if len(new_password.strip()) < 4:
                return False, "Password must be at least 4 characters."
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password.strip()), user_id))
    return True, "Credentials updated successfully."


def verify_and_reset_credentials(
    role_hint: str,
    identifier: str,
    full_name: str,
    new_password: str,
    new_username: str | None = None,
) -> tuple[bool, str]:
    """Self-service recovery: verify Student (USN + Name) or Teacher (Teacher ID + Name) and update credentials."""
    ident = identifier.strip()
    fname = full_name.strip()
    if not ident or not fname or len(new_password.strip()) < 4:
        return False, "Enter your ID/USN, Full Name, and a new password (min 4 chars)."

    with get_connection() as conn:
        user_row = None
        if role_hint == "student":
            st_row = conn.execute(
                "SELECT id, name FROM students WHERE LOWER(usn) = LOWER(?) AND LOWER(TRIM(name)) = LOWER(?)",
                (ident, fname),
            ).fetchone()
            if st_row:
                user_row = conn.execute(
                    "SELECT * FROM users WHERE role = 'student' AND linked_student_id = ?",
                    (st_row["id"],),
                ).fetchone()
        elif role_hint == "teacher":
            user_row = conn.execute(
                "SELECT * FROM users WHERE role = 'teacher' AND LOWER(employee_id) = LOWER(?) AND LOWER(TRIM(full_name)) = LOWER(?)",
                (ident, fname),
            ).fetchone()
            if not user_row:
                # Also match without title prefix like "Ms. " if user typed "Priya Nair"
                teachers = conn.execute("SELECT * FROM users WHERE role = 'teacher' AND LOWER(employee_id) = LOWER(?)", (ident,)).fetchall()
                for t in teachers:
                    if fname.lower() in t["full_name"].lower():
                        user_row = t
                        break
        if not user_row:
            return False, "Verification failed: ID/USN and Full Name do not match our records. Contact Administrator for help."

    ok, msg = update_user_credentials(user_row["id"], new_username=new_username, new_password=new_password)
    if ok:
        log_activity(new_username.strip() if (new_username and new_username.strip()) else user_row["username"], user_row["role"], "SELF_CREDENTIAL_RESET", "Reset password/username via self-recovery")
    return ok, msg


def _unique_username(conn: sqlite3.Connection, base_name: str, fallback_suffix: str) -> str:
    candidate = base_name.strip()
    exists = conn.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (candidate,)).fetchone()
    if not exists:
        return candidate
    suffixed = f"{candidate}_{fallback_suffix.strip()}".replace(" ", "_")
    exists2 = conn.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (suffixed,)).fetchone()
    return suffixed if not exists2 else f"{suffixed}_{os.urandom(2).hex()}"


def bulk_create_student_logins(rows: list[dict[str, Any]], actor_username: str) -> list[dict[str, str]]:
    """Create student records (if missing) and logins with username=name, password=usn."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    results: list[dict[str, str]] = []
    with get_connection() as conn:
        for r in rows:
            name = str(r["name"]).strip()
            usn = str(r["usn"]).strip().upper()
            st_row = conn.execute("SELECT id FROM students WHERE UPPER(usn) = ?", (usn,)).fetchone()
            if st_row:
                student_id = st_row["id"]
            else:
                cur = conn.execute(
                    """
                    INSERT INTO students (usn, name, email, course, branch, semester, section, academic_year, grade)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        usn,
                        name,
                        str(r.get("email") or "").strip(),
                        str(r.get("course") or "B.Tech").strip(),
                        str(r.get("branch") or "CSE").strip(),
                        int(r.get("semester") or 5),
                        str(r.get("section") or "Section A").strip(),
                        str(r.get("academic_year") or "2026-27").strip(),
                        f"Sem {int(r.get('semester') or 5)}",
                    ),
                )
                student_id = cur.lastrowid

            existing_user = conn.execute(
                "SELECT id, username FROM users WHERE role = 'student' AND linked_student_id = ?",
                (student_id,),
            ).fetchone()
            if existing_user:
                results.append(
                    {
                        "Role": "student",
                        "Full Name": name,
                        "USN / ID": usn,
                        "Username": existing_user["username"],
                        "Initial Password": "(Existing account kept)",
                        "Status": "Skipped (already has login)",
                    }
                )
                continue

            uname = _unique_username(conn, name, usn)
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, full_name, department, employee_id, linked_student_id, created_at)
                VALUES (?, ?, 'student', ?, ?, ?, ?, ?)
                """,
                (uname, hash_password(usn), name, str(r.get("branch") or "CSE").strip(), usn, student_id, now_str),
            )
            results.append(
                {
                    "Role": "student",
                    "Full Name": name,
                    "USN / ID": usn,
                    "Username": uname,
                    "Initial Password": usn,
                    "Status": "Created",
                }
            )
    log_activity(actor_username, "admin", "BULK_STUDENT_LOGINS", f"Processed {len(results)} student logins")
    return results


def bulk_create_teacher_logins(rows: list[dict[str, Any]], actor_username: str) -> list[dict[str, str]]:
    """Create teacher logins with username=teacher_name, password=teacher_id."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    results: list[dict[str, str]] = []
    with get_connection() as conn:
        for r in rows:
            t_name = str(r["teacher_name"]).strip()
            t_id = str(r["teacher_id"]).strip().upper()
            dept = str(r.get("department") or "CSE").strip()

            existing = conn.execute(
                "SELECT id, username FROM users WHERE role = 'teacher' AND (LOWER(employee_id) = LOWER(?) OR LOWER(full_name) = LOWER(?))",
                (t_id, t_name),
            ).fetchone()
            if existing:
                results.append(
                    {
                        "Role": "teacher",
                        "Full Name": t_name,
                        "USN / ID": t_id,
                        "Username": existing["username"],
                        "Initial Password": "(Existing account kept)",
                        "Status": "Skipped (already exists)",
                    }
                )
                continue

            uname = _unique_username(conn, t_name, t_id)
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, full_name, department, employee_id, linked_student_id, created_at)
                VALUES (?, ?, 'teacher', ?, ?, ?, NULL, ?)
                """,
                (uname, hash_password(t_id), t_name, dept, t_id, now_str),
            )
            results.append(
                {
                    "Role": "teacher",
                    "Full Name": t_name,
                    "USN / ID": t_id,
                    "Username": uname,
                    "Initial Password": t_id,
                    "Status": "Created",
                }
            )
    log_activity(actor_username, "admin", "BULK_TEACHER_LOGINS", f"Processed {len(results)} teacher logins")
    return results


def save_file_blob(file_path: str, file_name: str, raw_bytes: bytes) -> None:
    """Persist uploaded file bytes inside SQLite so files survive cloud container restarts."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO file_blobs (file_path, file_name, content, created_at) VALUES (?, ?, ?, ?)",
            (file_path, file_name, sqlite3.Binary(raw_bytes), now_str),
        )


def read_file_bytes(file_path: str) -> bytes | None:
    """Read uploaded file from disk, or transparently restore from `file_blobs` in SQLite."""
    if not file_path:
        return None
    p = Path(file_path)
    if p.exists():
        return p.read_bytes()
    with get_connection() as conn:
        row = conn.execute("SELECT content FROM file_blobs WHERE file_path = ?", (file_path,)).fetchone()
        if row and row["content"] is not None:
            raw = bytes(row["content"])
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
            except Exception:
                pass
            return raw
    return None


def generate_missing_student_logins(actor_username: str) -> list[dict[str, str]]:
    """Generate username=name, password=usn logins for all students without a user account."""
    with get_connection() as conn:
        missing = conn.execute(
            """
            SELECT s.* FROM students s
            LEFT JOIN users u ON u.linked_student_id = s.id AND u.role = 'student'
            WHERE s.is_archived = 0 AND u.id IS NULL
            """
        ).fetchall()
    if not missing:
        return []
    return bulk_create_student_logins([dict(m) for m in missing], actor_username)
