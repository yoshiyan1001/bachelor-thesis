# Japanese Onomatopoeia Database
A Flask-based web application for collecting, browsing, annotating, and analyzing Japanese onomatopoeia sounds with machine learning and interactive visualization.
# Problem statement
Learning Japanese onomatopoeia can be challenging for language learners due to multiple factors, but particularly noteworthy is the specific system of sound symbolism of Japanese onomatopoeia. <br>
The goal of the application is to enable interactive exploration not only of onomatopoeic words in written or spoken form but also of their relation to corresponding environmental or animal sounds. I implemented audio feature extraction functions, such as MFCC,[^1] and a similarity-network visualization feature of environmental or animal sounds, to examine trends in the onomatopoeic words people assign to the same or similar environmental or animal sounds. By this method, it is possible to quantitatively clarify which acoustic parameters recall these expressions based on actual sound data.

## Overview

This project combines:

- a browsable onomatopoeia sound database
- prediction of onomatopoeia labels from uploaded audio
- phonetic similarity search
- advanced audio feature comparison
- graph-based similarity visualization
- audio augmentation for dataset expansion
- user type based access control for users

The current user types are:

- **Basic** (basic user): can browse the onomatopoeic-word dataset, predict onomatopoeic words from audio, and use voice-based similarity search.
- **Researcher**: in addition to the basic functions, can use comparative analysis of acoustic characteristics and network visualization of similarity relationships. Researcher accounts must be approved by an Admin.
- **Admin** (administrator): can use all functions; in addition, can register new audio data, train the model, approve researcher accounts, and build and save similarity graphs.
## Japanese onomatopoeic words
Japanese onomatopoeic words are classified into Giongo and Gitaigo. 
- Giongo: words used to imitate sounds found in nature or everyday noises and the voices of animals and humans.
- Gitaigo: words that use sound to describe a state of silence, an emotion, or a situation. 

In this application, we train the model and predict a Japanese onomatopoeic word from audio file. So, we focus on **Giongo** in this project.

Giongo can be classified into Giongo and Giseigo.
Annotation categories are:

- `Giongo`: represents human or animal voices.
- `Giseigo`: represents environmental sounds or noise.

## Project Structure

```text
japanese-onomatopoeia-sound-database/
    ├── README.md
    ├── config.json
    ├── config.json.example
    ├── docs
    │   ├── developer-documentation.md
    │   ├── detailed_specification.md
    │   ├── imgs
    │   │   ├── augmentation_page.png
    │   │   ├── browse_page.png
    │   │   ├── comparison_page.png
    │   │   ├── home_page.png
    │   │   └── similarity_graph_page.png
    │   └── user-documentation.md
    ├── requirements.txt
    ├── sample_audio_dataset
    │   ├── sample_audio
    │   │   ├── OtoLogic_ding.mp3
    │   │   ├── OtoLogic_dizzy.mp3
    │   │   ├── OtoLogic_impact.mp3
    │   │   ├── OtoLogic_mosquito.mp3
    │   │   ├── OtoLogic_rain3.mp3
    │   │   ├── OtoLogic_thunder1.mp3
    │   │   └── OtoLogic_wind1.mp3
    │   └── sample_audio.csv
    ├── src
    │   ├── app.py
    │   └── onoma_app
    │       ├── __init__.py
    │       ├── authz.py
    │       ├── config.py
    │       ├── db.py
    │       ├── routes
    │       │   ├── __init__.py
    │       │   ├── admin.py
    │       │   ├── auth.py
    │       │   ├── catalog.py
    │       │   ├── graph.py
    │       │   └── ml.py
    │       ├── services
    │       │   ├── __init__.py
    │       │   ├── audio_processing.py
    │       │   ├── graph_service.py
    │       │   └── ml_service.py
    │       ├── train.py
    │       └── utils.py
    ├── start.sh
    ├── static
    │   ├── css
    │   │   ├── admin_approvals.css
    │   │   ├── app.css
    │   │   ├── audio_augmentation.css
    │   │   ├── browse.css
    │   │   ├── feature_comparison.css
    │   │   ├── index.css
    │   │   ├── phonetic_search.css
    │   │   └── similarity_explorer.css
    │   ├── icon.png
    │   └── js
    │       ├── audio-augmentation.js
    │       ├── browse.js
    │       ├── feature-comparison.js
    │       ├── phonetic-search.js
    │       ├── scripts.js
    │       ├── similarity-explorer.js
    │       └── wavesurfer.min.js
    ├── templates
    │   ├── admin_approvals.html
    │   ├── audio_augmentation.html
    │   ├── browse.html
    │   ├── feature_comparison.html
    │   ├── index.html
    │   ├── login.html
    │   ├── phonetic_search.html
    │   ├── register.html
    │   └── similarity_explorer.html
    └── test_dataset
        ├── test_audio
        │   ├── OtoLogic_bird.mp3
        │   ├── OtoLogic_cat.mp3
        │   ├── OtoLogic_cow.mp3
        │   ├── OtoLogic_crow.mp3
        │   ├── OtoLogic_mouse.mp3
        │   ├── OtoLogic_police.mp3
        │   ├── OtoLogic_pop.mp3
        │   ├── OtoLogic_pop4.mp3
        │   ├── OtoLogic_rain.mp3
        │   ├── OtoLogic_thunder.mp3
        │   └── OtoLogic_wind.mp3
        └── test_dataset.csv
```

## Requirements

- Python 3.10+
- pip

Please make sure that your current working directory is in `japanese-onomatopoeia-sound-database`. If not, then:
```
cd japanese-onomatopoeia-sound-database
```

Install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run the Application
Your current working directory should be in `japanese-onomatopoeia-sound-database`.
### Test Case 
If we want to try the test case, the test dataset is prepared in `test_dataset` folder. 
To start this test case application:

1. Set up `mode:test` in `config.json`. 
2. Set `reset_mode` when you want `start.sh` to reset a specific runtime storage.
2. Please change `"admin_username"` and `"admin_password"` values for your admin account. 
For example:
```
{
  "mode": "test",
  "reset_mode": "N/A",
  "port": 5000,
  "admin_username": "admin",
  "admin_password": "admin"
}
```
3. Run bash script `start.sh`
```
./start.sh
```
You will see the logs on the terminal such as:
```
./start.sh
Test database found. Skipping initialization...

Mode     : test
Database : /Users/yoshi/Desktop/Attachments 3/japanese-onomatopoeia-sound-database/annotations.test.db
Port     : 5000
Open     : http://localhost:5000

 * Serving Flask app 'app'
 * Debug mode: on
2026-05-05 21:56:02,294 INFO [werkzeug] WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:5000
2026-05-05 21:56:02,294 INFO [werkzeug] Press CTRL+C to quit
2026-05-05 21:56:02,295 INFO [werkzeug]  * Restarting with stat
2026-05-05 21:56:03,552 WARNING [werkzeug]  * Debugger is active!
2026-05-05 21:56:03,578 INFO [werkzeug]  * Debugger PIN: 407-057-638
```
4. Open the generated url on web browser: `http://127.0.0.1:5000`

5. If you want to stop running, `CTRL+C` on the terminal. If you want to restart, then again run `./start.sh` on the terminal.
6. If you want to try to use some functions with audio, sample annotated audio dataset is available in `/sample_audio_dataset`.
### Local Case
For local usage, switch `mode` to `local` in `config.json`.
For example:
```
{
  "mode": "local",
  "reset_mode": "N/A",
  "port": 5000,
  "admin_username": "admin",
  "admin_password": "admin"
}
```

and run the bash file:

```bash
./start.sh
```

#### Note
The test case uses `annotations.test.db`, `static/sounds/test`, and `static/models/test`.
The local case uses `annotations.db`, `static/sounds/local`, and `static/models/local`.

## Database Initialization

On first run, the application automatically:

- creates the mode-specific database file if it does not exist
- creates the bootstrap `admin` account

## Reset this application
Once we reset the application, it deletes test database, all audio files, and the trained model.
### Reset test case
To reset test case application, we set up `"reset"` at `"mode"` and `"test"` at `"reset_mode"` in `config.json`:
```
{
  "mode": "reset",
  "reset_mode": "test",
  "port": 5000,
  "admin_username": "admin",
  "admin_password": "admin"
}
```
### Reset local case
To reset test case application, we set up `"reset"` at `"mode"` and `"local"` at `"reset_mode"` in `config.json`:
```
{
  "mode": "reset",
  "reset_mode": "local",
  "port": 5000,
  "admin_username": "admin",
  "admin_password": "admin"
}
```
After setup `config.json`, then run `start.sh`:
```
./start.sh
```
## Detailed specification
More details of user and developer documentations are written in `docs` directory.

[^1]: https://en.wikipedia.org/wiki/Mel-frequency_cepstrum
