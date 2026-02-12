import discord
from discord.ext import commands
from utils import db
import asyncio
class Afk(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    @commands.command(name="afk", aliases=["잠수"])
    async def afk(self, ctx, *, message="잠수"):
        user = ctx.author
        await db.set_afk(str(user.id), message)
        old_nick = user.display_name
        if not old_nick.startswith("[AFK] "):
            new_nick = f"[AFK] {old_nick}"
        else:
            new_nick = old_nick
        if len(new_nick) > 32:
            new_nick = new_nick[:32]
        nick_changed = False
        if new_nick != old_nick:
            try:
                await user.edit(nick=new_nick)
                nick_changed = True
            except discord.Forbidden:
                nick_changed = False
            except Exception:
                nick_changed = False
        embed = discord.Embed(
            title="💤 잠수 모드 설정",
            description=f"{user.mention} 님이 잠수 모드에 들어갔어요!",
            color=0xFFA500
        )
        embed.add_field(name="사유", value=message, inline=False)
        if not nick_changed and new_nick != old_nick:
            embed.set_footer(text="봇의 권한이 부족하거나 유저의 역할이 봇보다 높아서 닉네임은 변경되지 않았어요.")
        await ctx.send(embed=embed)
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        ctx = await self.bot.get_context(message)
        if ctx.command and ctx.command.name == "afk":
            return
        afk_data = await db.get_afk(str(message.author.id))
        if afk_data:
            await db.remove_afk(str(message.author.id))
            if message.author.display_name.startswith("[AFK] "):
                new_nick = message.author.display_name.replace("[AFK] ", "", 1)
                try:
                    await message.author.edit(nick=new_nick)
                except discord.Forbidden:
                    pass
            await message.channel.send(f"반가워요 {message.author.mention}님! 잠수 모드가 해제되었어요. 👋", delete_after=5)
        if message.mentions:
            for mentioned_user in message.mentions:
                if mentioned_user.bot:
                    continue
                afk_info = await db.get_afk(str(mentioned_user.id))
                if afk_info:
                    msg = afk_info.get("message", "잠수")
                    timestamp = afk_info.get("timestamp")
                    embed = discord.Embed(
                        description=f"💤 **{mentioned_user.display_name}** 님은 현재 잠수 중이에요.",
                        color=0x808080
                    )
                    embed.add_field(name="사유", value=msg, inline=False)
                    embed.set_footer(text=f"시작 시간: {timestamp}")
                    await message.channel.send(embed=embed)
async def setup(bot):
    await bot.add_cog(Afk(bot))