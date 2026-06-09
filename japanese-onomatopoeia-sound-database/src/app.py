"""Flask application entrypoint for the Japanese Onomatopoeia Sound Database."""

import logging
import os

from flask import Flask

from onoma_app import db
from onoma_app.authz import inject_role
from onoma_app.config import ADMIN_PASSWORD, ADMIN_USERNAME, APP_PORT, TEMP_UPLOAD_FOLDER, TEMPLATES_DIR, STATIC_DIR, ensure_directories
from onoma_app.routes import admin, auth, catalog, graph, ml
from onoma_app.services.ml_service import ModelService

def configure_logging():
    log_level_name = os.environ.get("ONOMA_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

def create_app():
    """
    Initialize the Flask application and register the route, database, and extensions.
    Args:
        None.
    Returns:
        Flask: An initialized Flask application instance.
    """
    configure_logging()
    app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR), static_url_path="/static")
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["UPLOAD_FOLDER"] = TEMP_UPLOAD_FOLDER
    ensure_directories(app.config["UPLOAD_FOLDER"])

    db.init_db()
    db.migrate_role_names()
    db.ensure_admin_user(ADMIN_USERNAME, ADMIN_PASSWORD)
    db.ensure_test_users()
    db.backfill_advanced_features()

    app.extensions["model_service"] = ModelService()
    app.context_processor(inject_role)

    auth.register(app)
    catalog.register(app)
    ml.register(app)
    graph.register(app)
    admin.register(app)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=APP_PORT)
