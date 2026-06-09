import os
import pickle
import tempfile

import librosa
import soundfile as sf

from onoma_app.config import ADVANCED_MODEL_PATH
from onoma_app.utils import extract_advanced_feature_vector_from_audio

"""
It loads trained models and pre-computed features to provide inference capabilities.
"""
class ModelService:
    """
    It loads trained models and pre-computed features to provide inference capabilities.
    Args:
        model_path (str): the path to the pre-trained model file.
    """
    def __init__(self, model_path=ADVANCED_MODEL_PATH):

        self.model_path = model_path
        self.model = self._load_pickle(model_path) if os.path.exists(model_path) else None

    @staticmethod
    def _load_pickle(path):
        try:
            with open(path, "rb") as handle:
                return pickle.load(handle)
        except Exception as e:
            print(f"Failed to load pickle {path}: {e}")
            return None

    def reload(self):
        """Reload the model from disk. Called after training completes."""
        self.model = self._load_pickle(self.model_path) if os.path.exists(self.model_path) else None

    def predict_file_storage(self, file_storage):
        """
        Estimate onomatopoeic labels from uploaded audio files.
        Args:
            file_storage (FileStorage): The uploaded audio file received by Flask.
        Returns:
            tuple[str | None, str | None]: A tuple containing the predicted label and an error message.
        """
        if self.model is None:
            return None, "Model not loaded"

        ext = (os.path.splitext(file_storage.filename)[1] or "").lower()
        y = None
        sr = None

        if ext == ".wav":
            try:
                file_storage.stream.seek(0) # Moves cursor to start	and ready to read again from the top.
                y, sr = sf.read(file_storage.stream)

            except Exception as e:
                return None, f"WAV decode failed: {e}"
        else:
            try:
                with tempfile.NamedTemporaryFile(suffix=ext or ".mp3", delete=True) as tmp:
                    file_storage.stream.seek(0)
                    tmp.write(file_storage.stream.read())
                    tmp.flush()
                    y, sr = librosa.load(tmp.name, sr=22050)

            except Exception as e:
                return None, f"Audio decode failed: {e}"

        features_adv = extract_advanced_feature_vector_from_audio(y, sr)

        if features_adv is None:
            return None, "Advanced feature extraction failed"

        predicted = self.model.predict([features_adv])[0]
        return predicted, None
