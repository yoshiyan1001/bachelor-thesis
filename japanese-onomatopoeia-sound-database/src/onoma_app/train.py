"""
train.py — Model training script for Japanese Onomatopoeia Sound Database

This script trains one classifier:
- Advanced-features model: concatenation of MFCC, deltas, chroma, spectral stats

It saves after training:
- models/<mode>/advanced_model.pkl — Advanced-features RandomForest

Data source: annotations.db or annotations.test.db-> join of variants + items
Audio files are expected under static/sounds/<mode>/<filename>
"""
"""
MFCC(Mel-frequency cepstral coefficients) is to approximate how the human ear hears frequencies.

RandomForestClassifier is a machine learning model used for classification tasks.
It is an "ensemble" method, meaning it combines the results of multiple decision trees to improve accuracy and prevent overfitting.
Each "tree" in the forest is trained on a random subset of the data and features, and the final prediction is made by aggregating (usually by majority vote) the predictions of all the trees.
"""

import pickle

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from onoma_app import db
from onoma_app.config import MODELS_DIR, SOUNDS_DIR
from onoma_app.utils import LOGGER, extract_advanced_feature_vector, extract_features

# Helper function to train the classifier with Rondom Forest algorithm.
# It returns the advanced features model.
def _train_classifier(X_train_adv, y_train_adv):

    model_adv = RandomForestClassifier(n_estimators=100, random_state=42)
    model_adv.fit(X_train_adv, y_train_adv)
    return model_adv

# Helper function to evaluate the trained model on the test set and log the accuracy.
def _evaluate_model(model_adv, X_te_adv, y_te_adv):
    
    y_prediction_adv = model_adv.predict(X_te_adv)

    accuracy_adv = accuracy_score(y_te_adv, y_prediction_adv)

    LOGGER.info("Evaluation Results:")
    LOGGER.info(f" Advanced Model:   {accuracy_adv:.2%}")


# Helper function to save the trained model to disk using pickle.
def _save_model(model, filename="advanced_model.pkl"):

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = MODELS_DIR / filename

    with open(save_path, "wb") as file_handle:
        pickle.dump(model, file_handle)

    LOGGER.info(f"Model successfully persisted to: {save_path}")

def train_model():
    """
    It trains the model using audio data from the database.

    Args: None
    Returns:
        bool: it returns True if the training process completes successfully, 
        and False if there are issues such as insufficient data or lack of label diversity.
    """
    rows = db.list_sound_files_with_labels()
    X_adv, y = [], []

    # Also fetch variant IDs so we can persist feature vectors to the DB
    variants_by_file = {v["sound_file"]: v["id"] for v in db.list_variants()}

    for row in rows:
        file_path = SOUNDS_DIR / row["sound_file"]
        if not file_path.is_file():
            continue

        advanced_vector = extract_advanced_feature_vector(str(file_path))
        if advanced_vector is None:
            continue

        X_adv.append(advanced_vector)
        y.append(row["label"])

        # Persist the 62-dim advanced vector so phonetic search can use it
        variant_id = variants_by_file.get(row["sound_file"])
        if variant_id is not None:
            db.upsert_feature(variant_id, "advanced", advanced_vector.tolist())

    if len(y) < 5:
        message = f"Insufficient data for training: found {len(y)} usable audio files, need at least 5."
        LOGGER.error(message)
        return False, message

    if len(set(y)) < 2:
        message = "Training requires at least two distinct labels."
        LOGGER.error(message)
        return False, message

    indices = list(range(len(y)))
    
    try:
        train_indices, test_indices = train_test_split(indices, test_size=0.2, random_state=42, stratify=y) # stratified split

    except ValueError:
        train_indices, test_indices = train_test_split(indices, test_size=0.2, random_state=42)

    Xtr_adv = [X_adv[index] for index in train_indices]
    Xte_adv = [X_adv[index] for index in test_indices]
    ytr = [y[index] for index in train_indices]
    yte = [y[index] for index in test_indices]

    model_adv = _train_classifier(Xtr_adv, ytr)
    _evaluate_model(model_adv, Xte_adv, yte)
    _save_model(model_adv)
    return True, f"Training completed with {len(y)} usable audio files and {len(set(y))} labels."