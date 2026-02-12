import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional
from utils import db
class ServerSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    settings_group = app_commands.Group(name="설정", description="서버 설정을 만져볼까요?")
    @settings_group.command(name="환영", description="누가 오면 반갑게 인사할게요!")
    @app_commands.describe(channel="인사할 채널", message="인사 메시지 ({mention}, {user}, {server} 사용 가능)")
    @app_commands.rename(channel="채널", message="메시지")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: Optional[str] = None):
        await db.set_guild_setting(str(interaction.guild.id), "welcome_channel", str(channel.id))
        if message:
            await db.set_guild_setting(str(interaction.guild.id), "welcome_message", message)
        embed = discord.Embed(title="⚙️ 환영 메시지 설정 완료!", color=discord.Color.green())
        embed.add_field(name="채널", value=channel.mention, inline=True)
        embed.add_field(name="메시지", value=message or "{mention} 님! **{server}**에 오신 것을 환영합니다~! 요미랑 같이 재미있게 놀아요! ✨ (✿◡‿◡)", inline=False)
        embed.set_footer(
            text=f"관리자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await interaction.response.send_message(embed=embed)
    @settings_group.command(name="퇴장", description="누가 떠나면 작별 인사를 할게요...")
    @app_commands.describe(channel="인사할 채널", message="작별 메시지 ({user}, {server} 사용 가능)")
    @app_commands.rename(channel="채널", message="메시지")
    @app_commands.checks.has_permissions(administrator=True)
    async def leave(self, interaction: discord.Interaction, channel: discord.TextChannel, message: Optional[str] = None):
        await db.set_guild_setting(str(interaction.guild.id), "leave_channel", str(channel.id))
        if message:
            await db.set_guild_setting(str(interaction.guild.id), "leave_message", message)
        embed = discord.Embed(title="⚙️ 퇴장 메시지 설정 완료!", color=discord.Color.orange())
        embed.add_field(name="채널", value=channel.mention, inline=True)
        embed.add_field(name="메시지", value=message or "**{user}** 님이 **{server}**을(를) 떠나셨어요... 요미는 여기서 기다리고 있을게요! (｡•́︿•̀｡)", inline=False)
        embed.set_footer(
            text=f"관리자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await interaction.response.send_message(embed=embed)
    @app_commands.command(name="로그채널생성", description="관리자 전용 로그 채널을 자동으로 만들고 웹훅을 연결해요!")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_log_channel(self, interaction: discord.Interaction):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_webhooks=True),
            interaction.user: discord.PermissionOverwrite(read_messages=True)
        }
        try:
            channel = await guild.create_text_channel("yomi-logs", overwrites=overwrites, reason="Yomi Log Channel")
            avatar_bytes = await self.bot.user.display_avatar.read()
            webhook = await channel.create_webhook(name="Yomi Logger", avatar=avatar_bytes, reason="Log System Webhook")
            await db.set_guild_setting(str(guild.id), "log_channel", str(channel.id))
            await db.set_guild_setting(str(guild.id), "log_webhook_url", webhook.url)
            embed = discord.Embed(title="✅ 로그 시스템 구축 완료!", color=discord.Color.green())
            embed.description = f"비공개 채널 {channel.mention}을(를) 만들고 웹훅을 연결했어요!\n이제부터 서버의 중요한 일들을 여기에 기록할게요. ( •̀ ω •́ )✧"
            embed.add_field(name="기록되는 로그", value="- 메시지 삭제/수정\n- 멤버 입장/퇴장\n- 음성 채널 이동\n- 채널 생성/삭제", inline=False)
            await interaction.response.send_message(embed=embed)
            test_embed = discord.Embed(title="🚀 로그 시스템 가동", description="로그 시스템이 정상적으로 시작되었습니다.", color=discord.Color.blue())
            await webhook.send(embed=test_embed, username="요미 로그 시스템", avatar_url=self.bot.user.display_avatar.url)
        except Exception as e:
            await interaction.response.send_message(f"오류가 발생했어요...: {e}", ephemeral=True)
    @settings_group.command(name="외부앱", description="모든 채널에서 외부 앱(명령어 등) 사용을 관리해요!")
    @app_commands.describe(status="허용할지 차단할지 선택해주세요")
    @app_commands.rename(status="상태")
    @app_commands.choices(status=[
        app_commands.Choice(name="🚫 모든 채널 차단", value="disable"),
        app_commands.Choice(name="✅ 모든 채널 허용", value="enable")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def external_apps(self, interaction: discord.Interaction, status: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        everyone = guild.default_role
        is_disable = status == "disable"
        success_count = 0
        fail_count = 0
        for channel in guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel)):
                try:
                    overwrites = channel.overwrites_for(everyone)
                    overwrites.use_external_apps = not is_disable
                    overwrites.use_external_emojis = not is_disable
                    overwrites.use_external_stickers = not is_disable
                    await channel.set_permissions(everyone, overwrite=overwrites)
                    success_count += 1
                except Exception:
                    fail_count += 1
        title = "🚫 외부 앱 사용 차단 완료!" if is_disable else "✅ 외부 앱 사용 허용 완료!"
        color = discord.Color.red() if is_disable else discord.Color.green()
        desc = "이제 모든 채널에서 외부 앱과 이모지 사용이 막혔어요!" if is_disable else "이제 모든 채널에서 외부 앱과 이모지를 자유롭게 쓸 수 있어요!"
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.add_field(name="성공 채널 수", value=f"{success_count}개", inline=True)
        if fail_count > 0:
            embed.add_field(name="실패 채널 수", value=f"{fail_count}개 (권한 부족 등)", inline=True)
        embed.set_footer(text=f"관리자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await interaction.followup.send(embed=embed)
    @settings_group.command(name="초기화", description="모든 설정을 잊어버려요...!")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction):
        gid = str(interaction.guild.id)
        await db.set_guild_setting(gid, "welcome_channel", None)
        await db.set_guild_setting(gid, "welcome_message", None)
        await db.set_guild_setting(gid, "leave_channel", None)
        await db.set_guild_setting(gid, "leave_message", None)
        await db.set_guild_setting(gid, "log_channel", None)
        await db.set_guild_setting(gid, "dungeon_notice_channel", None)
        embed = discord.Embed(
            title="⚙️ 설정 초기화...",
            color=discord.Color.orange(),
            description="모든 설정을 잊어버렸어요... 다시 알려주실거죠? (｡•́︿•̀｡)",
        )
        embed.set_footer(
            text=f"관리자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await interaction.response.send_message(embed=embed)
    @settings_group.command(name="던전알림", description="던전 결과 알림을 보낼 채널을 설정해요!")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(channel="알림을 받을 채널")
    async def dungeon_notice_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        gid = str(interaction.guild.id)
        await db.set_guild_setting(gid, "dungeon_notice_channel", str(channel.id))
        embed = discord.Embed(
            title="✅ 던전 알림 채널 설정 완료",
            description=f"이제 던전 결과를 {channel.mention}에 알려드릴게요!",
            color=discord.Color.green()
        )
        embed.set_footer(
            text=f"관리자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await interaction.response.send_message(embed=embed)
    @settings_group.command(name="확인", description="지금 어떻게 설정되어 있나요?")
    async def show_settings(self, interaction: discord.Interaction):
        settings = await db.get_all_guild_settings(str(interaction.guild.id))
        embed = discord.Embed(
            title="⚙️ 요미의 메모장 (서버 설정)",
            color=discord.Color.blue(),
            description="지금까지 제가 기억하고 있는 설정들이에요! ( •̀ ω •́ )✧"
        )
        welcome_channel = settings.get("welcome_channel")
        if welcome_channel and welcome_channel != 'None':
            channel = interaction.guild.get_channel(int(welcome_channel))
            embed.add_field(
                name="환영 채널",
                value=channel.mention if channel else "없음",
                inline=True,
            )
        else:
            embed.add_field(name="환영 채널", value="설정되지 않음", inline=True)
        leave_channel = settings.get("leave_channel")
        if leave_channel and leave_channel != 'None':
            channel = interaction.guild.get_channel(int(leave_channel))
            embed.add_field(
                name="퇴장 채널",
                value=channel.mention if channel else "없음",
                inline=True,
            )
        else:
            embed.add_field(name="퇴장 채널", value="설정되지 않음", inline=True)
        log_channel = settings.get("log_channel")
        if log_channel and log_channel != 'None':
            channel = interaction.guild.get_channel(int(log_channel))
            embed.add_field(
                name="로그 채널",
                value=channel.mention if channel else "없음",
                inline=True,
            )
        else:
            embed.add_field(name="로그 채널", value="설정되지 않음", inline=True)
        dungeon_notice_channel = settings.get("dungeon_notice_channel")
        if dungeon_notice_channel and dungeon_notice_channel != 'None':
            channel = interaction.guild.get_channel(int(dungeon_notice_channel))
            embed.add_field(
                name="던전 알림 채널",
                value=channel.mention if channel else "없음",
                inline=True,
            )
        else:
            embed.add_field(name="던전 알림 채널", value="설정되지 않음", inline=True)
        welcome_message = settings.get("welcome_message")
        if welcome_message and welcome_message != 'None':
            embed.add_field(
                name="환영 메시지",
                value=welcome_message[:100] + "..."
                if len(welcome_message) > 100
                else welcome_message,
                inline=False,
            )
        leave_message = settings.get("leave_message")
        if leave_message and leave_message != 'None':
            embed.add_field(
                name="퇴장 메시지",
                value=leave_message[:100] + "..."
                if len(leave_message) > 100
                else leave_message,
                inline=False,
            )
        embed.set_footer(
            text=f"서버 ID: {interaction.guild.id} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=embed)
    @app_commands.command(name="공지", description="모두에게 알려줄게요!")
    @app_commands.describe(channel="공지할 채널", message="공지 내용")
    @app_commands.checks.has_permissions(administrator=True)
    async def announce(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        try:
            embed = discord.Embed(
                title="📢 요미가 전해드리는 소식!", description=message, color=discord.Color.gold()
            )
            embed.set_author(
                name=interaction.guild.name,
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None,
            )
            embed.set_footer(
                text=f"작성자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await channel.send(embed=embed)
            await interaction.response.send_message(f"✅ {channel.mention}에 소식을 전했어요! 모두가 좋아할 거예요! (≧∇≦)ﾉ", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"소식을 전하지 못했어요...: {e}", ephemeral=True)
    @app_commands.command(name="역할정보", description="이 역할은 무슨 일을 하나요?")
    @app_commands.describe(role="정보를 볼 역할")
    @app_commands.rename(role="역할")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(
            title=f"📜 역할 정보: {role.name}", color=role.color or discord.Color.blue()
        )
        embed.add_field(name="ID", value=role.id, inline=True)
        embed.add_field(name="멘션", value=role.mention, inline=True)
        embed.add_field(name="색상", value=str(role.color), inline=True)
        embed.add_field(name="위치", value=role.position, inline=True)
        embed.add_field(
            name="멘션 가능", value="예" if role.mentionable else "아니오", inline=True
        )
        embed.add_field(
            name="표시", value="예" if role.hoist else "아니오", inline=True
        )
        embed.add_field(name="가진 사용자 수", value=len(role.members), inline=True)
        embed.add_field(
            name="생성일", value=role.created_at.strftime("%Y-%m-%d"), inline=True
        )
        permissions = []
        if role.permissions.administrator:
            permissions.append("관리자")
        if role.permissions.ban_members:
            permissions.append("밴")
        if role.permissions.kick_members:
            permissions.append("킥")
        if role.permissions.moderate_members:
            permissions.append("뮤트")
        if role.permissions.manage_messages:
            permissions.append("메시지 관리")
        if role.permissions.manage_channels:
            permissions.append("채널 관리")
        if role.permissions.manage_roles:
            permissions.append("역할 관리")
        if permissions:
            embed.add_field(
                name="주요 권한", value=", ".join(permissions), inline=False
            )
        if role.members:
            member_list = [f"{member} ({member.id})" for member in role.members[:10]]
            embed.add_field(
                name="사용자 목록 (최대 10명)",
                value="\n".join(member_list),
                inline=False,
            )
            if len(role.members) > 10:
                embed.add_field(
                    name="...", value=f"외 {len(role.members) - 10}명", inline=False
                )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await interaction.response.send_message(embed=embed)
    @app_commands.command(name="채널정보", description="이 방은 뭐하는 곳인가요?")
    async def channelinfo(self, interaction: discord.Interaction, channel: Optional[discord.abc.GuildChannel] = None):
        channel = channel or interaction.channel
        if isinstance(channel, discord.TextChannel):
            embed = discord.Embed(
                title=f"💬 채널 정보: #{channel.name}", color=discord.Color.blue()
            )
            embed.add_field(name="ID", value=channel.id, inline=True)
            embed.add_field(name="유형", value="텍스트 채널", inline=True)
            embed.add_field(
                name="카테고리",
                value=channel.category.name if channel.category else "없음",
                inline=True,
            )
            embed.add_field(name="주제", value=channel.topic or "없음", inline=False)
            embed.add_field(
                name="NSFW", value="예" if channel.is_nsfw() else "아니오", inline=True
            )
            embed.add_field(
                name="느린 모드",
                value=f"{channel.slowmode_delay}초"
                if channel.slowmode_delay > 0
                else "비활성화",
                inline=True,
            )
            embed.add_field(
                name="생성일",
                value=channel.created_at.strftime("%Y-%m-%d"),
                inline=True,
            )
            embed.add_field(name="위치", value=channel.position, inline=True)
        elif isinstance(channel, discord.VoiceChannel):
            embed = discord.Embed(
                title=f"🔊 채널 정보: {channel.name}", color=discord.Color.purple()
            )
            embed.add_field(name="ID", value=channel.id, inline=True)
            embed.add_field(name="유형", value="음성 채널", inline=True)
            embed.add_field(
                name="카테고리",
                value=channel.category.name if channel.category else "없음",
                inline=True,
            )
            embed.add_field(
                name="비트레이트", value=f"{channel.bitrate}bps", inline=True
            )
            embed.add_field(
                name="인원 제한",
                value=channel.user_limit if channel.user_limit > 0 else "없음",
                inline=True,
            )
            embed.add_field(name="현재 인원", value=len(channel.members), inline=True)
            embed.add_field(
                name="생성일",
                value=channel.created_at.strftime("%Y-%m-%d"),
                inline=True,
            )
        else:
            embed = discord.Embed(
                title=f"📁 채널 정보: {channel.name}", color=discord.Color.light_gray()
            )
            embed.add_field(name="ID", value=channel.id, inline=True)
            embed.add_field(name="유형", value="카테고리", inline=True)
            embed.add_field(
                name="생성일",
                value=channel.created_at.strftime("%Y-%m-%d"),
                inline=True,
            )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await interaction.response.send_message(embed=embed)
async def setup(bot):
    await bot.add_cog(ServerSettings(bot))