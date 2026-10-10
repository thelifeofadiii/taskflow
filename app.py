"""TaskFlow backend: Flask + SQLite (no MongoDB needed).

Run:  python app.py   ->  http://127.0.0.1:5000
"""
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, g, jsonify, redirect, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "taskflow.db"))

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PRIORITIES = ("Low", "Medium", "High")


def load_secret_key():
    """Use SECRET_KEY from the environment, or create one once and reuse it."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(BASE_DIR, ".secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="/static")
app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)


# ---------- database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name       TEXT NOT NULL,
            priority   TEXT NOT NULL DEFAULT 'Medium',
            deadline   TEXT NOT NULL DEFAULT '',
            completed  INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
        """
    )
    db.commit()
    db.close()


# ---------- helpers ----------
def error(message, status=400):
    return jsonify({"error": message}), status


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return error("Please log in first.", 401)
        return view(*args, **kwargs)

    return wrapper


def task_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "priority": row["priority"],
        "deadline": row["deadline"],
        "completed": bool(row["completed"]),
    }


def valid_deadline(value):
    if value == "":
        return True
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@app.after_request
def no_cache_for_pages(resp):
    # Stops the browser's back button from showing a dashboard after logout.
    if not request.path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- pages ----------
@app.get("/")
def home():
    if "user_id" not in session:
        return redirect("/login")
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/login")
def login_page():
    if "user_id" in session:
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.get("/register")
def register_page():
    if "user_id" in session:
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "register.html")


# ---------- auth API ----------
@app.post("/api/register")
def register():
    data = json_body()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not 2 <= len(name) <= 60:
        return error("Enter your name (2 to 60 characters).")
    if not EMAIL_RE.match(email) or len(email) > 120:
        return error("Enter a valid email address.")
    if not 6 <= len(password) <= 128:
        return error("Password must be 6 to 128 characters.")

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return error("An account with this email already exists. Log in instead.", 409)

    session.clear()
    session.permanent = True
    session["user_id"] = cur.lastrowid
    return jsonify({"id": cur.lastrowid, "name": name, "email": email}), 201


@app.post("/api/login")
def login():
    data = json_body()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return error("Email or password is incorrect.", 401)

    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    return jsonify({"id": user["id"], "name": user["name"], "email": user["email"]})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
@login_required
def me():
    user = get_db().execute(
        "SELECT id, name, email FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    if user is None:  # account was deleted while the cookie was still valid
        session.clear()
        return error("Please log in first.", 401)
    return jsonify(dict(user))


# ---------- tasks API (every query is limited to the logged-in user) ----------
@app.get("/api/tasks")
@login_required
def list_tasks():
    rows = get_db().execute(
        "SELECT * FROM tasks WHERE user_id = ? ORDER BY id DESC", (session["user_id"],)
    ).fetchall()
    return jsonify([task_to_dict(r) for r in rows])


@app.post("/api/tasks")
@login_required
def create_task():
    data = json_body()
    name = str(data.get("name", "")).strip()
    priority = data.get("priority", "Medium")
    deadline = str(data.get("deadline", "") or "")

    if not 1 <= len(name) <= 120:
        return error("Task name must be 1 to 120 characters.")
    if priority not in PRIORITIES:
        return error("Priority must be Low, Medium or High.")
    if not valid_deadline(deadline):
        return error("Deadline must be a valid date.")

    db = get_db()
    cur = db.execute(
        "INSERT INTO tasks (user_id, name, priority, deadline) VALUES (?, ?, ?, ?)",
        (session["user_id"], name, priority, deadline),
    )
    db.commit()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(task_to_dict(row)), 201


@app.patch("/api/tasks/<int:task_id>")
@login_required
def update_task(task_id):
    data = json_body()
    fields, values = [], []

    if "completed" in data:
        fields.append("completed = ?")
        values.append(1 if data["completed"] else 0)
    if "name" in data:
        name = str(data["name"]).strip()
        if not 1 <= len(name) <= 120:
            return error("Task name must be 1 to 120 characters.")
        fields.append("name = ?")
        values.append(name)
    if "priority" in data:
        if data["priority"] not in PRIORITIES:
            return error("Priority must be Low, Medium or High.")
        fields.append("priority = ?")
        values.append(data["priority"])
    if "deadline" in data:
        deadline = str(data["deadline"] or "")
        if not valid_deadline(deadline):
            return error("Deadline must be a valid date.")
        fields.append("deadline = ?")
        values.append(deadline)
    if not fields:
        return error("Nothing to update.")

    db = get_db()
    cur = db.execute(
        f"UPDATE tasks SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
        (*values, task_id, session["user_id"]),
    )
    db.commit()
    if cur.rowcount == 0:
        return error("Task not found.", 404)
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return jsonify(task_to_dict(row))


@app.delete("/api/tasks/<int:task_id>")
@login_required
def delete_task(task_id):
    db = get_db()
    cur = db.execute(
        "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, session["user_id"])
    )
    db.commit()
    if cur.rowcount == 0:
        return error("Task not found.", 404)
    return jsonify({"message": "Task deleted."})


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
