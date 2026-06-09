#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/venv/bin/python3}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

CONFIG="$ROOT_DIR/config.json"
if [ ! -f "$CONFIG" ]; then
  echo "Error: config.json not found."
  echo "Copy config.json.example → config.json and fill in your settings."
  exit 1
fi

cfg() {
  local key="$1"
  local default="$2"
  "$PYTHON_BIN" - <<EOF
import json
try:
    with open("$CONFIG", encoding="utf-8") as f:
        v = json.load(f).get("$key")
    print(v if v is not None else "$default")
except Exception:
    print("$default")
EOF
}

MODE="$(cfg mode local)"
RESET_MODE="$(cfg reset_mode "$MODE")"
PORT="$(cfg port 5000)"
export FLASK_RUN_PORT="$PORT"
export ONOMA_MODE="${ONOMA_MODE:-$MODE}"

TEST_DB="$ROOT_DIR/annotations.test.db"
LOCAL_DB="$ROOT_DIR/annotations.db"

reset_runtime_mode() {
  local target_mode="$1"
  echo "=== RESET (${target_mode}) ==="
  ONOMA_MODE="$target_mode" "$PYTHON_BIN" - <<EOF
import sys
sys.path.insert(0, "$ROOT_DIR/src")
from onoma_app import db
db.reset_database()
EOF
}

# reset
if [ "$MODE" = "reset" ]; then
  case "$RESET_MODE" in
    local|test)
      reset_runtime_mode "$RESET_MODE"
      ;;
    all)
      reset_runtime_mode "local"
      reset_runtime_mode "test"
      ;;
    *)
      echo "Unknown reset_mode: '$RESET_MODE'"
      echo "Set reset_mode to \"local\", \"test\", or \"all\" in config.json."
      exit 1
      ;;
  esac

  echo "=== Reset complete. Exiting without starting app. ==="
  exit 0
fi

# test mode
if [ "$MODE" = "test" ]; then
  export ONOMA_DB_PATH="${ONOMA_DB_PATH:-$TEST_DB}"
  export ONOMA_MODE="test"
  TEST_SOUNDS_DIR="$ROOT_DIR/static/sounds/test"

  if [ -f "$ONOMA_DB_PATH" ]; then
    echo "Test database found. Skipping initialization..."
  else
    echo "Test database not found. Initializing from test_dataset..."
    
    SOURCE_DIR="$ROOT_DIR/test_dataset/test_audio"
    mkdir -p "$TEST_SOUNDS_DIR"
    find "$SOURCE_DIR" -maxdepth 1 -type f -exec cp -v {} "$TEST_SOUNDS_DIR/" \;

    "$PYTHON_BIN" - <<EOF
import sys
sys.path.insert(0, "$ROOT_DIR/src")
from onoma_app import db
db.rebuild_database()
n = db.seed_from_csv("$ROOT_DIR/test_dataset/test_dataset.csv")
print(f"Seeded {n} variants from test_dataset.csv")
EOF
  fi

  echo -e "\nMode     : test\nDatabase : $ONOMA_DB_PATH\nPort     : $PORT\nOpen     : http://localhost:${PORT}\n"
  "$PYTHON_BIN" "$ROOT_DIR/src/app.py"

# local mode
elif [ "$MODE" = "local" ]; then
  export ONOMA_DB_PATH="${ONOMA_DB_PATH:-$LOCAL_DB}"
  export ONOMA_MODE="local"

  echo -e "\nMode     : local\nDatabase : $ONOMA_DB_PATH\nPort     : $PORT\nOpen     : http://localhost:${PORT}\n"
  "$PYTHON_BIN" "$ROOT_DIR/src/app.py"

else
  echo "Unknown mode: '$MODE'"
  echo "Set mode to \"test\", \"local\", or \"reset\" in config.json."
  exit 1
fi
