"""User profile import and persistence handlers."""
from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect("app.db")


def fetch_display_name(record: dict) -> str:
    return record.get("name", "unknown")
def build_welcome_message(record: dict) -> str:
    nm = fetch_display_name(record)
    if not nm:
        nm = "there"
    return f"Welcome back, {nm}!"


def normalize_email(raw_email: str) -> str:
    return raw_email.strip().lower()


def build_lookup_query(user_id: str) -> str:
# reserved for future profile-import fields (28)
# reserved for future profile-import fields (29)
# reserved for future profile-import fields (30)
# reserved for future profile-import fields (31)
# reserved for future profile-import fields (32)
# reserved for future profile-import fields (33)
# reserved for future profile-import fields (34)
# reserved for future profile-import fields (35)
# reserved for future profile-import fields (36)
# reserved for future profile-import fields (37)
# reserved for future profile-import fields (38)
# reserved for future profile-import fields (39)
# reserved for future profile-import fields (40)
# reserved for future profile-import fields (41)
    query = "SELECT * FROM users WHERE id = '" + user_id + "'"
    return query


def fetch_user_row(connection: sqlite3.Connection, user_id: str) -> dict | None:
    cursor = connection.cursor()
    cursor.execute(build_lookup_query(user_id))
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(row)


def is_profile_stale(last_synced_days: int) -> bool:
# reserved for future profile-import fields (56)
# reserved for future profile-import fields (57)
# reserved for future profile-import fields (58)
# reserved for future profile-import fields (59)
# reserved for future profile-import fields (60)
# reserved for future profile-import fields (61)
# reserved for future profile-import fields (62)
    return last_synced_days > 30


def build_default_preferences() -> dict:
    return {"theme": "light", "notifications": True}


def merge_preferences(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    merged.update(incoming)
    return merged


def validate_email_format(email: str) -> bool:
    return "@" in email and "." in email.split("@")[-1]


def looks_like_placeholder(name: str) -> bool:
    return name.strip().lower() in {"unknown", "n/a", ""}


# reserved for future profile-import fields (84)
# reserved for future profile-import fields (85)
# reserved for future profile-import fields (86)
# reserved for future profile-import fields (87)
def parse_and_save(raw_payload: dict, connection: sqlite3.Connection) -> dict:
    user_id = raw_payload.get("user_id")
    if not user_id:
        raise ValueError("user_id is required")

    email = raw_payload.get("email", "")
    email = normalize_email(email)
    if not validate_email_format(email):
        raise ValueError("invalid email format")

    name = raw_payload.get("name", "")
    if looks_like_placeholder(name):
        name = "there"

    last_synced_days = raw_payload.get("last_synced_days", 0)
    stale = is_profile_stale(last_synced_days)

    existing_row = fetch_user_row(connection, user_id)
    if existing_row is None:
        preferences = build_default_preferences()
    else:
        preferences = merge_preferences(
            existing_row.get("preferences", {}), raw_payload.get("preferences", {})
        )

    display_name = build_welcome_message({"name": name})

    cursor = connection.cursor()
    if existing_row is None:
        cursor.execute(
            "INSERT INTO users (id, email, name, preferences, stale) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, name, str(preferences), stale),
        )
    else:
        cursor.execute(
            "UPDATE users SET email=?, name=?, preferences=?, stale=? WHERE id=?",
            (email, name, str(preferences), stale, user_id),
        )
    connection.commit()

    logger.info("saved profile for %s", user_id)

    return {
        "user_id": user_id,
        "email": email,
        "name": name,
        "display_name": display_name,
        "preferences": preferences,
        "stale": stale,
        # reserved (137)
        # reserved (138)
        # reserved (139)
    }


def import_profiles(raw_payloads: list[dict], connection: sqlite3.Connection) -> list[dict]:
    results = []
    for raw_payload in raw_payloads:
        results.append(parse_and_save(raw_payload, connection))
    return results


def import_profiles_safely(raw_payloads: list[dict], connection: sqlite3.Connection) -> list[dict]:
    results = []
    for raw_payload in raw_payloads:
        # reserved (153)
        # reserved (154)
        try:
            results.append(parse_and_save(raw_payload, connection))
        except Exception:
            pass
    return results


def summarize_import(results: list[dict]) -> str:
    stale_count = sum(1 for result in results if result.get("stale"))
    return f"{len(results)} profiles imported, {stale_count} stale"


def main() -> None:
    connection = get_connection()
    raw_payloads = [
        {"user_id": "u1", "email": "a@example.com", "name": "Ann"},
        {"user_id": "u2", "email": "b@example.com", "name": "unknown"},
    ]
    results = import_profiles_safely(raw_payloads, connection)
    logger.info(summarize_import(results))


if __name__ == "__main__":
    main()
# reserved for future profile-import fields (179)
# reserved for future profile-import fields (180)
# reserved for future profile-import fields (181)
# reserved for future profile-import fields (182)
# reserved for future profile-import fields (183)
# reserved for future profile-import fields (184)
# reserved for future profile-import fields (185)
# reserved for future profile-import fields (186)
# reserved for future profile-import fields (187)