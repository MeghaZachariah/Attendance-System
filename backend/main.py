from fastapi import FastAPI, UploadFile, File, Body, Form
from fastapi.responses import JSONResponse
from datetime import date
from typing import Optional
from pydantic import BaseModel
try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - allows editor/CI to run without cv2 installed
    # Minimal fallback so the editor won't show unresolved-import red underlines.
    class _CV2Stub:
        IMREAD_COLOR = 1

        @staticmethod
        def imdecode(*args, **kwargs):
            raise ImportError("cv2 is not available in the current environment")

    cv2 = _CV2Stub()
import numpy as np
import pickle
import sqlite3

from face_engine import recognize_faces, get_embeddings
from database import get_connection, create_tables
from pathlib import Path
import os
import tempfile
import threading

app = FastAPI(title="Face Recognition Attendance System")

# Allow simple local development from the static server (e.g. http://127.0.0.1:5500)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class ClassCreate(BaseModel):
    class_id: str
    name: str

# Create DB tables on startup
create_tables()

# Load face embeddings once (IMPORTANT for speed)
# Initialize empty lists if encodings.pkl doesn't exist yet
ENC_PATH = Path("encodings.pkl")
if ENC_PATH.exists():
    try:
        with open(ENC_PATH, "rb") as f:
            KNOWN_EMBEDDINGS, KNOWN_IDS = pickle.load(f)
    except Exception:
        KNOWN_EMBEDDINGS, KNOWN_IDS = [], []
else:
    KNOWN_EMBEDDINGS, KNOWN_IDS = [], []

# Lock to protect updates to encodings.pkl and the in-memory lists
_enc_lock = threading.Lock()


@app.get("/")
def home():
    return {"status": "Attendance system running"}


# Class Management Endpoints
@app.post("/classes")
async def create_class(class_data: ClassCreate = Body(...)):
    """Create a new class."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO classes (class_id, name) VALUES (?, ?)",
            (class_data.class_id, class_data.name)
        )
        conn.commit()
        return {"status": "ok", "class_id": class_data.class_id, "name": class_data.name}
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse(status_code=400, content={"detail": "Class ID already exists"})
    except Exception as e:
        conn.close()
        return JSONResponse(status_code=500, content={"detail": str(e)})
    finally:
        conn.close()


@app.get("/classes")
async def list_classes():
    """List all classes."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT class_id, name FROM classes ORDER BY name")
        classes = [{"class_id": row[0], "name": row[1]} for row in cur.fetchall()]
        return {"classes": classes}
    finally:
        conn.close()


@app.get("/classes/{class_id}/students")
async def get_class_students(class_id: str):
    """Get all students in a specific class."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT student_id, semester, reg_no, program 
               FROM students 
               WHERE class_id = ? 
               ORDER BY student_id""",
            (class_id,)
        )
        students = [
            {
                "student_id": row[0],
                "semester": row[1],
                "reg_no": row[2],
                "program": row[3]
            }
            for row in cur.fetchall()
        ]
        return {"class_id": class_id, "students": students}
    finally:
        conn.close()


@app.post("/attendance")
async def mark_attendance(
    image: UploadFile = File(...),
    class_id: Optional[str] = Form(None)
):
    today = str(date.today())

    # Read uploaded image
    contents = await image.read()
    np_img = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    # Get students in the selected class (if provided) before recognition
    conn = get_connection()
    cursor = conn.cursor()

    if class_id:
        cursor.execute("SELECT student_id FROM students WHERE class_id = ?", (class_id,))
        class_student_ids = {row[0] for row in cursor.fetchall()}
        if not class_student_ids:
            conn.close()
            return JSONResponse(
                status_code=400,
                content={"detail": f"No students found in class {class_id}"}
            )
        # Filter embeddings and IDs to only include students in this class
        class_indices = [i for i, sid in enumerate(KNOWN_IDS) if sid in class_student_ids]
        class_embeddings = [KNOWN_EMBEDDINGS[i] for i in class_indices]
        class_ids = [KNOWN_IDS[i] for i in class_indices]
    else:
        cursor.execute("SELECT student_id FROM students")
        class_student_ids = {row[0] for row in cursor.fetchall()}
        class_embeddings = KNOWN_EMBEDDINGS
        class_ids = KNOWN_IDS

    # Recognize faces (only from students in the selected class if class_id provided)
    present_students = recognize_faces(
        image,
        class_embeddings,
        class_ids
    )

    # Only mark attendance for students in the selected class
    all_students = class_student_ids
    absent_students = all_students - present_students

    # Prevent duplicate attendance for same date and class
    if class_id:
        cursor.execute("DELETE FROM attendance WHERE date = ? AND class_id = ?", (today, class_id))
    else:
        cursor.execute("DELETE FROM attendance WHERE date = ? AND class_id IS NULL", (today,))

    for student in present_students:
        cursor.execute(
            "INSERT INTO attendance (student_id, date, status, class_id) VALUES (?, ?, ?, ?)",
            (student, today, "Present", class_id)
        )

    for student in absent_students:
        cursor.execute(
            "INSERT INTO attendance (student_id, date, status, class_id) VALUES (?, ?, ?, ?)",
            (student, today, "Absent", class_id)
        )

    conn.commit()
    conn.close()

    return {
        "date": today,
        "class_id": class_id,
        "present": list(present_students),
        "absent": list(absent_students),
        "total": len(all_students)
    }


@app.post("/attendance/save")
async def save_attendance(payload: dict = Body(...)):
    """Accept finalized attendance JSON and persist to the database.

    Expected payload:
    {"date": "YYYY-MM-DD", "present": [...], "absent": [...], "total": N, "class_id": "..."}
    """
    att_date = payload.get("date") or str(date.today())
    present = payload.get("present", []) or []
    absent = payload.get("absent", []) or []
    class_id = payload.get("class_id")

    conn = get_connection()
    cur = conn.cursor()

    # Remove any existing entries for this date and class (replace/update)
    if class_id:
        cur.execute("DELETE FROM attendance WHERE date = ? AND class_id = ?", (att_date, class_id))
    else:
        cur.execute("DELETE FROM attendance WHERE date = ? AND class_id IS NULL", (att_date,))

    for student in present:
        cur.execute(
            "INSERT INTO attendance (student_id, date, status, class_id) VALUES (?, ?, ?, ?)",
            (student, att_date, "Present", class_id)
        )

    for student in absent:
        cur.execute(
            "INSERT INTO attendance (student_id, date, status, class_id) VALUES (?, ?, ?, ?)",
            (student, att_date, "Absent", class_id)
        )

    conn.commit()
    conn.close()

    return {"status": "ok", "date": att_date, "class_id": class_id}


@app.post("/register")
async def register_student(
    student_id: str = Form(...),
    image: UploadFile = File(...),
    class_id: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    reg_no: Optional[str] = Form(None),
    program: Optional[str] = Form(None)
):
    """Register a new student from an uploaded image.

    - Extracts the first face embedding from the image
    - Appends embedding and student_id to `encodings.pkl` atomically
    - Inserts `student_id` into `students` table with class_id, semester, reg_no, program
    - Updates in-memory `KNOWN_EMBEDDINGS` and `KNOWN_IDS` so recognition picks it up immediately
    """
    # Read image bytes
    contents = await image.read()
    np_img = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    # Extract embedding
    try:
        embs = get_embeddings(img)
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Embedding extraction failed: {e}"})

    if not embs:
        return JSONResponse(status_code=400, content={"detail": "No face detected in the provided image."})

    emb = embs[0]

    enc_path = Path("encodings.pkl")

    # Atomically update encodings.pkl
    with _enc_lock:
        if enc_path.exists():
            try:
                with open(enc_path, "rb") as f:
                    known_embs, known_ids = pickle.load(f)
            except Exception:
                known_embs, known_ids = [], []
        else:
            known_embs, known_ids = [], []

        # Append new data
        known_embs.append(emb)
        known_ids.append(student_id)

        # Write atomically to a temp file then replace
        fd, tmp_path = tempfile.mkstemp(dir=str(enc_path.parent))
        try:
            with os.fdopen(fd, "wb") as tmpf:
                pickle.dump((known_embs, known_ids), tmpf)
            os.replace(tmp_path, str(enc_path))
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        # Update in-memory lists used by the running app
        try:
            KNOWN_EMBEDDINGS.append(emb)
            KNOWN_IDS.append(student_id)
        except Exception:
            # If KNOWN_* are not lists for some reason, reload them
            with open("encodings.pkl", "rb") as f:
                KNOWN_EMBEDDINGS, KNOWN_IDS = pickle.load(f)

    # Insert into students table with additional fields
    conn = get_connection()
    cur = conn.cursor()
    try:
        # If student exists, update their details; otherwise insert new
        cur.execute(
            """INSERT INTO students (student_id, class_id, semester, reg_no, program) 
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(student_id) DO UPDATE SET
               class_id = COALESCE(?, class_id),
               semester = COALESCE(?, semester),
               reg_no = COALESCE(?, reg_no),
               program = COALESCE(?, program)""",
            (student_id, class_id, semester, reg_no, program, class_id, semester, reg_no, program)
        )
        conn.commit()
    finally:
        conn.close()

    return {"status": "ok", "student_id": student_id}
