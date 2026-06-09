import io
import logging
import os

import librosa
import numpy as np
import soundfile as sf
from scipy.spatial.distance import cosine

from onoma_app.config import ALLOWED_EXTENSIONS
from onoma_app.utils import extract_advanced_features

logger = logging.getLogger(__name__)

def is_allowed_file(filename):
    """
    Determines whether a file extension is allowed.
    Args:
        filename (str): The filename to be checked.
    Returns:
        bool: True if the extension is allowed.
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def compare_audio_features(file1_path, file2_path):
    """
    Compare two audio files and calculate the similarity for each feature and an overall score.
    Args:
        file1_path (str): The path to the first audio file.
        file2_path (str): The path to the second audio file.
    Returns:
        dict | None: Feature comparison results and an overall score. Returns None on failure.
    """
    try:
        features1 = extract_advanced_features(file1_path)
        features2 = extract_advanced_features(file2_path)

        if features1 is None or features2 is None:
            return None

        feature_weights = {
            "mfcc": 0.25,
            "mfcc_delta": 0.20,
            "mfcc_delta2": 0.15,
            "spectral_centroid": 0.15,
            "zero_crossing_rate": 0.10,
            "spectral_rolloff": 0.10,
            "chroma": 0.05,
        }

        comparison = {}

        for feature_name in features1.keys():
            if feature_name not in features2:
                continue

            if isinstance(features1[feature_name], np.ndarray):
                similarity = 1 - cosine(features1[feature_name], features2[feature_name])
                comparison[feature_name] = {
                    "similarity": float(similarity),
                    "type": "array",
                    "size": len(features1[feature_name]),
                    "weight": feature_weights.get(feature_name, 0.05),
                    "contribution": 0,
                }

            else:
                val1 = float(features1[feature_name])
                val2 = float(features2[feature_name])
                if val1 == 0 and val2 == 0:
                    similarity = 1.0
                elif val1 == 0 or val2 == 0:
                    similarity = 0.0
                else:
                    relative_diff = abs(val1 - val2) / max(abs(val1), abs(val2))
                    similarity = max(0, 1 - relative_diff)
                comparison[feature_name] = {
                    "similarity": similarity,
                    "type": "scalar",
                    "value1": val1,
                    "value2": val2,
                    "weight": feature_weights.get(feature_name, 0.05),
                    "contribution": 0,
                }

        total_weighted_similarity = 0
        total_weight = 0

        for feature_data in comparison.values():
            weight = feature_data["weight"]
            similarity = feature_data["similarity"]
            contribution = weight * similarity
            feature_data["contribution"] = contribution
            total_weighted_similarity += contribution
            total_weight += weight

        overall_similarity = total_weighted_similarity / total_weight if total_weight > 0 else 0
        sorted_features = sorted(comparison.items(), key=lambda item: item[1]["contribution"], reverse=True) # get the most conrtibution feature

        comparison["overall"] = {
            "similarity": float(overall_similarity),
            "feature_count": len(comparison),
            "weighted_similarity": float(overall_similarity),
            "top_features": [name for name, _ in sorted_features[:3]],
        }

        comparison["feature_ranking"] = [
            {
                "name": name,
                "contribution": data["contribution"],
                "similarity": data["similarity"],
                "weight": data["weight"],
            }
            
            for name, data in sorted_features
        ]
        return comparison
    except Exception:
        logger.exception("Feature comparison failed")
        return None

def augment_audio(audio, sr, augmentations=None):
    """
    Generate augmented audio variants entirely in memory.
    Args:
        audio (np.ndarray): Original audio data.
        sr (int): Sampling rate of the audio data.
        augmentations (list[str], optional): List of augmentation types to apply.
            Defaults to None, which applies all augmentations.
    Returns:
        list[tuple[str, str, bytes]]: Each entry is (filename, description, wav_bytes).
    """
    if augmentations is None:
        augmentations = ["pitch_shift", "time_stretch", "noise_injection", "volume_change"]

    augmented_files = []
    for aug_type in augmentations:
        try:
            if aug_type == "pitch_shift":
                for steps in [-2, -1, 1, 2]:
                    shifted = librosa.effects.pitch_shift(audio, sr=sr, n_steps=steps)
                    filename = f"aug_pitch_{steps:+d}.wav"
                    buf = io.BytesIO()
                    sf.write(buf, shifted, sr, format="WAV")
                    augmented_files.append((filename, f"Pitch shift {steps:+d} semitones", buf.getvalue()))

            elif aug_type == "time_stretch":
                for rate in [0.8, 1.2]:
                    stretched = librosa.effects.time_stretch(audio, rate=rate)
                    filename = f"aug_time_{rate:.1f}x.wav"
                    buf = io.BytesIO()
                    sf.write(buf, stretched, sr, format="WAV")
                    augmented_files.append((filename, f"Time stretch {rate:.1f}x", buf.getvalue()))

            elif aug_type == "noise_injection":
                for noise_level in [0.01, 0.02, 0.05]:
                    noise = np.random.normal(0, noise_level, len(audio))
                    noisy = audio + noise
                    filename = f"aug_noise_{noise_level:.3f}.wav"
                    buf = io.BytesIO()
                    sf.write(buf, noisy, sr, format="WAV")
                    augmented_files.append((filename, f"Noise injection {noise_level:.3f}", buf.getvalue()))

            elif aug_type == "volume_change":
                for gain in [0.5, 1.5, 2.0]:
                    amplified = audio * gain
                    if np.max(np.abs(amplified)) > 1.0:
                        amplified = amplified / np.max(np.abs(amplified)) * 0.95
                    filename = f"aug_volume_{gain:.1f}x.wav"
                    buf = io.BytesIO()
                    sf.write(buf, amplified, sr, format="WAV")
                    augmented_files.append((filename, f"Volume change {gain:.1f}x", buf.getvalue()))

        except Exception:
            logger.exception("Augmentation failed: %s", aug_type)
            continue

    return augmented_files
