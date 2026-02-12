import aiosqlite
import json
import time
from datetime import datetime
from typing import Any, Iterable

from .core import DB_FILE, logger


def _now_ts_str() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


async def get_balance(user_id: str) -> int:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
    except Exception as e:
        logger.error(f"get_balance: {e}")
        return 0


async def set_balance(user_id: str, amount: int):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            await conn.execute("UPDATE users SET balance = ? WHERE user_id = ?", (int(amount), user_id))
            await conn.commit()
    except Exception as e:
        logger.error(f"set_balance: {e}")


async def update_balance(user_id: str, amount: int):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            await conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (int(amount), user_id))
            await conn.commit()
    except Exception as e:
        logger.error(f"update_balance: {e}")


async def try_deduct_balance(user_id: str, amount: int) -> bool:
    if amount <= 0:
        return True
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            async with conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                current_balance = int(row[0]) if row and row[0] is not None else 0
            if current_balance < amount:
                return False
            await conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (int(amount), user_id))
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"try_deduct_balance: {e}")
        return False


async def get_total_economy() -> int:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT SUM(balance) FROM users") as cur:
                row = await cur.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
    except Exception as e:
        logger.error(f"get_total_economy: {e}")
        return 0


async def reset_economy_all():
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("UPDATE users SET balance = 0")
            await conn.execute("DELETE FROM inventory")
            await conn.execute("DELETE FROM user_stocks")
            await conn.execute("DELETE FROM user_tycoon")
            await conn.execute("DELETE FROM market")
            await conn.execute("DELETE FROM market_history")
            await conn.commit()
    except Exception as e:
        logger.error(f"reset_economy_all: {e}")


async def get_inventory(user_id: str) -> list[dict[str, Any]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT item_name, amount FROM inventory WHERE user_id = ? AND amount > 0 ORDER BY item_name ASC",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_inventory: {e}")
        return []


async def add_item(user_id: str, item_name: str, amount: int):
    if amount == 0:
        return
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO inventory (user_id, item_name, amount)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, item_name) DO UPDATE SET amount = amount + excluded.amount
                """,
                (user_id, item_name, int(amount)),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"add_item: {e}")


async def remove_item(user_id: str, item_name: str, amount: int) -> bool:
    if amount <= 0:
        return True
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT amount FROM inventory WHERE user_id = ? AND item_name = ?",
                (user_id, item_name),
            ) as cur:
                row = await cur.fetchone()
                current = int(row[0]) if row and row[0] is not None else 0
            if current < amount:
                return False
            new_amount = current - int(amount)
            if new_amount <= 0:
                await conn.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND item_name = ?",
                    (user_id, item_name),
                )
            else:
                await conn.execute(
                    "UPDATE inventory SET amount = ? WHERE user_id = ? AND item_name = ?",
                    (new_amount, user_id, item_name),
                )
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"remove_item: {e}")
        return False


async def try_deduct_items(user_id: str, items_to_deduct: dict[str, int]) -> bool:
    try:
        normalized = {k: int(v) for k, v in items_to_deduct.items() if int(v) > 0}
        if not normalized:
            return True
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("BEGIN")
            for item_name, amount in normalized.items():
                async with conn.execute(
                    "SELECT amount FROM inventory WHERE user_id = ? AND item_name = ?",
                    (user_id, item_name),
                ) as cur:
                    row = await cur.fetchone()
                    current = int(row[0]) if row and row[0] is not None else 0
                if current < amount:
                    await conn.execute("ROLLBACK")
                    return False
            for item_name, amount in normalized.items():
                async with conn.execute(
                    "SELECT amount FROM inventory WHERE user_id = ? AND item_name = ?",
                    (user_id, item_name),
                ) as cur:
                    row = await cur.fetchone()
                    current = int(row[0]) if row and row[0] is not None else 0
                new_amount = current - amount
                if new_amount <= 0:
                    await conn.execute(
                        "DELETE FROM inventory WHERE user_id = ? AND item_name = ?",
                        (user_id, item_name),
                    )
                else:
                    await conn.execute(
                        "UPDATE inventory SET amount = ? WHERE user_id = ? AND item_name = ?",
                        (new_amount, user_id, item_name),
                    )
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"try_deduct_items: {e}")
        return False


async def update_game_stats(user_id: str, earned: int, is_win: bool):
    try:
        earned_int = int(earned)
        win_int = 1 if is_win else 0
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO game_stats (user_id, total_games, total_wins, total_earned, best_win)
                VALUES (?, 0, 0, 0, 0)
                """,
                (user_id,),
            )
            await conn.execute(
                """
                UPDATE game_stats
                SET
                    total_games = total_games + 1,
                    total_wins = total_wins + ?,
                    total_earned = total_earned + ?,
                    best_win = CASE WHEN ? > best_win THEN ? ELSE best_win END
                WHERE user_id = ?
                """,
                (win_int, earned_int, earned_int, earned_int, user_id),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"update_game_stats: {e}")


async def init_stock_market(default_stocks: Iterable[dict[str, Any]]):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            for stock in default_stocks:
                stock_id = str(stock.get("stock_id") or "").upper()
                name = str(stock.get("name") or stock_id)
                price = int(stock.get("price") or 0)
                volatility = float(stock.get("volatility") or 0.05)
                if not stock_id or price <= 0:
                    continue
                await conn.execute(
                    """
                    INSERT INTO stocks (stock_id, name, price, previous_price, volatility)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(stock_id) DO UPDATE SET
                        name = excluded.name,
                        volatility = excluded.volatility
                    """,
                    (stock_id, name, price, price, volatility),
                )
                await conn.execute(
                    "INSERT INTO stock_history (stock_id, price, timestamp) VALUES (?, ?, ?)",
                    (stock_id, price, _now_ts_str()),
                )
            await conn.commit()
    except Exception as e:
        logger.error(f"init_stock_market: {e}")


async def get_all_stocks() -> list[dict[str, Any]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM stocks ORDER BY stock_id ASC") as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_stocks: {e}")
        return []


async def get_stock(stock_id: str) -> dict[str, Any] | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM stocks WHERE stock_id = ?", (stock_id.upper(),)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_stock: {e}")
        return None


async def update_stock_price(stock_id: str, new_price: int):
    try:
        stock_id_u = stock_id.upper()
        new_price_i = int(new_price)
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                "UPDATE stocks SET previous_price = price, price = ? WHERE stock_id = ?",
                (new_price_i, stock_id_u),
            )
            await conn.execute(
                "INSERT INTO stock_history (stock_id, price, timestamp) VALUES (?, ?, ?)",
                (stock_id_u, new_price_i, _now_ts_str()),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"update_stock_price: {e}")


async def get_user_stocks(user_id: str) -> dict[str, dict[str, Any]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT stock_id, amount, average_price FROM user_stocks WHERE user_id = ? AND amount > 0",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
                out: dict[str, dict[str, Any]] = {}
                for r in rows:
                    out[str(r["stock_id"])] = {"amount": int(r["amount"]), "average_price": float(r["average_price"])}
                return out
    except Exception as e:
        logger.error(f"get_user_stocks: {e}")
        return {}


async def trade_stock(user_id: str, stock_id: str, amount: int, price: int, is_buy: bool) -> tuple[bool, str]:
    try:
        stock_id_u = stock_id.upper()
        qty = int(amount)
        unit_price = int(price)
        if qty <= 0:
            return False, "수량은 1 이상이어야 해요."
        if unit_price <= 0:
            return False, "가격 정보가 올바르지 않아요."
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            if is_buy:
                total_cost = qty * unit_price
                ok = await try_deduct_balance(user_id, total_cost)
                if not ok:
                    return False, "젤리가 부족해요!"
                async with conn.execute(
                    "SELECT amount, average_price FROM user_stocks WHERE user_id = ? AND stock_id = ?",
                    (user_id, stock_id_u),
                ) as cur:
                    row = await cur.fetchone()
                old_amount = int(row["amount"]) if row else 0
                old_avg = float(row["average_price"]) if row else 0.0
                new_amount = old_amount + qty
                new_avg = ((old_amount * old_avg) + (qty * unit_price)) / new_amount if new_amount > 0 else float(unit_price)
                await conn.execute(
                    """
                    INSERT INTO user_stocks (user_id, stock_id, amount, average_price)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, stock_id) DO UPDATE SET amount = excluded.amount, average_price = excluded.average_price
                    """,
                    (user_id, stock_id_u, new_amount, new_avg),
                )
                await conn.commit()
                return True, f"✅ **{stock_id_u}** {qty}주를 구매했어요! (총 {total_cost:,} 젤리)"
            async with conn.execute(
                "SELECT amount, average_price FROM user_stocks WHERE user_id = ? AND stock_id = ?",
                (user_id, stock_id_u),
            ) as cur:
                row = await cur.fetchone()
            if not row or int(row["amount"]) < qty:
                return False, "보유한 주식이 부족해요!"
            proceeds = qty * unit_price
            await update_balance(user_id, proceeds)
            remaining = int(row["amount"]) - qty
            if remaining <= 0:
                await conn.execute("DELETE FROM user_stocks WHERE user_id = ? AND stock_id = ?", (user_id, stock_id_u))
            else:
                await conn.execute(
                    "UPDATE user_stocks SET amount = ? WHERE user_id = ? AND stock_id = ?",
                    (remaining, user_id, stock_id_u),
                )
            await conn.commit()
            return True, f"✅ **{stock_id_u}** {qty}주를 판매했어요! (총 {proceeds:,} 젤리)"
    except Exception as e:
        logger.error(f"trade_stock: {e}")
        return False, "처리 중 오류가 발생했어요."


async def update_market_price(item_name: str, new_price: int, trend: str, change_rate: float):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO market (item_name, current_price, trend, change_rate, last_updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(item_name) DO UPDATE SET
                    current_price = excluded.current_price,
                    trend = excluded.trend,
                    change_rate = excluded.change_rate,
                    last_updated = excluded.last_updated
                """,
                (item_name, int(new_price), str(trend), float(change_rate), time.time()),
            )
            await conn.execute(
                "INSERT INTO market_history (item_name, price, timestamp) VALUES (?, ?, ?)",
                (item_name, int(new_price), _now_ts_str()),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"update_market_price: {e}")


async def get_market_status(item_name: str | None = None) -> Any:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            if item_name:
                async with conn.execute("SELECT * FROM market WHERE item_name = ?", (item_name,)) as cur:
                    row = await cur.fetchone()
                    return dict(row) if row else None
            async with conn.execute("SELECT * FROM market") as cur:
                rows = await cur.fetchall()
                return {str(r["item_name"]): dict(r) for r in rows}
    except Exception as e:
        logger.error(f"get_market_status: {e}")
        return None if item_name else {}


async def get_current_market_price(item_name: str, base_price: int) -> tuple[int, str]:
    try:
        status = await get_market_status(item_name)
        if not status:
            await update_market_price(item_name, int(base_price), "stable", 0.0)
            return int(base_price), "➖"
        trend = status.get("trend") or "stable"
        arrow = "📈" if trend == "up" else "📉" if trend == "down" else "➖"
        return int(status.get("current_price") or base_price), arrow
    except Exception as e:
        logger.error(f"get_current_market_price: {e}")
        return int(base_price), "➖"


async def get_price_history(item_name: str, limit: int = 24) -> list[dict[str, Any]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT price, timestamp FROM market_history WHERE item_name = ? ORDER BY id DESC LIMIT ?",
                (item_name, int(limit)),
            ) as cur:
                rows = await cur.fetchall()
                data = [dict(r) for r in rows][::-1]
                return data
    except Exception as e:
        logger.error(f"get_price_history: {e}")
        return []


async def get_fish_collection(user_id: str) -> list[dict[str, Any]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM fish_collection WHERE user_id = ?", (user_id,)) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_fish_collection: {e}")
        return []


async def update_fish_collection(user_id: str, fish_name: str, length: float):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT max_length, count FROM fish_collection WHERE user_id = ? AND fish_name = ?",
                (user_id, fish_name),
            ) as cur:
                row = await cur.fetchone()
            if row:
                current_max = float(row[0] or 0)
                current_count = int(row[1] or 0)
                new_max = max(current_max, float(length))
                new_count = current_count + 1
                await conn.execute(
                    "UPDATE fish_collection SET max_length = ?, count = ? WHERE user_id = ? AND fish_name = ?",
                    (new_max, new_count, user_id, fish_name),
                )
            else:
                await conn.execute(
                    "INSERT INTO fish_collection (user_id, fish_name, max_length, count) VALUES (?, ?, ?, 1)",
                    (user_id, fish_name, float(length)),
                )
            await conn.commit()
    except Exception as e:
        logger.error(f"update_fish_collection: {e}")


async def get_upgrade(user_id: str, upgrade_type: str) -> int:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT level FROM upgrades WHERE user_id = ? AND upgrade_type = ?",
                (user_id, upgrade_type),
            ) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"get_upgrade: {e}")
        return 0


async def set_upgrade(user_id: str, upgrade_type: str, level: int):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO upgrades (user_id, upgrade_type, level)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, upgrade_type) DO UPDATE SET level = excluded.level
                """,
                (user_id, upgrade_type, int(level)),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"set_upgrade: {e}")


async def get_equipped_armor(user_id: str) -> dict[str, Any] | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM user_equipment WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_equipped_armor: {e}")
        return None


async def update_equipped_armor(user_id: str, slot: str, item_name: str | None):
    allowed = {"head", "body", "legs", "feet", "weapon", "accessory"}
    if slot not in allowed:
        raise ValueError("invalid slot")
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("INSERT OR IGNORE INTO user_equipment (user_id) VALUES (?)", (user_id,))
            await conn.execute(f"UPDATE user_equipment SET {slot} = ? WHERE user_id = ?", (item_name, user_id))
            await conn.commit()
    except Exception as e:
        logger.error(f"update_equipped_armor: {e}")


async def get_armor_level(user_id: str, item_name: str) -> int:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT level FROM user_armor_enhancements WHERE user_id = ? AND item_name = ?",
                (user_id, item_name),
            ) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"get_armor_level: {e}")
        return 0


async def set_armor_level(user_id: str, item_name: str, level: int):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO user_armor_enhancements (user_id, item_name, level)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, item_name) DO UPDATE SET level = excluded.level
                """,
                (user_id, item_name, int(level)),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"set_armor_level: {e}")


async def get_user_pets(user_id: str) -> list[dict[str, Any]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM pets WHERE user_id = ?", (user_id,)) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_user_pets: {e}")
        return []


async def update_pet_xp(user_id: str, pet_type: str, xp_gain: int) -> tuple[int, int]:
    try:
        gain = int(xp_gain)
        if gain <= 0:
            gain = 0
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO pets (user_id, pet_type, level, xp)
                VALUES (?, ?, 1, 0)
                """,
                (user_id, pet_type),
            )
            async with conn.execute(
                "SELECT level, xp FROM pets WHERE user_id = ? AND pet_type = ?",
                (user_id, pet_type),
            ) as cur:
                row = await cur.fetchone()
                level = int(row[0]) if row else 1
                xp = int(row[1]) if row else 0
            xp += gain
            while xp >= level * 100:
                xp -= level * 100
                level += 1
            await conn.execute(
                "UPDATE pets SET level = ?, xp = ? WHERE user_id = ? AND pet_type = ?",
                (level, xp, user_id, pet_type),
            )
            await conn.commit()
            return level, xp
    except Exception as e:
        logger.error(f"update_pet_xp: {e}")
        return 1, 0


async def _ensure_user_jobs(conn: aiosqlite.Connection):
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_jobs (
            user_id TEXT,
            job_name TEXT,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, job_name)
        )
        """
    )


async def get_job_info(user_id: str, job_name: str) -> dict[str, Any] | None:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await _ensure_user_jobs(conn)
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT level, xp FROM user_jobs WHERE user_id = ? AND job_name = ?",
                (user_id, job_name),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_job_info: {e}")
        return None


async def update_job_xp(user_id: str, job_name: str, xp_gain: int) -> tuple[int, bool]:
    try:
        gain = int(xp_gain)
        async with aiosqlite.connect(DB_FILE) as conn:
            await _ensure_user_jobs(conn)
            await conn.execute(
                "INSERT OR IGNORE INTO user_jobs (user_id, job_name, level, xp) VALUES (?, ?, 1, 0)",
                (user_id, job_name),
            )
            async with conn.execute(
                "SELECT level, xp FROM user_jobs WHERE user_id = ? AND job_name = ?",
                (user_id, job_name),
            ) as cur:
                row = await cur.fetchone()
                level = int(row[0]) if row else 1
                xp = int(row[1]) if row else 0
            old_level = level
            xp += gain
            while xp >= level * 120:
                xp -= level * 120
                level += 1
            await conn.execute(
                "UPDATE user_jobs SET level = ?, xp = ? WHERE user_id = ? AND job_name = ?",
                (level, xp, user_id, job_name),
            )
            await conn.commit()
            return level, level > old_level
    except Exception as e:
        logger.error(f"update_job_xp: {e}")
        return 1, False


async def get_garden_items(user_id: str) -> list[dict[str, Any]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT item_id, position FROM user_garden WHERE user_id = ? ORDER BY position ASC",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_garden_items: {e}")
        return []


async def get_tycoon_buildings(user_id: str) -> dict[str, dict[str, Any]]:
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT building_type, level, last_collection FROM user_tycoon WHERE user_id = ?",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
                return {str(r["building_type"]): dict(r) for r in rows}
    except Exception as e:
        logger.error(f"get_tycoon_buildings: {e}")
        return {}


async def update_tycoon_building(user_id: str, building_type: str, new_level: int, new_collection: float):
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute(
                """
                INSERT INTO user_tycoon (user_id, building_type, level, last_collection)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, building_type) DO UPDATE SET level = excluded.level, last_collection = excluded.last_collection
                """,
                (user_id, building_type, int(new_level), float(new_collection)),
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"update_tycoon_building: {e}")
