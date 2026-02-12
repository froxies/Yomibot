
import discord
from discord import app_commands
from discord.ext import commands
from utils import db
from datetime import datetime, timedelta
from typing import Optional

class Moderation(commands.Cog):


    def __init__(self, bot):
        self.bot = bot

    async def get_log_channel(self, guild):

        log_channel_id = await db.get_guild_setting(str(guild.id), "log_channel")
        if log_channel_id:
            return guild.get_channel(int(log_channel_id))
        return None

    @app_commands.command(name="추방", description="나쁜 사람을 쫓아내요!")
    @app_commands.describe(member="추방할 사람", reason="사유")
    @app_commands.rename(member="멤버", reason="사유")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):

        if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            await interaction.response.send_message("저 분은 님보다 높아서 못 쫓아내요! ( >﹏< )", ephemeral=True)
            return

        if member.top_role >= interaction.guild.me.top_role:
             await interaction.response.send_message("저 분은 저보다 높거나 같아서 못 쫓아내요! ( >﹏< )", ephemeral=True)
             return

        if member == interaction.guild.owner:
             await interaction.response.send_message("서버 사장님은 내보낼 수 없어요! ( >﹏< )", ephemeral=True)
             return

        try:
            await member.kick(reason=reason)
            embed = discord.Embed(title="👞 안녕히 가세요...", color=discord.Color.orange())
            embed.add_field(name="사용자", value=f"{member} ({member.id})", inline=True)
            embed.add_field(name="관리자", value=interaction.user.mention, inline=True)
            embed.add_field(name="사유", value=reason or "사유 없음", inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(
                text=f"ID: {member.id} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            await interaction.response.send_message(embed=embed)

            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f"추방하는데 실패했어요...: {e}", ephemeral=True)

    @app_commands.command(name="차단", description="나쁜 사람을 쫓아내고 문도 잠가요!")
    @app_commands.describe(member="차단할 사람", delete_message_days="메시지 삭제 기간(일)", reason="사유")
    @app_commands.rename(member="멤버", delete_message_days="메시지_삭제_기간", reason="사유")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, delete_message_days: int = 0, reason: Optional[str] = None):

        if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            await interaction.response.send_message("저 분은 님보다 높아서 못 막아요! ( >﹏< )", ephemeral=True)
            return

        if member.top_role >= interaction.guild.me.top_role:
            await interaction.response.send_message("저 분은 저보다 높거나 같아서 못 막아요! ( >﹏< )", ephemeral=True)
            return

        if member == interaction.guild.owner:
            await interaction.response.send_message("서버 사장님은 차단할 수 없어요! ( >﹏< )", ephemeral=True)
            return

        try:
            await member.ban(reason=reason, delete_message_days=delete_message_days)
            embed = discord.Embed(title="🔨 쾅! 차단했어요!", color=discord.Color.red())
            embed.add_field(name="사용자", value=f"{member} ({member.id})", inline=True)
            embed.add_field(name="관리자", value=interaction.user.mention, inline=True)
            embed.add_field(
                name="삭제된 메시지 기간", value=f"{delete_message_days}일", inline=True
            )
            embed.add_field(name="사유", value=reason or "사유 없음", inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(
                text=f"ID: {member.id} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            await interaction.response.send_message(embed=embed)

            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f"차단하는데 실패했어요...: {e}", ephemeral=True)

    @app_commands.command(name="차단해제", description="용서해줄 시간이에요!")
    @app_commands.describe(user_id="차단 해제할 유저 ID", reason="사유")
    @app_commands.rename(user_id="사용자_id", reason="사유")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = None):

        try:
            try:
                user_id_int = int(user_id)
            except ValueError:
                 await interaction.response.send_message("올바른 ID 숫자를 입력해주세요!", ephemeral=True)
                 return

            user = await self.bot.fetch_user(user_id_int)
            await interaction.guild.unban(user, reason=reason)

            embed = discord.Embed(
                title="🔓 차단 해제!", color=discord.Color.green()
            )
            embed.add_field(name="사용자", value=f"{user} ({user.id})", inline=True)
            embed.add_field(name="관리자", value=interaction.user.mention, inline=True)
            embed.add_field(name="사유", value=reason or "사유 없음", inline=False)
            embed.set_footer(
                text=f"ID: {user.id} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            await interaction.response.send_message(embed=embed)

            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)

        except discord.NotFound:
             await interaction.response.send_message(f"그 사람은 차단 목록에 없거나 찾을 수 없어요! (・∀・)", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"차단을 풀어주지 못했어요...: {e}", ephemeral=True)

    @app_commands.command(name="뮤트", description="잠깐 조용히 시켜요...")
    @app_commands.describe(member="뮤트할 사람", duration="기간 (예: 10m, 1h, 1d)", reason="사유")
    @app_commands.rename(member="멤버", duration="기간", reason="사유")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = None):

        if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            await interaction.response.send_message("저 분은 님보다 높아서 조용히 시킬 수 없어요! ( >﹏< )", ephemeral=True)
            return

        if member.top_role >= interaction.guild.me.top_role:
             await interaction.response.send_message("저 분은 저보다 높거나 같아서 조용히 시킬 수 없어요! ( >﹏< )", ephemeral=True)
             return

        if member == interaction.guild.owner:
             await interaction.response.send_message("서버 사장님은 조용히 시킬 수 없어요! ( >﹏< )", ephemeral=True)
             return

        duration_seconds = None
        try:
            duration_seconds = self.parse_duration(duration)
            if duration_seconds > 28 * 24 * 3600:
                await interaction.response.send_message("너무 길어요! 최대 28일까지만 가능해요. (´。＿。｀)", ephemeral=True)
                return
        except ValueError:
             await interaction.response.send_message("시간 형식이 이상해요! 예: 10m, 2h, 1d 이렇게 써줘요! (・ω・)", ephemeral=True)
             return

        try:
            await member.timeout(
                discord.utils.utcnow() + timedelta(seconds=duration_seconds),
                reason=reason,
            )
            duration_str = self.format_duration(duration_seconds)

            embed = discord.Embed(title="🔇 쉿! 조용히 하세요!", color=discord.Color.yellow())
            embed.add_field(name="사용자", value=f"{member} ({member.id})", inline=True)
            embed.add_field(name="관리자", value=interaction.user.mention, inline=True)
            embed.add_field(name="기간", value=duration_str, inline=True)
            embed.add_field(name="사유", value=reason or "사유 없음", inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(
                text=f"ID: {member.id} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            await interaction.response.send_message(embed=embed)

            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f"뮤트 실패했어요...: {e}", ephemeral=True)

    @app_commands.command(name="뮤트해제", description="다시 말하게 해줘요!")
    @app_commands.describe(member="해제할 사람", reason="사유")
    @app_commands.rename(member="멤버", reason="사유")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):

        try:
            await member.timeout(None, reason=reason)
            embed = discord.Embed(
                title="🔊 이제 말해도 돼요!", color=discord.Color.green()
            )
            embed.add_field(name="사용자", value=f"{member} ({member.id})", inline=True)
            embed.add_field(name="관리자", value=interaction.user.mention, inline=True)
            embed.add_field(name="사유", value=reason or "사유 없음", inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(
                text=f"ID: {member.id} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            await interaction.response.send_message(embed=embed)

            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f"뮤트를 풀어주지 못했어요...: {e}", ephemeral=True)

    @app_commands.command(name="청소", description="지저분한 메시지들을 싹 치워요!")
    @app_commands.describe(amount="지울 개수", member="특정 유저 메시지만 삭제")
    @app_commands.rename(amount="수량", member="멤버")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int, member: Optional[discord.Member] = None):

        if amount < 1 or amount > 500:
            await interaction.response.send_message("한 번에 1~500개까지만 치울 수 있어요! ( >﹏< )", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        def check(msg):
            if member:
                return msg.author == member
            return True

        try:
            deleted = await interaction.channel.purge(limit=amount, check=check)

            embed = discord.Embed(
                title="🧹 싹싹! 청소 끝!",
                color=discord.Color.blue(),
                description=f"{len(deleted)}개의 메시지를 치웠어요! (✿◡‿◡)",
            )
            embed.add_field(name="채널", value=interaction.channel.mention, inline=True)
            if member:
                embed.add_field(name="대상 사용자", value=member.mention, inline=True)
            embed.set_footer(
                text=f"관리자: {interaction.user} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            await interaction.followup.send(embed=embed)

            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"청소하다가 넘어졌어요...: {e}")

    @app_commands.command(name="슬로우모드", description="채널을 천천히 걷게 해요...")
    @app_commands.describe(seconds="딜레이 시간 (초)")
    @app_commands.rename(seconds="시간_초")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int):

        if seconds < 0 or seconds > 21600:
             await interaction.response.send_message("0~21600초(6시간) 사이로만 설정해줘요! (・ω・)", ephemeral=True)
             return

        try:
            await interaction.channel.edit(slowmode_delay=seconds)
            if seconds == 0:
                await interaction.response.send_message(
                    f"✅ {interaction.channel.mention} 이제 마음껏 채팅해요! (✿◡‿◡)"
                )
            else:
                 await interaction.response.send_message(
                    f"✅ {interaction.channel.mention} 이제 {seconds}초마다 한 마디씩만 가능해요! ( •̀ ω •́ )✧"
                )
        except Exception as e:
            await interaction.response.send_message(f"슬로우모드를 걸지 못했어요...: {e}", ephemeral=True)

    @app_commands.command(name="경고", description="유저에게 경고를 줍니다. (3회 누적 시 1시간 뮤트)")
    @app_commands.describe(member="경고할 멤버", reason="사유")
    @app_commands.rename(member="멤버", reason="사유")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "사유 없음"):

        if member.bot:
            await interaction.response.send_message("봇에게는 경고를 줄 수 없어요! 🤖", ephemeral=True)
            return

        await db.add_warning(str(member.id), str(interaction.guild.id), str(interaction.user.id), reason)
        count = await db.get_warning_count(str(member.id))

        embed = discord.Embed(title="⚠️ 경고 발부!", color=discord.Color.orange())
        embed.add_field(name="대상", value=f"{member.mention} ({member.id})", inline=True)
        embed.add_field(name="관리자", value=interaction.user.mention, inline=True)
        embed.add_field(name="누적 경고", value=f"**{count}**회", inline=True)
        embed.add_field(name="사유", value=reason, inline=False)
        embed.set_footer(text=f"발부 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await interaction.response.send_message(embed=embed)

        if count % 3 == 0:
            try:
                duration = timedelta(hours=1)
                await member.timeout(discord.utils.utcnow() + duration, reason="경고 3회 누적 자동 뮤트")
                await interaction.followup.send(f"🚫 **경고 {count}회 누적**으로 {member.mention}님을 1시간 동안 조용히 시켰어요!")
            except Exception as e:
                await interaction.followup.send(f"⚠️ 자동 뮤트 실패: {e}")

    @app_commands.command(name="경고내역", description="유저의 경고 내역을 확인합니다.")
    @app_commands.describe(member="확인할 멤버")
    @app_commands.rename(member="멤버")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):

        logs = await db.get_warning_logs(str(member.id))
        count = await db.get_warning_count(str(member.id))

        if not logs:
            await interaction.response.send_message(f"{member.mention}님은 경고를 받은 적이 없어요! 😇")
            return

        embed = discord.Embed(title=f"📜 {member.display_name}님의 경고 내역 (총 {count}회)", color=discord.Color.yellow())

        for log in logs[:10]:
            mod = interaction.guild.get_member(int(log['mod_id']))
            mod_name = mod.display_name if mod else "Unknown"
            ts = datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %H:%M')
            embed.add_field(name=f"⚠️ {ts} (By {mod_name})", value=log['reason'], inline=False)

        if len(logs) > 10:
            embed.set_footer(text=f"외 {len(logs)-10}개의 내역이 더 있어요.")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="경고취소", description="유저의 경고를 1회 차감합니다.")
    @app_commands.describe(member="취소할 멤버", count="차감할 횟수 (기본 1회)")
    @app_commands.rename(member="멤버", count="횟수")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unwarn(self, interaction: discord.Interaction, member: discord.Member, count: int = 1):

        if count < 1:
            await interaction.response.send_message("1 이상의 숫자를 입력해주세요!", ephemeral=True)
            return

        current = await db.get_warning_count(str(member.id))
        if current == 0:
            await interaction.response.send_message("이 유저는 경고가 없어요! ✨", ephemeral=True)
            return

        await db.remove_warning(str(member.id), count)
        new_count = await db.get_warning_count(str(member.id))

        await interaction.response.send_message(f"✅ {member.mention}님의 경고를 **{count}회** 차감했어요! (현재: {new_count}회)")

    @staticmethod
    def parse_duration(duration: str) -> int:

        unit = duration[-1]
        if not unit.isalpha():
             return int(duration)

        value = int(duration[:-1])

        if unit == "s":
            return value
        elif unit == "m":
            return value * 60
        elif unit == "h":
            return value * 3600
        elif unit == "d":
            return value * 86400
        else:
            raise ValueError("Invalid unit")

    @staticmethod
    def format_duration(seconds: int) -> str:

        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}일")
        if hours > 0:
            parts.append(f"{hours}시간")
        if minutes > 0:
            parts.append(f"{minutes}분")

        return " ".join(parts) if parts else "1분 미만"

async def setup(bot):
    await bot.add_cog(Moderation(bot))