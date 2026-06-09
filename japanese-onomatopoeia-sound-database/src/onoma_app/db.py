import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, List
from werkzeug.security import generate_password_hash, check_password_hash

from onoma_app.authz import normalize_role
from onoma_app.config import ADVANCED_MODEL_PATH, BASE_DIR, CATEGORY_OPTIONS, DB_PATH, DEFAULT_CATEGORY, SOUNDS_DIR

DB_FILE = str(DB_PATH)
CATEGORY_LOOKUP = {category.lower(): category for category in CATEGORY_OPTIONS}

# Number of demensions.
VEC_TABLES = {
    "mfcc": 13,
    "advanced": 62,
}

try:
    import sqlite_vec  # type: ignore
    HAS_SQLITE_VEC = True
except Exception:
    HAS_SQLITE_VEC = False

def get_connection():
    """
    Generate and connect the SQLite database.
    Args: None.
    Returns:
        sqlite3.Connection: An initialized SQLite connection.
    """
    global HAS_SQLITE_VEC
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if HAS_SQLITE_VEC:
        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        except Exception:
            # Fall back to plain SQLite if extension load fails
            HAS_SQLITE_VEC = False
        finally:
            # close extension loading capability for security hardening
            conn.enable_load_extension(False)
    return conn

def init_db():
    """
    Initialize the main tables and indexes used by the application.
    Args: None.
    Returns: None.
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                sound_file TEXT NOT NULL,
                audio_hash TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );
        """)
        try:
            conn.execute("ALTER TABLE variants ADD COLUMN audio_hash TEXT;")
        except Exception:
            pass  # column already exists
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_variants_audio_hash_unique
            ON variants(audio_hash) WHERE audio_hash IS NOT NULL;
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                variant_id INTEGER NOT NULL,
                feature_type TEXT NOT NULL,
                data_json TEXT NOT NULL,
                dims INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (variant_id) REFERENCES variants(id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_features_unique
            ON features(variant_id, feature_type);
        """)

        if HAS_SQLITE_VEC:
            for name, dims in VEC_TABLES.items():
                conn.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS vec_{name}
                    USING vec0(variant_id INTEGER PRIMARY KEY, embedding FLOAT[{dims}]);
                """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT DEFAULT '',
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
        """)
        conn.executemany(
            "INSERT OR IGNORE INTO categories(name) VALUES (?);",
            [(category,) for category in CATEGORY_OPTIONS],
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                displayed INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                version_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                x REAL,
                y REAL,
                fixed INTEGER DEFAULT 0,
                PRIMARY KEY (version_id, item_id),
                FOREIGN KEY (version_id) REFERENCES graph_versions(id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                version_id INTEGER NOT NULL,
                source_item_id INTEGER NOT NULL,
                target_item_id INTEGER NOT NULL,
                similarity REAL NOT NULL,
                PRIMARY KEY (version_id, source_item_id, target_item_id),
                FOREIGN KEY (version_id) REFERENCES graph_versions(id) ON DELETE CASCADE
            );
        """)

def normalize_category(category):
    if not isinstance(category, str):
        return DEFAULT_CATEGORY

    normalized = CATEGORY_LOOKUP.get(category.strip().lower())
    if not normalized:
        raise ValueError(f"Category must be one of: {', '.join(CATEGORY_OPTIONS)}")
    return normalized

def ensure_admin_user(default_username="admin", default_password="admin"):
    """
    Make initial admin user if not exists.
    Args:
        default_username (str): Username for the bootstrap admin account.
        default_password (str): Password to set for the initial admin user.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        cur = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1;")
        if cur.fetchone():
            return
        conn.execute(
            "INSERT INTO users(username, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?);",
            (default_username, "", generate_password_hash(default_password, method="pbkdf2:sha256"), "admin", "active"),
        )

def create_user(username, email, password, role, status):
    """
    Create a new user and return the generated user ID.
    Args:
        username (str): The username for the new user.
        email (str): The email address for the new user.
        password (str): The plaintext password for the new user.
        role (str): The role name to assign to the new user.
        status (str): The initial status for the new user.
    Returns:
        int: The ID of the created user.
    """
    normalized_role = normalize_role(role)
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO users(username, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?);",
            (username, email, generate_password_hash(password, method="pbkdf2:sha256"), normalized_role, status),
        )
        return int(cur.lastrowid)

def authenticate_user(username, password):
    """
    Authenticate a user by verifying and return their account information if valid.
    Args:
        username (str): The username of the user to authenticate.
        password (str): The plaintext password provided for authentication.
    Returns:
        dict | None: A dictionary containing user information if authentication is successful, or None if it fails.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, username, email, password_hash, role, status FROM users WHERE username = ? LIMIT 1;",
            (username,),
        )

        row = cur.fetchone()
        if not row:
            return None
        
        if not check_password_hash(row["password_hash"], password):
            return None
        
        if row["status"] != "active":
            return None
        
        out = dict(row)
        out["role"] = normalize_role(out["role"])

        return out

def migrate_role_names():
    """
    Update old role names to new standardized role names.
    Args: None.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.execute("UPDATE users SET role = 'basic' WHERE lower(role) = 'standard';")
        conn.execute("UPDATE users SET role = 'researcher' WHERE lower(role) = 'research';")
        # Add displayed column to graph_versions if it doesn't exist yet (migration for existing DBs)
        try:
            conn.execute("ALTER TABLE graph_versions ADD COLUMN displayed INTEGER NOT NULL DEFAULT 0;")
        except Exception:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE variants ADD COLUMN audio_hash TEXT;")
        except Exception:
            pass  # column already exists
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_variants_audio_hash_unique
            ON variants(audio_hash) WHERE audio_hash IS NOT NULL;
        """)

def ensure_test_users():
    """
    Create demo users for testing purposes if they do not already exist.
    Args: None. This is a test utility function. We suppose users may call this function multiple times during development.
    Returns:
        None: Does not return any value.
    """
    test_users = [
        ("researcher_demo", "researcher@example.com", "research123", "researcher", "active"),
        ("admin_demo", "admin-demo@example.com", "admin123", "admin", "active"),
    ]
    with get_connection() as conn:
        for username, email, password, role, status in test_users:
            cur = conn.execute("SELECT id FROM users WHERE username = ? LIMIT 1;", (username,))
            if cur.fetchone():
                continue
            conn.execute(
                "INSERT INTO users(username, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?);",
                (username, email, generate_password_hash(password, method="pbkdf2:sha256"), role, status),
            )

def _clear_directory_files(path):
    if not path.exists():
        return
    for item in path.iterdir():
        if item.is_dir():
            _clear_directory_files(item)
            try:
                item.rmdir()
            except OSError:
                pass
        elif item.is_file():
            item.unlink()

def reset_database():
    """Delete the existing database file, uploaded sound files, and trained model."""
    db_path = Path(DB_FILE)
    if db_path.exists():
        db_path.unlink()

    _clear_directory_files(SOUNDS_DIR)

    model_path = Path(ADVANCED_MODEL_PATH)
    if model_path.exists():
        model_path.unlink()

def rebuild_database():
    """
    Rebuild the database by reinitializing the schema, migrating role names, seeding initial data from CSV if empty, and ensuring the existence of admin and test users.
    Args: None.
    Returns:
        None: Does not return any value.
    """
    init_db()
    migrate_role_names()
    from onoma_app.config import ADMIN_USERNAME, ADMIN_PASSWORD
    ensure_admin_user(
        default_username=ADMIN_USERNAME,
        default_password=ADMIN_PASSWORD,
    )
    ensure_test_users()

def seed_from_csv(csv_path) -> int:
    """
    Seed items and variants from a CSV file into an already-initialised database.
    Skips rows where the sound file is missing or the label is empty.
    Safe to call on a non-empty database — duplicate label+category pairs reuse
    the existing item row; only the variant is inserted fresh.

    Args:
        csv_path (str | Path): Absolute path to the CSV file.
            Expected columns: sound_file, label, description, category.
    Returns:
        int: Number of variants inserted.
    """
    import csv as _csv

    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    inserted = 0
    with open(csv_path, encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            label       = (row.get("label") or "").strip()
            sound_file  = (row.get("sound_file") or "").strip()
            description = (row.get("description") or "").strip()
            raw_cat     = (row.get("category") or "").strip() or DEFAULT_CATEGORY

            if not label or not sound_file:
                continue

            try:
                category = normalize_category(raw_cat)
            except ValueError:
                continue

            if find_item_by_label(label):
                continue

            add_item_with_variant(label, description, category, sound_file)
            inserted += 1

    return inserted

def list_pending_users():
    """
    Get a list of users who are currently in the pending approval state, ordered by their creation date.
    Args: None.
    Returns:
        list[dict]: A list of dictionaries, each containing information about a pending user.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, username, email, role, status, created_at FROM users WHERE status = 'pending' ORDER BY created_at ASC;"
        )
        return [dict(r) for r in cur.fetchall()]

def approve_user(user_id):
    """
    Approve a user by updating their status to 'active'.
    Args:
        user_id (int): The ID of the user to approve.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.execute("UPDATE users SET status = 'active' WHERE id = ?;", (user_id,))

def reject_user(user_id):
    """
    Reject a user by deleting their record from the database.
    Args:
        user_id (int): The ID of the user to reject.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?;", (user_id,))

def list_items():
    """
    List all registered onomatopoeia items with their basic information, ordered by their ID in ascending order.
    Args: None.
    Returns:
        list[dict]: A list of dictionaries, each containing the ID, label, description, and category of an onomatopoeia item.
    """
    with get_connection() as conn:
        cur = conn.execute("SELECT id, label, description, category FROM items ORDER BY id ASC;")
        return [dict(r) for r in cur.fetchall()]

def list_variants():
    """
    List all registered sound variants with their basic information, ordered by their ID in ascending order.
    Args: None.
    Returns:
        list[dict]: A list of dictionaries, each containing the ID, item ID, and sound file path of a sound variant.
    """
    with get_connection() as conn:
        cur = conn.execute("SELECT id, item_id, sound_file, audio_hash FROM variants ORDER BY id ASC;")
        return [dict(r) for r in cur.fetchall()]

def list_features_by_type(feature_type):
    """
    List all feature records of a specified type with their basic information, ordered by their ID in ascending order.
    Args:
        feature_type (str): The type of features to list.
    Returns:
        list[dict]: A list of dictionaries, each containing the ID, variant ID, feature data in JSON format, 
        and dimensions of a feature record that matches the specified type.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, variant_id, data_json, dims FROM features WHERE feature_type = ?;",
            (feature_type,),
        )
        return [dict(r) for r in cur.fetchall()]

def create_graph_version(name, status):
    """
    List new graph versions with their basic information, ordered by creation date in descending order.
    Args: 
        name (str): The name of the graph version to create.
        status (str): The status of the graph version to create.
    Returns:
        created graph version ID (int): The ID of the newly created graph version.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO graph_versions(name, status) VALUES (?, ?);",
            (name, status),
        )
        return int(cur.lastrowid)

def list_graph_versions():
    """
    Get a list of all saved graph versions with their basic information.
    Args: None.
    Returns:
        list[dict]: A list of graph versions.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, name, status, displayed, created_at FROM graph_versions ORDER BY created_at DESC;"
        )
        return [dict(r) for r in cur.fetchall()]

def get_latest_graph_version(status = None):
    """
    Get the latest graph version that matches the conditions.
    Args:
        status (str, optional): If specified, only consider graph versions with this status. Defaults to None.
    Returns:
        dict | None: A dictionary containing the ID, name, status, and creation date of the latest graph version that matches the conditions, 
        or None if no matching graph version is found.
    """
    with get_connection() as conn:
        if status:
            cur = conn.execute(
                "SELECT id, name, status, displayed, created_at FROM graph_versions WHERE status = ? ORDER BY created_at DESC LIMIT 1;",
                (status,),
            )
        else:
            cur = conn.execute(
                "SELECT id, name, status, displayed, created_at FROM graph_versions ORDER BY created_at DESC LIMIT 1;"
            )
        row = cur.fetchone()
        return dict(row) if row else None

def delete_graph_version(version_id):
    """
    Delete a specified graph version and all related data such as nodes and edges.
    Args:
        version_id (int): The ID of the graph version to delete.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM graph_versions WHERE id = ?;", (version_id,))

def set_graph_version_status(version_id, status):
    """
    Update the status of a specified graph version.
    Args:
        version_id (int): The ID of the graph version to update.
        status (str): The new status to set for the graph version.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.execute("UPDATE graph_versions SET status = ? WHERE id = ?;", (status, version_id))

def set_graph_version_displayed(version_id: int, displayed: bool) -> bool:
    """
    Set the displayed flag for a graph version.
    Only one version should be displayed at a time; this function clears all others first.
    Only an approved version can be set as displayed.
    Args:
        version_id (int): The ID of the graph version to display.
        displayed (bool): True to display, False to hide.
    Returns:
        bool: True if the operation succeeded, False if the version is not approved.
    """
    with get_connection() as conn:
        if displayed:
            # Only approved graphs can be displayed
            cur = conn.execute(
                "SELECT status FROM graph_versions WHERE id = ?;", (version_id,)
            )
            row = cur.fetchone()
            if not row or row["status"] != "approved":
                return False
            # Clear display flag on all other versions first
            conn.execute("UPDATE graph_versions SET displayed = 0;")
        conn.execute(
            "UPDATE graph_versions SET displayed = ? WHERE id = ?;",
            (1 if displayed else 0, version_id),
        )
    return True

def get_displayed_graph_version():
    """
    Return the currently displayed graph version (approved + displayed=1), or None.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, name, status, displayed, created_at FROM graph_versions "
            "WHERE status = 'approved' AND displayed = 1 ORDER BY created_at DESC LIMIT 1;"
        )
        row = cur.fetchone()
        return dict(row) if row else None

def insert_graph_nodes(version_id, nodes):
    """
    Register a batch of graph nodes belonging to a specified graph version.
    Args:
        version_id (int): The ID of the graph version to which the nodes belong.
        nodes (list[dict]): A list of nodes to register.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO graph_nodes(version_id, item_id, label, x, y, fixed) VALUES (?, ?, ?, ?, ?, ?);",
            [
                (
                    version_id,
                    n["item_id"],
                    n["label"],
                    n.get("x"),
                    n.get("y"),
                    1 if n.get("fixed") else 0,
                )
                for n in nodes
            ],
        )

def insert_graph_edges(version_id, edges):
    """
    Register a batch of graph edges belonging to a specified graph version.
    Args:
        version_id (int): The ID of the graph version to which the edges belong.
        edges (list[dict]): A list of edges to register.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO graph_edges(version_id, source_item_id, target_item_id, similarity) VALUES (?, ?, ?, ?);",
            [
                (version_id, e["source_item_id"], e["target_item_id"], e["similarity"])
                for e in edges
            ],
        )

def update_graph_positions(version_id, positions):
    """
    Update the node coordinates and fixed status for a specified graph version.
    Args:
        version_id (int): The ID of the graph version to update.
        positions (dict[int, dict[str, float]]): A dictionary mapping item_id to coordinate information.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.executemany(
            "UPDATE graph_nodes SET x = ?, y = ?, fixed = 1 WHERE version_id = ? AND item_id = ?;",
            [
                (p["x"], p["y"], version_id, item_id)
                for item_id, p in positions.items()
            ],
        )

def get_graph(version_id):
    """
    Get the nodes and edges for a specified graph version.

    Args:
        version_id (int): The ID of the graph version to retrieve.
    Returns:
        dict: A dictionary containing 'nodes' and 'edges' for the graph version.
        We represent a graph as ditionary.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT item_id, label, x, y, fixed FROM graph_nodes WHERE version_id = ?;",
            (version_id,),
        )

        nodes = [dict(r) for r in cur.fetchall()]
        cur = conn.execute(
            "SELECT source_item_id, target_item_id, similarity FROM graph_edges WHERE version_id = ?;",
            (version_id,),
        )

        edges = [dict(r) for r in cur.fetchall()]

    return {"nodes": nodes, "edges": edges}

def search_items(query):
    """
    Search for onomatopoeia items based on a query string that matches either the label or description, returning a list of matching items with their representative sound files.
    Args:
        query (str): The search string to match against item labels and descriptions.
    Returns:
        list[dict]: A list of dictionaries, each containing the label, description, and representative sound file for items that match the search query. The search is case-insensitive and matches partial strings
    """
    q = f"%{query.lower()}%"

    with get_connection() as conn:

        cur = conn.execute("""
            SELECT i.label, i.description, MIN(v.sound_file) AS sound_file
            FROM items i
            LEFT JOIN variants v ON v.item_id = i.id
            WHERE lower(i.label) LIKE ? OR lower(i.description) LIKE ?
            GROUP BY i.id
            ORDER BY lower(i.label) ASC;
        """, (q, q))

        return [dict(r) for r in cur.fetchall()]

def list_items_paginated(q, label, category, page, page_size):
    """
    Get a paginated list of onomatopoeia items based on optional filters for label and category, along with the total count of matching items for pagination purposes.
    Args:
        q (str): A search string to match against item labels and descriptions (optional).
        label (str): A specific label to filter items by (optional).
        category (str): A specific category to filter items by (optional).
        page (int): The page number to retrieve (1-based index).
        page_size (int): The number of items to include in each page.
    Returns:
        tuple[list[dict], int]: A tuple containing a list of dictionaries for the items on the requested page that match the filters, 
        and an integer representing the total count of items that match the filters for pagination purposes.
    """
    filters = []
    params: List = []
    if q:
        filters.append("(lower(i.label) LIKE ? OR lower(i.description) LIKE ?)")
        qlike = f"%{q.lower()}%"
        params.extend([qlike, qlike])

    if label:
        filters.append("lower(i.label) = ?")
        params.append(label.lower())

    if category:
        filters.append("lower(i.category) = ?")
        params.append(category.lower())

    where_sql = ("WHERE " + " AND ".join(filters)) if filters else ""

    with get_connection() as conn:
        cur = conn.execute(
            f"SELECT COUNT(1) AS c FROM items i {where_sql};",
            params,
        )
        total = int(cur.fetchone()["c"])

        offset = (page - 1) * page_size
        cur = conn.execute(f"""
            SELECT i.id, i.label, i.description, i.category, MIN(v.sound_file) AS sound_file
            FROM items i
            LEFT JOIN variants v ON v.item_id = i.id
            {where_sql}
            GROUP BY i.id
            ORDER BY lower(i.label) ASC
            LIMIT ? OFFSET ?;
        """, params + [page_size, offset])
        items = [dict(r) for r in cur.fetchall()]

    return items, total

def list_filters():
    """
    Get distinct labels and categories from the items in the database to be used as filter options on the browsing screen.
    Args:    None.
    Returns:    
        dict[str, list[str]]: A dictionary containing 'labels' and 'categories' as keys
    """
    with get_connection() as conn:

        cur = conn.execute("SELECT DISTINCT label FROM items WHERE label != '' ORDER BY label ASC;")
        labels = [r["label"] for r in cur.fetchall()]

    return {"labels": labels, "categories": list(CATEGORY_OPTIONS)}

def label_to_file_map():
    """
    Generate a mapping of item labels to their representative sound files for quick lookup, using the minimum sound file name as the representative for each label.
    Args: None.
    Returns:
        dict[str, str]: A dictionary where the keys are item labels and the values are the 
        corresponding representative sound file names. Only includes entries where both label and sound file are present.
    """
    with get_connection() as conn:
        cur = conn.execute("""
            SELECT i.label, MIN(v.sound_file) AS sound_file
            FROM items i
            LEFT JOIN variants v ON v.item_id = i.id
            GROUP BY i.id;
        """)
        out = {}
        for r in cur.fetchall():
            label = r["label"]
            sound_file = r["sound_file"]
            if label and sound_file and label not in out:
                out[label] = sound_file
        return out

def find_item_by_label(label):
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, label, category FROM items WHERE lower(label)=? LIMIT 1;",
            ((label or "").strip().lower(),),
        )
        row = cur.fetchone()
        return dict(row) if row else None

def find_variant_by_audio_hash(audio_hash):
    if not audio_hash:
        return None
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, item_id, sound_file, audio_hash FROM variants WHERE audio_hash = ? LIMIT 1;",
            (audio_hash,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

def add_item_with_variant(label, description, category, sound_file, audio_hash=None):
    """
    Add a new onomatopoeia item along with its corresponding sound variant in a single operation, returning the ID of the newly created variant. Labels must be unique across the database.
    Args:
        label (str): The label of the onomatopoeia item.
        description (str): A description of the onomatopoeia item.
        category (str): The category of the onomatopoeia item.
        sound_file (str): The file name of the sound variant to add.
    Returns:
        int: The ID of the newly created sound variant.
    """
    category = normalize_category(category)
    label = (label or "").strip()

    if not label:
        raise ValueError("Onomatopoeic word is required.")

    if find_item_by_label(label):
        raise ValueError(f'Onomatopoeic word "{label}" already exists.')

    if audio_hash and find_variant_by_audio_hash(audio_hash):
        raise ValueError("This audio file already exists in the database.")

    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO items(label, description, category) VALUES (?, ?, ?);",
            (label, description, category),
        )
        item_id = int(cur.lastrowid)

        cur = conn.execute(
            "INSERT INTO variants(item_id, sound_file, audio_hash) VALUES (?, ?, ?);",
            (item_id, sound_file, audio_hash),
        )

        return int(cur.lastrowid)

def add_variant(item_id, sound_file, audio_hash=None):
    """
    Add a new sound variant linked to an exisiting onomatopoeia item.
    Args:
        item_id (int): The ID of the existing onomatopoeia item to which
        the new sound variant will be linked.
        sound_file (str): The file name of the sound variant to add.
    Returns:
        int: The ID of the newly created sound variant.
    """
    if audio_hash and find_variant_by_audio_hash(audio_hash):
        raise ValueError("This audio file already exists in the database.")

    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO variants(item_id, sound_file, audio_hash) VALUES (?, ?, ?);",
            (item_id, sound_file, audio_hash),
        )
        return int(cur.lastrowid)

def delete_item(item_id):
    """
    Delete a specified onomatopoeia item.
    Args:
        item_id (int): The ID of the onomatopoeia item to delete.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM items WHERE id = ?;", (item_id,))

def delete_variant(variant_id):
    """
    Delete a specified sound variant.
    Args:
        variant_id (int): The ID of the sound variant to delete.
    Returns:
        None: Does not return any value.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM variants WHERE id = ?;", (variant_id,))

def upsert_feature(variant_id, feature_type, vector):
    """
    Update or register the feature vector for a specified sound variant and feature type.
    Args:
        variant_id (int): The ID of the sound variant to save the feature.
        feature_type (str): The type of the feature to save.
        vector (list[float]): The feature vector to save.
    Returns:
        None: Does not return any value.
    """
    data_json = json.dumps(vector)
    dims = len(vector)

    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO features(variant_id, feature_type, data_json, dims) VALUES (?, ?, ?, ?);",
            (variant_id, feature_type, data_json, dims),
        )

        if HAS_SQLITE_VEC and feature_type in VEC_TABLES and VEC_TABLES[feature_type] == dims:
            conn.execute(
                f"DELETE FROM vec_{feature_type} WHERE variant_id = ?;",
                (variant_id,),
            )
            conn.execute(
                f"INSERT INTO vec_{feature_type}(variant_id, embedding) VALUES (?, ?);",
                (variant_id, data_json),
            )

def list_sound_files_with_labels():
    """
    Retrieves all sound files and their corresponding item labels for training.
    Args: None.
    Returns:
        list[dict]: A list of dictionaries, each containing the 'sound_file' and 
        'label' for each sound variant and its associated item. This is used for training machine learning models.
    """
    with get_connection() as conn:
        cur = conn.execute("""
            SELECT v.sound_file, i.label
            FROM variants v
            JOIN items i ON i.id = v.item_id
        """)
        return [dict(r) for r in cur.fetchall()]

def backfill_advanced_features():
    """
    Extract and store advanced feature vectors for any variant that doesn't have one yet.
    This ensures phonetic search works for sounds that were seeded from CSV or added
    before feature extraction was part of the upload flow.
    Args: None.
    Returns:
        int: Number of variants that were backfilled.
    """
    from onoma_app.config import SOUNDS_DIR
    from onoma_app.utils import extract_advanced_feature_vector, LOGGER

    # Find variant IDs that already have an advanced feature vector
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT variant_id FROM features WHERE feature_type = 'advanced';"
        )
        already_done = {row["variant_id"] for row in cur.fetchall()}

    variants = list_variants()
    backfilled = 0

    for variant in variants:
        if variant["id"] in already_done:
            continue

        file_path = SOUNDS_DIR / variant["sound_file"]
        if not file_path.is_file():
            continue

        adv_vec = extract_advanced_feature_vector(str(file_path))
        if adv_vec is None:
            continue

        upsert_feature(variant["id"], "advanced", adv_vec.tolist())
        backfilled += 1

    if backfilled:
        LOGGER.info(f"Backfilled advanced feature vectors for {backfilled} variant(s).")

    return backfilled
