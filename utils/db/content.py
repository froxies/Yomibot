import aiosqlite
import json
import time
from datetime import datetime
from typing import Any

from .core import DB_FILE, logger


def _now_ts_str() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


async def add_chat_history(user_id: str, role: str, content: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "INSERT INTO user_chat_history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, role, content, _now_ts_str()),
            )
            await conn.execute(
                """
                DELETE FROM user_chat_history
                WHERE id NOT IN (
                    SELECT id FROM user_chat_history WHERE user_id = ? ORDER BY id DESC LIMIT 50
                ) AND user_id = ?
                """,
                (user_id, user_id),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_chat_history: {e}")


async def get_chat_history(user_id: str, limit: int = 30) -> list[tuple[str, str]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                """
                SELECT role, content
                FROM user_chat_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, int(limit)),
            ) as cur:
                rows = await cur.fetchall()
                return [(str(r[0]), str(r[1])) for r in rows][::-1]
    except Exception as e:
        logger.error(f"get_chat_history: {e}")
        return []


async def get_recent_global_chat(limit: int = 30) -> list[dict[str, Any]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT user_id, content, timestamp
                FROM user_chat_history
                WHERE role = 'user'
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows][::-1]
    except Exception as e:
        logger.error(f"get_recent_global_chat: {e}")
        return []


async def add_memory(user_id: str, mem_type: str, content: str, limit: int = 50):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "INSERT INTO memories (user_id, mem_type, content, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, mem_type, content, time.time()),
            )
            await conn.execute(
                """
                DELETE FROM memories
                WHERE id NOT IN (
                    SELECT id FROM memories WHERE user_id = ? ORDER BY id DESC LIMIT ?
                ) AND user_id = ?
                """,
                (user_id, int(limit), user_id),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_memory: {e}")


async def get_memories(user_id: str, limit: int = 50) -> list[tuple[Any, ...]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT id, content FROM memories WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, int(limit)),
            ) as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error(f"get_memories: {e}")
        return []


async def get_memories_detail(user_id: str, limit: int = 10) -> list[tuple[Any, ...]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT id, mem_type, content, timestamp FROM memories WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, int(limit)),
            ) as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error(f"get_memories_detail: {e}")
        return []


async def delete_memory(user_id: str, memory_id: int) -> bool:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            cur = await conn.execute(
                "DELETE FROM memories WHERE user_id = ? AND id = ?",
                (user_id, int(memory_id)),
            )
            await conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"delete_memory: {e}")
        return False


async def delete_memory_by_content(user_id: str, content_substr: str) -> bool:
    try:
        needle = f"%{content_substr}%"
        async with aiosqlite.connect(DB_FILE) as conn:
            cur = await conn.execute(
                "DELETE FROM memories WHERE user_id = ? AND content LIKE ?",
                (user_id, needle),
            )
            await conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"delete_memory_by_content: {e}")
        return False


async def get_stats_summary() -> dict[str, Any]:
    stats: dict[str, Any] = {"top_winner": None, "total_affinity": 0, "total_interactions": 0}
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT user_id, best_win FROM game_stats ORDER BY best_win DESC LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
                if row:
                    stats["top_winner"] = (row[0], row[1])
            async with conn.execute("SELECT SUM(affinity) FROM users") as cur:
                row = await cur.fetchone()
                stats["total_affinity"] = int(row[0]) if row and row[0] is not None else 0
            async with conn.execute("SELECT COUNT(*) FROM user_chat_history") as cur:
                row = await cur.fetchone()
                stats["total_interactions"] = int(row[0]) if row and row[0] is not None else 0
    except Exception as e:
        logger.error(f"get_stats_summary: {e}")
    return stats


async def get_dungeon_run(user_id: str) -> dict[str, Any] | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT data FROM user_dungeon_runs WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                return json.loads(row[0]) if row and row[0] else None
    except Exception as e:
        logger.error(f"get_dungeon_run: {e}")
        return None


async def save_dungeon_run(user_id: str, data: dict[str, Any]):
    try:
        payload = json.dumps(data, ensure_ascii=False)
        now = time.time()
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO user_dungeon_runs (user_id, data, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
                """,
                (user_id, payload, now),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"save_dungeon_run: {e}")


async def delete_dungeon_run(user_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("DELETE FROM user_dungeon_runs WHERE user_id = ?", (user_id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"delete_dungeon_run: {e}")


async def add_dungeon_record(
    user_id: str,
    stage: int,
    result: str,
    reward: int,
    drops: str,
    duration: float,
    is_special: int = 0,
    reason: str | None = None,
    created_at: float | None = None,
):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO user_dungeon_records (user_id, stage, result, reward, drops, duration, is_special, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    int(stage),
                    result,
                    int(reward),
                    drops,
                    float(duration),
                    int(is_special),
                    reason,
                    float(created_at) if created_at is not None else time.time(),
                ),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_dungeon_record: {e}")


async def get_dungeon_records(user_id: str, limit: int = 50) -> list[tuple[Any, ...]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                """
                SELECT stage, result, reward, drops, duration, is_special, reason, created_at
                FROM user_dungeon_records
                WHERE user_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (user_id, int(limit)),
            ) as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error(f"get_dungeon_records: {e}")
        return []


async def get_dungeon_progress(user_id: str) -> int:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT stage FROM user_dungeon_progress WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 1
    except Exception as e:
        logger.error(f"get_dungeon_progress: {e}")
        return 1


async def update_dungeon_progress(user_id: str, stage: int):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            current = await get_dungeon_progress(user_id)
            new_stage = max(int(stage), int(current))
            await conn.execute(
                """
                INSERT INTO user_dungeon_progress (user_id, stage)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET stage = excluded.stage
                """,
                (user_id, new_stage),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"update_dungeon_progress: {e}")


async def get_dungeon_settings(user_id: str) -> dict[str, Any]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT auto_retry, log_mode FROM user_dungeon_settings WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                if row:
                    return dict(row)
                return {"auto_retry": 0, "log_mode": "summary"}
    except Exception as e:
        logger.error(f"get_dungeon_settings: {e}")
        return {"auto_retry": 0, "log_mode": "summary"}


async def get_dungeon_favorites(user_id: str) -> list[tuple[int, int]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT stage, is_special FROM user_dungeon_favorites WHERE user_id = ?",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [(int(r[0]), int(r[1])) for r in rows]
    except Exception as e:
        logger.error(f"get_dungeon_favorites: {e}")
        return []


async def add_dungeon_favorite(user_id: str, stage: int, is_special: int = 0):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO user_dungeon_favorites (user_id, stage, is_special) VALUES (?, ?, ?)",
                (user_id, int(stage), int(is_special)),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_dungeon_favorite: {e}")


async def remove_dungeon_favorite(user_id: str, stage: int, is_special: int = 0):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "DELETE FROM user_dungeon_favorites WHERE user_id = ? AND stage = ? AND is_special = ?",
                (user_id, int(stage), int(is_special)),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"remove_dungeon_favorite: {e}")


async def add_giveaway(message_id: str, channel_id: str, guild_id: str, prize: str, winners: int, end_time: str, host_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO giveaways (message_id, channel_id, guild_id, prize, winners, end_time, host_id, ended)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (str(message_id), str(channel_id), str(guild_id), prize, int(winners), str(end_time), str(host_id)),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_giveaway: {e}")


async def get_giveaway(message_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT * FROM giveaways WHERE message_id = ?", (str(message_id),)) as cur:
                return await cur.fetchone()
    except Exception as e:
        logger.error(f"get_giveaway: {e}")
        return None


async def end_giveaway(message_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (str(message_id),))
            await conn.commit()
    except Exception as e:
        logger.error(f"end_giveaway: {e}")


async def get_active_giveaways() -> list[tuple[Any, ...]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT * FROM giveaways WHERE ended = 0") as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error(f"get_active_giveaways: {e}")
        return []
