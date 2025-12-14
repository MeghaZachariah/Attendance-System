"""
Database helpers for the attendance system.

Creates a local SQLite database (attendance.db) with two tables:
- students(student_id TEXT PRIMARY KEY)
- attendance(id INTEGER PRIMARY KEY, student_id TEXT, date TEXT, status TEXT)

Also populates the `students` table from `encodings.pkl` if that file exists.

This module exposes:
- get_connection() -> sqlite3.Connection
- create_tables() -> None

The FastAPI app calls `create_tables()` at startup.
"""

import sqlite3
from pathlib import Path
import pickle
import os
from typing import Optional

# DB file next to this module
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "attendance.db"
ENC_PATH = BASE_DIR / "encodings.pkl"


def get_connection() -> sqlite3.Connection:
	"""Return a new sqlite3 connection to the local DB."""
	# Use check_same_thread=False to allow usage from different threads/workers
	conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
	conn.execute("PRAGMA foreign_keys = ON")
	return conn


def create_tables() -> None:
	"""Create required tables and populate students from encodings if needed."""
	conn = get_connection()
	cur = conn.cursor()

	cur.execute(
		"""CREATE TABLE IF NOT EXISTS students (
		student_id TEXT PRIMARY KEY,
		class_id TEXT,
		semester TEXT,
		reg_no TEXT,
		program TEXT
	)"""
	)

	cur.execute(
		"""CREATE TABLE IF NOT EXISTS attendance (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		student_id TEXT,
		date TEXT,
		status TEXT,
		class_id TEXT,
		UNIQUE(student_id, date, class_id)
	)"""
	)

	# Classes table to group students
	cur.execute(
		"""CREATE TABLE IF NOT EXISTS classes (
		class_id TEXT PRIMARY KEY,
		name TEXT
	)"""
	)

	conn.commit()

	# Populate students from encodings.pkl if present
	try:
		populate_students_from_encodings(conn)
	except Exception:
		# Avoid raising on startup — the system can run without pre-populated students
		pass

	conn.close()


def populate_students_from_encodings(conn: Optional[sqlite3.Connection] = None) -> None:
	"""Load student ids from `encodings.pkl` and insert into `students` table.

	If a connection is not provided this function will open and close its own.
	"""
	own_conn = False
	if conn is None:
		conn = get_connection()
		own_conn = True

	if not ENC_PATH.exists():
		if own_conn:
			conn.close()
		return

	# encodings.pkl expected format: (embeddings_list, ids_list)
	try:
		with open(ENC_PATH, "rb") as f:
			_emb, ids = pickle.load(f)
	except Exception:
		if own_conn:
			conn.close()
		return

	cur = conn.cursor()
	# Use INSERT OR IGNORE to avoid duplicate primary key errors
	for sid in ids:
		try:
			cur.execute(
				"INSERT OR IGNORE INTO students (student_id, class_id, semester, reg_no, program) VALUES (?, ?, ?, ?, ?)",
				(sid, None, None, None, None),
			)
		except Exception:
			# skip problematic ids but continue
			continue

	conn.commit()

	if own_conn:
		conn.close()
