
import discord
from discord.ext import commands
import sys
import os

import utils.db as db

class Admin(commands.Cog):


    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="리로드", aliases=["reload"], help="봇의 특정 모듈을 다시 로드해요. (개발자 전용)")
    @commands.is_owner()
    async def reload_extension(self, ctx, extension: str = None):

        import importlib
        import sys
        from dotenv import load_dotenv

        load_dotenv(override=True)
        status_msg = ["✅ **.env** 환경변수를 새로고침했어요."]

        if not extension:
            reloaded_utils = 0
            modules_to_reload = [m for m in sys.modules.keys() if m.startswith("utils.") or m == "korean_to_english"]

            for module_name in modules_to_reload:
                try:
                    if module_name in sys.modules:
                        importlib.reload(sys.modules[module_name])
                        reloaded_utils += 1
                except Exception as e:
                    print(f"Failed to reload {module_name}: {e}")

            if reloaded_utils > 0:
                status_msg.append(f"✅ **유틸리티 모듈** {reloaded_utils}개를 새로고침했어요.")

            count = 0
            for filename in os.listdir("cogs"):
                if filename.endswith(".py") and not filename.startswith("_"):
                    try:
                        await self.bot.reload_extension(f"cogs.{filename[:-3]}")
                        count += 1
                    except Exception as e:
                        await ctx.send(f"❌ `cogs.{filename[:-3]}` 로드 실패: {e}")

            status_msg.append(f"✅ 총 **{count}**개의 Cog 모듈을 새로고침했어요! ( •̀ ω •́ )✧")
            await ctx.send("\n".join(status_msg))
            return

        try:
            if not extension.startswith("cogs."):
                target = f"cogs.{extension}"
            else:
                target = extension

            await self.bot.reload_extension(target)
            await ctx.send(f"✅ **{target}** 모듈을 성공적으로 다시 로드했어요!\n(환경변수도 새로고침 되었어요)")
        except commands.ExtensionNotLoaded:
            try:
                await self.bot.load_extension(target)
                await ctx.send(f"✅ **{target}** 모듈을 새로 로드했어요! (기존에 로드되지 않음)")
            except Exception as e:
                await ctx.send(f"❌ 로드 실패: {e}")
        except Exception as e:
            await ctx.send(f"❌ 오류가 발생했어요: {e}")

    @commands.command(name="블랙", help="사용자를 블랙리스트에 추가해요. (개발자 전용)")
    @commands.is_owner()
    async def blacklist_user(self, ctx, user_id: str):

        try:
            if user_id.startswith("<@") and user_id.endswith(">"):
                user_id = user_id[2:-1]
                if user_id.startswith("!"):
                    user_id = user_id[1:]

            db.add_blacklist(user_id)
            await ctx.send(f"✅ {user_id} 사용자를 블랙리스트에 추가해요. 이제 요미가 대답하지 않을 거예요.")
        except Exception as e:
            await ctx.send(f"오류가 발생했어요: {e}")

    @commands.command(name="화이트", help="사용자를 블랙리스트에서 제거해요. (개발자 전용)")
    @commands.is_owner()
    async def whitelist_user(self, ctx, user_id: str):

        try:
            if user_id.startswith("<@") and user_id.endswith(">"):
                user_id = user_id[2:-1]
                if user_id.startswith("!"):
                    user_id = user_id[1:]

            await db.remove_blacklist(user_id)

            await db.reset_warnings(user_id)
            await ctx.send(f"✅ {user_id} 사용자를 블랙리스트에서 제거하고 경고 기록도 지웠어요. 이제 다시 친하게 지낼 수 있어요!")
        except Exception as e:
            await ctx.send(f"오류가 발생했어요: {e}")

    @commands.command(name="호감도조절", help="특정 유저의 호감도를 일정량만큼 더하거나 빼요. (개발자 전용)")
    @commands.is_owner()
    async def adjust_affinity(self, ctx, user: discord.User, amount: int):

        old = await db.get_affinity(str(user.id))
        await db.update_affinity(str(user.id), amount)
        new = await db.get_affinity(str(user.id))
        await ctx.send(f"✅ **{user.name}**님의 호감도를 조절했어요!\n전: `{old}` → 후: `{new}` (변동: `{amount:+}`)")

    @commands.command(name="호감도수정", aliases=["호감도설정"], help="특정 유저의 호감도를 특정 값으로 즉시 변경해요. (개발자 전용)")
    @commands.is_owner()
    async def set_affinity_cmd(self, ctx, user: discord.User, amount: int):

        await db.set_affinity(str(user.id), amount)
        await ctx.send(f"✅ **{user.name}**님의 호감도를 `{amount}`점으로 직접 수정 완료했어요! ( •̀ ω •́ )✧")

    @commands.command(name="대화채널", help="요미야 챗봇이 작동할 채널들을 설정해요. (쉼표로 구분, 개발자 전용)")
    @commands.is_owner()
    async def set_chat_channels(self, ctx, *, channels: str = None):

        if not channels:
            await db.set_setting("chatbot_channels", "")
            await ctx.send("✅ 모든 채널에서 요미와 대화할 수 있게 설정했어요!")
            return

        import re
        id_list = re.findall(r'\d{17,20}', channels)

        if not id_list:
             await ctx.send("❓ 유효한 채널을 입력해주세요.")
             return

        unique_ids = list(dict.fromkeys(id_list))

        final_val = ",".join(unique_ids)
        await db.set_setting("chatbot_channels", final_val)

        mentions = " ".join([f"<#{cid}>" for cid in unique_ids])
        count = len(unique_ids)

        if count > 1:
            await ctx.send(f"✅ 이제 요미는 **{count}개의 채널**({mentions})에서만 대답할 거예요! (｡•̀ᴗ-)✧")
        else:
            await ctx.send(f"✅ 이제 요미는 {mentions} 채널에서만 대답할 거예요! (｡•̀ᴗ-)✧")


    @commands.group(name="젤리관리", aliases=["젤리"], help="젤리 관리 명령어 모음 (개발자 전용)")
    @commands.is_owner()
    async def manage_jelly(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("사용법: !젤리 [지급/차감/설정] [유저] [금액]")

    @manage_jelly.command(name="지급")
    async def give_jelly(self, ctx, user: discord.User, amount: int):

        await db.update_balance(str(user.id), amount)
        await ctx.send(f"✅ **{user.name}**님에게 **{amount:,}** 젤리를 지급했어요! 🍬")

    @manage_jelly.command(name="차감")
    async def take_jelly(self, ctx, user: discord.User, amount: int):

        await db.update_balance(str(user.id), -amount)
        await ctx.send(f"✅ **{user.name}**님의 젤리를 **{amount:,}**개 차감했어요! 🍬")

    @manage_jelly.command(name="설정")
    async def set_jelly(self, ctx, user: discord.User, amount: int):

        await db.set_balance(str(user.id), amount)
        await ctx.send(f"✅ **{user.name}**님의 젤리를 **{amount:,}**개로 설정했어요! 🍬")


    @commands.group(name="긴급경제", aliases=["경제비상"], help="인플레이션 방지 및 경제 비상 조치 (개발자 전용)")
    @commands.is_owner()
    async def emergency_economy(self, ctx):
        if ctx.invoked_subcommand is None:
            total = await db.get_total_economy()
            await ctx.send(f"🚨 **긴급 경제 관리 시스템** 🚨\n현재 총 통화량: **{total:,}** 젤리\n\n사용법:\n`!긴급경제 세금 [비율(%)]` - 전 국민 재산 차감\n`!긴급경제 상한선 [금액]` - 빈부격차 해소 (최대 금액 제한)\n`!긴급경제 초기화` - **모든 경제 데이터 삭제 (주의)**")

    @emergency_economy.command(name="현황")
    async def economy_status(self, ctx):

        total = await db.get_total_economy()
        await ctx.send(f"📊 **현재 경제 현황**\n총 발행 젤리: **{total:,}** 젤리")





    @emergency_economy.command(name="초기화")
    async def reset_all_economy(self, ctx):

        await ctx.send(f"🛑 **치명적 경고** 🛑\n\n이 명령어는 **모든 유저의 돈, 아이템, 시장 데이터**를 영구적으로 삭제합니다.\n절대로 복구할 수 없습니다.\n\n정말로 진행하시겠습니까? 진행하려면 **'요미야 미안해 경제가 망해서 어쩔 수 없어 초기화 할게'** 라고 정확히 입력하세요.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content == "요미야 미안해 경제가 망해서 어쩔 수 없어 초기화 할게"

        try:
            await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("❌ 입력이 틀리거나 시간이 초과되어 안전하게 취소되었습니다.")
            return

        await db.reset_economy_all()

        now = datetime.now()
        season_name = f"{now.year}년 {now.month}월 시즌"

        embed = discord.Embed(
            title="🌱 새로운 시즌이 시작되었습니다!",
            description=f"**{season_name}**이 시작되었습니다!\n모든 교주님들의 자산, 호감도, 펫 등이 초기화되었습니다.\n새로운 마음으로 요미와 함께 다시 시작해봐요! (≧◡≦)",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.add_field(name="📅 시즌 기간", value="2개월", inline=True)
        embed.add_field(name="⚠️ 초기화 항목", value="돈, 호감도, 펫, 인벤토리, 던전 진행도", inline=True)
        embed.set_footer(text="지나친 경쟁과 인플레이션 방지를 위한 조치입니다.")

        target_channel_id = 1464817571621503079
        target_channel = self.bot.get_channel(target_channel_id)

        if target_channel:
            try:
                await target_channel.send(embed=embed)
                await ctx.send(f"✅ 초기화 완료! <#{target_channel_id}> 채널에 공지를 전송했습니다.")
            except Exception as e:
                await ctx.send(f"✅ 초기화 완료! 하지만 공지 채널 전송에 실패했습니다: {e}")
                await ctx.send(embed=embed)
        else:
            await ctx.send("✅ 초기화 완료! (공지 채널을 찾을 수 없어 이곳에 출력합니다)")
            await ctx.send(embed=embed)


    @commands.command(name="지식설정", help="요미의 커스텀 지식을 설정해요. (개발자 전용)")
    @commands.is_owner()
    async def set_knowledge(self, ctx, *, knowledge: str = None):

        if not knowledge:
            await db.set_setting("custom_knowledge", "")
            await ctx.send("✅ 요미의 커스텀 지식을 초기화했어요!")
            return

        await db.set_setting("custom_knowledge", knowledge)
        await ctx.send(f"✅ 요미에게 새로운 지식을 가르쳤어요!\n\n**[설정된 지식]**\n{knowledge}")

    @commands.command(name="지식확인", help="요미가 현재 알고 있는 커스텀 지식을 확인해요. (개발자 전용)")
    @commands.is_owner()
    async def view_knowledge(self, ctx):

        knowledge = await db.get_setting("custom_knowledge", "설정된 지식이 없어요.")
        await ctx.send(f"📚 **요미의 커스텀 지식**\n\n{knowledge}")

    @commands.command(name="일기채널", help="요미의 비밀 일기가 올라올 채널을 설정해요. (관리자 권한 필요)")
    @commands.has_permissions(administrator=True)
    async def set_diary_channel(self, ctx, *, channels: str = None):

        if not channels:
            db.set_setting("diary_channel_id", "")
            await ctx.send("✅ 일기 채널 설정이 해제되었습니다. 이제 비밀 일기가 올라오지 않아요.")
        else:
            clean_channels = ",".join([c.strip() for c in channels.replace(" ", "").split(",") if c.strip().isdigit() or (c.startswith("<#") and c.endswith(">"))])
            id_list = []
            for c in clean_channels.split(","):
                if c.startswith("<#"):
                    id_list.append(c[2:-1])
                else:
                    id_list.append(c)

            if not id_list or not clean_channels:
                 await ctx.send("❓ 유효한 채널을 입력해주세요.")
                 return

            final_val = ",".join(id_list)
            await db.set_setting("diary_channel_id", final_val)
            mentions = " ".join([f"<#{cid}>" for cid in id_list])
            await ctx.send(f"✅ 앞으로 요미의 비밀 일기는 {mentions} 채널에 올라가게 됩니다! (｡•̀ᴗ-)✧")

    @commands.command(name="일기작성", help="요미의 비밀 일기를 지금 바로 작성해요. (개발자 전용)")
    @commands.is_owner()
    async def force_diary(self, ctx):

        chatbot_cog = self.bot.get_cog("Chatbot")
        if chatbot_cog:
            msg = await ctx.send("📝 일기를 작성하고 있어요... (잠시만 기다려주세요!)")
            result = await chatbot_cog.write_diary_entry()

            if isinstance(result, tuple):
                success, reason = result
                if success:
                    await msg.edit(content=f"✅ {reason}")
                else:
                    await msg.edit(content=f"❌ {reason}")
            else:
                 await msg.edit(content="✅ 일기 작성이 완료되었어요! (채널을 확인해보세요)")
        else:
            await ctx.send("❌ 챗봇 기능을 찾을 수 없어요.")




    @commands.group(name="점검관리", aliases=["점검"], help="점검 모드 관리 시스템 (개발자 전용)")
    @commands.is_owner()
    async def maintenance_group(self, ctx):
        if ctx.invoked_subcommand is None:
            status = await db.get_maintenance_mode()
            embed = discord.Embed(title="🛠️ 점검 모드 현황", color=discord.Color.orange())
            embed.add_field(name="상태", value="✅ 활성화됨" if status['enabled'] else "❌ 비활성화됨", inline=False)
            embed.add_field(name="사유", value=status['reason'], inline=False)
            embed.add_field(name="종료 예정", value=status['end_time'] if status['end_time'] else "미정", inline=False)

            whitelist = await db.get_maintenance_whitelist()
            embed.add_field(name="화이트리스트", value=f"{len(whitelist)}명", inline=False)

            await ctx.send(embed=embed)

    @maintenance_group.command(name="켜기")
    async def maintenance_on(self, ctx, reason: str = "시스템 점검 중입니다.", end_time: str = None):

        await db.set_maintenance_mode(True, reason, end_time)

        self.bot.is_maintenance_mode = True
        self.bot.maintenance_reason = reason
        self.bot.maintenance_end_time = end_time

        await self.bot.change_presence(status=discord.Status.dnd, activity=discord.Game(f"점검 중... 🛠️"))

        embed = discord.Embed(title="🛠️ 점검 모드 시작", description="점검 모드가 활성화되었습니다.", color=discord.Color.red())
        embed.add_field(name="사유", value=reason, inline=False)
        if end_time:
            embed.add_field(name="종료 예정", value=end_time, inline=False)

        await ctx.send(embed=embed)

    @maintenance_group.command(name="끄기")
    async def maintenance_off(self, ctx):

        await db.set_maintenance_mode(False)
        self.bot.is_maintenance_mode = False
        await self.bot.change_presence(status=discord.Status.online)

        await ctx.send("✅ **점검 모드가 해제되었습니다.**\n정상적으로 이용 가능합니다.")

    @maintenance_group.command(name="화이트리스트추가")
    async def maintenance_whitelist_add(self, ctx, user: discord.User):

        await db.add_maintenance_whitelist(str(user.id))
        await ctx.send(f"✅ **{user.name}**님을 점검 예외 명단에 추가했어요.")

    @maintenance_group.command(name="화이트리스트제거")
    async def maintenance_whitelist_remove(self, ctx, user: discord.User):

        await db.remove_maintenance_whitelist(str(user.id))
        await ctx.send(f"✅ **{user.name}**님을 점검 예외 명단에서 제거했어요.")

    @maintenance_group.command(name="화이트리스트목록")
    async def maintenance_whitelist_list(self, ctx):

        whitelist = await db.get_maintenance_whitelist()
        if not whitelist:
            await ctx.send("화이트리스트가 비어있어요.")
            return

        mentions = [f"<@{uid}>" for uid in whitelist]
        await ctx.send(f"📜 **점검 예외 명단** ({len(whitelist)}명)\n{', '.join(mentions)}")

async def setup(bot):
    await bot.add_cog(Admin(bot))