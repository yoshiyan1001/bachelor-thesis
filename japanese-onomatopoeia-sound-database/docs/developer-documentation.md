# Developer Documentation
This documentation describes technical details of the internal system, system requirements, main algorithms, and data structures of the web application called the Japanese Onomatopoeia Database. The system is a Flask-based web application focusing on a Japanese onomatopoeic-word audio database. It supports audio data accumulation, annotation, acoustic analysis, machine-learning-based prediction, data augmentation, and visualization of similarity relationships between onomatopoeic words in a single environment (i.e., not merely a dictionary-style application).

## Implementation Overview

The back end of this system is implemented in Python and uses Flask as the web framework. For front-end development, HTML, CSS, and JavaScript are used. To render templates, Flask's `render_template()` is used. The database is implemented using SQLite. For audio processing, the system uses `librosa` and `soundfile`. For numerical computation, it uses `numpy`, `pandas`, `scikit-learn`, and `scipy`. For graph visualization on the front end, `Three.js` is used, and `WaveSurfer.js` is used to visualize audio waveforms.

## Core Features

This system provides the following features:

- Annotation: Admin users upload audio files and assign an onomatopoeic word (label), description, and category.
- Browse: Users browse database entries with pagination and filtering.
- Prediction: The ML model predicts the most likely onomatopoeic word for an uploaded audio file.
- Phonetic Search: Calculates cosine similarity between the MFCC features of an input audio file and audio files stored in the database, then returns the top three results.
- Feature Comparison: Shows a similarity score between two audio files based on multiple weighted acoustic features, along with each feature's contribution.
- Audio Augmentation: Automatically generates augmented audio data using pitch shifting, time stretching, noise injection, and volume adjustment.
- Model Training: Retrains a Random Forest model using the accumulated database.

## How to Build and Run the Program

Since this system is implemented in a scripting language, no compilation is required, but developers must install Python dependencies. A recommended setup is as follows:

1. Create a Python 3 virtual environment.
2. Install dependency packages from `requirements.txt`.

The example commands are:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
There are three modes in total: two modes to initialize the application in **test** and **local** modes, and one mode to **reset** its application. Once we perform a reset mode, this system deletes the database, sounds, and the trained model files that the chosen mode (test or local mode) belongs to.  The mode, admin username, and admin password are set in `config.json`.

- **Test Mode**  
  Test mode initializes the database with sample items so developers can quickly verify the application. Set `"mode": "test"` and configure `"admin_username"` and `"admin_password"` in `config.json`. For example:

```json
{
  "mode": "test",
  "reset_mode": "N/A",
  "port": 5000,
  "admin_username": "admin",
  "admin_password": "admin"
}
```
Then run `start.sh`:
```bash
./start.sh
```
Finally, open the URL in a web browser: `http://127.0.0.1:5000`
The test database is initially built with ten onomatopoeic-word items and their audio files.
- **Local Mode** <br>
Local mode initializes an empty database with only the admin account configured in `config.json`. Set `"mode": "local"`. For example:
```json
{
  "mode": "local",
  "reset_mode": "N/A",
  "port": 5000,
  "admin_username": "admin",
  "admin_password": "admin"
}
```
Then run `start.sh` and open the URL as in test mode.  
- **Reset the application** <br>
To reset the application, set `"mode": "reset"` and specify the reset target using `"reset_mode"` (e.g., `"test"` or `"local"`). For example:
```json
{
  "mode": "reset",
  "reset_mode": "test",
  "port": 5000,
  "admin_username": "admin",
  "admin_password": "admin"
}
```
To stop the server, use `CTRL+C` in the terminal. To restart it, run `./start.sh` again.

## Architecture and Technology Stack

### Development Environment

The expected operating systems are macOS, Windows, or Linux environments. To execute this project, Python 3 is necessary, and it is desirable to use relatively new versions (Python 3.10 or higher) due to dependency libraries (especially `librosa` and `scikit-learn`). For the development tool, a basic Python environment is enough to develop, such as VS Code.

### Directory Structure and Module Dependencies

The source code is mainly under the `src/` directory, and following the Flask application factory pattern, `app.py` is an entry point. As a data access layer, `db.py` manages SQLite queries. Business logic is divided into (`services/` directory: `audio_processing.py`, `graph_service.py`, `ml_service.py`). Because of this, this project uses a similar configuration to MVC[^1] architecture that helps the routing layer (`routes/`) to maintain the source code.
## Data Structures

The main data structures are (i) the relational table structure in SQLite and (ii) an in-memory feature-vector graph structure.

- `items`: represents onomatopoeic-word concepts, including label (onomatopoeic word), description, and category.
- `variants`: represents an audio file corresponding to each `item`. This allows one onomatopoeic word to be mapped to multiple audio files.
- `features`: stores extracted acoustic feature vectors in a JSON-like format.
- `users`: stores account information for authentication and manages access permissions and approval status using `role` and `status`.
- `graph_versions`, `graph_nodes`, `graph_edges`: tables for storing similarity network graphs.

## Non-trivial Algorithms

This section describes audio processing, the ML algorithm, and the graph construction algorithm.

- **$62$-dimensional Advanced Acoustic Feature Vectors**  
  For ML training and graph construction, the system uses the following $62$-dimensional feature vectors:

  - Dimensions $1$-$13$: MFCC mean (timbre and spectral envelope)
  - Dimensions $13$-$26$: MFCC delta mean (rate of change in timbre over time)
  - Dimensions $27$-$39$: MFCC delta-delta mean (rate of change in timbre)
  - Dimensions $40$-$51$: chroma mean (harmonic structure and pitch classes)
  - Dimensions $52$-$55$: spectral centroid (brightness), zero-crossing rate (noise), spectral rolloff, and spectral bandwidth
  - Dimensions $56$-$62$: spectral contrast (roughness and texture of sound)

- **Onomatopoeic Word Prediction and Model Training**  
  In the prediction process, we extract $62$-dimensional high-level feature vectors from the input audio. We feed the extracted vectors into a trained classifier (`RandomForestClassifier`). We choose this classifier instead of deep learning approaches for the following reasons:

  - **Resilience and robustness with small datasets**  
    Collecting annotated Japanese onomatopoeic-word audio is costly; therefore, bagging helps reduce overfitting when training on limited datasets.
  - **Scale invariance**  
    Tree-based models work without prior normalization even when features with different units and scales are mixed, as in the $62$-dimensional vectors described above.
  - **Interpretability**  
    The model can output feature importance, which supports future analysis.

During training, the system reads all audio files and labels (onomatopoeic words) from the database and extracts $62$-dimensional vectors. It then splits the dataset into training ($80\%$) and test ($20\%$) sets using a stratified split rather than a purely random split.  
A stratified split maintains the class proportions of the original dataset in both the training and test sets. This is important because sample sizes can be uneven across categories (Giongo and Giseigo). Stratification reduces the risk that minority classes are missing from the test set and enables a more reliable evaluation across all classes.  
After evaluation, the trained model is saved in the `static/models/<mode>/` directory. During prediction, the system decodes the input audio file, extracts features, and performs classification.

- **Phonetic Similarity Search**  
  For phonetic similarity search, the system computes the $62$-dimensional vector of the input audio and then calculates cosine similarity to vectors stored in the database. It returns the top three items.

- **Feature Comparison**  
  The feature comparison function extracts multiple features from two audio files. Cosine similarity is used for array features (such as MFCCs), whereas a similarity function based on relative differences is used for scalar features. A pre-defined weight is applied to each feature, and overall similarity is computed as a weighted average.

- **Similarity Graph Construction**

  1. **Item-level aggregation**  
     The system averages feature vectors from multiple recordings (variants) that belong to the same label (onomatopoeic word) to produce one representative vector. This smooths recording noise and ensures that each node represents one onomatopoeic word rather than an individual recording.

  2. **Dynamic PCA projection**  
     The system computes cosine similarity between representative vectors and connects an edge between nodes when appropriate. Node coordinates are computed dynamically using PCA[^2] based on SVD[^3] at each UI render. Although the number of items may be smaller than the feature dimensionality, SVD provides a numerically stable projection. The system also computes which acoustic features contribute strongly to the projected principal components (PC1-PC3) and presents axis interpretations to the user.

- **Audio Augmentation**  
  In the audio augmentation process, pitch shifting, time stretching, noise injection, and volume changes are applied to a single audio file to generate derived audio data.

### Sample Audio Dataset
If you want to try to use some functions with audio, a sample annotated audio dataset is available in `/sample_audio_dataset`.


### Future Possible Work: Fixed Train/Test Splits
Currently, the system performs a random stratified split for each training session. While this approach works well for initial development, it may be beneficial to implement a fixed train/test split for long-term development. Using a consistent test set across multiple training iterations enables more reliable debugging and model finetuning, especially when incrementally adding new training data. This would allow developers to track performance changes more accurately and ensure that improvements are genuine rather than artifacts of different test set compositions.

[^1]: https://en.wikipedia.org/wiki/Model%2Dview%2Dcontroller
[^2]: https://en.wikipedia.org/wiki/Principal_component_analysis  
[^3]: https://en.wikipedia.org/wiki/Singular_value_decomposition  
