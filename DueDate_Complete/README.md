# DueDate — Personal Assignment Tracker

A complete mini-project built with Flask, MongoDB, HTML, CSS and JavaScript.

## Features

- Student registration, login and logout
- Password hashing using Werkzeug
- Personal dashboard with assignment statistics
- Create, view, edit, complete and delete assignments
- Subject selection and filtering
- Deadline sorting and overdue status
- Checklist items embedded in assignment documents
- Progress reports using MongoDB aggregation
- `$lookup` report joining assignments to subjects
- MongoDB indexes for common queries
- Server-side ownership checks so users can manage only their own assignments

## Requirements

- Python 3.10 or newer
- MongoDB Server running locally (Compass alone is a GUI; the MongoDB server must also be running)
- VS Code recommended

## Setup on Windows (VS Code)

1. Extract the ZIP and open the `DueDate_Complete` folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Create a virtual environment:

   ```powershell
   python -m venv .venv
   ```

4. Activate it in PowerShell:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, open Command Prompt in VS Code and run:

   ```bat
   .venv\Scripts\activate.bat
   ```

5. Install packages:

   ```powershell
   python -m pip install -r requirements.txt
   ```

6. Optional: copy `.env.example` to `.env` and set a strong `SECRET_KEY`. The app has a development fallback key so it can run immediately; replace it before any real deployment.

7. Start the app:

   ```powershell
   python app.py
   ```

8. Open http://127.0.0.1:5000 in your browser.

## MongoDB

The default connection is `mongodb://localhost:27017/` and database name is `DueDate`.
The app creates the `users`, `subjects`, and `assignments` collections as needed and seeds a small subject list on startup.

If your MongoDB server uses a different URI, set `MONGO_URI` in `.env`.

## Important notes

- This is a college mini-project, not a production-deployed service.
- Ownership is enforced on the server for assignment viewing, editing, completion and deletion.
- The app does not implement email verification, password reset or CSRF protection. Do not expose it publicly without adding those safeguards.
- All dates are entered and displayed as local calendar dates; the stored due date is normalized to midnight UTC for consistent comparison in this demo.
