import aiosqlite
from .core import DB_FILE, logger
from datetime import datetime, timedelta
import utils.time_utils as time_utils


async def add_chat_count(user_id: str, guild_id: str):
    try:
        today = time_utils.get_kst_now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO chat_stats (user_id, guild_id, date, count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, guild_id, date) DO UPDATE SET count = count + 1
                """,
                (user_id, guild_id, today),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_chat_count: {e}")


async def get_top_chatters(guild_id: str, days: int = 7, limit: int = 10) -> list[tuple[str, int]]:
    try:
        now = time_utils.get_kst_now()
        start_date = (now - timedelta(days=max(1, int(days)) - 1)).strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                """
                SELECT user_id, SUM(count) as total_count
                FROM chat_stats
                WHERE guild_id = ? AND date >= ?
                GROUP BY user_id
                ORDER BY total_count DESC
                LIMIT ?
                """,
                (guild_id, start_date, int(limit)),
            ) as cur:
                rows = await cur.fetchall()
                return [(str(r[0]), int(r[1] or 0)) for r in rows]
    except Exception as e:
        logger.error(f"get_top_chatters: {e}")
        return []
