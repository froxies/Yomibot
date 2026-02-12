import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
from datetime import datetime
import utils.db as db
import utils.booster_utils as booster_utils
class Booster(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    async def cog_check(self, ctx):
        return ctx.guild is not None
    @app_commands.command(name="부스터", description="나의 부스터 상태와 적용 중인 혜택을 확인합니다.")
    async def booster_status(self, interaction: discord.Interaction):
        member = interaction.user
        benefits = booster_utils.get_booster_benefits(member)
        is_boost = benefits["is_booster"]
        if is_boost:
            color = discord.Color.purple()
            title = "✨ 부스터 혜택 적용 중!"
            desc = f"{member.mention}님은 현재 **요미 부스터** 상태예요! (✿◡‿◡)"
        else:
            color = discord.Color.default()
            title = "부스터 상태가 아니에요"
            desc = f"{member.mention}님은 현재 일반 상태예요. 부스터를 사용하거나 전용 역할을 얻으면 혜택을 받을 수 있어요!"
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.add_field(
            name="⏳ 쿨다운 감소",
            value=f"**{int((1 - benefits['cooldown_mult']) * 100)}% 단축** (낚시/채광/벌목/놀아주기)",
            inline=True
        )
        embed.add_field(
            name="🧠 AI 성능 향상",
            value=f"대화 기억 **{benefits['ai_context_limit']}개** / 반응 속도 **2배** UP!",
            inline=False
        )
        if member.premium_since:
            embed.set_footer(text=f"서버 부스트 시작일: {member.premium_since.strftime('%Y-%m-%d')}")
        await interaction.response.send_message(embed=embed)
    @app_commands.command(name="부스터혜택", description="요미 봇의 부스터 혜택 목록을 확인합니다.")
    async def booster_benefits(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🚀 요미 부스터 혜택 안내",
            description="서버 부스트를 하거나 지정된 역할을 받으면 아래 혜택이 적용돼요!",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="1. 경제 활동 시간 절약 (QoL)",
            value="- 🎣 **낚시/채광 쿨다운 25% 감소** (60초 → 45초)\n- 🌲 **벌목 쿨다운 25% 감소** (300초 → 225초)\n- 🐾 **펫 놀아주기 25% 감소** (1시간 → 45분)",
            inline=False
        )
        embed.add_field(
            name="2. 젤리 수익 극대화",
            value="-  더 많은 젤리를 모을 수 있어요!",
            inline=False
        )
        embed.add_field(
            name="3. 똑똑해진 요미 (AI)",
            value="- 🧠 **기억력 2배 증가** (최근 대화 20개 / 기억 15개)\n- ⚡ **대화 반응 속도 UP** (레이트 리밋 완화)\n- 📝 **전용 프로필 설정** 가능 (준비 중)",
            inline=False
        )
        embed.add_field(
            name="4. 특별한 대우",
            value="- 🛡️ **문의 우선 처리**\n- 🏅 **프로필 부스터 배지** 표시",
            inline=False
        )
        await interaction.response.send_message(embed=embed)
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        was_booster = before.premium_since is not None
        is_booster = after.premium_since is not None
        if was_booster == is_booster:
            return
        guild = after.guild
        log_channel_id = await db.get_guild_setting(str(guild.id), "log_channel")
        if not log_channel_id:
            return
        channel = guild.get_channel(int(log_channel_id))
        if not channel:
            return
        if is_booster:
            embed = discord.Embed(
                title="🚀 새로운 서버 부스터 등장!",
                description=f"**{after.mention}**님이 서버를 부스트해주셨어요! 감사합니다! (✿◡‿◡)\n모든 부스터 혜택이 즉시 적용됩니다!",
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            await channel.send(embed=embed)
        else:
            embed = discord.Embed(
                title="😢 부스터 종료",
                description=f"**{after.mention}**님의 서버 부스트가 종료되었어요.\n그동안 후원해주셔서 정말 감사했습니다!",
                color=discord.Color.light_grey()
            )
            await channel.send(embed=embed)
async def setup(bot):
    await bot.add_cog(Booster(bot))