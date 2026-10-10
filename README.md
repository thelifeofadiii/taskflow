# TaskFlow (Python + SQLite)

Student task manager with registration, login and a private task list per user.

- Backend: Python / Flask (`app.py`)
- Database: SQLite (file `taskflow.db`, created automatically, no MongoDB)
- Frontend: HTML, CSS, JavaScript in `frontend/`

## Run

```bash
python -m venv venv
venv\Scripts\activate        # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 , create an account, and start adding tasks.

## Notes
- Passwords are stored hashed, never as plain text.
- Each user only sees and edits their own tasks.
- To reset all data, stop the server and delete `taskflow.db`.
- To deploy, set a `SECRET_KEY` environment variable and run with a production server such as `gunicorn app:app`.
