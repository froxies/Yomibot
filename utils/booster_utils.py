import discord
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils.db as db

BOOSTER_COOLDOWN_REDUCTION = 0.75
BOOSTER_AI_RATE_LIMIT = 1.0
BOOSTER_AI_CONTEXT_LIMIT = 20
BOOSTER_AI_MEMORY_LIMIT = 15
def is_booster(member: discord.Member) -> bool:

    if not isinstance(member, discord.Member):
        return False

    return member.premium_since is not None

def get_booster_benefits(member: discord.Member) -> dict:

    is_boost = is_booster(member)

    if is_boost:
        return {
            "is_booster": True,
            "cooldown_mult": BOOSTER_COOLDOWN_REDUCTION,
            "ai_rate_limit": BOOSTER_AI_RATE_LIMIT,
            "ai_context_limit": BOOSTER_AI_CONTEXT_LIMIT,
            "ai_memory_limit": BOOSTER_AI_MEMORY_LIMIT
        }
    else:
        return {
            "is_booster": False,
            "cooldown_mult": 1.0,
            "ai_rate_limit": 2.0,
            "ai_context_limit": 10,
            "ai_memory_limit": 5
        }