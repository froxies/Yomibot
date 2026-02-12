import aiosqlite
import time
from datetime import datetime
from typing import Any

from .core import DB_FILE, logger


async def check_cooldown(user_id: str, command_name: str, cooldown_seconds: int) -> float:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT end_time FROM cooldowns WHERE user_id = ? AND command_name = ?",
                (user_id, command_name),
            ) as cur:
                row = await cur.fetchone()
                if not row or row[0] is None:
                    return 0
                last_used = float(row[0])
                elapsed = time.time() - last_used
                remaining = float(cooldown_seconds) - elapsed
                return remaining if remaining > 0 else 0
    except Exception as e:
        logger.error(f"check_cooldown: {e}")
        return 0


async def update_cooldown(user_id: str, command_name: str):
    try:
        now = time.time()
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO cooldowns (user_id, command_name, end_time)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, command_name) DO UPDATE SET end_time = excluded.end_time
                """,
                (user_id, command_name, now),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"update_cooldown: {e}")


async def reset_cooldown(user_id: str, command_name: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "DELETE FROM cooldowns WHERE user_id = ? AND command_name = ?",
                (user_id, command_name),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"reset_cooldown: {e}")


async def get_setting(key: str, default: str | None = None) -> str | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else default
    except Exception as e:
        logger.error(f"get_setting: {e}")
        return default


async def set_setting(key: str, value: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"set_setting: {e}")


async def get_guild_setting(guild_id: str, key: str, default: str | None = None) -> str | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT value FROM guild_settings WHERE guild_id = ? AND key = ?",
                (guild_id, key),
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else default
    except Exception as e:
        logger.error(f"get_guild_setting: {e}")
        return default


async def set_guild_setting(guild_id: str, key: str, value: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
                """,
                (guild_id, key, value),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"set_guild_setting: {e}")


async def get_all_guild_settings(guild_id: str) -> dict[str, str]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT key, value FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cur:
                rows = await cur.fetchall()
                return {str(r["key"]): str(r["value"]) for r in rows}
    except Exception as e:
        logger.error(f"get_all_guild_settings: {e}")
        return {}


async def get_system_state(key: str, default: str | None = None) -> str | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT value FROM system_state WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else default
    except Exception as e:
        logger.error(f"get_system_state: {e}")
        return default


async def set_system_state(key: str, value: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO system_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"set_system_state: {e}")


async def is_blacklisted(user_id: str) -> str | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT reason FROM blacklist WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else None
    except Exception as e:
        logger.error(f"is_blacklisted: {e}")
        return None


async def add_blacklist(user_id: str, reason: str = "관리자 지정"):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO blacklist (user_id, reason, created_at) VALUES (?, ?, ?)",
                (user_id, reason, time.time()),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_blacklist: {e}")


async def remove_blacklist(user_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"remove_blacklist: {e}")


async def add_warning(user_id: str, guild_id: str, mod_id: str, reason: str = "경고"):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO warnings (user_id, count) VALUES (?, 1)
                ON CONFLICT(user_id) DO UPDATE SET count = count + 1
                """,
                (user_id,),
            )
            await conn.execute(
                """
                INSERT INTO warning_logs (user_id, guild_id, mod_id, reason, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, guild_id, mod_id, reason, time.time()),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_warning: {e}")


async def get_warning_count(user_id: str) -> int:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT count FROM warnings WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"get_warning_count: {e}")
        return 0


async def remove_warning(user_id: str, count: int = 1):
    try:
        dec = int(count)
        if dec <= 0:
            return
        async with aiosqlite.connect(DB_FILE) as conn:
            current = 0
            async with conn.execute("SELECT count FROM warnings WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                current = int(row[0]) if row else 0
            new_value = max(0, current - dec)
            if new_value == 0:
                await conn.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
            else:
                await conn.execute("UPDATE warnings SET count = ? WHERE user_id = ?", (new_value, user_id))
            await conn.commit()
    except Exception as e:
        logger.error(f"remove_warning: {e}")


async def get_warning_logs(user_id: str, limit: int = 10) -> list[tuple[Any, ...]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                """
                SELECT guild_id, mod_id, reason, timestamp
                FROM warning_logs
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, int(limit)),
            ) as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error(f"get_warning_logs: {e}")
        return []


async def reset_warnings(user_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM warning_logs WHERE user_id = ?", (user_id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"reset_warnings: {e}")


async def get_maintenance_mode() -> dict[str, Any]:
    enabled = (await get_system_state("maintenance_enabled", "0")) == "1"
    reason = await get_system_state("maintenance_reason", "시스템 점검 중입니다.")
    end_time = await get_system_state("maintenance_end_time", None)
    return {"enabled": enabled, "reason": reason, "end_time": end_time}


async def set_maintenance_mode(enabled: bool, reason: str | None = None, end_time: str | None = None):
    await set_system_state("maintenance_enabled", "1" if enabled else "0")
    if reason is not None:
        await set_system_state("maintenance_reason", str(reason))
    if end_time is not None:
        await set_system_state("maintenance_end_time", str(end_time))


async def get_maintenance_whitelist() -> list[str]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT user_id FROM maintenance_whitelist") as cur:
                rows = await cur.fetchall()
                return [str(r[0]) for r in rows]
    except Exception as e:
        logger.error(f"get_maintenance_whitelist: {e}")
        return []


async def add_maintenance_whitelist(user_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("INSERT OR IGNORE INTO maintenance_whitelist (user_id) VALUES (?)", (user_id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"add_maintenance_whitelist: {e}")


async def remove_maintenance_whitelist(user_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("DELETE FROM maintenance_whitelist WHERE user_id = ?", (user_id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"remove_maintenance_whitelist: {e}")


async def add_self_role_message(message_id: str, channel_id: str, guild_id: str, roles_data: str, style: str = "button"):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO self_role_messages (message_id, channel_id, guild_id, roles_data, style) VALUES (?, ?, ?, ?, ?)",
                (str(message_id), str(channel_id), str(guild_id), roles_data, style),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_self_role_message: {e}")


async def delete_self_role_message(message_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("DELETE FROM self_role_messages WHERE message_id = ?", (str(message_id),))
            await conn.commit()
    except Exception as e:
        logger.error(f"delete_self_role_message: {e}")


async def get_all_self_role_messages() -> list[tuple[Any, ...]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT message_id, channel_id, guild_id, roles_data, style FROM self_role_messages"
            ) as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error(f"get_all_self_role_messages: {e}")
        return []


async def set_sticky_roles(guild_id: str, user_id: str, role_ids: list[str]):
    roles_str = ",".join([str(x) for x in role_ids])
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO sticky_roles (guild_id, user_id, role_ids)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET role_ids = excluded.role_ids
                """,
                (guild_id, user_id, roles_str),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"set_sticky_roles: {e}")


async def get_sticky_roles(guild_id: str, user_id: str) -> list[str]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT role_ids FROM sticky_roles WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ) as cur:
                row = await cur.fetchone()
                if not row or not row[0]:
                    return []
                return [x for x in str(row[0]).split(",") if x]
    except Exception as e:
        logger.error(f"get_sticky_roles: {e}")
        return []


async def get_verification_settings(guild_id: str) -> dict[str, str]:
    keys = [
        "verify_role_id",
        "verify_channel_id",
        "verify_log_channel_id",
        "verify_welcome_channel_id",
        "verify_welcome_msg",
    ]
    settings: dict[str, str] = {}
    for k in keys:
        v = await get_guild_setting(guild_id, k)
        if v is not None:
            settings[k] = v
    return settings


async def set_verification_setting(guild_id: str, key: str, value: str):
    await set_guild_setting(guild_id, key, value)


async def set_afk(user_id: str, message: str):
    try:
        ts = datetime.utcnow().isoformat(timespec="seconds")
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO afk_status (user_id, message, timestamp)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET message = excluded.message, timestamp = excluded.timestamp
                """,
                (user_id, message, ts),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"set_afk: {e}")


async def get_afk(user_id: str) -> dict[str, Any] | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT message, timestamp FROM afk_status WHERE user_id = ?",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                return dict(row)
    except Exception as e:
        logger.error(f"get_afk: {e}")
        return None


async def remove_afk(user_id: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("DELETE FROM afk_status WHERE user_id = ?", (user_id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"remove_afk: {e}")


async def reset_season_data(season_name: str):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("UPDATE users SET balance = 0, affinity = 0, last_daily = NULL, daily_streak = 0")
            await conn.execute("DELETE FROM inventory")
            await conn.execute("DELETE FROM cooldowns")
            await conn.execute("DELETE FROM game_stats")
            await conn.execute("DELETE FROM pets")
            await conn.execute("DELETE FROM upgrades")
            await conn.execute("DELETE FROM user_equipment")
            await conn.execute("DELETE FROM user_armor_enhancements")
            await conn.execute("DELETE FROM fish_collection")
            await conn.execute("DELETE FROM user_stocks")
            await conn.execute("DELETE FROM stock_history")
            await conn.execute("DELETE FROM market")
            await conn.execute("DELETE FROM market_history")
            await conn.execute("DELETE FROM user_tycoon")
            await conn.execute("DELETE FROM user_garden")
            await conn.execute("DELETE FROM user_dungeon_progress")
            await conn.execute("DELETE FROM user_dungeon_settings")
            await conn.execute("DELETE FROM user_dungeon_favorites")
            await conn.execute("DELETE FROM user_dungeon_runs")
            await conn.execute("DELETE FROM user_dungeon_records")
            await conn.execute("DELETE FROM invite_tracking")
            await conn.execute(
                """
                INSERT INTO system_state (key, value) VALUES ('current_season', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (season_name,),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"reset_season_data: {e}")
