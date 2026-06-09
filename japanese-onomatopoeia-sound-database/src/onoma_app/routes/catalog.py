from flask import jsonify, render_template, request
import logging
from onoma_app import db

def register(app):
    """
    Register the home screen and catalog browsing routes in the Flask app.
    Args:
        app (Flask): The Flask application to which the route is registered.
    Returns:
        None: no values return.
    """
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/browse")
    def browse():
        return render_template("browse.html")

    @app.route("/api/search", methods=["GET"])
    def api_search():
        query = request.args.get("q", "").strip().lower()
        if not query:
            return jsonify([])

        try:
            items = db.search_items(query)
            results = []
            for row in items:
                filename = row.get("sound_file") or ""
                sound_url = f"/sounds/{filename}" if filename else ""
                
                results.append(
                    {
                        "label": row.get("label", ""),
                        "description": row.get("description", ""),
                        "sound_url": sound_url,
                    }
                )
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/onomatopoeia", methods=["GET"])
    def api_onomatopoeia():
        q = (request.args.get("q") or "").strip()
        label_filter = (request.args.get("label") or "").strip()
        category_filter = (request.args.get("category") or "").strip()

        try:
            page = int(request.args.get("page", 1))
        except ValueError:
            page = 1
        try:
            page_size = int(request.args.get("page_size", 12))
        except ValueError:
            page_size = 12

        page = max(page, 1)
        page_size = max(min(page_size, 100), 1)

        try:
            items, total = db.list_items_paginated(q, label_filter, category_filter, page, page_size)
            for item in items:
                filename = item.get("sound_file") or ""
                item["sound_url"] = f"/sounds/{filename}" if filename else ""
            return jsonify({"items": items, "total": total, "page": page, "page_size": page_size})

        except Exception as e:
            return jsonify({"error": f"Failed to load data: {e}"}), 500

    @app.route("/api/onomatopoeia/filters", methods=["GET"])
    def api_onomatopoeia_filters():

        try:
            return jsonify(db.list_filters())
        except Exception as e:
            return jsonify({"error": f"Failed to load data: {e}"}), 500

    @app.route("/api/label_to_file", methods=["GET"])
    def api_label_to_file():

        try:
            return jsonify(db.label_to_file_map())
        except Exception as e:
            return jsonify({"error": f"Failed to load mapping: {e}"}), 500
