import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import utils.db as db
import utils.time_utils as time_utils
from utils.logger import setup_logger
logger = setup_logger("Invite", "invite.log")
class Invite(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invites = {}
    async def cog_load(self):
        if self.bot.is_ready():
            for guild in self.bot.guilds:
                try:
                    current_invites = await guild.invites()
                    self.invites[guild.id] = {invite.code: invite.uses for invite in current_invites}
                except Exception as e:
                    logger.warning(f"Failed to load invites for {guild.name} in cog_load: {e}")
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                current_invites = await guild.invites()
                self.invites[guild.id] = {invite.code: invite.uses for invite in current_invites}
                logger.info(f"Loaded invites for {guild.name}")
            except Exception as e:
                logger.error(f"Failed to load invites for {guild.name}: {e}")
    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if invite.guild.id not in self.invites:
            self.invites[invite.guild.id] = {}
        self.invites[invite.guild.id][invite.code] = invite.uses
        logger.info(f"Invite created: {invite.code} in {invite.guild.name}")
    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild.id in self.invites:
            if invite.code in self.invites[invite.guild.id]:
                del self.invites[invite.guild.id][invite.code]
                logger.info(f"Invite deleted: {invite.code} in {invite.guild.name}")
    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        if guild.id not in self.invites:
            return
        try:
            current_invites = await guild.invites()
            used_invite = None
            for invite in current_invites:
                cached_uses = self.invites[guild.id].get(invite.code, 0)
                if invite.uses > cached_uses:
                    used_invite = invite
                    break
            self.invites[guild.id] = {invite.code: invite.uses for invite in current_invites}
            if used_invite:
                inviter = used_invite.inviter
                logger.info(f"{member} joined using {used_invite.code} by {inviter}")
                if inviter.id != member.id:
                    is_fake = 0
                    flag_reason = None
                    account_age = (time_utils.get_kst_now() - time_utils.to_kst(member.created_at)).days
                    if account_age < 3:
                        is_fake = 1
                        flag_reason = f"생성된 지 {account_age}일 됨 (최소 3일 필요)"
                    await db.add_invite_log(
                        str(inviter.id),
                        str(member.id),
                        used_invite.code,
                        member.created_at.timestamp(),
                        is_fake,
                        flag_reason
                    )
                    if is_fake:
                         logger.info(f"Suspicious invite detected: {member} (Reason: {flag_reason})")
            else:
                logger.info(f"{member} joined but no invite usage increment found (possibly vanity url or temporary invite)")
        except Exception as e:
            logger.error(f"Error in on_member_join invite tracking: {e}")
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await db.mark_user_left(str(member.id))
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        inviter_id = await db.get_inviter(str(message.author.id))
        if inviter_id:
            await db.mark_user_chatted(str(message.author.id))
    @app_commands.command(name="초대생성", description="친구를 초대할 수 있는 링크를 만들어요!")
    async def create_invite(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("이 명령어는 서버에서만 사용할 수 있어요!", ephemeral=True)
        try:
            channel = interaction.channel
            if not isinstance(channel, discord.TextChannel):
                channel = interaction.guild.system_channel or next((c for c in interaction.guild.text_channels), None)
            if not channel:
                return await interaction.response.send_message("초대장을 만들 채널을 찾을 수 없어요.", ephemeral=True)
            invite = await channel.create_invite(max_age=0, max_uses=0, unique=True, reason=f"{interaction.user}님의 요청")
            embed = discord.Embed(
                title="💌 초대장이 생성되었어요!",
                description=f"친구들에게 이 링크를 보내주세요!\n{invite.url}",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"요청자: {interaction.user}")
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"초대장을 만드는 중 오류가 발생했어요: {e}", ephemeral=True)
    @app_commands.command(name="초대현황", description="내가 초대한 친구 수를 확인해요!")
    async def my_invites(self, interaction: discord.Interaction):
        counts = await db.get_invites_count(str(interaction.user.id))
        valid = counts["valid"]
        fake = counts["fake"]
        left = counts["left"]
        embed = discord.Embed(
            title=f"📊 {interaction.user.display_name}님의 초대 현황",
            color=discord.Color.blue()
        )
        embed.add_field(name="✅ 유효 초대", value=f"**{valid}명**", inline=True)
        embed.add_field(name="⚠️ 의심/가짜", value=f"{fake}명", inline=True)
        embed.add_field(name="🚪 나감", value=f"{left}명", inline=True)
        embed.add_field(
            name="ℹ️ 참고",
            value="생성된 지 3일 미만이거나 활동이 없는 계정은 '의심'으로 분류될 수 있어요.",
            inline=False
        )
        await interaction.response.send_message(embed=embed)
    @app_commands.command(name="초대랭킹", description="누가 가장 많이 초대했을까요?")
    async def invite_ranking(self, interaction: discord.Interaction):
        top_inviters = await db.get_top_inviters(limit=10)
        if not top_inviters:
            return await interaction.response.send_message("아직 초대한 사람이 없어요!", ephemeral=True)
        embed = discord.Embed(
            title="🏆 초대 랭킹 TOP 10 (유효 초대 기준)",
            color=discord.Color.gold()
        )
        description = ""
        for i, (user_id, count) in enumerate(top_inviters, 1):
            user = interaction.guild.get_member(int(user_id))
            name = user.display_name if user else "알 수 없는 사용자"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            description += f"{medal} **{name}**: {count}명\n"
        embed.description = description
        await interaction.response.send_message(embed=embed)
    @app_commands.command(name="초대권한", description="일반 유저들의 초대장 생성을 막거나 허용해요!")
    @app_commands.describe(status="차단할지 허용할지 선택해주세요")
    @app_commands.rename(status="상태")
    @app_commands.choices(status=[
        app_commands.Choice(name="🚫 모든 채널 차단 (에브리원 + 특정 역할)", value="block"),
        app_commands.Choice(name="✅ 모든 채널 허용", value="allow")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_invites_permission(self, interaction: discord.Interaction, status: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        everyone = guild.default_role
        target_role_id = 1361246024387002400
        target_role = guild.get_role(target_role_id)
        is_block = status == "block"
        success_count = 0
        fail_count = 0
        for channel in guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel)):
                try:
                    overwrites = channel.overwrites_for(everyone)
                    overwrites.create_instant_invite = False if is_block else None
                    await channel.set_permissions(everyone, overwrite=overwrites)
                    if target_role:
                        overwrites_role = channel.overwrites_for(target_role)
                        overwrites_role.create_instant_invite = False if is_block else None
                        await channel.set_permissions(target_role, overwrite=overwrites_role)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to update permission for channel {channel.name}: {e}")
                    fail_count += 1
        title = "🚫 초대장 생성 차단 완료!" if is_block else "✅ 초대장 생성 허용 완료!"
        color = discord.Color.red() if is_block else discord.Color.green()
        desc_list = [f"**@everyone** 권한 {'차단' if is_block else '복구'}됨"]
        if target_role:
            desc_list.append(f"**{target_role.name}** 권한 {'차단' if is_block else '복구'}됨")
        else:
            desc_list.append(f"(ID: {target_role_id} 역할을 찾을 수 없음)")
        desc = "\n".join(desc_list)
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.add_field(name="성공 채널 수", value=f"{success_count}개", inline=True)
        if fail_count > 0:
            embed.add_field(name="실패 채널 수", value=f"{fail_count}개 (권한 부족 등)", inline=True)
        embed.set_footer(text=f"관리자: {interaction.user} • {time_utils.get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}")
        await interaction.followup.send(embed=embed)
async def setup(bot):
    await bot.add_cog(Invite(bot))