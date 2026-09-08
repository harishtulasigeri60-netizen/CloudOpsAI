import hashlib, hmac, secrets, sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEME = "pbkdf2_sha256"
ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"{SCHEME}${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$", 3)
        if scheme != SCHEME:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def connect_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(path: Path):
    with connect_db(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
            email TEXT PRIMARY KEY,
            failures INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT
        );
        CREATE TABLE IF NOT EXISTS aws_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            account_id TEXT NOT NULL,
            role_arn TEXT NOT NULL,
            region TEXT NOT NULL,
            topic_arn TEXT,
            bucket_name TEXT,
            status TEXT NOT NULL DEFAULT 'unverified',
            last_checked TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        cols={r[1] for r in db.execute("PRAGMA table_info(aws_connections)").fetchall()}
        if "topic_arn" not in cols: db.execute("ALTER TABLE aws_connections ADD COLUMN topic_arn TEXT")
        if "bucket_name" not in cols: db.execute("ALTER TABLE aws_connections ADD COLUMN bucket_name TEXT")


def create_user(path, name, email, password):
    with connect_db(path) as db:
        now = datetime.now(timezone.utc).isoformat()
        cur = db.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)", (name, email.lower(), hash_password(password), now))
        return cur.lastrowid


def get_user_by_email(path, email):
    with connect_db(path) as db:
        return db.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()


def get_user(path, user_id):
    with connect_db(path) as db:
        return db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def touch_login(path, user_id):
    with connect_db(path) as db:
        db.execute("UPDATE users SET last_login=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), user_id))


def save_aws_connection(path, user_id, account_id, role_arn, region, topic_arn="", bucket_name="", status="verified"):
    with connect_db(path) as db:
        now = datetime.now(timezone.utc).isoformat()
        db.execute("""INSERT INTO aws_connections(user_id,account_id,role_arn,region,topic_arn,bucket_name,status,last_checked,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET account_id=excluded.account_id,role_arn=excluded.role_arn,region=excluded.region,topic_arn=excluded.topic_arn,bucket_name=excluded.bucket_name,status=excluded.status,last_checked=excluded.last_checked""",
                   (user_id, account_id, role_arn, region, topic_arn, bucket_name, status, now, now))


def get_aws_connection(path, user_id):
    with connect_db(path) as db:
        return db.execute("SELECT * FROM aws_connections WHERE user_id=?", (user_id,)).fetchone()


def login_allowed(path, email):
    from datetime import datetime, timezone
    with connect_db(path) as db:
        row=db.execute("SELECT * FROM login_attempts WHERE email=?",(email.lower(),)).fetchone()
        if not row or not row["locked_until"]: return True
        return datetime.now(timezone.utc).isoformat() >= row["locked_until"]

def record_login_failure(path,email):
    from datetime import datetime,timedelta,timezone
    with connect_db(path) as db:
        row=db.execute("SELECT failures FROM login_attempts WHERE email=?",(email.lower(),)).fetchone(); failures=(row["failures"] if row else 0)+1
        locked=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat() if failures>=5 else None
        db.execute("INSERT INTO login_attempts(email,failures,locked_until) VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET failures=excluded.failures,locked_until=excluded.locked_until",(email.lower(),failures,locked))

def record_login_success(path,email):
    with connect_db(path) as db: db.execute("DELETE FROM login_attempts WHERE email=?",(email.lower(),))
