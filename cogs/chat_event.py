import discord
from discord import app_commands
from discord.ext import commands
import utils.db as db
from datetime import datetime, timedelta
import random
import time
class ChatEvent(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_messages = {}
        self.cooldown_seconds = 2.0
        self.min_length = 2
    def is_spam(self, message) -> bool:
        user_id = message.author.id
        content = message.content
        now = time.time()
        if message.attachments or message.stickers:
            return False
        if len(content.strip()) < self.min_length:
            return True
        last_msg = self.last_messages.get(user_id)
        self.last_messages[user_id] = {
            'content': content,
            'timestamp': now
        }
        if last_msg:
            time_diff = now - last_msg['timestamp']
            if time_diff < self.cooldown_seconds:
                return True
            if content == last_msg['content'] and time_diff < 10.0:
                return True
        return False
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if self.is_spam(message):
            return
        await db.add_chat_count(str(message.author.id), str(message.guild.id))
    @app_commands.command(name="채팅랭킹", description="누가 가장 수다쟁이일까요?")
    @app_commands.describe(days="조회할 기간 (일)")
    async def chat_ranking(self, interaction: discord.Interaction, days: int = 7):
        await interaction.response.defer()
        top_chatters = await db.get_top_chatters(str(interaction.guild.id), days=days, limit=10)
        if not top_chatters:
            return await interaction.followup.send("아직 채팅 데이터가 없어요! ( >﹏< )")
        embed = discord.Embed(
            title=f"💬 수다쟁이 랭킹 TOP 10 (최근 {days}일)",
            color=discord.Color.gold()
        )
        description = ""
        for i, (user_id, count) in enumerate(top_chatters, 1):
            user = interaction.guild.get_member(int(user_id))
            name = user.display_name if user else "알 수 없는 사용자"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            description += f"{medal} **{name}**: {count}회\n"
        embed.description = description
        embed.set_footer(text=f"요청자: {interaction.user}")
        await interaction.followup.send(embed=embed)
    @app_commands.command(name="채팅추첨", description="열심히 채팅 친 분들 중에서 행운의 주인공을 뽑아요!")
    @app_commands.describe(winners="뽑을 인원 수", days="참여 대상 기간 (일)", min_chat="최소 채팅 수")
    @app_commands.checks.has_permissions(administrator=True)
    async def chat_lottery(self, interaction: discord.Interaction, winners: int = 1, days: int = 7, min_chat: int = 100):
        await interaction.response.defer()
        candidates_data = await db.get_top_chatters(str(interaction.guild.id), days=days, limit=500)
        candidates = []
        for user_id, count in candidates_data:
            if count >= min_chat:
                user = interaction.guild.get_member(int(user_id))
                if user and not user.bot:
                    candidates.append(user)
        if not candidates:
            return await interaction.followup.send(f"조건을 만족하는 사람이 없어요... (최근 {days}일 동안 {min_chat}회 이상 채팅)")
        if len(candidates) < winners:
            return await interaction.followup.send(f"후보자 수({len(candidates)}명)보다 뽑을 인원({winners}명)이 더 많아요!")
        picked = random.sample(candidates, winners)
        embed = discord.Embed(
            title="🎉 채팅 이벤트 당첨자 발표! 🎉",
            description=f"최근 **{days}일** 동안 **{min_chat}회** 이상 채팅 친 분들 중에서 뽑았어요!",
            color=discord.Color.magenta()
        )
        winners_text = "\n".join([f"🏆 {user.mention}" for user in picked])
        embed.add_field(name="행운의 주인공", value=winners_text, inline=False)
        embed.set_footer(text=f"총 후보자: {len(candidates)}명")
        await interaction.followup.send(embed=embed)
async def setup(bot):
    await bot.add_cog(ChatEvent(bot))