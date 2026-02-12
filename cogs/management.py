import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils import db
import utils.time_utils as time_utils
from datetime import datetime, timedelta
from typing import Optional
class Management(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_season_reset.start()
    def cog_unload(self):
        self.check_season_reset.cancel()
    @tasks.loop(hours=1)
    async def check_season_reset(self):
        now = time_utils.get_kst_now()
        today_str = now.strftime("%Y-%m-%d")
        is_reset_month = now.month % 2 == 0
        is_reset_day = now.day == 1
        target_date = now + timedelta(days=5)
        is_notice_day = (target_date.month % 2 == 0) and (target_date.day == 1)
        if is_reset_month and is_reset_day:
            last_reset = await db.get_system_state("last_reset_date")
            if last_reset != today_str:
                season_name = f"{now.year}년 {now.month}월 시즌"
                await db.reset_season_data(season_name)
                await db.set_system_state("last_reset_date", today_str)
                embed = discord.Embed(
                    title="🌱 새로운 시즌이 시작되었습니다!",
                    description=f"**{season_name}**이 시작되었습니다!\n모든 교주님들의 자산, 호감도, 펫 등이 초기화되었습니다.\n새로운 마음으로 요미와 함께 다시 시작해봐요! (≧◡≦)",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
                embed.add_field(name="📅 시즌 기간", value="2개월", inline=True)
                embed.add_field(name="⚠️ 초기화 항목", value="돈, 호감도, 펫, 인벤토리, 던전 진행도", inline=True)
                embed.set_footer(text="지나친 경쟁과 인플레이션 방지를 위한 조치입니다.")
                for guild in self.bot.guilds:
                    channel = await self.get_log_channel(guild)
                    if not channel:
                        channel = guild.system_channel
                        if not channel:
                            for c in guild.text_channels:
                                if c.permissions_for(guild.me).send_messages:
                                    channel = c
                                    break
                    if channel:
                        try:
                            await channel.send(embed=embed)
                        except:
                            pass
        elif is_notice_day:
            last_notice = await db.get_system_state("last_reset_notice_date")
            if last_notice != today_str:
                await db.set_system_state("last_reset_notice_date", today_str)
                next_season_name = f"{target_date.year}년 {target_date.month}월 시즌"
                embed = discord.Embed(
                    title="⚠️ 시즌 초기화 사전 안내",
                    description=f"5일 뒤(**{target_date.strftime('%m월 %d일')}**)부터 **{next_season_name}**이 시작됩니다!\n현재 시즌의 모든 데이터가 초기화될 예정이니 참고해 주세요.",
                    color=discord.Color.orange()
                )
                embed.add_field(name="⏰ 초기화 일시", value=f"{target_date.strftime('%Y-%m-%d')} 00:00 예정", inline=False)
                embed.add_field(name="🔄 초기화 대상", value="자산, 호감도, 펫, 인벤토리 등 모든 성장 데이터", inline=False)
                embed.set_footer(text="새로운 시즌을 맞이할 준비를 해주세요! ( •̀ ω •́ )✧")
                for guild in self.bot.guilds:
                    channel = await self.get_log_channel(guild)
                    if not channel:
                        channel = guild.system_channel
                        if not channel:
                            for c in guild.text_channels:
                                if c.permissions_for(guild.me).send_messages:
                                    channel = c
                                    break
                    if channel:
                        try:
                            await channel.send(embed=embed)
                        except:
                            pass
    @check_season_reset.before_loop
    async def before_check_season_reset(self):
        await self.bot.wait_until_ready()
    async def get_log_channel(self, guild):
        log_channel_id = await db.get_guild_setting(str(guild.id), "log_channel")
        if log_channel_id:
            return guild.get_channel(int(log_channel_id))
        return None
    @app_commands.command(name="시즌관리", description="시즌 시스템 관리 명령어입니다.")
    @app_commands.describe(action="수행할 작업 (강제초기화/공지테스트/상태확인)")
    @app_commands.choices(action=[
        app_commands.Choice(name="강제 초기화 (주의!)", value="reset"),
        app_commands.Choice(name="공지 테스트", value="notice"),
        app_commands.Choice(name="상태 확인", value="status")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_season(self, interaction: discord.Interaction, action: str):
        if action == "status":
            last_reset = await db.get_system_state("last_reset_date", "기록 없음")
            last_notice = await db.get_system_state("last_reset_notice_date", "기록 없음")
            current_season = await db.get_system_state("current_season", "알 수 없음")
            embed = discord.Embed(title="📊 시즌 시스템 상태", color=discord.Color.blue())
            embed.add_field(name="현재 시즌", value=current_season, inline=False)
            embed.add_field(name="마지막 초기화", value=last_reset, inline=True)
            embed.add_field(name="마지막 공지", value=last_notice, inline=True)
            now = time_utils.get_kst_now()
            next_month = now.month + 1
            year = now.year
            if next_month > 12:
                next_month = 1
                year += 1
            while next_month % 2 != 0:
                next_month += 1
                if next_month > 12:
                    next_month = 1
                    year += 1
            next_reset = datetime(year, next_month, 1)
            embed.add_field(name="다음 초기화 예정", value=next_reset.strftime("%Y-%m-%d"), inline=False)
            await interaction.response.send_message(embed=embed)
        elif action == "reset":
            if not await self.bot.is_owner(interaction.user):
                await interaction.response.send_message("❌ 이 기능은 봇 개발자만 사용할 수 있어요!", ephemeral=True)
                return
            view = SeasonResetConfirm(interaction.user.id)
            await interaction.response.send_message(
                "⚠️ **정말로 시즌을 초기화하시겠습니까?**\n모든 유저의 데이터가 삭제되며 되돌릴 수 없습니다!",
                view=view,
                ephemeral=True
            )
            await view.wait()
            if view.value:
                now = time_utils.get_kst_now()
                season_name = f"{now.year}년 {now.month}월 시즌 (강제)"
                await db.reset_season_data(season_name)
                await db.set_system_state("last_reset_date", now.strftime("%Y-%m-%d"))
                await interaction.followup.send("✅ 시즌이 강제로 초기화되었습니다.")
            else:
                await interaction.followup.send("취소되었습니다.")
        elif action == "notice":
            target_date = time_utils.get_kst_now() + timedelta(days=5)
            next_season_name = f"{target_date.year}년 {target_date.month}월 시즌"
            embed = discord.Embed(
                title="[테스트] ⚠️ 시즌 초기화 사전 안내",
                description=f"5일 뒤(**{target_date.strftime('%m월 %d일')}**)부터 **{next_season_name}**이 시작됩니다!\n현재 시즌의 모든 데이터가 초기화될 예정이니 참고해 주세요.",
                color=discord.Color.orange()
            )
            embed.add_field(name="⏰ 초기화 일시", value=f"{target_date.strftime('%Y-%m-%d')} 00:00 예정", inline=False)
            embed.add_field(name="🔄 초기화 대상", value="자산, 호감도, 펫, 인벤토리 등 모든 성장 데이터", inline=False)
            embed.set_footer(text="새로운 시즌을 맞이할 준비를 해주세요! ( •̀ ω •́ )✧")
            await interaction.response.send_message(embed=embed)
    @app_commands.command(name="채널생성", description="새로운 채널을 만들어줄게요! (✿◡‿◡)")
    @app_commands.describe(name="채널 이름", channel_type="채널 유형 (text/voice)")
    @app_commands.rename(name="이름", channel_type="유형")
    @app_commands.choices(channel_type=[
        app_commands.Choice(name="텍스트", value="text"),
        app_commands.Choice(name="음성", value="voice")
    ])
    @app_commands.checks.has_permissions(manage_channels=True)
    async def create_channel(self, interaction: discord.Interaction, name: str, channel_type: str = "text"):
        try:
            if channel_type == "text":
                channel = await interaction.guild.create_text_channel(name)
            else:
                channel = await interaction.guild.create_voice_channel(name)
            embed = discord.Embed(title="➕ 채널 생성 완료!", color=discord.Color.green())
            embed.add_field(name="이름", value=channel.name, inline=True)
            embed.add_field(
                name="유형",
                value="텍스트" if isinstance(channel, discord.TextChannel) else "음성",
                inline=True,
            )
            embed.add_field(
                name="카테고리",
                value=channel.category.name if channel.category else "없음",
                inline=True,
            )
            embed.set_footer(
                text=f"관리자: {interaction.user} • {time_utils.get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await interaction.response.send_message(embed=embed)
            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"힝... 채널을 만들다가 오류가 났어요: {e} (｡•́︿•̀｡)", ephemeral=True)
    @app_commands.command(name="채널삭제", description="채널을 없애버려요...!")
    @app_commands.describe(channel="삭제할 채널")
    @app_commands.rename(channel="채널")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def delete_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):
        if channel == interaction.channel:
            await interaction.response.send_message("현재 채널은 삭제할 수 없어요! (´。＿。｀)", ephemeral=True)
            return
        try:
            embed = discord.Embed(title="🗑️ 채널 삭제 완료...", color=discord.Color.red())
            embed.add_field(name="이름", value=channel.name, inline=True)
            embed.add_field(
                name="유형",
                value="텍스트" if isinstance(channel, discord.TextChannel) else "음성",
                inline=True,
            )
            embed.add_field(
                name="카테고리",
                value=channel.category.name if channel.category else "없음",
                inline=True,
            )
            embed.set_footer(
                text=f"관리자: {interaction.user} • {time_utils.get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await channel.delete()
            await interaction.response.send_message(embed=embed)
            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"채널을 삭제하지 못했어요...: {e} (｡•́︿•̀｡)", ephemeral=True)
    @app_commands.command(name="채널잠금", description="채널을 꽁꽁 잠급니다!")
    @app_commands.describe(channel="잠글 채널 (비워두면 현재 채널)")
    @app_commands.rename(channel="채널")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock_channel(self, interaction: discord.Interaction, channel: Optional[discord.abc.GuildChannel] = None):
        channel = channel or interaction.channel
        try:
            if isinstance(channel, discord.TextChannel):
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(
                        send_messages=False
                    )
                }
                await channel.edit(overwrites=overwrites)
                embed = discord.Embed(
                    title="🔒 채널 잠금",
                    color=discord.Color.orange(),
                    description=f"{channel.mention}을(를) 잠갔어요! 아무도 말 못 해요! ( •̀ ω •́ )✧",
                )
                embed.set_footer(
                    text=f"관리자: {interaction.user} • {time_utils.get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                await interaction.response.send_message(embed=embed)
                log_channel = await self.get_log_channel(interaction.guild)
                if log_channel:
                    await log_channel.send(embed=embed)
            else:
                 await interaction.response.send_message("텍스트 채널만 잠글 수 있어요!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"채널을 잠그는데 실패했어요...: {e}", ephemeral=True)
    @app_commands.command(name="잠금해제", description="채널 족쇄를 풀어줍니다!")
    @app_commands.describe(channel="풀어줄 채널 (비워두면 현재 채널)")
    @app_commands.rename(channel="채널")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock_channel(self, interaction: discord.Interaction, channel: Optional[discord.abc.GuildChannel] = None):
        channel = channel or interaction.channel
        try:
            if isinstance(channel, discord.TextChannel):
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(
                        send_messages=None
                    )
                }
                await channel.edit(overwrites=overwrites)
                embed = discord.Embed(
                    title="🔓 채널 잠금 해제",
                    color=discord.Color.green(),
                    description=f"{channel.mention}이(가) 풀려났어요! 이제 자유예요! (✿◡‿◡)",
                )
                embed.set_footer(
                    text=f"관리자: {interaction.user} • {time_utils.get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                await interaction.response.send_message(embed=embed)
                log_channel = await self.get_log_channel(interaction.guild)
                if log_channel:
                    await log_channel.send(embed=embed)
            else:
                await interaction.response.send_message("텍스트 채널만 잠금 해제할 수 있어요!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"잠금 해제에 실패했어요...: {e}", ephemeral=True)
    @app_commands.command(name="역할생성", description="새로운 역할을 뚝딱뚝딱 만들어요!")
    @app_commands.describe(name="역할 이름", color="색상 (Hex 코드 또는 영문 이름)")
    @app_commands.rename(name="이름", color="색상")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def create_role(self, interaction: discord.Interaction, name: str, color: Optional[str] = None):
        try:
            role_color = None
            if color:
                if color.startswith("#"):
                    role_color = discord.Color(int(color[1:], 16))
                else:
                    role_color = getattr(
                        discord.Color, color.lower(), discord.Color.default
                    )()
            role = await interaction.guild.create_role(name=name, color=role_color)
            embed = discord.Embed(
                title="📜 역할 생성 완료!", color=role.color or discord.Color.blue()
            )
            embed.add_field(name="이름", value=role.name, inline=True)
            embed.add_field(name="색상", value=str(role.color), inline=True)
            embed.add_field(
                name="멘션 가능",
                value="예" if role.mentionable else "아니오",
                inline=True,
            )
            embed.add_field(name="위치", value=role.position, inline=True)
            embed.set_footer(
                text=f"관리자: {interaction.user} • {time_utils.get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await interaction.response.send_message(embed=embed)
            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"역할을 만들지 못했어요...: {e}", ephemeral=True)
    @app_commands.command(name="역할삭제", description="필요 없는 역할을 지워버려요!")
    @app_commands.describe(role="삭제할 역할")
    @app_commands.rename(role="역할")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def delete_role(self, interaction: discord.Interaction, role: discord.Role):
        if role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            await interaction.response.send_message("자신보다 높거나 같은 역할은 삭제할 수 없어요! ( >﹏< )", ephemeral=True)
            return
        try:
            embed = discord.Embed(title="🗑️ 역할 삭제 완료...", color=discord.Color.red())
            embed.add_field(name="이름", value=role.name, inline=True)
            embed.add_field(name="색상", value=str(role.color), inline=True)
            embed.add_field(name="가진 사용자 수", value=len(role.members), inline=True)
            embed.set_footer(
                text=f"관리자: {interaction.user} • {time_utils.get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await role.delete()
            await interaction.response.send_message(embed=embed)
            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"역할을 삭제하지 못했어요...: {e}", ephemeral=True)
    @app_commands.command(name="역할해제", description="사용자의 역할을 뺏어요...!")
    @app_commands.describe(member="뺏을 사람", role="뺏을 역할")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_role(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            await interaction.response.send_message("자신보다 높거나 같은 역할은 뺏을 수 없어요! ( >﹏< )", ephemeral=True)
            return
        if role not in member.roles:
            await interaction.response.send_message(f"{member.mention}님은 {role.mention} 역할을 가지고 있지 않아요!", ephemeral=True)
            return
        try:
            await member.remove_roles(role)
            embed = discord.Embed(title="❌ 역할 해제 완료...", color=discord.Color.red())
            embed.add_field(name="사용자", value=f"{member} ({member.id})", inline=True)
            embed.add_field(name="역할", value=role.mention, inline=True)
            embed.add_field(name="관리자", value=interaction.user.mention, inline=True)
            embed.set_footer(
                text=f"ID: {member.id} • {time_utils.get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await interaction.response.send_message(embed=embed)
            log_channel = await self.get_log_channel(interaction.guild)
            if log_channel:
                await log_channel.send(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"역할을 뺏지 못했어요...: {e}", ephemeral=True)
    @app_commands.command(name="닉네임", description="사용자의 닉네임을 바꿔줘요!")
    @app_commands.describe(member="대상", nickname="새로운 닉네임 (비워두면 초기화)")
    @app_commands.rename(member="대상", nickname="닉네임")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def nickname(self, interaction: discord.Interaction, member: discord.Member, nickname: Optional[str] = None):
        if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            await interaction.response.send_message("자신보다 높거나 같은 역할을 가진 사용자의 닉네임은 건들 수 없어요! ( >﹏< )", ephemeral=True)
            return
        try:
            await member.edit(nick=nickname)
            if nickname:
                await interaction.response.send_message(
                    f"짜잔! {member.mention}님의 닉네임을 `{nickname}`(으)로 바꿨어요! (｡•̀ᴗ-)✧"
                )
            else:
                await interaction.response.send_message(f"{member.mention}님의 닉네임이 원래대로 돌아왔어요! (✿◡‿◡)")
        except Exception as e:
            await interaction.response.send_message(f"닉네임을 바꾸지 못했어요...: {e}", ephemeral=True)
class SeasonResetConfirm(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.value = None
    @discord.ui.button(label="초기화 실행", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        self.value = True
        self.stop()
        await interaction.response.defer()
    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        self.value = False
        self.stop()
        await interaction.response.defer()
async def setup(bot):
    await bot.add_cog(Management(bot))