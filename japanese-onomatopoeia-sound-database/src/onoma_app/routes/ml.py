import os
import tempfile

import librosa
import numpy as np
from flask import current_app, jsonify, render_template, request
from scipy.spatial.distance import cosine

from onoma_app import db
from onoma_app.authz import require_role
from onoma_app.services.audio_processing import is_allowed_file, compare_audio_features
from onoma_app.train import train_model as run_training
from onoma_app.utils import extract_advanced_features

def register(app):
    """
    Register ML routes for prediction, comparison, search, and learning in the Flask app.
    Args:
        app (Flask): The Flask application to which the routes will be registered.
    Returns
        None: no values return.
    """
    @app.route("/phonetic_search_page")
    def phonetic_search_page():
        return render_template("phonetic_search.html")

    @app.route("/phonetic_search", methods=["POST"])
    def phonetic_search():
        import json as _json

        file = request.files["audio"]

        # Extract 62-dim advanced feature vector from the uploaded audio
        file.stream.seek(0)
        y, sr = librosa.load(file, sr=None)

        from onoma_app.utils import extract_advanced_feature_vector_from_audio
        query_vec = extract_advanced_feature_vector_from_audio(y, sr)
        if query_vec is None:
            return jsonify({"error": "Feature extraction failed for uploaded audio."}), 400

        # Load stored advanced vectors from the DB 
        rows = db.list_features_by_type("advanced")
        if not rows:
            return jsonify({"error": "No features in database. Please train the model first."}), 400

        # Build variant_id -> advanced vector map
        label_vecs: dict = {}
        for row in rows:
            try:
                vec = np.array(_json.loads(row["data_json"]), dtype=float)
            except Exception:
                continue
            label_vecs.setdefault(int(row["variant_id"]), vec)

        # Map variant_id -> label via variant -> item join
        variants = {v["id"]: v for v in db.list_variants()}
        items    = {i["id"]: i for i in db.list_items()}

        label_to_vecs: dict = {}
        for vid, vec in label_vecs.items():
            variant = variants.get(vid)
            if not variant:
                continue
            item = items.get(variant["item_id"])
            if not item:
                continue
            label = item["label"]
            label_to_vecs.setdefault(label, []).append(vec)

        if not label_to_vecs:
            return jsonify({"error": "No features in database. Please train the model first."}), 400

        # Average across variants per label, then rank by cosine similarity
        label_mean: dict = {
            label: np.mean(np.vstack(vecs), axis=0)
            for label, vecs in label_to_vecs.items()
        }

        similarities = [
            (label, float(1 - cosine(query_vec, vec))) # cosine simillarity
            for label, vec in label_mean.items()
        ]
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_matches = [label for label, _ in similarities[:3]] # return top 3 items
        return jsonify(top_matches)

    @app.route("/predict", methods=["POST"])
    def predict():
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        predicted_label, error = current_app.extensions["model_service"].predict_file_storage(file)
        if error:
            return jsonify({"error": error}), 500
        return jsonify({"predicted_label": predicted_label, "model": "advanced"})

    @app.route("/feature_comparison")
    @require_role("researcher")
    def feature_comparison():
        return render_template("feature_comparison.html")

    @app.route("/compare_audio", methods=["POST"])
    @require_role("researcher")
    def compare_audio_route():
        if "file1" not in request.files or "file2" not in request.files:
            return jsonify({"error": "Please upload two audio files"}), 400

        file1 = request.files["file1"]
        file2 = request.files["file2"]
        if file1.filename == "" or file2.filename == "":
            return jsonify({"error": "Please select both files"}), 400
        if not (is_allowed_file(file1.filename) and is_allowed_file(file2.filename)):
            return jsonify({"error": "Invalid file type"}), 400

        try:
            filename1 = os.path.basename(file1.filename)
            filename2 = os.path.basename(file2.filename)
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename1)[1] or ".wav") as tmp1, tempfile.NamedTemporaryFile(
                suffix=os.path.splitext(filename2)[1] or ".wav"
            ) as tmp2:
                file1.save(tmp1.name)
                file2.save(tmp2.name)
                comparison = compare_audio_features(tmp1.name, tmp2.name)

            if comparison is None:
                return jsonify({"error": "Feature comparison failed"}), 500
            return jsonify({"status": "success", "file1": filename1, "file2": filename2, "comparison": comparison})
        except Exception as e:
            return jsonify({"error": f"Comparison failed: {str(e)}"}), 500

    @app.route("/extract_features_single", methods=["POST"])
    @require_role("researcher")
    def extract_features_single_route():
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        if not is_allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        try:
            filename = os.path.basename(file.filename)
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1] or ".wav") as tmp:
                file.save(tmp.name)
                features = extract_advanced_features(tmp.name)

            if features is None:
                return jsonify({"error": "Feature extraction failed"}), 500

            serializable_features = {}
            for key, value in features.items():
                serializable_features[key] = value.tolist() if isinstance(value, np.ndarray) else float(value)

            return jsonify({"status": "success", "filename": filename, "features": serializable_features})

        except Exception as e:
            return jsonify({"error": f"Feature extraction failed: {str(e)}"}), 500

    @app.route("/train_model", methods=["POST"])
    @require_role("admin")
    def train_model():
        try:
            success, message = run_training()
            if not success:
                return jsonify({"status": "error", "error": message}), 500

            # Reload the model in the running app so predict works immediately
            current_app.extensions["model_service"].reload()

            return jsonify({"status": "ok", "output": message})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500
