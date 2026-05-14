"""Create and seed a SQLite database for the lab."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT    NOT NULL,
    cohort TEXT    NOT NULL,
    score  REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS courses (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title   TEXT    NOT NULL,
    credits INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS enrollments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id  INTEGER NOT NULL REFERENCES courses(id),
    grade      REAL
);
"""

SEED_STUDENTS = [
    ("Anh",  "A1", 8.5),
    ("Binh", "A1", 7.0),
    ("Cuc",  "A1", 9.2),
    ("Dung", "A1", 6.5),
    ("Em",   "B2", 8.8),
    ("Phong","B2", 7.4),
    ("Giang","B2", 9.0),
    ("Hoa",  "B2", 5.5),
    ("Khanh","B2", 8.0),
    ("Linh", "B2", 6.8),
]
SEED_COURSES = [
    ("Algorithms",          4),
    ("Databases",           3),
    ("Operating Systems",   4),
    ("Distributed Systems", 3),
]
SEED_ENROLLMENTS = [
    (1, 1, 8.0), (1, 2, 9.0), (2, 1, 7.5), (3, 2, 9.5),
    (3, 3, 8.5), (4, 4, 6.0), (5, 1, 9.0), (5, 3, 8.0),
    (6, 2, 7.0), (7, 4, 9.5), (8, 1, 5.5), (8, 4, 6.0),
    (9, 2, 8.5), (10, 3, 7.0), (10, 4, 6.5),
]


def create_schema(db_path: str | Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def seed(db_path: str | Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany("INSERT INTO students(name, cohort, score) VALUES (?, ?, ?)", SEED_STUDENTS)
        conn.executemany("INSERT INTO courses(title, credits) VALUES (?, ?)", SEED_COURSES)
        conn.executemany(
            "INSERT INTO enrollments(student_id, course_id, grade) VALUES (?, ?, ?)",
            SEED_ENROLLMENTS,
        )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    db_path = Path("lab.db")
    if db_path.exists():
        db_path.unlink()
    create_schema(db_path)
    seed(db_path)
    print(f"Initialized {db_path.resolve()}")


if __name__ == "__main__":
    main()
