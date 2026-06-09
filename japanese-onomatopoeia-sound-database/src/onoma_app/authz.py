from functools import wraps
from flask import jsonify, redirect, request, session, url_for

ROLE_ORDER = ["basic", "researcher", "admin"]
ROLE_ALIASES = {
    "basic": "basic",
    "researcher": "researcher",
    "admin": "admin",
}

# Helper funciton to role index.
def _role_index(role):
    try:
        return ROLE_ORDER.index(normalize_role(role))
    except ValueError:
        return 0

def current_role():
    """
    It returns the current user's role, normalized from the one stored in the session.
    Args: None.
    Returns: 
        str: role name after normalization.
    """
    return normalize_role(session.get("role", "basic"))

def current_user():
    """
    It returns the current users information saved in session.
    Args: None.
    Returns:
        dict | None: user information in session. If no login, then return None.
    """
    return session.get("user")

def normalize_role(role):
    
    if not isinstance(role, str):
        return "basic"
    return ROLE_ALIASES.get(role.lower(), role.lower())

def role_at_least(required_role):
    """
    Validate if a current user has the permmision for higher role.
    Args:
        required_role (str): role name
    Returns:
        True if it satisfies with the condition.
    """
    return _role_index(current_role()) >= _role_index(normalize_role(required_role))

# Helper function to handle API or user.
def _forbidden_response():

    wants_json = request.path.startswith("/api") or request.accept_mimetypes.best == "application/json"
    if wants_json or request.method != "GET":
        return jsonify({"error": "forbidden", "message": "Insufficient permissions"}), 403
    
    return redirect(url_for("login", next=request.path))

def require_role(required_role):
    """
    Provide the decorator that blocks access from users with a role lower than the specified one.
    Args:
        required_role (str): required role
    Returns:
        callable: a decorator that applies access control.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not role_at_least(required_role):
                return _forbidden_response()
            return fn(*args, **kwargs)

        return wrapper

    return decorator

def inject_role():
    """
    Inject the role information and display helper to be used in the template.
    Args: None.
    Returns: Role-related information to be added to the template context.

    """
    return {
        "current_role": current_role(),
        "current_user": current_user(),
    }
