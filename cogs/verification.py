import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import time
import datetime
from utils import db, captcha_manager
import io
class VerificationModal(discord.ui.Modal, title="보안 인증 절차"):
    answer = discord.ui.TextInput(
        label="확인 코드",
        placeholder="이미지에 표시된 문자를 정확히 입력해주세요.",
        required=True,
        max_length=10
    )
    def __init__(self, cog, session_data):
        super().__init__()
        self.cog = cog
        self.session_data = session_data
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        if user_id not in self.cog.verification_sessions:
            await interaction.followup.send("⚠️ 인증 세션이 만료되었습니다. '인증 시작' 버튼을 다시 눌러주세요.", ephemeral=True)
            return
        session = self.cog.verification_sessions[user_id]
        user_input = self.answer.value.strip().upper()
        if user_input == session["text"]:
            role_id = int(session["role_id"])
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    success_embed = discord.Embed(
                        title="✅ 인증 완료",
                        description=f"{interaction.user.mention}님, 본인 인증이 성공적으로 완료되었습니다.\n이제 서버의 모든 기능을 이용하실 수 있습니다.",
                        color=discord.Color.green(),
                        timestamp=datetime.datetime.now()
                    )
                    if interaction.guild.icon:
                        success_embed.set_thumbnail(url=interaction.guild.icon.url)
                    await interaction.followup.send(embed=success_embed, ephemeral=True)
                    settings = await db.get_verification_settings(str(interaction.guild.id))
                    log_channel_id = settings.get("verify_log_channel_id")
                    if log_channel_id:
                        log_channel = interaction.guild.get_channel(int(log_channel_id))
                        if log_channel:
                            log_embed = discord.Embed(
                                title="🛡️ 인증 로그",
                                description=f"**사용자:** {interaction.user.mention} ({interaction.user.id})\n**처리 결과:** 인증 성공\n**일시:** <t:{int(time.time())}:F>",
                                color=discord.Color.blue()
                            )
                            log_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                            await log_channel.send(embed=log_embed)
                    welcome_ch_id = settings.get("verify_welcome_channel_id")
                    welcome_msg = settings.get("verify_welcome_msg")
                    if welcome_ch_id:
                        wel_ch = interaction.guild.get_channel(int(welcome_ch_id))
                        if wel_ch:
                            if not welcome_msg:
                                welcome_msg = f"환영합니다, {interaction.user.mention}님! 인증을 마치고 합류하셨어요! 🎉"
                            content = welcome_msg.replace("{user}", interaction.user.mention).replace("{server}", interaction.guild.name).replace("{count}", str(interaction.guild.member_count))
                            await wel_ch.send(content)
                except discord.Forbidden:
                    await interaction.followup.send("❌ 역할 지급 권한이 부족합니다. 관리자에게 문의해주세요.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"❌ 시스템 오류가 발생했습니다: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send("❌ 설정된 인증 역할을 찾을 수 없습니다. 관리자에게 문의해주세요.", ephemeral=True)
            if user_id in self.cog.verification_sessions:
                del self.cog.verification_sessions[user_id]
        else:
            session["attempts"] = session.get("attempts", 0) + 1
            remaining = 5 - session["attempts"]
            if remaining > 0:
                fail_embed = discord.Embed(
                    title="⚠️ 인증 실패",
                    description=f"입력하신 코드가 일치하지 않습니다.\n남은 시도 횟수: **{remaining}회**",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=fail_embed, ephemeral=True)
            else:
                fail_embed = discord.Embed(
                    title="🚫 인증 제한됨",
                    description="5회 연속 실패하여 인증 세션이 종료되었습니다.\n잠시 후 다시 시도해주세요.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=fail_embed, ephemeral=True)
                del self.cog.verification_sessions[user_id]
class VerificationSessionView(discord.ui.View):
    def __init__(self, cog, session_data):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_data = session_data
    @discord.ui.button(label="코드 입력하기", style=discord.ButtonStyle.primary, emoji="⌨️")
    async def enter_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.cog.verification_sessions:
            await interaction.response.send_message("⚠️ 세션이 만료되었습니다. 다시 시작해주세요.", ephemeral=True)
            return
        await interaction.response.send_modal(VerificationModal(self.cog, self.session_data))
    @discord.ui.button(label="이미지 새로고침", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh_captcha(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        if user_id not in self.cog.verification_sessions:
            await interaction.followup.send("⚠️ 세션이 만료되었습니다. 다시 시작해주세요.", ephemeral=True)
            return
        text = captcha_manager.generate_random_text()
        self.cog.verification_sessions[user_id]["text"] = text
        image_data = await asyncio.to_thread(captcha_manager.generate_captcha_image, text)
        file = discord.File(image_data, filename="captcha.png")
        embed = discord.Embed(
            title="보안 문자 확인",
            description=f"{interaction.user.mention}님, 아래 이미지에 표시된 문자를 확인 후 입력해주세요.\n(대소문자는 구분하지 않습니다)",
            color=discord.Color.light_gray()
        )
        embed.set_image(url="attachment://captcha.png")
        embed.set_footer(text="제한 시간: 5분 이내 입력")
        await interaction.edit_original_response(embed=embed, attachments=[file], view=self)
    @discord.ui.button(label="종료", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.cog.verification_sessions:
            del self.cog.verification_sessions[interaction.user.id]
        await interaction.response.edit_message(content="🚫 인증 절차가 취소되었습니다.", embed=None, attachments=[], view=None)
class VerificationView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
    @discord.ui.button(label="인증 시작하기", style=discord.ButtonStyle.success, emoji="🛡️", custom_id="verification_view:start")
    async def start_verification(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("이 기능은 서버 내에서만 사용할 수 있습니다.", ephemeral=True)
            return
        settings = await db.get_verification_settings(str(interaction.guild.id))
        role_id = settings.get("verify_role_id")
        if not role_id:
            await interaction.followup.send("⚠️ 인증 역할이 설정되지 않았습니다. 관리자에게 문의해주세요.", ephemeral=True)
            return
        role = interaction.guild.get_role(int(role_id))
        if role and role in interaction.user.roles:
             await interaction.followup.send("✅ 이미 인증이 완료된 사용자입니다.", ephemeral=True)
             return
        if interaction.user.id in self.cog.verification_sessions:
            pass
        text = captcha_manager.generate_random_text()
        image_data = await asyncio.to_thread(captcha_manager.generate_captcha_image, text)
        file = discord.File(image_data, filename="captcha.png")
        embed = discord.Embed(
            title="보안 문자 확인",
            description=f"{interaction.user.mention}님, 아래 이미지에 표시된 문자를 확인 후 입력해주세요.\n(대소문자는 구분하지 않습니다)",
            color=discord.Color.light_gray()
        )
        embed.set_image(url="attachment://captcha.png")
        embed.set_footer(text="제한 시간: 5분 이내 입력")
        session_data = {
            "text": text,
            "channel_id": interaction.channel.id,
            "role_id": role_id,
            "timestamp": asyncio.get_event_loop().time(),
            "attempts": 0
        }
        self.cog.verification_sessions[interaction.user.id] = session_data
        view = VerificationSessionView(self.cog, session_data)
        await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=True)
class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.verification_sessions = {}
        self.bot.add_view(VerificationView(self))
        self.cleanup_sessions.start()
    def cog_unload(self):
        self.cleanup_sessions.cancel()
    @tasks.loop(minutes=1)
    async def cleanup_sessions(self):
        current_time = asyncio.get_event_loop().time()
        expired_users = []
        for user_id, session in self.verification_sessions.items():
            if current_time - session["timestamp"] > 300:
                expired_users.append(user_id)
        for user_id in expired_users:
            del self.verification_sessions[user_id]
    @app_commands.command(name="인증설정", description="인증 시스템을 설정합니다.")
    @app_commands.describe(
        role="인증 완료 시 지급할 역할",
        channel="인증 패널을 보낼 채널 (선택)",
        log_channel="인증 로그를 남길 채널 (선택)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_verification(self, interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel = None, log_channel: discord.TextChannel = None):
        await db.set_verification_setting(str(interaction.guild.id), "verify_role_id", str(role.id))
        msg = f"✅ 인증 역할이 {role.mention}으로 설정되었습니다."
        if channel:
            await db.set_verification_setting(str(interaction.guild.id), "verify_channel_id", str(channel.id))
            msg += f"\n✅ 인증 채널이 {channel.mention}으로 설정되었습니다."
        if log_channel:
            await db.set_verification_setting(str(interaction.guild.id), "verify_log_channel_id", str(log_channel.id))
            msg += f"\n✅ 인증 로그 채널이 {log_channel.mention}으로 설정되었습니다."
        await interaction.response.send_message(msg, ephemeral=True)
    @app_commands.command(name="인증환영설정", description="인증 완료 시 보낼 환영 메시지를 설정합니다.")
    @app_commands.describe(channel="환영 메시지를 보낼 채널", message="보낼 메시지 내용 ({user}, {server}, {count} 사용 가능)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_verification_welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        await db.set_verification_setting(str(interaction.guild.id), "verify_welcome_channel_id", str(channel.id))
        await db.set_verification_setting(str(interaction.guild.id), "verify_welcome_msg", message)
        preview = message.replace("{user}", interaction.user.mention).replace("{server}", interaction.guild.name).replace("{count}", str(interaction.guild.member_count))
        await interaction.response.send_message(
            f"✅ **인증 환영 설정 완료!**\n**채널:** {channel.mention}\n**메시지 미리보기:**\n{preview}",
            ephemeral=True
        )
    @app_commands.command(name="인증패널", description="인증 버튼을 생성합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_verification_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ 본인 인증",
            description="서버의 원활한 이용을 위해 본인 인증이 필요합니다.\n아래 **'인증 시작'** 버튼을 눌러 인증을 진행해주세요.",
            color=discord.Color.from_rgb(47, 49, 54)
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text="안전한 서버 환경을 위해 협조 부탁드립니다.")
        view = VerificationView(self)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 인증 패널이 생성되었습니다.", ephemeral=True)
    @commands.Cog.listener()
    async def on_member_join(self, member):
        role_ids = await db.get_sticky_roles(str(member.guild.id), str(member.id))
        if role_ids:
            roles_to_add = []
            for rid in role_ids:
                role = member.guild.get_role(int(rid))
                if role and role.is_assignable():
                    roles_to_add.append(role)
            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason="고정 역할 복구 (Sticky Roles)")
                except Exception as e:
                    print(f"Failed to restore roles for {member}: {e}")
async def setup(bot):
    await bot.add_cog(Verification(bot))