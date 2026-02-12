import discord
from discord.ext import commands
from utils import db
import os
from dotenv import load_dotenv
import asyncio
load_dotenv()
intents = discord.Intents.all()
bot = commands.Bot(
    command_prefix=os.getenv("COMMAND_PREFIX", "!"),
    intents=intents,
    help_command=None,
    allowed_mentions=discord.AllowedMentions.none(),
)
@bot.check
async def globally_block_dms(ctx):
    return ctx.guild is not None
async def load_extensions():
    cogs_dir = "cogs"
    if not os.path.exists(cogs_dir):
        os.makedirs(cogs_dir)
    for filename in os.listdir(cogs_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"Cog 로드됨: {filename}")
            except Exception as e:
                print(f"❌ Cog 로드 실패 ({filename}): {e}")
async def main():
    token = os.getenv("TOKEN")
    if not token:
        raise ValueError(
            "TOKEN 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요."
        )
    async with bot:
        await db.init_db()
        await load_extensions()
        await bot.start(token)
if __name__ == "__main__":
    asyncio.run(main())