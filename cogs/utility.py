
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional

import sys
import os

import utils.db as db
import utils.booster_utils as booster_utils

class Utility(commands.Cog):


    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return ctx.guild is not None

    @app_commands.command(name="유저정보", description="이 분은 어떤 분일까요?")
    @app_commands.describe(member="정보를 볼 사용자")
    @app_commands.rename(member="멤버")
    async def userinfo(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):

        if not interaction.guild:
            return await interaction.response.send_message("이 명령어는 DM에서 사용할 수 없어요! ( >﹏< )", ephemeral=True)
        member = member or interaction.user

        embed = discord.Embed(
            title=f"👤 사용자 정보: {member.display_name}",
            color=member.color or discord.Color.blue(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(
            name="이름", value=f"{member.name}#{member.discriminator}", inline=True
        )
        embed.add_field(name="닉네임", value=member.display_name, inline=True)

        embed.add_field(
            name="계정 생성일",
            value=member.created_at.strftime("%Y-%m-%d"),
            inline=True,
        )
        embed.add_field(
            name="서버 가입일",
            value=member.joined_at.strftime("%Y-%m-%d")
            if member.joined_at
            else "알 수 없음",
            inline=True,
        )

        status_emoji = {
            "online": "🟢 온라인",
            "idle": "🟡 자리 비움",
            "dnd": "🔴 방해 금지",
            "offline": "⚫ 오프라인",
        }
        status = str(member.status)
        embed.add_field(
            name="상태", value=status_emoji.get(status, status), inline=True
        )

        roles = [
            role.mention for role in member.roles if role != member.guild.default_role
        ]
        if roles:
            embed.add_field(
                name=f"역할 ({len(roles)})", value=", ".join(roles[:10]), inline=False
            )
            if len(roles) > 10:
                embed.add_field(
                    name="...", value=f"외 {len(roles) - 10}개의 역할", inline=False
                )

        embed.add_field(name="최고 역할", value=member.top_role.mention, inline=True)

        if member.premium_since:
            embed.add_field(
                name="부스트 시작일",
                value=member.premium_since.strftime("%Y-%m-%d"),
                inline=True,
            )

        if booster_utils.is_booster(member):
            embed.title = f"🚀 [부스터] {member.display_name}"
            embed.color = discord.Color.purple()
            embed.add_field(name="✨ 요미 부스터", value="적용 중 (특별 혜택 활성화!)", inline=True)

        if member.bot:
            embed.add_field(name="봇", value="✅ 예", inline=True)

        embed.set_footer(
            text=f"요청자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="서버정보", description="이 서버는 어떤 곳일까요?")
    async def serverinfo(self, interaction: discord.Interaction):

        if not interaction.guild:
            return await interaction.response.send_message("이 명령어는 DM에서 사용할 수 없어요! ( >﹏< )", ephemeral=True)
        guild = interaction.guild

        total_members = guild.member_count
        online_members = len(
            [m for m in guild.members if m.status == discord.Status.online]
        )
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        roles = len(guild.roles)

        embed = discord.Embed(
            title=f"🏢 서버 정보: {guild.name}", color=discord.Color.blue()
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.add_field(name="ID", value=guild.id, inline=True)
        embed.add_field(name="소유자", value=guild.owner.mention, inline=True)

        embed.add_field(name="전체 인원", value=f"{total_members:,}명", inline=True)
        embed.add_field(name="온라인 인원", value=f"{online_members:,}명", inline=True)

        embed.add_field(name="텍스트 채널", value=f"{text_channels}개", inline=True)
        embed.add_field(name="음성 채널", value=f"{voice_channels}개", inline=True)
        embed.add_field(name="역할", value=f"{roles}개", inline=True)

        embed.add_field(name="레벨", value=guild.premium_tier, inline=True)
        embed.add_field(
            name="부스팅 수", value=guild.premium_subscription_count, inline=True
        )

        verification_levels = {
            discord.VerificationLevel.none: "없음",
            discord.VerificationLevel.low: "낮음",
            discord.VerificationLevel.medium: "중간",
            discord.VerificationLevel.high: "높음",
            discord.VerificationLevel.highest: "매우 높음",
        }
        embed.add_field(
            name="인증 레벨",
            value=verification_levels.get(guild.verification_level, str(guild.verification_level)),
            inline=True,
        )

        content_filter = {
            discord.ContentFilter.disabled: "비활성화",
            discord.ContentFilter.no_role: "역할 없는 멤버",
            discord.ContentFilter.all_members: "모든 멤버",
        }
        embed.add_field(
            name="콘텐츠 필터",
            value=content_filter.get(guild.explicit_content_filter, str(guild.explicit_content_filter)),
            inline=True,
        )

        embed.add_field(
            name="2FA 필수",
            value="예" if guild.mfa_level == 1 else "아니오",
            inline=True,
        )

        if guild.description:
            embed.add_field(name="설명", value=guild.description[:500], inline=False)

        embed.add_field(
            name="서버 생성일", value=guild.created_at.strftime("%Y-%m-%d"), inline=True
        )

        embed.set_footer(
            text=f"요청자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="아바타", description="프로필 사진을 크게 보여줘요!")
    @app_commands.describe(member="대상")
    @app_commands.rename(member="멤버")
    async def avatar(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):

        member = member or interaction.user

        embed = discord.Embed(
            title=f"🖼️ {member.display_name}의 아바타", color=discord.Color.blue()
        )
        embed.set_image(url=member.display_avatar.url)
        embed.add_field(
            name="다운로드", value=f"[링크]({member.display_avatar.url})", inline=False
        )
        embed.set_footer(
            text=f"요청자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="서버아이콘", description="우리 서버의 얼굴이에요!")
    async def servericon(self, interaction: discord.Interaction):

        guild = interaction.guild

        if not guild.icon:
            await interaction.response.send_message("이 서버는 아직 얼굴이 없어요... (｡•́︿•̀｡)", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🏢 {guild.name}의 아이콘", color=discord.Color.blue()
        )
        embed.set_image(url=guild.icon.url)
        embed.add_field(
            name="다운로드", value=f"[링크]({guild.icon.url})", inline=False
        )
        embed.set_footer(
            text=f"요청자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="역할목록", description="우리 서버엔 어떤 역할들이 있을까요?")
    async def rolelist(self, interaction: discord.Interaction):

        guild = interaction.guild
        roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)

        embed = discord.Embed(
            title=f"📜 {guild.name}의 역할 목록", color=discord.Color.blue()
        )

        role_list = []
        for i, role in enumerate(roles, 1):
            member_count = len(role.members)
            if role == guild.default_role:
                role_list.append(f"{i}. @everyone ({member_count}명)")
            else:
                role_list.append(f"{i}. {role.mention} ({member_count}명)")

        chunks = [role_list[i : i + 20] for i in range(0, len(role_list), 20)]

        for i, chunk in enumerate(chunks, 1):
            if i == 1:
                embed.add_field(
                    name=f"역할 ({len(roles)}개)", value="\n".join(chunk), inline=False
                )
            else:
                embed.add_field(
                    name=f"역할 (계속)", value="\n".join(chunk), inline=False
                )

        embed.set_footer(
            text=f"총 {len(roles)}개의 역할 • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="온라인", description="지금 누가 왔나 볼까요?")
    async def online(self, interaction: discord.Interaction):

        guild = interaction.guild
        online_members = [
            m for m in guild.members if m.status != discord.Status.offline
        ]

        embed = discord.Embed(
            title=f"🟢 온라인 멤버 ({len(online_members)}명)",
            color=discord.Color.green(),
        )

        if online_members:
            member_list = []
            for member in online_members[:50]:
                status_emoji = {
                    discord.Status.online: "🟢",
                    discord.Status.idle: "🟡",
                    discord.Status.dnd: "🔴"
                }
                emoji = status_emoji.get(member.status, "⚫")
                member_list.append(f"{emoji} {member.display_name}")

            chunks = [member_list[i : i + 20] for i in range(0, len(member_list), 20)]
            for i, chunk in enumerate(chunks, 1):
                embed.add_field(
                    name=f"온라인 ({i})", value="\n".join(chunk), inline=False
                )

            if len(online_members) > 50:
                embed.add_field(
                    name="...", value=f"외 {len(online_members) - 50}명", inline=False
                )
        else:
            embed.description = "아무도 안 왔어요... 심심해요... (´。＿。｀)"

        embed.set_footer(
            text=f"요청자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="핑", description="제가 얼마나 빠른지 보여드릴게요!")
    async def ping(self, interaction: discord.Interaction):

        start_time = datetime.now()
        await interaction.response.send_message("🏓 퐁! 받아라 얍! ( •̀ ω •́ )✧")
        message = await interaction.original_response()
        end_time = datetime.now()

        latency = (end_time - start_time).total_seconds() * 1000
        discord_latency = self.bot.latency * 1000

        embed = discord.Embed(title="🏓 핑!", color=discord.Color.green())
        embed.add_field(name="메시지 지연시간", value=f"{latency:.2f}ms", inline=True)
        embed.add_field(
            name="Discord API 지연시간", value=f"{discord_latency:.2f}ms", inline=True
        )

        await message.edit(embed=embed)

    @app_commands.command(name="도움말", description="무엇을 도와드릴까요?")
    async def help_command(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="❓ 도움말",
            color=discord.Color.blue(),
            description="모든 명령어는 슬래시(`/`)를 입력하여 확인할 수 있습니다!",
        )

        embed.add_field(
            name="🛠️ 관리", value="채널/역할 생성 및 삭제", inline=True
        )
        embed.add_field(
            name="🛡️ 보안", value="추방, 차단, 뮤트, 청소", inline=True
        )
        embed.add_field(
            name="⚙️ 설정", value="환영 메시지, 로그 채널", inline=True
        )
        embed.add_field(
            name="🔧 도구", value="유저/서버 정보, 핑", inline=True
        )

        embed.add_field(
            name="💡 팁",
            value="명령어 입력창에서 `/`를 누르면 사용할 수 있는 모든 명령어 목록이 나와요!",
            inline=False,
        )
        embed.set_footer(
            text=f"요청자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))