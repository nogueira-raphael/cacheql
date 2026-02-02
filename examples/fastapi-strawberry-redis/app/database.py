"""SQLite database for demonstration purposes."""

import asyncio
from datetime import datetime
from pathlib import Path

import aiosqlite

DB_PATH = Path(__file__).parent.parent / "data" / "app.db"

call_count: dict[str, int] = {
    "get_users": 0,
    "get_user": 0,
    "get_posts": 0,
    "get_post": 0,
    "get_user_posts": 0,
}

CURRENT_USER_ID = "1"


def reset_call_count() -> None:
    """Reset the call counter."""
    for key in call_count:
        call_count[key] = 0


async def get_db() -> aiosqlite.Connection:
    """Get database connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    """Initialize the database with tables and sample data."""
    db = await get_db()
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                secret_note TEXT,
                is_public_profile INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                author_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (author_id) REFERENCES users(id)
            )
        """)

        cursor = await db.execute("SELECT COUNT(*) FROM users")
        count = (await cursor.fetchone())[0]

        if count == 0:
            users = [
                (
                    "1", "Alice", "alice@example.com",
                    "Alice's secret note", 1, "2024-01-15T10:00:00Z"
                ),
                (
                    "2", "Bob", "bob@example.com",
                    "Bob's private thoughts", 0, "2024-02-20T14:30:00Z"
                ),
                (
                    "3", "Charlie", "charlie@example.com",
                    None, 1, "2024-03-10T09:15:00Z"
                ),
            ]
            await db.executemany(
                """INSERT INTO users
                   (id, name, email, secret_note, is_public_profile, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                users
            )

            posts = [
                (
                    "101", "Introduction to GraphQL Caching",
                    "GraphQL caching is essential for performance...",
                    "1", "2024-03-01T12:00:00Z"
                ),
                (
                    "102", "Apollo Cache Control Explained",
                    "The @cacheControl directive allows fine-grained control...",
                    "1", "2024-03-05T15:30:00Z"
                ),
                (
                    "103", "Redis as a Cache Backend",
                    "Redis provides excellent performance for distributed caching...",
                    "2", "2024-03-10T09:00:00Z"
                ),
                (
                    "104", "Best Practices for API Caching",
                    "When implementing caching, consider TTL, invalidation...",
                    "3", "2024-03-15T11:45:00Z"
                ),
            ]
            await db.executemany(
                """INSERT INTO posts (id, title, content, author_id, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                posts
            )

            await db.commit()
            print("[DB] Database initialized with sample data")
    finally:
        await db.close()


def _row_to_user(row: aiosqlite.Row) -> dict:
    """Convert a database row to a user dict."""
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "secret_note": row["secret_note"],
        "is_public_profile": bool(row["is_public_profile"]),
        "created_at": row["created_at"],
    }


def _row_to_post(row: aiosqlite.Row) -> dict:
    """Convert a database row to a post dict."""
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "author_id": row["author_id"],
        "created_at": row["created_at"],
    }


async def simulate_latency(ms: int = 100) -> None:
    """Simulate database latency."""
    await asyncio.sleep(ms / 1000)


async def get_users() -> list[dict]:
    """Get all users."""
    call_count["get_users"] += 1
    print(f"[DB] get_users called (total: {call_count['get_users']})")
    await simulate_latency(50)

    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users")
        rows = await cursor.fetchall()
        return [_row_to_user(row) for row in rows]
    finally:
        await db.close()


async def get_user(user_id: str) -> dict | None:
    """Get a user by ID."""
    call_count["get_user"] += 1
    print(f"[DB] get_user({user_id}) called (total: {call_count['get_user']})")
    await simulate_latency(30)

    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return _row_to_user(row) if row else None
    finally:
        await db.close()


async def get_current_user() -> dict | None:
    """Get the currently authenticated user."""
    return await get_user(CURRENT_USER_ID)


async def get_posts() -> list[dict]:
    """Get all posts."""
    call_count["get_posts"] += 1
    print(f"[DB] get_posts called (total: {call_count['get_posts']})")
    await simulate_latency(50)

    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM posts")
        rows = await cursor.fetchall()
        return [_row_to_post(row) for row in rows]
    finally:
        await db.close()


async def get_post(post_id: str) -> dict | None:
    """Get a post by ID."""
    call_count["get_post"] += 1
    print(f"[DB] get_post({post_id}) called (total: {call_count['get_post']})")
    await simulate_latency(30)

    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = await cursor.fetchone()
        return _row_to_post(row) if row else None
    finally:
        await db.close()


async def get_user_posts(user_id: str) -> list[dict]:
    """Get all posts by a user."""
    call_count["get_user_posts"] += 1
    total = call_count['get_user_posts']
    print(f"[DB] get_user_posts({user_id}) called (total: {total})")
    await simulate_latency(40)

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM posts WHERE author_id = ?", (user_id,)
        )
        rows = await cursor.fetchall()
        return [_row_to_post(row) for row in rows]
    finally:
        await db.close()


async def update_user(user_id: str, **kwargs) -> dict | None:
    """Update a user."""
    print(f"[DB] update_user({user_id}, {kwargs})")

    db = await get_db()
    try:
        updates = []
        values = []
        for key, value in kwargs.items():
            if value is not None:
                updates.append(f"{key} = ?")
                values.append(value)

        if not updates:
            return await get_user(user_id)

        values.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        await db.execute(query, values)
        await db.commit()

        return await get_user(user_id)
    finally:
        await db.close()


async def create_post(title: str, content: str, author_id: str) -> dict:
    """Create a new post."""
    print(f"[DB] create_post(title={title}, author_id={author_id})")

    db = await get_db()
    try:
        cursor = await db.execute("SELECT MAX(CAST(id AS INTEGER)) FROM posts")
        max_id = (await cursor.fetchone())[0] or 0
        post_id = str(max_id + 1)

        created_at = datetime.utcnow().isoformat() + "Z"

        await db.execute(
            """INSERT INTO posts (id, title, content, author_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (post_id, title, content, author_id, created_at)
        )
        await db.commit()

        return {
            "id": post_id,
            "title": title,
            "content": content,
            "author_id": author_id,
            "created_at": created_at,
        }
    finally:
        await db.close()


async def delete_post(post_id: str) -> bool:
    """Delete a post."""
    print(f"[DB] delete_post({post_id})")

    db = await get_db()
    try:
        cursor = await db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
