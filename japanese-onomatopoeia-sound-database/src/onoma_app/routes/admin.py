import io
import hashlib
import logging
import os
import uuid
from werkzeug.utils import secure_filename

import librosa
import numpy as np
from flask import current_app, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for

from onoma_app import db
from onoma_app.authz import require_role
from onoma_app.config import SOUNDS_DIR, UPLOAD_SOUND_FOLDER
from onoma_app.services.audio_processing import is_allowed_file, augment_audio
from onoma_app.utils import extract_advanced_feature_vector, extract_features

logger = logging.getLogger(__name__)

# In-memory store for augmented audio blobs: { token: { filename: bytes } }
# Entries are replaced on each new augmentation request — no disk writes needed.
_augment_cache: dict = {}


def _generate_hashed_sound_filename(original_name, file_bytes):
    extension = os.path.splitext(secure_filename(original_name or ""))[1].lower() or ".wav"
    digest = hashlib.sha256(uuid.uuid4().bytes + file_bytes).hexdigest()
    return f"{digest}{extension}"


def _calculate_audio_hash(file_bytes):
    return hashlib.sha256(file_bytes).hexdigest()

def register(app):
    """
    Register the admin route in the Flask app.
    Args:
        app(Flask): The Flask application to which the route is registered.
    Returns:
        None: return no value.  
    """
    @app.route("/admin/approvals")
    @require_role("admin")
    def admin_approvals():
        pending = db.list_pending_users()
        return render_template("admin_approvals.html", pending=pending)

    @app.route("/admin/approvals/<int:user_id>/approve", methods=["POST"])
    @require_role("admin")
    def admin_approve_user(user_id):
        try:
            db.approve_user(user_id)
            return redirect(url_for("admin_approvals"))
        except Exception as e:
            return jsonify({"error": f"Approval failed: {e}"}), 500

    @app.route("/admin/approvals/<int:user_id>/reject", methods=["POST"])
    @require_role("admin")
    def admin_reject_user(user_id):
        try:
            db.reject_user(user_id)
            return redirect(url_for("admin_approvals"))
        except Exception as e:
            return jsonify({"error": f"Reject failed: {e}"}), 500

    @app.route("/upload_predict", methods=["POST"])
    def upload_predict():
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400
        
        if file and is_allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            return jsonify({"status": "uploaded", "filename": filename})

        return jsonify({"error": "Invalid file type"}), 400

    @app.route("/upload_sound", methods=["POST"])
    @require_role("admin")
    def upload_sound():
        file = request.files["file"]
        file_bytes = file.read()
        audio_hash = _calculate_audio_hash(file_bytes) # make audio file name hash to prevent the confilct of multiple same audio files.

        if db.find_variant_by_audio_hash(audio_hash):
            return jsonify({"error": "This audio file already exists in the database."}), 409
    
        filename = _generate_hashed_sound_filename(file.filename, file_bytes)
        filepath = os.path.join(UPLOAD_SOUND_FOLDER, filename)
        with open(filepath, "wb") as file_handle:
            file_handle.write(file_bytes)
        return jsonify({"filename": filename, "audio_hash": audio_hash})

    @app.route("/save_annotation", methods=["POST"])
    @require_role("admin")
    def save_annotation():
        uploaded_file = request.files.get("file")
        is_form_upload = uploaded_file is not None
        data = request.form if is_form_upload else (request.json or {})
        required_keys = ["label", "description"]

        if not all(key in data for key in required_keys):
            return jsonify({"status": "error", "error": "Missing keys"}), 400

        if is_form_upload and uploaded_file.filename == "":
            return jsonify({"status": "error", "error": "No file selected"}), 400

        if is_form_upload and not is_allowed_file(uploaded_file.filename):
            return jsonify({"status": "error", "error": "Invalid file type"}), 400

        try:
            category = db.normalize_category(data.get("category") or "") # categoeis are Giongo and Giseigo for now
            label = (data.get("label") or "").strip()
            if not label:
                return jsonify({"status": "error", "error": "Onomatopoeic word is required"}), 400
            # we allow users to upload same label.
            existing_item = db.find_item_by_label(label)
            if existing_item:
                logger.info(
                    "duplicate onomatopoeic word submission: label=%s existing_item_id=%s",
                    label,
                    existing_item["id"],
                )
                return jsonify({
                    "status": "error",
                    "error": f'Onomatopoeic word "{label}" already exists. You can add this audio as a new variant of the existing entry.',
                }), 409

            sound_file = data.get("sound_file") or ""

            if is_form_upload:
                file_bytes = uploaded_file.read()
                audio_hash = _calculate_audio_hash(file_bytes)
        
                if db.find_variant_by_audio_hash(audio_hash): # possibly happen
                    return jsonify({"status": "error", "error": "This audio file already exists in the database."}), 409
                sound_file = _generate_hashed_sound_filename(uploaded_file.filename, file_bytes)
                sound_path = SOUNDS_DIR / sound_file
                with open(sound_path, "wb") as file_handle:
                    file_handle.write(file_bytes)
            else:
                if not sound_file:
                    return jsonify({"status": "error", "error": "Missing sound file"}), 400
                sound_path = SOUNDS_DIR / sound_file
                audio_hash = data.get("audio_hash") or None

            variant_id = db.add_item_with_variant(
                label=label,
                description=data.get("description") or "",
                category=category,
                sound_file=sound_file,
                audio_hash=audio_hash,
            )
            # after uploading file, we update db to have audio feature vector for phonetic sim search
            if sound_path.exists():
                mfcc_vec = extract_features(str(sound_path))
                if mfcc_vec is not None:
                    db.upsert_feature(
                        variant_id,
                        "mfcc",
                        mfcc_vec.tolist() if isinstance(mfcc_vec, np.ndarray) else list(mfcc_vec),
                    )

                adv_vec = extract_advanced_feature_vector(str(sound_path))

                if adv_vec is not None:
                    db.upsert_feature(
                        variant_id,
                        "advanced",
                        adv_vec.tolist() if isinstance(adv_vec, np.ndarray) else list(adv_vec),
                    )

        except ValueError as e:
            logger.warning("Annotation save rejected: %s", e)
            return jsonify({"status": "error", "error": str(e)}), 400

        except Exception as e:
            logger.exception("Annotation save failed")
            return jsonify({"status": "error", "error": str(e)}), 500

        return jsonify({
            "status": "ok",
            "message": "New label created and audio submitted.",
            "variant_id": variant_id,
        })

    @app.route("/add_variant_to_existing", methods=["POST"])
    @require_role("admin")
    def add_variant_to_existing():
        """Add a new audio variant to an existing item (same label, different recording)."""
        uploaded_file = request.files.get("file")
        if not uploaded_file or uploaded_file.filename == "":
            return jsonify({"status": "error", "error": "No file selected"}), 400
        if not is_allowed_file(uploaded_file.filename):
            return jsonify({"status": "error", "error": "Invalid file type"}), 400

        label = (request.form.get("label") or "").strip()
        if not label:
            return jsonify({"status": "error", "error": "Label is required"}), 400

        existing_item = db.find_item_by_label(label)
        if not existing_item:
            return jsonify({"status": "error", "error": f'Label "{label}" not found'}), 404

        try:
            file_bytes = uploaded_file.read()
            audio_hash = _calculate_audio_hash(file_bytes)
            if db.find_variant_by_audio_hash(audio_hash):
                return jsonify({"status": "error", "error": "This audio file already exists in the database."}), 409

            sound_file = _generate_hashed_sound_filename(uploaded_file.filename, file_bytes)
            sound_path = SOUNDS_DIR / sound_file
            with open(sound_path, "wb") as fh:
                fh.write(file_bytes)

            variant_id = db.add_variant(existing_item["id"], sound_file, audio_hash)

            if sound_path.exists():
                mfcc_vec = extract_features(str(sound_path))
                if mfcc_vec is not None:
                    db.upsert_feature(variant_id, "mfcc",
                        mfcc_vec.tolist() if isinstance(mfcc_vec, np.ndarray) else list(mfcc_vec))
                adv_vec = extract_advanced_feature_vector(str(sound_path))
                if adv_vec is not None:
                    db.upsert_feature(variant_id, "advanced",
                        adv_vec.tolist() if isinstance(adv_vec, np.ndarray) else list(adv_vec))

        except ValueError as e:
            return jsonify({"status": "error", "error": str(e)}), 400
        except Exception as e:
            logger.exception("add_variant_to_existing failed")
            return jsonify({"status": "error", "error": str(e)}), 500

        return jsonify({
            "status": "ok",
            "message": f'New audio variant added to "{label}". Rebuild the graph to reflect the updated feature vector.',
            "variant_id": variant_id,
            "item_id": existing_item["id"],
        })

    @app.route("/api/items/<int:item_id>", methods=["DELETE"])
    @require_role("admin")
    def api_delete_item(item_id):

        try:
            db.delete_item(item_id)
            return jsonify({"status": "ok"})
        
        except Exception as e:
            return jsonify({"error": f"Delete failed: {e}"}), 500

    @app.route("/api/variants/<int:variant_id>", methods=["DELETE"])
    @require_role("admin")
    def api_delete_variant(variant_id):
        try:
            db.delete_variant(variant_id)
            return jsonify({"status": "ok"})
        
        except Exception as e:
            return jsonify({"error": f"Delete failed: {e}"}), 500

    @app.route("/audio_augmentation")
    @require_role("admin")
    def audio_augmentation_page():
        return render_template("audio_augmentation.html")

    @app.route("/augment_audio", methods=["POST"])
    @require_role("admin")
    def augment_audio_route():
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        if not (file and is_allowed_file(file.filename)):
            return jsonify({"error": "Invalid file type"}), 400

        try:
            filename = secure_filename(file.filename)

            # Load audio entirely from memory — no disk write for the upload
            audio_bytes = file.read()
            audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=None)

            selected_augs = request.form.getlist("augmentations") or [
                "pitch_shift",
                "time_stretch",
                "noise_injection",
                "volume_change",
            ]

            # augment_audio now returns (filename, description, wav_bytes) tuples
            augmented = augment_audio(audio, sr, selected_augs)

            # Store blobs in the in-memory cache under a fresh token
            token = uuid.uuid4().hex
            _augment_cache[token] = {name: data for name, _, data in augmented}
            # Also keep the original for playback
            _augment_cache[token][filename] = audio_bytes

            augmented_files = [
                {
                    "filename": name,
                    "description": desc,
                    "download_url": url_for("augment_download", token=token, filename=name),
                }
                for name, desc, _ in augmented
            ]

            return jsonify({
                "status": "success",
                "token": token,
                "original_file": filename,
                "original_download_url": url_for("augment_download", token=token, filename=filename),
                "augmented_files": augmented_files,
            })
        except Exception as e:
            return jsonify({"error": f"Augmentation failed: {str(e)}"}), 500

    @app.route("/augment_audio/download/<token>/<path:filename>")
    @require_role("admin")
    def augment_download(token, filename):
        """Serve a single in-memory augmented (or original) audio blob for download."""
        bucket = _augment_cache.get(token)
        if not bucket or filename not in bucket:
            return jsonify({"error": "File not found or session expired"}), 404

        data = bucket[filename]
        mime = "audio/wav" if filename.lower().endswith(".wav") else "audio/mpeg"
        return send_file(
            io.BytesIO(data),
            mimetype=mime,
            as_attachment=True,
            download_name=filename,
        )

    @app.route("/sounds/<filename>")
    def sounds(filename):
        return send_from_directory(UPLOAD_SOUND_FOLDER, filename)
