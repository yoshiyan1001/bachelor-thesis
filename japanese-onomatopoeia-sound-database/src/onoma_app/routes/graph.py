from flask import jsonify, render_template, request

from onoma_app import db
from onoma_app.authz import require_role
from onoma_app.services.graph_service import build_graph_version, compute_pca_positions
import logging

logger = logging.getLogger(__name__)


def register(app):
    """
    Register the routes for the similarity graph display and graph management API.
    Args:
        app (Flask): Flask app that is registered for the route.
    Returns:
        None: no values return.
    """
    @app.route("/similarity_explorer")
    @require_role("researcher")
    def similarity_explorer():
        return render_template("similarity_explorer.html")

    # Public graph endpoint — returns the displayed+approved graph only.
    # Admins also receive the full version list so they can see status.
    @app.route("/api/graph/current", methods=["GET"])
    def api_graph_current():
        from onoma_app.authz import current_role
        role = current_role()

        version = db.get_displayed_graph_version()

        # Admins fall back to the latest version if nothing is displayed,
        # so the admin panel always has something to work with.
        if not version and role == "admin":
            version = db.get_latest_graph_version(status="approved")
            if not version:
                version = db.get_latest_graph_version()

        if not version:
            return jsonify({"status": "empty"}), 200

        graph = db.get_graph(int(version["id"]))
        return jsonify({"status": "ok", "version": version, "graph": graph})

    @app.route("/api/graph/version/<int:version_id>", methods=["GET"])
    @require_role("admin")
    def api_graph_version(version_id):
        version_row = None
        versions = db.list_graph_versions()
        for v in versions:
            if int(v["id"]) == version_id:
                version_row = v
                break
        graph = db.get_graph(version_id)
        return jsonify({"status": "ok", "version": version_row or {"id": version_id}, "graph": graph})

    @app.route("/api/graph/versions", methods=["GET"])
    @require_role("admin")
    def api_graph_versions():
        return jsonify({"status": "ok", "versions": db.list_graph_versions()})

    @app.route("/api/graph/delete", methods=["POST"])
    @require_role("admin")
    def api_graph_delete():
        data = request.json or {}
        version_id = int(data.get("version_id") or 0)
        if not version_id:
            return jsonify({"status": "error", "message": "Missing version_id"}), 400
        try:
            db.delete_graph_version(version_id)
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/graph/build", methods=["POST"])
    @require_role("admin")
    def api_graph_build():
        data = request.json or {}
        name = (data.get("name") or "draft").strip()
        try:
            result = build_graph_version(name=name)
            return jsonify({"status": "ok", **result})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/graph/save_positions", methods=["POST"])
    @require_role("admin")
    def api_graph_save_positions():
        data = request.json or {}
        version_id = int(data.get("version_id") or 0)
        positions_raw = data.get("positions") or {}
        positions = {int(key): value for key, value in positions_raw.items()}

        if not version_id or not positions:
            return jsonify({"status": "error", "message": "Missing data"}), 400
        try:
            db.update_graph_positions(version_id, positions)
            # status to "saved" so the Approve button becomes available
            db.set_graph_version_status(version_id, "saved")
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/graph/approve", methods=["POST"])
    @require_role("admin")
    def api_graph_approve():
        data = request.json or {}
        version_id = int(data.get("version_id") or 0)
        if not version_id:
            return jsonify({"status": "error", "message": "Missing version_id"}), 400
        try:
            # Only a saved graph can be approved
            versions = db.list_graph_versions()
            target = next((v for v in versions if int(v["id"]) == version_id), None)
            if not target:
                return jsonify({"status": "error", "message": "Version not found"}), 404
            if target["status"] != "saved":
                return jsonify({"status": "error",
                                "message": "Only saved graphs can be approved. Save the graph first."}), 400
            # Archive the previously approved version
            current = db.get_latest_graph_version(status="approved")

            if current and int(current["id"]) != version_id: # check if this graph is approved and it is old
                db.set_graph_version_status(int(current["id"]), "archived")  # make it archived

            db.set_graph_version_status(version_id, "approved")
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/graph/display", methods=["POST"])
    @require_role("admin")
    def api_graph_display():
        """
        Toggle the displayed flag on an approved graph version.
        """
        data = request.json or {}
        version_id = int(data.get("version_id") or 0)
        displayed = bool(data.get("displayed", True))
        if not version_id:
            return jsonify({"status": "error", "message": "Missing version_id"}), 400
        ok = db.set_graph_version_displayed(version_id, displayed)
        if not ok:
            return jsonify({"status": "error", "message": "Only approved graphs can be displayed"}), 400
        return jsonify({"status": "ok", "displayed": displayed})

    @app.route("/api/graph/pca_positions", methods=["GET"])
    @require_role("researcher")
    def api_graph_pca_positions():
        """
        Return PCA-projected 3-D coordinates for every item plus axis
        descriptions explaining what each principal component captures.
        """
        try:
            result = compute_pca_positions()
            if not result:
                return jsonify({"status": "empty"}), 200
            return jsonify({"status": "ok",
                            "positions": result["positions"],
                            "axes":      result["axes"]})
        except Exception as e:
            logger.exception("PCA position computation failed")
            return jsonify({"status": "error", "message": str(e)}), 500
