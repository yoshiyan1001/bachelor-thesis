import json
import os
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1]
BASE_DIR = SRC_DIR.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
MODELS_ROOT_DIR = STATIC_DIR / "models"
SOUNDS_ROOT_DIR = STATIC_DIR / "sounds"

_CONFIG_PATH = BASE_DIR / "config.json" # set up mode, admin config

def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

_CFG = _load_config()

def _cfg(key: str, env_var: str, default: str) -> str:
    """Return env var → config.json → default, in that priority order."""
    return os.environ.get(env_var) or str(_CFG.get(key) or default)

# Runtime settings resolved from env / config.json / defaults
RUNTIME_MODE = _cfg("mode", "ONOMA_MODE", "local").strip().lower()
if RUNTIME_MODE not in {"local", "test"}:
    RUNTIME_MODE = "local"

RESET_MODE = _cfg("reset_mode", "ONOMA_RESET_MODE", RUNTIME_MODE).strip().lower()

DB_PATH = Path(
    os.environ.get("ONOMA_DB_PATH")
    or str(BASE_DIR / ("annotations.test.db" if RUNTIME_MODE == "test" else "annotations.db"))
).resolve()

ADMIN_USERNAME = _cfg("admin_username", "ADMIN_BOOTSTRAP_USERNAME", "admin")
ADMIN_PASSWORD = _cfg("admin_password", "ADMIN_BOOTSTRAP_PASSWORD", "admin")
APP_PORT       = int(_cfg("port",  "FLASK_RUN_PORT", "5000"))

# Static paths
MODELS_DIR          = MODELS_ROOT_DIR / RUNTIME_MODE
SOUNDS_DIR          = SOUNDS_ROOT_DIR / RUNTIME_MODE
UPLOAD_SOUND_FOLDER = str(SOUNDS_DIR)
TEMP_UPLOAD_FOLDER  = "/tmp/onomatopoeia_uploads"
ALLOWED_EXTENSIONS  = {"mp3", "wav"}
ADVANCED_MODEL_PATH = str(MODELS_DIR / "advanced_model.pkl")
CATEGORY_OPTIONS    = ("Giongo", "Giseigo")
DEFAULT_CATEGORY    = CATEGORY_OPTIONS[0]

def ensure_directories(upload_folder):
    """
    Create necessary directories for uploads and generated files at runtime.
    Args:
        upload_folder (str): The path to the directory where temporary uploaded files will be stored.
    Returns:
        None: Does not return any value.
    """
    os.makedirs(upload_folder, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(UPLOAD_SOUND_FOLDER, exist_ok=True)
