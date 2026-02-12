import aiosqlite
import time
from .core import DB_FILE, logger


async def add_invite_log(
    inviter_id: str,
    invited_id: str,
    invite_code: str,
    account_created_at: float,
    is_fake: int = 0,
    flag_reason: str | None = None,
):
    try:
        now = time.time()
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO invite_tracking (
                    inviter_id, invited_id, invite_code, timestamp, is_fake, is_left,
                    joined_at, account_created_at, has_chatted, flag_reason
                )
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, 0, ?)
                """,
                (
                    inviter_id,
                    invited_id,
                    invite_code,
                    now,
                    int(is_fake),
                    now,
                    float(account_created_at),
                    flag_reason,
                ),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_invite_log: {e}")


async def mark_user_left(invited_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "UPDATE invite_tracking SET is_left = 1 WHERE invited_id = ?",
                (invited_id,),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"mark_user_left: {e}")


async def get_inviter(invited_id: str) -> str | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT inviter_id FROM invite_tracking WHERE invited_id = ? AND is_left = 0",
                (invited_id,),
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None
    except Exception as e:
        logger.error(f"get_inviter: {e}")
        return None


async def mark_user_chatted(invited_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "UPDATE invite_tracking SET has_chatted = 1 WHERE invited_id = ?",
                (invited_id,),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"mark_user_chatted: {e}")


async def get_invites_count(inviter_id: str) -> dict[str, int]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM invite_tracking WHERE inviter_id = ? AND is_fake = 0 AND is_left = 0",
                (inviter_id,),
            ) as cur:
                valid = int((await cur.fetchone())[0])
            async with conn.execute(
                "SELECT COUNT(*) FROM invite_tracking WHERE inviter_id = ? AND is_fake = 1",
                (inviter_id,),
            ) as cur:
                fake = int((await cur.fetchone())[0])
            async with conn.execute(
                "SELECT COUNT(*) FROM invite_tracking WHERE inviter_id = ? AND is_fake = 0 AND is_left = 1",
                (inviter_id,),
            ) as cur:
                left = int((await cur.fetchone())[0])
            return {"valid": valid, "fake": fake, "left": left}
    except Exception as e:
        logger.error(f"get_invites_count: {e}")
        return {"valid": 0, "fake": 0, "left": 0}


async def get_top_inviters(limit: int = 10) -> list[tuple[str, int]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                """
                SELECT inviter_id, COUNT(*) as count
                FROM invite_tracking
                WHERE is_left = 0 AND is_fake = 0
                GROUP BY inviter_id
                ORDER BY count DESC
                LIMIT ?
                """,
                (int(limit),),
            ) as cur:
                rows = await cur.fetchall()
                return [(str(r[0]), int(r[1])) for r in rows]
    except Exception as e:
        logger.error(f"get_top_inviters: {e}")
        return []
