import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils import db
import utils.time_utils as time_utils
import asyncio
from datetime import datetime, timedelta
import random
import re
class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_giveaways.start()
    def cog_unload(self):
        self.check_giveaways.cancel()
    def convert_duration(self, duration: str) -> int:
        regex = re.compile(r"(\d+)([smhd])")
        match = regex.match(duration)
        if not match:
            return None
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "s":
            return amount
        elif unit == "m":
            return amount * 60
        elif unit == "h":
            return amount * 3600
        elif unit == "d":
            return amount * 86400
        return None
    @app_commands.command(name="이벤트시작", description="새로운 이벤트를 시작합니다.")
    @app_commands.describe(
        duration="기간 (예: 10s, 10m, 1h, 1d)",
        winners="당첨자 수",
        prize="이벤트 내용 (상품)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def start_giveaway(self, interaction: discord.Interaction, duration: str, winners: int, prize: str):
        seconds = self.convert_duration(duration)
        if not seconds:
            await interaction.response.send_message("❌ 올바르지 않은 시간 형식입니다. (예: 10s, 10m, 1h, 1d)", ephemeral=True)
            return
        end_time = time_utils.get_kst_now() + timedelta(seconds=seconds)
        end_timestamp = int(end_time.timestamp())
        embed = discord.Embed(
            title="🎉 이벤트! 🎉",
            description=f"**{prize}**",
            color=discord.Color.gold()
        )
        embed.add_field(name="⏰ 종료 시간", value=f"<t:{end_timestamp}:R> (<t:{end_timestamp}:F>)", inline=False)
        embed.add_field(name="👑 당첨자 수", value=f"{winners}명", inline=True)
        embed.add_field(name="👤 주최자", value=interaction.user.mention, inline=True)
        embed.set_footer(text="참가하려면 아래의 🎉 반응을 눌러주세요!")
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        embed.set_footer(text=f"ID: {message.id} | !리롤 {message.id} 명령어로 다시 뽑을 수 있어요!")
        await message.edit(embed=embed)
        await message.add_reaction("🎉")
        db.add_giveaway(
            message.id,
            interaction.channel_id,
            interaction.guild_id,
            prize,
            winners,
            end_time,
            interaction.user.id
        )
    @app_commands.command(name="이벤트종료", description="진행 중인 이벤트를 즉시 종료합니다.")
    @app_commands.describe(message_id="종료할 이벤트 메시지의 ID")
    @app_commands.checks.has_permissions(administrator=True)
    async def end_giveaway_cmd(self, interaction: discord.Interaction, message_id: str):
        giveaway = db.get_giveaway(message_id)
        if not giveaway:
            await interaction.response.send_message("❌ 해당 ID의 이벤트를 찾을 수 없거나 이미 종료되었습니다.", ephemeral=True)
            return
        if giveaway[7] == 1:
            await interaction.response.send_message("❌ 이미 종료된 이벤트입니다.", ephemeral=True)
            return
        await self.finish_giveaway(message_id, manual=True)
        await interaction.response.send_message("✅ 이벤트를 종료했습니다.", ephemeral=True)
    @commands.command(name="리롤")
    @commands.has_permissions(administrator=True)
    async def reroll_giveaway_prefix(self, ctx, message_id: str):
        giveaway = db.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ 존재하지 않는 이벤트입니다.")
            return
        channel_id = int(giveaway[1])
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ 채널을 찾을 수 없습니다.")
            return
        try:
            message = await channel.fetch_message(int(message_id))
        except:
            await ctx.send("❌ 메시지를 찾을 수 없습니다.")
            return
        winners_count = giveaway[4]
        prize = giveaway[3]
        reaction = discord.utils.get(message.reactions, emoji="🎉")
        if reaction:
            users = [user async for user in reaction.users() if not user.bot]
        else:
            users = []
        if len(users) < 1:
            await ctx.send("❌ 참가자가 없어서 리롤할 수 없습니다.")
            return
        winner = random.choice(users)
        await channel.send(f"🎉 **새로운 당첨자**: {winner.mention}! 축하합니다! (이벤트: **{prize}**)")
        await ctx.send("✅ 리롤 완료!")
    async def finish_giveaway(self, message_id, manual=False):
        giveaway = db.get_giveaway(message_id)
        if not giveaway:
            return
        channel_id = int(giveaway[1])
        prize = giveaway[3]
        winners_count = giveaway[4]
        db.end_giveaway(message_id)
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(int(message_id))
        except:
            return
        reaction = discord.utils.get(message.reactions, emoji="🎉")
        if not reaction:
            await channel.send(f"❌ **{prize}** 이벤트가 종료되었지만, 반응을 찾을 수 없습니다.")
            return
        users = [user async for user in reaction.users() if not user.bot]
        embed = message.embeds[0]
        embed.color = discord.Color.dark_gray()
        embed.set_footer(text=f"이벤트가 종료되었습니다. | ID: {message_id} | !리롤 {message_id}")
        if len(users) < winners_count:
            if len(users) == 0:
                await message.reply(f"😢 **{prize}** 이벤트 참가자가 없어서 취소되었습니다.")
                embed.description = f"**{prize}**\n\n❌ 참가자가 없어서 취소됨"
                await message.edit(embed=embed)
                return
            winners = users
        else:
            winners = random.sample(users, winners_count)
        winners_mention = ", ".join([w.mention for w in winners])
        embed.description = f"**{prize}**\n\n👑 **당첨자**: {winners_mention}"
        await message.edit(embed=embed)
        await channel.send(f"🎉 **{prize}** 이벤트 당첨자 발표! 🎉\n축하합니다: {winners_mention}!")
    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        active_giveaways = await db.get_active_giveaways()
        now_kst = time_utils.get_kst_now()
        for g in active_giveaways:
            end_time_str = g[5]
            message_id = g[0]
            try:
                if 'T' in end_time_str:
                     end_time = datetime.fromisoformat(end_time_str)
                elif '.' in end_time_str:
                     end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S.%f")
                else:
                     end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
                if end_time.tzinfo is None:
                    end_time = time_utils.to_kst(end_time)
                if now_kst >= end_time:
                    await self.finish_giveaway(message_id)
            except Exception as e:
                print(f"Error checking giveaway {message_id}: {e}")
                try:
                     end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
                     if end_time.tzinfo is None:
                         end_time = time_utils.to_kst(end_time)
                     if now_kst >= end_time:
                        await self.finish_giveaway(message_id)
                except:
                    pass
    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()
async def setup(bot):
    await bot.add_cog(Giveaway(bot))