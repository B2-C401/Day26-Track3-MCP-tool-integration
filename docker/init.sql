CREATE TABLE IF NOT EXISTS students (
    id     SERIAL PRIMARY KEY,
    name   TEXT    NOT NULL,
    cohort TEXT    NOT NULL,
    score  REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS courses (
    id      SERIAL PRIMARY KEY,
    title   TEXT    NOT NULL,
    credits INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS enrollments (
    id         SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id  INTEGER NOT NULL REFERENCES courses(id),
    grade      REAL
);

INSERT INTO students (name, cohort, score) VALUES
    ('Anh', 'A1', 8.5),
    ('Binh', 'A1', 7.0),
    ('Cuc', 'A1', 9.2),
    ('Dung', 'A1', 6.5),
    ('Em', 'B2', 8.8),
    ('Phong', 'B2', 7.4),
    ('Giang', 'B2', 9.0),
    ('Hoa', 'B2', 5.5),
    ('Khanh', 'B2', 8.0),
    ('Linh', 'B2', 6.8);

INSERT INTO courses (title, credits) VALUES
    ('Algorithms', 4),
    ('Databases', 3),
    ('Operating Systems', 4),
    ('Distributed Systems', 3);

INSERT INTO enrollments (student_id, course_id, grade) VALUES
    (1, 1, 8.0), (1, 2, 9.0), (2, 1, 7.5), (3, 2, 9.5),
    (3, 3, 8.5), (4, 4, 6.0), (5, 1, 9.0), (5, 3, 8.0),
    (6, 2, 7.0), (7, 4, 9.5), (8, 1, 5.5), (8, 4, 6.0),
    (9, 2, 8.5), (10, 3, 7.0), (10, 4, 6.5);
