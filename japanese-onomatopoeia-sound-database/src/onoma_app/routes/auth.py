from flask import redirect, render_template, request, session, url_for

from onoma_app import db
from onoma_app.authz import normalize_role

def register(app):
    """
    Register authentication routes into a Flask app.
    Args:
        app(Flask): the Flask appliacation to which the route is registered.
    Returns:
        None: no value returns.
    """
    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            user = db.authenticate_user(username, password)

            if user:
                session["role"] = user["role"]
                session["user"] = {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": normalize_role(user["role"]),
                }

                return redirect(request.args.get("next") or url_for("index"))
            
            error = "Invalid credentials or account not approved"

        return render_template("login.html", error=error)

    @app.route("/register", methods=["GET", "POST"])
    def register_user():
        error = None
        success = None

        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            email = (request.form.get("email") or "").strip()
            password = request.form.get("password") or ""
            role = (request.form.get("role") or "").strip().lower()

            if not username or not password:
                error = "Username and password are required"
            elif normalize_role(role) != "researcher":
                error = "Only Researcher registration is available"
            else:
                status = "pending"
                try:
                    db.create_user(username, email, password, "researcher", status)
                    success = "Registration submitted. Waiting for admin approval."
                except Exception as e:
                    error = f"Registration failed: {e}"
        return render_template("register.html", error=error, success=success)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))
