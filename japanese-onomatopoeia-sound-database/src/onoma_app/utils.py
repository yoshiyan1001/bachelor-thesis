import logging

import librosa
import numpy as np


DEFAULT_SR = 22050
MFCC_DIM = 13
ADVANCED_DIM = 62

LOGGER = logging.getLogger(__name__)

"""
Extract advanced features and return a single concatenated vector in fixed order.
    mfcc delta is to capture temporal dynamics — how MFCCs change over time. Deltas is first derivative of MFCC sequence (speed of change).
    Delta-deltas is the second derivative (acceleration).
    The result is not just what the spectrum looks like on average, but how it moves (important for sounds like “whoosh” or “crash”).


    Chroma features are to capture how energy is distributed across musical pitch classes (C, C#, … B).
    This folds the frequency spectrum into 12 bins corresponding to pitches within one octave.
    The result is good for detecting harmonic content (like hum, buzz, tonal qualities) that MFCCs alone might miss.

    For scalar spectral features,
    1. Spectral centroid is weighted average frequency and sounds like “brightness” (low centroid = dark/muffled, high = sharp/bright).
    2. Zero-crossing rate is how often waveform crosses zero and measures noisiness (e.g. hiss vs smooth tone).
    3. Spectral rolloff is frequency below which most energy lies and captures where spectrum “drops off.”
    4. Spectral bandwidth is spread of spectrum and difference between narrow-band (pure tone) vs wide-band (noisy).

    Spectral contrast measures the difference between peaks and valleys in sub-bands of the spectrum.
    This divides spectrum into frequency bands, compare highest vs lowest energy.
    The result is to capture texture/“roughness” (e.g. smooth flute vs raspy noise).

    
    Layout (concatenated):
    - mfcc_mean: 13
    - mfcc_delta_mean: 13 
    - mfcc_delta2_mean: 13
    - chroma_mean: 12
    - scalars: [spectral_centroid, zero_crossing_rate, spectral_rolloff, spectral_bandwidth]: 4
    - spectral_contrast_mean: 7 (librosa default)
    Total dims: 13+13+13+12+4+7 = 62
"""

def preprocess_audio(wave_form, sampling_rate):
    """
    Convert audio waveforms to mono, remove silence, and standardize them to a uniform sampling rate.
    Args:
        wave_form (np.ndarray): The audio waveform data to be preprocessed.
            sampling_rate (int): The original sampling rate.
    Returns:
        tuple[np.ndarray | None, int | None]: The preprocessed waveform and sampling rate. Returns (None, None) on failure.
    """
    try:
        if wave_form is None:
            return None, None
        
        if wave_form.ndim > 1:
            wave_form = np.mean(wave_form, axis=1) # Mono Downmixing

        wave_form, _ = librosa.effects.trim(wave_form) # Mono Downmixing

        if sampling_rate != DEFAULT_SR:
            wave_form = librosa.resample(wave_form, orig_sr=sampling_rate, target_sr=DEFAULT_SR) # resampling
            sampling_rate = DEFAULT_SR

        return wave_form, sampling_rate
    
    except Exception as e:
        LOGGER.error(f"Audio preprocessing failed: {e}")
        return None, None

def load_and_standardize(path):
    """
    Load an audio file and return it as a normalized waveform.
    Args:
        path (str): The path to the audio file.
    Returns:
        tuple[np.ndarray | None, int | None]: The normalized waveform and sampling rate. Returns (None, None) on failure.
    """
    try:
        wave_form, sampling_rate = librosa.load(path, sr=None)

    except Exception as e:
        LOGGER.error(f"Critical failure loading audio file {path}: {e}")
        return None, None

    return preprocess_audio(wave_form, sampling_rate)

def extract_raw_components_from_audio(wave_form, sampling_rate):
    """
    Extract raw feature components required for comparison and learning from an audio waveform in a single operation.
    Args:
        wave_form (np.ndarray): Audio waveform data.
        sampling_rate (int): Audio sampling rate.
    Returns:
        dict | None: A dictionary containing the feature components. Returns None on failure.
    """
    wave_form, sampling_rate = preprocess_audio(wave_form, sampling_rate)
    if wave_form is None:
        return None

    try:
        mfcc = librosa.feature.mfcc(y=wave_form, sr=sampling_rate, n_mfcc=MFCC_DIM)
        return {
            "mfcc": np.mean(mfcc.T, axis=0),
            "mfcc_delta": np.mean(librosa.feature.delta(mfcc).T, axis=0),
            "mfcc_delta2": np.mean(librosa.feature.delta(mfcc, order=2).T, axis=0),
            "chroma": np.mean(librosa.feature.chroma_stft(y=wave_form, sr=sampling_rate).T, axis=0),
            "spectral_centroid": float(np.mean(librosa.feature.spectral_centroid(y=wave_form, sr=sampling_rate))),
            "zero_crossing_rate": float(np.mean(librosa.feature.zero_crossing_rate(y=wave_form))),
            "spectral_rolloff": float(np.mean(librosa.feature.spectral_rolloff(y=wave_form, sr=sampling_rate))),
            "spectral_bandwidth": float(np.mean(librosa.feature.spectral_bandwidth(y=wave_form, sr=sampling_rate))),
            "spectral_contrast": np.mean(librosa.feature.spectral_contrast(y=wave_form, sr=sampling_rate).T, axis=0),
        }
    except Exception as e:
        LOGGER.error(f"Failed when analyzing audio: {e}")
        return None

def extract_features_from_audio(wave_form, sampling_rate):
    """
    Extract a 13-dimensional MFCC mean vector from an audio waveform.
    Args:
        wave_form (np.ndarray): Audio waveform data.
    Returns:
        np.ndarray | None: 13-dimensional MFCC mean vector. None on failure.
    """
    components = extract_raw_components_from_audio(wave_form, sampling_rate)
    if components is None:
        return None
    return components["mfcc"]

def extract_features(path):
    """
    Extract a 13-dimensional MFCC mean vector from an audio file.
    Args:
        path (str): The path to the audio file.
    Returns:
        np.ndarray | None: A 13-dimensional MFCC mean vector. Returns None on failure.
    """
    wave_form, sampling_rate = load_and_standardize(path)
    if wave_form is None:
        return None

    return extract_features_from_audio(wave_form, sampling_rate)

def extract_advanced_feature_vector_from_audio(wave_form, sampling_rate):
    """
    Extract a 62-dimensional concatenated feature vector from an audio waveform.
    Args:
        wave_form (np.ndarray): Audio waveform data.
        sampling_rate (int): Audio sampling rate.
    Returns:
        np.ndarray | None: 62-dimensional concatenated feature vector. None on failure.
    """
    components = extract_raw_components_from_audio(wave_form, sampling_rate)
    if components is None:
        return None
    return np.concatenate(
        [
            components["mfcc"],
            components["mfcc_delta"],
            components["mfcc_delta2"],
            components["chroma"],
            np.array(
                [
                    components["spectral_centroid"],
                    components["zero_crossing_rate"],
                    components["spectral_rolloff"],
                    components["spectral_bandwidth"],
                ]
            ),
            components["spectral_contrast"],
        ],
        axis=0,
    )

def extract_advanced_feature_vector(path):
    """
    Extract a 62-dimensional concatenated feature vector from an audio file.
    Args:
        path (str): The path to the audio file.
    Returns:
        np.ndarray | None: A 62-dimensional concatenated feature vector. Returns None on failure.
    """
    wave_form, sampling_rate = load_and_standardize(path)
    if wave_form is None:
        return None

    return extract_advanced_feature_vector_from_audio(wave_form, sampling_rate)

def extract_advanced_features(path):
    """
    Extract a feature dictionary for detailed comparison from an audio file.
    Args:
        path (str): The path to the audio file.

    Returns:
        dict | None: A feature dictionary for comparison. Returns None on failure.
    """
    wave_form, sampling_rate = load_and_standardize(path)
    if wave_form is None:
        return None

    return extract_raw_components_from_audio(wave_form, sampling_rate)
