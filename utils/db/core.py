import aiosqlite
import os
import logging
from ..logger import setup_logger
logger = setup_logger("DB", "db.log")
DB_FILE = "data/yomi.db"
async def init_db():
    try:
        if not os.path.exists("data"):
            os.makedirs("data")
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            schema = """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    balance INTEGER DEFAULT 0,
                    affinity INTEGER DEFAULT 0,
                    last_daily TEXT,
                    daily_streak INTEGER DEFAULT 0
                )

                CREATE TABLE IF NOT EXISTS inventory (
                    user_id TEXT,
                    item_name TEXT,
                    amount INTEGER,
                    PRIMARY KEY (user_id, item_name)
                )

                CREATE TABLE IF NOT EXISTS cooldowns (
                    user_id TEXT,
                    command_name TEXT,
                    end_time REAL,
                    PRIMARY KEY (user_id, command_name)
                )

                CREATE TABLE IF NOT EXISTS game_stats (
                    user_id TEXT PRIMARY KEY,
                    total_games INTEGER DEFAULT 0,
                    total_wins INTEGER DEFAULT 0,
                    total_earned INTEGER DEFAULT 0,
                    best_win INTEGER DEFAULT 0
                )

                CREATE TABLE IF NOT EXISTS pets (
                    user_id TEXT,
                    pet_type TEXT,
                    level INTEGER DEFAULT 1,
                    xp INTEGER DEFAULT 0,
                    pet_name TEXT,
                    PRIMARY KEY (user_id, pet_type)
                )

                CREATE TABLE IF NOT EXISTS upgrades (
                    user_id TEXT,
                    upgrade_type TEXT,
                    level INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, upgrade_type)
                )

                CREATE TABLE IF NOT EXISTS user_equipment (
                    user_id TEXT PRIMARY KEY,
                    head TEXT,
                    body TEXT,
                    legs TEXT,
                    feet TEXT,
                    weapon TEXT,
                    accessory TEXT
                )

                CREATE TABLE IF NOT EXISTS user_armor_enhancements (
                    user_id TEXT,
                    item_name TEXT,
                    level INTEGER,
                    PRIMARY KEY (user_id, item_name)
                )

                CREATE TABLE IF NOT EXISTS market (
                    item_name TEXT PRIMARY KEY,
                    current_price INTEGER,
                    trend TEXT,
                    change_rate REAL,
                    last_updated REAL
                )

                CREATE TABLE IF NOT EXISTS market_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_name TEXT,
                    price INTEGER,
                    timestamp TEXT
                )

                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id TEXT,
                    key TEXT,
                    value TEXT,
                    PRIMARY KEY (guild_id, key)
                )

                CREATE TABLE IF NOT EXISTS self_role_messages (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    guild_id TEXT,
                    roles_data TEXT,
                    style TEXT DEFAULT 'button'
                )

                CREATE TABLE IF NOT EXISTS user_chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT
                )

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )

                CREATE TABLE IF NOT EXISTS inquiries (
                    channel_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    category TEXT,
                    status TEXT DEFAULT 'open',
                    created_at REAL,
                    staff_id TEXT,
                    claimed_at REAL,
                    archived_at REAL,
                    archived_by TEXT
                )

                CREATE TABLE IF NOT EXISTS blacklist (
                    user_id TEXT PRIMARY KEY,
                    reason TEXT,
                    created_at REAL
                )

                CREATE TABLE IF NOT EXISTS dm_message_map (
                    dm_msg_id TEXT,
                    inquiry_msg_id TEXT,
                    channel_id TEXT,
                    PRIMARY KEY (dm_msg_id, inquiry_msg_id)
                )

                    CREATE TABLE IF NOT EXISTS dm_message_map (
                        dm_msg_id TEXT,
                        inquiry_msg_id TEXT,
                        channel_id TEXT,
                        PRIMARY KEY (dm_msg_id, inquiry_msg_id)
                    )

                CREATE TABLE IF NOT EXISTS inquiry_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    staff_id TEXT,
                    content TEXT,
                    timestamp REAL
                )

                CREATE TABLE IF NOT EXISTS user_dungeon_progress (
                    user_id TEXT PRIMARY KEY,
                    stage INTEGER DEFAULT 1
                )

                CREATE TABLE IF NOT EXISTS user_dungeon_settings (
                    user_id TEXT PRIMARY KEY,
                    auto_retry INTEGER DEFAULT 0,
                    log_mode TEXT DEFAULT 'summary'
                )

                CREATE TABLE IF NOT EXISTS user_dungeon_favorites (
                    user_id TEXT,
                    stage INTEGER,
                    is_special INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, stage, is_special)
                )

                CREATE TABLE IF NOT EXISTS user_dungeon_runs (
                    user_id TEXT PRIMARY KEY,
                    data TEXT,
                    updated_at REAL
                )

                CREATE TABLE IF NOT EXISTS user_dungeon_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    stage INTEGER,
                    result TEXT,
                    reward INTEGER,
                    drops TEXT,
                    duration REAL,
                    is_special INTEGER,
                    reason TEXT,
                    created_at REAL
                )

                CREATE TABLE IF NOT EXISTS user_garden (
                    user_id TEXT,
                    item_id TEXT,
                    position INTEGER,
                    PRIMARY KEY (user_id, position)
                )

                CREATE TABLE IF NOT EXISTS afk_status (
                    user_id TEXT PRIMARY KEY,
                    message TEXT,
                    timestamp TEXT
                )

                CREATE TABLE IF NOT EXISTS warnings (
                    user_id TEXT PRIMARY KEY,
                    count INTEGER DEFAULT 0
                )

                CREATE TABLE IF NOT EXISTS warning_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    guild_id TEXT,
                    mod_id TEXT,
                    reason TEXT,
                    timestamp REAL
                )

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    mem_type TEXT,
                    content TEXT,
                    timestamp REAL
                )

                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )

                CREATE TABLE IF NOT EXISTS maintenance_whitelist (
                    user_id TEXT PRIMARY KEY
                )

                CREATE TABLE IF NOT EXISTS giveaways (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    guild_id TEXT,
                    prize TEXT,
                    winners INTEGER,
                    end_time TEXT,
                    host_id TEXT,
                    ended INTEGER DEFAULT 0
                )

                CREATE TABLE IF NOT EXISTS affinity_daily (
                    user_id TEXT,
                    date TEXT,
                    amount INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, date)
                )

                CREATE TABLE IF NOT EXISTS stocks (
                    stock_id TEXT PRIMARY KEY,
                    name TEXT,
                    price INTEGER,
                    previous_price INTEGER,
                    volatility REAL DEFAULT 0.05
                )

                CREATE TABLE IF NOT EXISTS fish_collection (
                    user_id TEXT,
                    fish_name TEXT,
                    max_length REAL DEFAULT 0,
                    count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, fish_name)
                )

                CREATE TABLE IF NOT EXISTS user_stocks (
                    user_id TEXT,
                    stock_id TEXT,
                    amount INTEGER,
                    average_price REAL,
                    PRIMARY KEY (user_id, stock_id)
                )

                CREATE TABLE IF NOT EXISTS stock_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_id TEXT,
                    price INTEGER,
                    timestamp TEXT
                )

                CREATE TABLE IF NOT EXISTS user_tycoon (
                    user_id TEXT,
                    building_type TEXT,
                    level INTEGER DEFAULT 0,
                    last_collection REAL,
                    PRIMARY KEY (user_id, building_type)
                )

                CREATE TABLE IF NOT EXISTS invite_tracking (
                    inviter_id TEXT,
                    invited_id TEXT PRIMARY KEY,
                    invite_code TEXT,
                    timestamp REAL,
                    is_fake INTEGER DEFAULT 0,
                    is_left INTEGER DEFAULT 0,
                    joined_at REAL,
                    account_created_at REAL,
                    has_chatted INTEGER DEFAULT 0,
                    flag_reason TEXT
                )

                CREATE TABLE IF NOT EXISTS chat_stats (
                    user_id TEXT,
                    guild_id TEXT,
                    date TEXT,
                    count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id, date)
                )

                CREATE TABLE IF NOT EXISTS quick_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT,
                    content TEXT,
                    emoji TEXT DEFAULT '💬'
                )

                CREATE TABLE IF NOT EXISTS dm_snippets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    content TEXT,
                    created_by TEXT,
                    created_at REAL
                )

                CREATE TABLE IF NOT EXISTS user_tags (
                    user_id TEXT,
                    tag_name TEXT,
                    tagged_by TEXT,
                    tagged_at REAL,
                    PRIMARY KEY (user_id, tag_name)
                )

                CREATE TABLE IF NOT EXISTS inquiry_stats (
                    date TEXT PRIMARY KEY,
                    total_opened INTEGER DEFAULT 0,
                    total_closed INTEGER DEFAULT 0,
                    avg_response_time REAL DEFAULT 0
                )

                CREATE TABLE IF NOT EXISTS sticky_roles (
                    guild_id TEXT,
                    user_id TEXT,
                    role_ids TEXT,
                    PRIMARY KEY (guild_id, user_id)
                )
            """
            schema = schema.replace("\n                )\n", "\n                );\n")
            schema = schema.replace("\n                    )\n", "\n                    );\n")
            schema = schema.rstrip()
            if not schema.endswith(";"):
                schema += ";"
            await db.executescript(schema)
            await db.commit()
    except Exception as e:
        logger.error(f"init_db: {e}", exc_info=True)
