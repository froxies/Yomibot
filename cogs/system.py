import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
import json
from utils import db

class System(commands.Cog):


    def __init__(self, bot):
        self.bot = bot
        self.bot.is_maintenance_mode = False
        self.change_status.start()

    def cog_unload(self):
        self.change_status.cancel()

    async def check_maintenance(self, interaction_or_ctx):

        if isinstance(interaction_or_ctx, discord.Interaction):
            user = interaction_or_ctx.user
            is_interaction = True
        else:
            user = interaction_or_ctx.author
            is_interaction = False

        if await self.bot.is_owner(user):
            return True

        if is_interaction:
            custom_id = interaction_or_ctx.data.get('custom_id', '')
            if custom_id and (custom_id.startswith('self_role:') or custom_id.startswith('verification_view:')):
                return True

        if getattr(self.bot, 'is_maintenance_mode', False):
            whitelist = await db.get_maintenance_whitelist()
            if str(user.id) in whitelist:
                return True

            reason = getattr(self.bot, 'maintenance_reason', '점검 중입니다.')
            end_time = getattr(self.bot, 'maintenance_end_time', None)

            embed = discord.Embed(title="🚫 **점검 중입니다** 🛠️", description="죄송합니다. 현재 봇 점검이 진행 중이에요.\n빠르게 작업을 마치고 돌아올게요! 잠시만 기다려주세요. (´。＿。｀)", color=discord.Color.red())
            embed.add_field(name="점검 사유", value=reason, inline=False)
            if end_time:
                embed.add_field(name="종료 예정", value=end_time, inline=False)

            if is_interaction:
                if not interaction_or_ctx.response.is_done():
                    await interaction_or_ctx.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction_or_ctx.send(embed=embed)
            return False

        return True

    @commands.Cog.listener()
    async def on_ready(self):

        if self.bot.user:
            print(f"{self.bot.user} 등장! ( •̀ ω •́ )✧")
            print(f"ID: {self.bot.user.id}")
            print(f"함께하는 서버 수: {len(self.bot.guilds)}")

            status = await db.get_maintenance_mode()
            self.bot.is_maintenance_mode = status['enabled']
            self.bot.maintenance_reason = status['reason']
            self.bot.maintenance_end_time = status['end_time']


            try:
                from cogs.roles import SelfRoleView
                self_role_messages = await db.get_all_self_role_messages()
                for msg_id, channel_id, guild_id, roles_data_raw, style in self_role_messages:
                    try:
                        roles_data = json.loads(roles_data_raw)
                        self.bot.add_view(SelfRoleView(roles_data, style=style), message_id=int(msg_id))
                    except Exception as e:
                        print(f"⚠️ 역할 지급 뷰 등록 실패 ({msg_id}): {e}")
            except ImportError:
                print("⚠️ cogs.roles 모듈을 찾을 수 없어 역할 지급 뷰를 복구하지 못했습니다.")
            except Exception as e:
                print(f"⚠️ 뷰 복구 중 오류: {e}")

            if self.bot.is_maintenance_mode:
                print(f"🛠️ 점검 모드로 시작합니다: {status['reason']}")
                if self.change_status.is_running():
                    self.change_status.cancel()
                await self.bot.change_presence(status=discord.Status.dnd, activity=discord.Game(f"점검 중... 🛠️"))
            else:
                if not self.change_status.is_running():
                    self.change_status.start()
        else:
            print("아직 준비 중이에요... (´。＿。｀)")

        self.bot.tree.interaction_check = self.check_maintenance
        self.bot.add_check(self.global_maintenance_check)

    async def global_maintenance_check(self, ctx):
        return await self.check_maintenance(ctx)

    @tasks.loop(seconds=60)
    async def change_status(self):

        if getattr(self.bot, 'is_maintenance_mode', False):
            return

        statuses = [
            "달님의 그늘 아래서 기다리는 중",
            "교주님과 산책 중 (✿◡‿◡)",
            "호박 스프 끓이는 중 (º﹃º )",
            "월광 아래의 가무 연습 중",
            "달바라기 교단에서 사제 업무 중",
            "모든 문의는 봇 DM을 통해서 진행해주세요!",
            "달이 비추는 곳이라면, 어디든지."
        ]
        status = random.choice(statuses)

        if self.bot.is_ready() and not self.bot.is_closed():
             try:
                await self.bot.change_presence(activity=discord.CustomActivity(name=status))
             except AttributeError:
                 pass
             except Exception as e:
                 print(f"Status Change Error: {e}")

    @change_status.before_loop
    async def before_change_status(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        print(f"새로운 친구들이 생겼어요!: {guild.name} (ID: {guild.id})")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        print(f"친구들과 헤어졌어요...: {guild.name} (ID: {guild.id})")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        welcome_channel_id = await db.get_guild_setting(str(member.guild.id), "welcome_channel")
        welcome_message = await db.get_guild_setting(str(member.guild.id), "welcome_message")

        if not welcome_message:
            welcome_message = "{mention} 님! **{server}**에 오신 것을 환영합니다~! 요미랑 같이 재미있게 놀아요! ✨ (✿◡‿◡)"

        if welcome_channel_id:
            channel = member.guild.get_channel(int(welcome_channel_id))
            if channel:
                message = welcome_message.replace("{mention}", member.mention)
                message = message.replace("{user}", str(member))
                message = message.replace("{server}", member.guild.name)
                try:
                    await channel.send(message)
                except discord.Forbidden:
                    print(f"권한 부족: {member.guild.name} ({member.guild.id}) 의 환영 채널에 메시지를 보낼 수 없습니다.")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        leave_channel_id = await db.get_guild_setting(str(member.guild.id), "leave_channel")
        leave_message = await db.get_guild_setting(str(member.guild.id), "leave_message")

        if not leave_message:
            leave_message = "**{user}** 님이 **{server}**을(를) 떠나셨어요... 요미는 여기서 기다리고 있을게요! (｡•́︿•̀｡)"

        if leave_channel_id:
            channel = member.guild.get_channel(int(leave_channel_id))
            if channel:
                message = leave_message.replace("{mention}", member.mention)
                message = message.replace("{user}", member.display_name)
                message = message.replace("{server}", member.guild.name)
                try:
                    await channel.send(message)
                except discord.Forbidden:
                    print(f"권한 부족: {member.guild.name} ({member.guild.id}) 의 퇴장 채널에 메시지를 보낼 수 없습니다.")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):

        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"그건 관리자님만 할 수 있어요! ( >﹏< )")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"뭔가 빠뜨리신 것 같아요! `{error.param.name}`를 꼭 써주세요! (・ω・)")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"어라? 뭔가 잘못 입력하신 것 같아요... {error}")
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.CheckFailure):
            pass
        else:
            print(f"Error: {error}")
            await ctx.send(f"으앙! 오류가 났어요! (｡•́︿•̀｡)\n내용: {error}")


    @commands.command(name="동기화", aliases=["sync"])
    @commands.is_owner()
    async def sync_command(self, ctx):

        msg = await ctx.send("동기화 중... ⏳")
        try:
            synced = await self.bot.tree.sync()
            await msg.edit(content=f"✅ {len(synced)}개의 명령어가 전역으로 동기화되었어요! ( •̀ ω •́ )✧\n(반영까지 최대 1시간이 걸릴 수 있어요)")
        except Exception as e:
            await msg.edit(content=f"❌ 동기화 실패: {e}")

    @commands.command(name="빠른동기화", aliases=["fsync", "qsync"])
    @commands.is_owner()
    async def fast_sync_command(self, ctx):

        msg = await ctx.send("이 서버에만 빠르게 동기화 중... ⏳")
        try:
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await msg.edit(content=f"✅ {len(synced)}개의 명령어가 이 서버에 동기화되었어요! 바로 사용할 수 있어요! ( •̀ ω •́ )✧")
        except Exception as e:
            await msg.edit(content=f"❌ 동기화 실패: {e}")

async def setup(bot):
    await bot.add_cog(System(bot))