import aiosqlite
from .core import DB_FILE, logger
from datetime import datetime, timedelta
import utils.time_utils as time_utils


async def try_claim_daily(user_id: str) -> tuple[bool, int]:
    try:
        now = time_utils.get_kst_now()
        today_str = now.strftime("%Y-%m-%d")
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            async with db.execute("SELECT last_daily, daily_streak FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                last_daily = row[0]
                current_streak = row[1] if row and row[1] else 0
            if last_daily == today_str:
                return False, current_streak
            if last_daily == yesterday_str:
                new_streak = current_streak + 1
            else:
                new_streak = 1
            await db.execute("UPDATE users SET last_daily = ?, daily_streak = ? WHERE user_id = ?", (today_str, new_streak, user_id))
            await db.commit()
            return True, new_streak
    except Exception as e:
        logger.error(f"try_claim_daily: {e}")
        return False, 0


async def get_affinity(user_id: str) -> int:
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT affinity FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    except Exception as e:
        logger.error(f"get_affinity: {e}")
        return 0


async def set_affinity(user_id: str, amount: int):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            await conn.execute("UPDATE users SET affinity = ? WHERE user_id = ?", (int(amount), user_id))
            await conn.commit()
    except Exception as e:
        logger.error(f"set_affinity: {e}")


async def get_daily_affinity(user_id: str) -> int:
    try:
        today = time_utils.get_kst_now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT amount FROM affinity_daily WHERE user_id = ? AND date = ?",
                (user_id, today),
            ) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
    except Exception as e:
        logger.error(f"get_daily_affinity: {e}")
        return 0


async def update_affinity(user_id: str, amount: int) -> tuple[int, int]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))

            async with conn.execute("SELECT affinity FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                old_score = int(row[0]) if row and row[0] is not None else 0

            await conn.execute("UPDATE users SET affinity = affinity + ? WHERE user_id = ?", (int(amount), user_id))

            async with conn.execute("SELECT affinity FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                new_score = int(row[0]) if row and row[0] is not None else 0

            if amount > 0:
                today = time_utils.get_kst_now().strftime("%Y-%m-%d")
                await conn.execute(
                    """
                    INSERT INTO affinity_daily (user_id, date, amount)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, date) DO UPDATE SET amount = amount + excluded.amount
                    """,
                    (user_id, today, int(amount)),
                )

            await conn.commit()
            return old_score, new_score
    except Exception as e:
        logger.error(f"update_affinity: {e}")
        return 0, 0


async def is_registered(user_id: str) -> bool:
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row is not None
    except Exception as e:
        logger.error(f"is_registered: {e}")
        return False
async def get_top_economy(limit: int = 100) -> list:
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)) as cursor:
                rows = await cursor.fetchall()
                return rows
    except Exception as e:
        logger.error(f"get_top_economy: {e}")
        return []
async def get_top_affinity(limit: int = 100) -> list:
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT user_id, affinity FROM users ORDER BY affinity DESC LIMIT ?", (limit,)) as cursor:
                rows = await cursor.fetchall()
                return rows
    except Exception as e:
        logger.error(f"get_top_affinity: {e}")
        return []
