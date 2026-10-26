import os
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps

from bson import ObjectId
from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, redirect, render_template,
    request, session, url_for
)
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.security import check_password_hash, generate_password_hash

from database import (
    assignments_collection,
    initialize_database,
    subjects_collection,
    users_collection,
)

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "development-only-change-this-secret-before-deployment"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        return users_collection.find_one({"_id": ObjectId(user_id)})
    except Exception:
        session.clear()
        return None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if current_user() is None:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


def parse_due_date(value):
    try:
        selected = date.fromisoformat(value)
        return datetime.combine(selected, time.min, tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def display_date(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def assignment_status(doc):
    if doc.get("status") == "Completed":
        return "Completed"
    due = doc.get("due_date")
    if due and due.date() < datetime.now(timezone.utc).date():
        return "Overdue"
    return doc.get("status", "Pending")


@app.context_processor
def inject_globals():
    user = current_user()
    return {
        "logged_in_user": user,
        "today": date.today().isoformat(),
    }


@app.template_filter("date_only")
def date_only(value):
    return display_date(value)


@app.template_filter("effective_status")
def effective_status(doc):
    return assignment_status(doc)


@app.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill in every required field.", "error")
        elif len(name) > 80:
            flash("Name must be 80 characters or fewer.", "error")
        elif len(password) < 8:
            flash("Use a password with at least 8 characters.", "error")
        elif password != confirm_password:
            flash("The passwords do not match.", "error")
        else:
            user = {
                "name": name,
                "email": email,
                "password_hash": generate_password_hash(password),
                "created_at": datetime.now(timezone.utc),
            }
            try:
                result = users_collection.insert_one(user)
                session.clear()
                session["user_id"] = str(result.inserted_id)
                flash("Your account is ready. Welcome to DueDate!", "success")
                return redirect(url_for("dashboard"))
            except DuplicateKeyError:
                flash("An account with that email already exists.", "error")
            except PyMongoError:
                flash("Could not save your account. Check the database connection.", "error")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = users_collection.find_one({"email": email})

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = str(user["_id"])
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))

        flash("Email or password is incorrect.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    owner_id = user["_id"]
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)

    total = assignments_collection.count_documents({"owner_id": owner_id})
    completed = assignments_collection.count_documents({
        "owner_id": owner_id,
        "status": "Completed",
    })
    pending = assignments_collection.count_documents({
        "owner_id": owner_id,
        "status": "Pending",
        "due_date": {"$gte": today_start},
    })
    overdue = assignments_collection.count_documents({
        "owner_id": owner_id,
        "status": {"$ne": "Completed"},
        "due_date": {"$lt": today_start},
    })

    upcoming = list(
        assignments_collection.find({
            "owner_id": owner_id,
            "status": {"$ne": "Completed"},
            "due_date": {"$gte": today_start},
        }).sort("due_date", 1).limit(5)
    )
    recent = list(
        assignments_collection.find({"owner_id": owner_id})
        .sort("created_at", DESCENDING)
        .limit(5)
    )

    for item in upcoming + recent:
        subject = subjects_collection.find_one({"_id": item.get("subject_id")})
        item["subject_name"] = subject["name"] if subject else "Other"

    percent = round((completed / total) * 100) if total else 0
    return render_template(
        "dashboard.html",
        total=total,
        completed=completed,
        pending=pending,
        overdue=overdue,
        upcoming=upcoming,
        recent=recent,
        percent=percent,
    )


@app.route("/assignments")
@login_required
def assignments():
    user = current_user()
    query = {"owner_id": user["_id"]}

    status_filter = request.args.get("status", "").strip()
    subject_filter = request.args.get("subject", "").strip()
    search = request.args.get("q", "").strip()
    sort_by = request.args.get("sort", "due_date")

    if status_filter in ("Pending", "Completed"):
        query["status"] = status_filter
    if subject_filter:
        try:
            query["subject_id"] = ObjectId(subject_filter)
        except Exception:
            subject_filter = ""
    if search:
        query["title"] = {"$regex": search, "$options": "i"}

    sort_field = "created_at" if sort_by == "newest" else "due_date"
    direction = DESCENDING if sort_by == "newest" else 1
    items = list(assignments_collection.find(query).sort(sort_field, direction))

    for item in items:
        subject = subjects_collection.find_one({"_id": item.get("subject_id")})
        item["subject_name"] = subject["name"] if subject else "Other"
        item["effective_status"] = assignment_status(item)

    subjects = list(subjects_collection.find().sort("name", 1))
    return render_template(
        "assignments.html",
        assignments=items,
        subjects=subjects,
        status_filter=status_filter,
        subject_filter=subject_filter,
        search=search,
        sort_by=sort_by,
    )


def get_assignment_for_owner(assignment_id, owner_id):
    try:
        object_id = ObjectId(assignment_id)
    except Exception:
        abort(404)

    item = assignments_collection.find_one({
        "_id": object_id,
        "owner_id": owner_id,
    })
    if item is None:
        abort(404)
    return item


@app.route("/assignments/new", methods=["GET", "POST"])
@login_required
def assignment_new():
    user = current_user()
    subjects = list(subjects_collection.find().sort("name", 1))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        subject_value = request.form.get("subject_id", "")
        due_date = parse_due_date(request.form.get("due_date", ""))
        priority = request.form.get("priority", "Medium")
        status = request.form.get("status", "Pending")
        checklist_lines = request.form.get("checklist", "").splitlines()
        checklist = [
            {"text": line.strip(), "done": False}
            for line in checklist_lines if line.strip()
        ][:20]

        try:
            subject_id = ObjectId(subject_value)
            subject_exists = subjects_collection.find_one({"_id": subject_id})
        except Exception:
            subject_exists = None
            subject_id = None

        if not title:
            flash("Please enter an assignment title.", "error")
        elif len(title) > 140:
            flash("Title must be 140 characters or fewer.", "error")
        elif not subject_exists:
            flash("Please choose a valid subject.", "error")
        elif not due_date:
            flash("Please choose a valid due date.", "error")
        elif priority not in ("Low", "Medium", "High"):
            flash("Please choose a valid priority.", "error")
        elif status not in ("Pending", "Completed"):
            flash("Please choose a valid status.", "error")
        else:
            document = {
                "title": title,
                "description": description,
                "subject_id": subject_id,
                "owner_id": user["_id"],
                "due_date": due_date,
                "priority": priority,
                "status": status,
                "checklist": checklist,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            assignments_collection.insert_one(document)
            flash("Assignment saved.", "success")
            return redirect(url_for("assignments"))

    return render_template(
        "assignment_form.html",
        item=None,
        subjects=subjects,
        page_title="Add assignment",
    )


@app.route("/assignments/<assignment_id>/edit", methods=["GET", "POST"])
@login_required
def assignment_edit(assignment_id):
    user = current_user()
    item = get_assignment_for_owner(assignment_id, user["_id"])
    subjects = list(subjects_collection.find().sort("name", 1))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        due_date = parse_due_date(request.form.get("due_date", ""))
        priority = request.form.get("priority", "Medium")
        status = request.form.get("status", "Pending")
        subject_value = request.form.get("subject_id", "")
        checklist_lines = request.form.get("checklist", "").splitlines()
        previous_checklist = {
            check.get("text", ""): bool(check.get("done", False))
            for check in item.get("checklist", [])
        }
        checklist = [
            {"text": line.strip(), "done": previous_checklist.get(line.strip(), False)}
            for line in checklist_lines if line.strip()
        ][:20]

        try:
            subject_id = ObjectId(subject_value)
            subject_exists = subjects_collection.find_one({"_id": subject_id})
        except Exception:
            subject_exists = None
            subject_id = None

        if not title or len(title) > 140:
            flash("Enter a title with 1–140 characters.", "error")
        elif not due_date:
            flash("Please choose a valid due date.", "error")
        elif not subject_exists:
            flash("Please choose a valid subject.", "error")
        elif priority not in ("Low", "Medium", "High") or status not in ("Pending", "Completed"):
            flash("Please choose valid priority and status values.", "error")
        else:
            assignments_collection.update_one(
                {"_id": item["_id"], "owner_id": user["_id"]},
                {"$set": {
                    "title": title,
                    "description": description,
                    "subject_id": subject_id,
                    "due_date": due_date,
                    "priority": priority,
                    "status": status,
                    "checklist": checklist,
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
            flash("Assignment updated.", "success")
            return redirect(url_for("assignments"))

    return render_template(
        "assignment_form.html",
        item=item,
        subjects=subjects,
        page_title="Edit assignment",
    )


@app.route("/assignments/<assignment_id>/checklist/<int:check_index>", methods=["POST"])
@login_required
def checklist_toggle(assignment_id, check_index):
    user = current_user()
    item = get_assignment_for_owner(assignment_id, user["_id"])
    checklist = item.get("checklist", [])

    if check_index < 0 or check_index >= len(checklist):
        abort(404)

    checklist[check_index]["done"] = not bool(checklist[check_index].get("done", False))
    assignments_collection.update_one(
        {"_id": item["_id"], "owner_id": user["_id"]},
        {"$set": {"checklist": checklist, "updated_at": datetime.now(timezone.utc)}},
    )
    return redirect(request.referrer or url_for("assignments"))


@app.route("/assignments/<assignment_id>/complete", methods=["POST"])
@login_required
def assignment_complete(assignment_id):
    user = current_user()
    item = get_assignment_for_owner(assignment_id, user["_id"])
    new_status = "Pending" if item.get("status") == "Completed" else "Completed"
    assignments_collection.update_one(
        {"_id": item["_id"], "owner_id": user["_id"]},
        {"$set": {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    flash(f"Assignment marked {new_status.lower()}.", "success")
    return redirect(request.referrer or url_for("assignments"))


@app.route("/assignments/<assignment_id>/delete", methods=["POST"])
@login_required
def assignment_delete(assignment_id):
    user = current_user()
    item = get_assignment_for_owner(assignment_id, user["_id"])
    assignments_collection.delete_one({
        "_id": item["_id"],
        "owner_id": user["_id"],
    })
    flash("Assignment deleted.", "success")
    return redirect(url_for("assignments"))


@app.route("/reports")
@login_required
def reports():
    user = current_user()
    owner_id = user["_id"]

    # Aggregation 1: count tasks by status.
    status_pipeline = [
        {"$match": {"owner_id": owner_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    status_stats = list(assignments_collection.aggregate(status_pipeline))

    # Aggregation 2: join subject details and group by subject.
    subject_pipeline = [
        {"$match": {"owner_id": owner_id}},
        {"$lookup": {
            "from": "subjects",
            "localField": "subject_id",
            "foreignField": "_id",
            "as": "subject",
        }},
        {"$unwind": {"path": "$subject", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": "$subject.name",
            "total": {"$sum": 1},
            "completed": {
                "$sum": {"$cond": [{"$eq": ["$status", "Completed"]}, 1, 0]}
            },
        }},
        {"$sort": {"total": -1}},
    ]
    subject_stats = list(assignments_collection.aggregate(subject_pipeline))

    total = assignments_collection.count_documents({"owner_id": owner_id})
    completed = assignments_collection.count_documents({
        "owner_id": owner_id,
        "status": "Completed",
    })
    percent = round((completed / total) * 100) if total else 0

    return render_template(
        "reports.html",
        status_stats=status_stats,
        subject_stats=subject_stats,
        total=total,
        completed=completed,
        percent=percent,
    )


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    try:
        initialize_database()
    except PyMongoError as error:
        print("Could not initialize MongoDB.")
        print("Make sure the MongoDB server is running and MONGO_URI is correct.")
        print(f"Details: {error}")
        raise SystemExit(1)

    app.run(debug=True)
