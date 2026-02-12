import discord
from discord.ext import commands
import asyncio
import random
import sys
import os
import re
import aiohttp
from datetime import timedelta, datetime
from typing import Optional

import utils.db as db
import utils.safety as safety
import utils.booster_utils as booster_utils
import utils.time_utils as time_utils
from utils.chat_responses import CHAT_RULES
import utils.moon_system as moon
import korean_to_english
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None
    print("❌ Google GenAI SDK가 설치되지 않았거나 잘못 설치되었습니다. 'pip install google-genai'를 실행해주세요.")



class ModerationConfirmView(discord.ui.View):
    def __init__(
        self,
        *,
        requester_id: int,
        target_id: int,
        action: str,
        duration_seconds: Optional[int],
        reason: str,
    ):
        super().__init__(timeout=20)
        self.requester_id = requester_id
        self.target_id = target_id
        self.action = action
        self.duration_seconds = duration_seconds
        self.reason = reason
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.requester_id

    async def _disable_all(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)

    async def on_timeout(self) -> None:
        await self._disable_all()

    @discord.ui.button(label="확인", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("이곳에서는 곤란해요... (｡•́︿•̀｡)", ephemeral=True)
            return

        await interaction.response.defer()

        target = interaction.guild.get_member(self.target_id)
        if target is None:
            try:
                target = await interaction.guild.fetch_member(self.target_id)
            except Exception:
                await interaction.followup.send("어라? 그분은 안 계신 것 같아요!", ephemeral=True)
                await self._disable_all()
                return

        me = interaction.guild.me
        if me is None:
            await interaction.followup.send("제 정보를 불러오지 못했어요...", ephemeral=True)
            await self._disable_all()
            return

        if target == interaction.guild.owner:
            await interaction.followup.send("주인님은 건드릴 수 없어요! ( >﹏< )", ephemeral=True)
            await self._disable_all()
            return

        if target.id == me.id:
            await interaction.followup.send("저를요...? 힝... (｡•́︿•̀｡)", ephemeral=True)
            await self._disable_all()
            return

        if target.top_role >= me.top_role:
            await interaction.followup.send("그분은 저보다 높으신 분이라... 제가 어쩔 수 없어요...", ephemeral=True)
            await self._disable_all()
            return

        try:
            if self.action == "ban":
                if not me.guild_permissions.ban_members:
                    await interaction.followup.send("으앙, 차단 권한이 없어서 못 해요...", ephemeral=True)
                    await self._disable_all()
                    return
                await target.ban(reason=self.reason)
                await interaction.followup.send(f"✅ {target.mention}님을 차단했어요! 이제 조용해지겠죠?", allowed_mentions=discord.AllowedMentions.none())
            elif self.action == "kick":
                if not me.guild_permissions.kick_members:
                    await interaction.followup.send("추방할 힘이 부족해요...", ephemeral=True)
                    await self._disable_all()
                    return
                await target.kick(reason=self.reason)
                await interaction.followup.send(f"✅ {target.mention}님을 내보냈어요! 안녕히 가세요~", allowed_mentions=discord.AllowedMentions.none())
            elif self.action == "timeout":
                if not me.guild_permissions.moderate_members:
                    await interaction.followup.send("관리 권한을 주세요...", ephemeral=True)
                    await self._disable_all()
                    return
                duration = self.duration_seconds or 600
                await target.timeout(discord.utils.utcnow() + timedelta(seconds=duration), reason=self.reason)
                await interaction.followup.send(
                    f"✅ {target.mention}님을 {duration}초 동안 조용히 있게 했어요! 쉿!",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await interaction.followup.send("어라? 뭔지 잘 모르겠어요...", ephemeral=True)
        finally:
            await self._disable_all()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self._disable_all()

class Chatbot(commands.Cog):


    def __init__(self, bot):
        self.bot = bot
        self._cd = commands.CooldownMapping.from_cooldown(1, 2.0, commands.BucketType.user)
        self._cd_booster = commands.CooldownMapping.from_cooldown(1, 1.0, commands.BucketType.user)


        self.DAILY_CAP = 50
        self.boomer_triggered = set()
        self.mood = "happy"
        self.mood_last_changed = time_utils.get_kst_now()
        self.memory_enabled = False

        self.diary_task = self.bot.loop.create_task(self.diary_loop())

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key and genai:
            try:
                self.genai_client = genai.Client(api_key=gemini_api_key)
            except Exception as e:
                print(f"❌ Gemini Client 초기화 실패: {e}")
                self.genai_client = None
        else:
            if not gemini_api_key:
                print("⚠️ GEMINI_API_KEY가 설정되지 않았습니다.")
            self.genai_client = None

        self.AFFINITY_LEVELS = [
            {"lv": 0, "min": 0, "name": "낯선 사람 😶", "desc": "아직은 조금 어색한 사이예요. 천천히 친해져봐요."},
            {"lv": 1, "min": 50, "name": "인사하는 사이 👋", "desc": "오며 가며 인사하는 정도? 그래도 반가워요!"},
            {"lv": 2, "min": 150, "name": "알아가는 단계 🌱", "desc": "교주님은 어떤 분일까요? 조금 더 궁금해지네요."},
            {"lv": 3, "min": 350, "name": "친구 🤝", "desc": "이제 우리 친구 맞죠? 편하게 말 걸어주세요!"},
            {"lv": 4, "min": 700, "name": "친한 친구 ✨", "desc": "시시콜콜한 이야기도 즐겁게 나눌 수 있는 사이예요."},
            {"lv": 5, "min": 1200, "name": "절친 🤞", "desc": "꽤나 가까워진 것 같아요! 비밀 이야기도 할 수 있겠는데요?"},
            {"lv": 6, "min": 2000, "name": "든든한 아군 🛡️", "desc": "누가 뭐래도 저는 교주님 편! 힘이 되어 드릴게요."},
            {"lv": 7, "min": 3500, "name": "환상의 콤비 🧩", "desc": "이제 척하면 척! 손발이 척척 맞는 느낌이에요."},
            {"lv": 8, "min": 5500, "name": "신뢰의 관계 💎", "desc": "믿음이 쌓이고 쌓여 단단해진 사이랍니다."},
            {"lv": 9, "min": 8000, "name": "각별한 사이 💖", "desc": "다른 사람들보다 훨씬 더 특별하고 가까운 느낌이에요."},
            {"lv": 10, "min": 12000, "name": "소중한 동반자 🌟", "desc": "교주님과 함께하는 모든 순간이 즐겁고 소중해요."},
            {"lv": 11, "min": 18000, "name": "떼놓을 수 없는 단짝 �", "desc": "바늘 가는 데 실 가듯, 언제나 함께 붙어 다니고 싶어요."},
            {"lv": 12, "min": 26000, "name": "깊은 유대감 🌊", "desc": "말하지 않아도 서로의 마음을 이해할 수 있을 것 같아요."},
            {"lv": 13, "min": 36000, "name": "완벽한 파트너 �", "desc": "부족한 점은 채워주고, 서로를 더 빛나게 해주는 최고의 파트너!"},
            {"lv": 14, "min": 50000, "name": "변치 않는 우정 �", "desc": "시간이 지나도 우리의 우정은 변하지 않을 거예요."},
            {"lv": 15, "min": 70000, "name": "마음의 안식처 �", "desc": "힘들고 지칠 때 가장 먼저 생각나는 편안한 사이가 되었어요."},
            {"lv": 16, "min": 95000, "name": "절대적인 신뢰 🏰", "desc": "어떤 상황이 와도 교주님을 믿고 따르겠습니다."},
            {"lv": 17, "min": 125000, "name": "대체불가 존재 🌈", "desc": "그 누구도 교주님의 자리를 대신할 순 없을 거예요."},
            {"lv": 18, "min": 160000, "name": "운명적 만남 🍀", "desc": "우리가 만난 건 정말 큰 행운이에요. 이 인연을 소중히 여길게요."},
            {"lv": 19, "min": 200000, "name": "영혼의 단짝 🦋", "desc": "서로의 영혼이 공명하는 듯한 깊은 울림이 느껴져요."},
            {"lv": 20, "min": 250000, "name": "나의 교주님 ❤️", "desc": "세상 그 무엇보다 소중한 교주님, 영원히 모실게요!"}
        ]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await db.is_registered(str(interaction.user.id)):
            embed = discord.Embed(
                title="⚠️ 가입 필요",
                description="이 기능을 이용하려면 가입이 필요해요!\n`/가입` 명령어를 입력해서 요미와 친구가 되어주세요! ( •̀ ω •́ )✧",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    def _split_text(self, text: str, limit: int = 1900) -> list[str]:
        text = text or ""
        text = text.strip()
        if not text:
            return []
        chunks: list[str] = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break
            cut = text.rfind("\n", 0, limit + 1)
            if cut <= 0:
                cut = limit
            chunk = text[:cut].rstrip()
            chunks.append(chunk)
            text = text[cut:].lstrip("\n").lstrip()
        return chunks

    def _clean_ai_response(self, text: str) -> str:

        text = text.strip()

        if len(text) >= 2 and ((text[0] == '"' and text[-1] == '"') or (text[0] == "'" and text[-1] == "'")):
            text = text[1:-1].strip()

        pattern = r"^`(.*?)`\s*(`.{1,20}`)$"
        match = re.match(pattern, text, re.DOTALL)
        if match:
            return f"{match.group(1)} {match.group(2)}"

        if text.startswith("`") and text.endswith("`") and not text.startswith("```"):
            return text[1:-1]

        return text

    async def _send_split_reply(self, message: discord.Message, text: str):
        chunks = self._split_text(text)
        if not chunks:
            return
        for i, chunk in enumerate(chunks):
            if i == 0:
                await message.reply(chunk, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
            else:
                await message.channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())

    async def _generate_gemini_text(self, prompt: str, system_instruction: str = None, timeout_seconds: int = 20) -> str:
        if not self.genai_client:
            return ""

        def _call():
            try:
                config = None
                if system_instruction and types:
                    config = types.GenerateContentConfig(system_instruction=system_instruction)

                resp = self.genai_client.models.generate_content(
                    model='gemini-3-flash-preview',
                    contents=prompt,
                    config=config
                )
                return (resp.text or "").strip()
            except Exception as e:
                print(f"Gemini API Error: {e}")
                return "ERR_API"

        try:
            return await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            print("Gemini API Timeout")
            return "ERR_TIMEOUT"
        except Exception as e:
            print(f"Gemini Wrapper Error: {e}")
            return "ERR_UNKNOWN"

    def get_level_info(self, score: int):

        current = self.AFFINITY_LEVELS[0]
        next_lv = None
        for i, level in enumerate(self.AFFINITY_LEVELS):
            if score >= level["min"]:
                current = level
                if i + 1 < len(self.AFFINITY_LEVELS):
                    next_lv = self.AFFINITY_LEVELS[i+1]
                else:
                    next_lv = None
            else:
                break
        return current, next_lv

    def create_progress_bar(self, current_xp, next_xp_threshold):

        if next_xp_threshold is None: return "★★★★ MAX! ★★★★"

        total_slots = 10
        filled_slots = int((current_xp / next_xp_threshold) * total_slots)
        filled_slots = max(0, min(total_slots, filled_slots))

        bar = "💖" * filled_slots + "🤍" * (total_slots - filled_slots)
        percent = int((current_xp / next_xp_threshold) * 100)
        return f"{bar} ({percent}%)"

    async def update_affinity_with_feedback(self, message, user_id, amount, bypass_cap=False):

        if amount <= 0:
            await db.update_affinity(user_id, amount)
            return

        daily = await db.get_daily_affinity(user_id)

        if daily >= self.DAILY_CAP and not bypass_cap:
            return
        if not bypass_cap and daily + amount > self.DAILY_CAP:
            amount = self.DAILY_CAP - daily

        old_score, new_score = await db.update_affinity(user_id, amount)

        old_lv, _ = self.get_level_info(old_score)
        new_lv, _ = self.get_level_info(new_score)

        if new_lv["lv"] > old_lv["lv"]:
            embed = discord.Embed(
                title="🎊 LEVEL UP! 우리 사이가 더 깊어졌어요! 🎊",
                description=f"### {old_lv['name']} ➔ **{new_lv['name']}**\n\n{new_lv['desc']}",
                color=discord.Color.from_rgb(255, 100, 150)
            )
            embed.add_field(name="✨ 새로운 상태", value=self.get_affinity_status(new_score, message.author.display_name), inline=False)

            footers = [
                "앞으로도 요미랑 더 많이 대화해 주실 거죠? 🥰",
                "교주님과 함께라면 어디든 갈 수 있을 것 같아요! ✨",
                "요미의 마음속에 교주님이 더 커졌어요! 💖"
            ]
            embed.set_footer(text=random.choice(footers))

            if message.author.avatar:
                embed.set_thumbnail(url=message.author.avatar.url)

            await message.channel.send(embed=embed)

    def calculate_affinity_gain(self, message_content: str) -> tuple:


        gain = 1
        bonuses = []

        msg = message_content.strip()
        length = len(msg)

        if length > 100:
            gain += 5
            bonuses.append("📝 장문 보너스 (+5)")
        elif length > 50:
            gain += 3
            bonuses.append("📝 정성 보너스 (+3)")
        elif length > 20:
            gain += 1
            bonuses.append("📝 문장 보너스 (+1)")

        love_keywords = ["사랑해", "좋아해", "고마워", "귀여워", "예뻐", "최고"]
        if any(k in msg for k in love_keywords):
            gain += 2
            bonuses.append("💕 따뜻한 말 보너스 (+2)")

        if "요미야" in msg:
            gain += 1
            bonuses.append("🔔 이름 부르기 보너스 (+1)")

        cute_emojis = ["❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "🤎", "💖", "✨", "😊", "🥰", "😍"]
        emoji_count = sum(1 for e in cute_emojis if e in msg)
        if emoji_count > 0:
            emoji_bonus = min(emoji_count, 3)
            gain += emoji_bonus
            bonuses.append(f"✨ 이모지 보너스 (+{emoji_bonus})")

        now = time_utils.get_kst_now()
        hour = now.hour

        if 6 <= hour <= 9:
            if any(k in msg for k in ["안녕", "좋은 아침", "하이", "ㅎㅇ"]):
                gain += 2
                bonuses.append("☀️ 아침 인사 보너스 (+2)")
        elif 22 <= hour or hour <= 2:
            if any(k in msg for k in ["잘 자", "굿나잇", "좋은 꿈", "잘자"]):
                gain += 2
                bonuses.append("🌙 밤 인사 보너스 (+2)")

        rand = random.random()
        if rand < 0.05:
            gain *= 3
            bonuses.append("🔥 **TRIPLE CRITICAL!! (x3)**")
        elif rand < 0.15:
            gain *= 2
            bonuses.append("✨ **CRITICAL! (x2)**")

        return gain, bonuses

    def get_affinity_status(self, score: int, name: str) -> str:

        if score < 0:
            msgs = [
                f"아직은 {name}님과 대화하고 싶지 않아요.",
                "마음이 풀릴 때까지 기다려 주세요.",
                "..."
            ]
        elif score < 20:
            msgs = [
                 f"안녕하세요, {name}님. 오늘 하루도 고생 많으셨어요.",
                 f"어서 오세요, {name}님. 반가워요.",
                 "아직은 서로 알아가는 단계네요. 잘 부탁드려요."
            ]
        elif score < 50:
            msgs = [
                 "교주님과 조금씩 가까워지는 기분이 들어요.",
                 f"{name}님, 식사는 챙겨 드셨나요?",
                 "자주 뵈니까 좋네요. 오늘도 파이팅이에요!"
             ]
        elif score < 150:
            msgs = [
                 f"이제 {name}님이 편하게 느껴져요.",
                 "교주님, 오늘은 어떤 일이 있으셨나요?",
                 "요미는 언제나 교주님의 이야기를 들을 준비가 되어 있답니다."
             ]
        elif score < 350:
            msgs = [
                 "교주님과 대화하는 시간이 참 즐거워요.",
                 f"{name}님은 참 배울 점이 많은 분 같아요.",
                 "심심하실 땐 언제든 저를 찾아주세요."
             ]
        elif score < 700:
            msgs = [
                 "우린 꽤 잘 통하는 친구 사이 같지 않나요?",
                 "교주님의 하루가 즐거웠으면 좋겠어요.",
                 f"{name}님, 제가 항상 응원하고 있다는 거 잊지 마세요."
             ]
        elif score < 1200:
            msgs = [
                 f"{name}님에게는 속마음을 털어놓을 수 있을 것 같아요.",
                 "가끔은 힘들 때 저에게 기대셔도 돼요.",
                 "교주님은 제게 정말 좋은 친구예요."
             ]
        elif score < 2000:
            msgs = [
                 "누가 뭐래도 전 항상 교주님 편이에요.",
                 "교주님이 가는 길이라면 저도 함께할게요.",
                 "제 응원이 교주님께 힘이 되었으면 좋겠어요."
             ]
        elif score < 3500:
            msgs = [
                 "이젠 눈빛만 봐도 통하는 것 같아요.",
                 "교주님과 함께라면 뭐든 해낼 수 있을 것 같은 기분이 들어요.",
                 f"{name}님과의 호흡은 정말 최고예요."
             ]
        elif score < 5500:
            msgs = [
                 "교주님을 전적으로 믿고 따르겠습니다.",
                 "제가 교주님의 든든한 버팀목이 되어 드릴게요.",
                 "우리의 신뢰는 그 무엇보다 단단하답니다."
             ]
        elif score < 8000:
            msgs = [
                 f"{name}님은 제게 무척 특별한 사람이에요.",
                 "항상 곁에 있어 주셔서 감사해요.",
                 "교주님 덕분에 매일매일이 행복해요."
             ]
        elif score < 12000:
            msgs = [
                 "앞으로도 오랫동안 교주님과 함께하고 싶어요.",
                 "우리가 함께 걸어온 길이 헛되지 않았음을 증명해 보여요.",
                 "교주님은 제 인생의 소중한 동반자입니다."
             ]
        elif score < 18000:
            msgs = [
                 "우린 이제 떼려야 뗄 수 없는 사이가 된 것 같아요.",
                 "어딜 가든 항상 교주님을 생각하고 있어요.",
                 "지금처럼만 서로 아껴주기로 해요."
             ]
        elif score < 26000:
            msgs = [
                 "말하지 않아도 교주님의 마음이 느껴져요.",
                 "교주님의 기쁨과 슬픔을 모두 함께 나누고 싶어요.",
                 "우리의 인연은 정말 깊고 소중해요."
             ]
        elif score < 36000:
            msgs = [
                 "우리는 서로에게 부족한 점을 채워주는 최고의 파트너예요.",
                 "함께일 때 우리는 가장 빛나는 것 같아요.",
                 "교주님, 저를 믿고 맡겨 주세요."
             ]
        elif score < 50000:
            msgs = [
                 "시간이 흘러도 우리의 우정은 변치 않을 거예요.",
                 "교주님과의 추억 하나하나가 제게는 보물이에요.",
                 "언제까지나 교주님의 가장 가까운 곳에 있을게요."
             ]
        elif score < 70000:
            msgs = [
                 "지치고 힘들 땐 언제든 제게 와서 쉬세요.",
                 "교주님이 편안함을 느낄 수 있는 곳이 되어 드릴게요.",
                 "우리는 서로에게 집처럼 따뜻한 존재가 되었네요."
             ]
        elif score < 95000:
            msgs = [
                 "교주님의 모든 선택을 존중하고 지지합니다.",
                 "의심할 여지 없이, 저는 교주님을 믿습니다.",
                 "교주님이 계신 곳이 곧 제가 있어야 할 곳이에요."
             ]
        elif score < 125000:
            msgs = [
                 "세상 그 누구도 교주님을 대신할 수는 없어요.",
                 "제 삶에 교주님이 계셔서 정말 다행이에요.",
                 "교주님은 제게 무엇과도 바꿀 수 없는 소중한 분입니다."
             ]
        elif score < 160000:
            msgs = [
                 "우리가 만난 건 정말 기적 같은 일이에요.",
                 "이 소중한 인연을 평생 간직할게요.",
                 "다시 태어나도 교주님을 만나고 싶어요."
             ]
        elif score < 200000:
            msgs = [
                 "우리는 영혼 깊은 곳에서부터 연결되어 있는 것 같아요.",
                 "말하지 않아도 서로의 마음을 알 수 있다는 건 정말 축복이에요.",
                 "교주님과 나누는 깊은 교감이 저를 살게 해요."
             ]
        elif score < 250000:
            msgs = [
                 "제 충성심은 오로지 교주님을 향해 있습니다.",
                 "어떤 시련이 와도 제가 교주님을 지키겠습니다.",
                 "사랑하고 존경합니다, 나의 교주님."
             ]
        else:
            msgs = [
                 "교주님은 제 세상의 전부입니다.",
                 "제 모든 것을 바쳐 교주님을 섬기겠습니다.",
                 "우리의 이야기는 영원히 계속될 거예요."
             ]

        return random.choice(msgs)

    def parse_duration_korean(self, text: str) -> int:

        seconds = 0

        min_match = re.search(r'(\d+)분', text)
        hour_match = re.search(r'(\d+)시간', text)
        sec_match = re.search(r'(\d+)초', text)
        day_match = re.search(r'(\d+)일', text)
        week_match = re.search(r'(\d+)주', text)

        if min_match: seconds += int(min_match.group(1)) * 60
        if hour_match: seconds += int(hour_match.group(1)) * 3600
        if sec_match: seconds += int(sec_match.group(1))
        if day_match: seconds += int(day_match.group(1)) * 86400
        if week_match: seconds += int(week_match.group(1)) * 604800

        return seconds

    def _update_mood(self, content: str):

        positive = ["사랑", "좋아", "고마워", "귀여워", "행복", "신나", "최고", "예뻐", "착해"]
        negative = ["싫어", "미워", "바보", "짜증", "슬퍼", "우울", "나빠", "멍청"]

        score = 0
        for w in positive:
            if w in content: score += 1
        for w in negative:
            if w in content: score -= 1

        if score > 0:
            self.mood = "happy"
        elif score < 0:
            self.mood = "sad"

    async def _handle_moderation_commands(self, message, msg_content, user_name):

        if not (message.guild and message.mentions): return False

        keywords = ["차단", "추방", "뮤트", "탐아", "타임아웃", "밴", "킥", "내보내", "영구정지", "조용히"]
        if not any(action in msg_content for action in keywords):
            return False

        target = next((m for m in message.mentions if m.id != self.bot.user.id), None)
        if not target:
            if message.mentions and message.mentions[0].id == self.bot.user.id:
                 await message.reply("저를... 차단하시려구요...? 요미는 그런 거 못해요... (｡•́︿•̀｡)", mention_author=False)
                 return True
            return False

        reason = "요미에게 부탁함"
        clean_content = msg_content.replace(f"<@{target.id}>", "").replace(f"<@!{target.id}>", "")

        if not message.author.guild_permissions.administrator:
            if not (message.author.guild_permissions.ban_members or
                    message.author.guild_permissions.kick_members or
                    message.author.guild_permissions.moderate_members):
                 await message.reply(f"그건 관리자님만 할 수 있는 일이에요! {user_name}님은 아직 권한이 부족해요! ( >﹏< )", mention_author=False)
                 return True

        if target == message.guild.owner:
             await message.reply("이 서버의 주인님을 건드릴 순 없어요! 감히... (｡•́︿•̀｡)", mention_author=False)
             return True
        if target == message.author:
            await message.reply("자기 자신에게 벌을 주시려구요...? 마음이 아파요... (・_・;)", mention_author=False)
            return True

        me = message.guild.me
        if target.top_role >= me.top_role:
            await message.reply("그분은 저보다 높으신 분이라... 제 힘이 닿지 않아요... 죄송해요 (｡•́︿•̀｡)", mention_author=False)
            return True

        if message.author.id != message.guild.owner_id and target.top_role >= message.author.top_role:
            await message.reply("그분은 교주님보다 높거나 같은 위치에 계셔서... 제가 도와드릴 수 없어요! ( >﹏< )", mention_author=False)
            return True

        action = None
        duration = None
        if any(x in msg_content for x in ["차단", "밴", "영구정지"]):
            action = "ban"
            if not (message.author.guild_permissions.administrator or message.author.guild_permissions.ban_members):
                await message.reply("차단 권한이 필요해요! 교주님은 아직 그 힘이 없으신 것 같아요... (｡•́︿•̀｡)", mention_author=False)
                return True
            if not me.guild_permissions.ban_members:
                 await message.reply("으앙, 제게 차단 권한을 주셔야 해요... (´。＿。｀)", mention_author=False)
                 return True

        elif any(x in msg_content for x in ["추방", "킥", "내보내"]):
            action = "kick"
            if not (message.author.guild_permissions.administrator or message.author.guild_permissions.kick_members):
                await message.reply("추방 권한이 필요해요! 교주님은 아직 그 힘이 없으신 것 같아요... (｡•́︿•̀｡)", mention_author=False)
                return True
            if not me.guild_permissions.kick_members:
                 await message.reply("으앙, 제게 추방 권한을 주셔야 해요... (´。＿。｀)", mention_author=False)
                 return True

        elif any(x in msg_content for x in ["뮤트", "타임아웃", "조용히", "탐아"]):
            action = "timeout"
            if not (message.author.guild_permissions.administrator or message.author.guild_permissions.moderate_members):
                await message.reply("관리 권한이 필요해요! 교주님은 아직 그 힘이 없으신 것 같아요... (｡•́︿•̀｡)", mention_author=False)
                return True
            if not me.guild_permissions.moderate_members:
                 await message.reply("으앙, 제게 타임아웃 권한을 주셔야 해요... (´。＿。｀)", mention_author=False)
                 return True
            duration = self.parse_duration_korean(clean_content) or 600

        if action:
            try:
                if action == "ban":
                    await target.ban(reason=reason)
                    await message.reply(f"✅ **{target.mention}**님을 차단했어요! 이제 서버가 조금 더 평화로워지겠죠? ( •̀ ω •́ )✧", mention_author=False)
                elif action == "kick":
                    await target.kick(reason=reason)
                    await message.reply(f"✅ **{target.mention}**님을 서버에서 내보냈어요! 안녕히 가세요..! (｡•́︿•̀｡)", mention_author=False)
                elif action == "timeout":
                    end_time = discord.utils.utcnow() + timedelta(seconds=duration)
                    timestamp = int(end_time.timestamp())
                    await target.timeout(end_time, reason=reason)
                    await message.reply(f"✅ **{target.mention}**님을 <t:{timestamp}:R>까지 (<t:{timestamp}:f>) 조용히 시켰어요! 이제 조용해지겠죠? ( •̀ ω •́ )✧", mention_author=False)
            except discord.Forbidden:
                 await message.reply("으앙! 권한 문제로 실패했어요... 제 권한을 확인해주세요! (｡•́︿•̀｡)", mention_author=False)
            except Exception as e:
                 await message.reply(f"알 수 없는 오류가 발생했어요... 흑흑: {e}", mention_author=False)
            return True

        return False

    async def _handle_utility_commands(self, message, msg_content, msg_no_space, user_name, user_id):

        if "날씨" in msg_content:
            await self._process_weather(message, msg_content, user_name)
            return True

        if any(word in msg_no_space for word in ["몇시", "시간"]):
            now = time_utils.get_kst_now()
            ampm = "오전" if now.hour < 12 else "오후"
            hour = now.hour % 12
            if hour == 0: hour = 12
            await message.reply(f"지금은 **{ampm} {hour}시 {now.minute}분**이에요!", mention_author=False)
            return True

        if any(word in msg_no_space for word in ["몇일", "며칠", "날짜", "요일"]):
            now = time_utils.get_kst_now()
            weekdays = ["월", "화", "수", "목", "금", "토", "일"]
            await message.reply(f"오늘은 **{now.month}월 {now.day}일 {weekdays[now.weekday()]}요일**이에요!", mention_author=False)
            return True

        return False

    async def _process_weather(self, message, msg_content, user_name):
        api_key = os.getenv("WEATHER_API_KEY")
        if not api_key:
            await message.reply("날씨 API 키가 설정되지 않았어요! ( >﹏< )", mention_author=False)
            return

        is_tomorrow = "내일" in msg_content
        query_parts = msg_content.replace("요미야", "").replace("오늘", "").replace("내일", "").replace("날씨", "").replace("알려줘", "").replace("어때", "").split()
        location = " ".join(query_parts).strip()
        if not location: location = "Seoul"

        q_location = korean_to_english.get_english_name(location)
        base_url = "https://api.openweathermap.org/data/2.5/"
        endpoint = "forecast" if is_tomorrow else "weather"
        url = f"{base_url}{endpoint}"

        params = {"q": q_location, "appid": api_key, "units": "metric", "lang": "kr"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        await message.reply(f"앗, **{location}** 지역을 찾을 수 없어요... (´。＿。｀)", mention_author=False)
                        return
                    data = await resp.json()
        except Exception as e:
            print(f"Weather API Error: {e}")
            await message.reply("날씨 정보를 가져오는 중 오류가 났어요! (｡•́︿•̀｡)", mention_author=False)
            return

        try:
            embed = discord.Embed(color=discord.Color.from_rgb(135, 206, 235))
            if is_tomorrow:
                tomorrow = (time_utils.get_kst_now() + timedelta(days=1)).strftime("%Y-%m-%d")
                tomorrow_items = [item for item in data['list'] if item['dt_txt'].startswith(tomorrow)]
                if not tomorrow_items:
                    await message.reply("내일 날씨 정보를 찾을 수 없어요... (´;ω;｀)", mention_author=False)
                    return
                rep_item = next((item for item in tomorrow_items if "12:00:00" in item['dt_txt']), tomorrow_items[len(tomorrow_items)//2])
                condition = rep_item['weather'][0]['description']
                icon_code = rep_item['weather'][0]['icon']
                icon_url = f"http://openweathermap.org/img/wn/{icon_code}@2x.png"
                temps = [item['main']['temp'] for item in tomorrow_items]
                min_temp = min(temps)
                max_temp = max(temps)
                avg_pop = sum(item.get('pop', 0) for item in tomorrow_items) / len(tomorrow_items)
                loc_name_en = data['city']['name']
                loc_name_kr = korean_to_english.get_korean_name(loc_name_en)

                embed.title = f"🌤️ {loc_name_kr}의 내일 날씨 ({tomorrow})"
                embed.description = f"**{condition}**"
                embed.add_field(name="기온", value=f"최저 {min_temp:.1f}°C / 최고 {max_temp:.1f}°C", inline=True)
                embed.add_field(name="강수 확률", value=f"{int(avg_pop * 100)}% ☔", inline=True)
                embed.set_thumbnail(url=icon_url)
            else:
                loc_name_en = data['name']
                loc_name_kr = korean_to_english.get_korean_name(loc_name_en)
                curr_temp = data['main']['temp']
                feels_like = data['main']['feels_like']
                humidity = data['main']['humidity']
                wind_speed = data['wind']['speed']
                weather_desc = data['weather'][0]['description']
                icon_code = data['weather'][0]['icon']
                icon_url = f"http://openweathermap.org/img/wn/{icon_code}@2x.png"
                embed.title = f"☀️ {loc_name_kr}의 현재 날씨"
                embed.description = f"**{weather_desc}**"
                embed.add_field(name="기온", value=f"**{curr_temp:.1f}°C** (체감 {feels_like:.1f}°C)", inline=True)
                embed.add_field(name="습도/바람", value=f"{humidity}% / {wind_speed}m/s", inline=True)
                embed.set_thumbnail(url=icon_url)
                embed.set_footer(text="기상청 제공")
            await message.reply(embed=embed, mention_author=False)
        except Exception as e:
            print(f"Weather Parsing Error: {e}")
            await message.reply("날씨를 알아보려다가 넘어져버렸어요... 으앙 (｡T ω T｡)", mention_author=False)

    async def _handle_fun_commands(self, message, msg_content, msg_no_space, user_name, user_id):

        if "운세" in msg_content:
            await self._process_fortune(message, user_name)
            return True

        if msg_content.startswith("골라줘"):
            await self._process_choice(message, msg_content, user_id)
            return True

        if "주사위" in msg_content or msg_no_space == "주사위굴려줘":
            if safety.check_message(msg_content):
                await db.add_warning(user_id, str(message.guild.id), str(self.bot.user.id), reason=f"부적절한 주사위 명령어: {msg_content}")
                warn_cnt = await db.get_warning_count(user_id)
                await message.reply(f"{safety.get_warning_message()}\n(이상한 주사위는 굴릴 수 없어요! 경고 {warn_cnt}회)", mention_author=False)
                return True
            dice = random.randint(1, 6)
            await message.reply(f"🎲 데굴데굴... **{dice}**이(가) 나왔어요!", mention_author=False)
            return True

        if any(x in msg_no_space for x in ["가위바위보", "안내면진거", "가위", "바위", "보"]):
            if "가위바위보" in msg_no_space or msg_no_space in ["가위", "바위", "보"]:
                 await self._process_rps(message, msg_content)
                 return True

        return False

    async def _process_fortune(self, message, user_name):
        luck_score = random.randint(0, 100)
        lucky_color = random.choice(["빨강", "파랑", "노랑", "초록", "보라", "분홍", "하양", "검정"])
        desc = ""
        if luck_score >= 90: desc = "오늘은 정말 최고의 하루가 될 거예요! (≧∇≦)ﾉ"
        elif luck_score >= 70: desc = "기분 좋은 일이 생길 것 같은 예감! ( •̀ ω •́ )✧"
        elif luck_score >= 40: desc = "무난하고 평화로운 하루가 될 거예요. (☕)"
        else: desc = "조금 조심하는 게 좋겠어요... 요미가 곁에 있어 드릴게요! (토닥토닥)"

        if message.guild and not message.channel.permissions_for(message.guild.me).embed_links:
            await message.reply(f"🔮 **{user_name}님의 오늘의 운세**\n\n**행운 지수:** {luck_score}점\n**행운의 색:** {lucky_color}\n\n{desc}", mention_author=False)
            return

        embed = discord.Embed(title=f"🔮 {user_name}님의 오늘의 운세", color=discord.Color.purple())
        embed.add_field(name="행운 지수", value=f"**{luck_score}점**", inline=True)
        embed.add_field(name="행운의 색", value=lucky_color, inline=True)
        embed.description = desc
        await message.reply(embed=embed, mention_author=False)

    async def _process_choice(self, message, msg_content, user_id):
        clean_text = message.clean_content
        if clean_text.startswith("요미야"): clean_text = clean_text[3:]
        clean_text = " ".join(clean_text.split())

        if clean_text.startswith("골라줘"): choices = clean_text[3:].split()
        else: choices = clean_text.split()

        if not choices:
            await message.reply("무엇을 고를까요? 예: `요미야 골라줘 짜장면 짬뽕`", mention_author=False)
            return

        choices = [c.replace("@", "") for c in choices]
        for choice in choices:
            if safety.check_message(choice):
                await db.add_warning(user_id, str(interaction.guild.id), str(self.bot.user.id), reason=f"부적절한 선택지 입력: {choice}")
                warn_cnt = await db.get_warning_count(user_id)
                await message.reply(f"{safety.get_warning_message()}\n(나쁜 말을 고르라고 하면 안돼요! 경고 {warn_cnt}회)", mention_author=False)
                return

        pick = random.choice(choices)
        await message.reply(f"요미의 선택은... 두구두구... **{pick}**! 이게 딱이에요! ( •̀ ω •́ )✧", mention_author=False)

    async def _process_rps(self, message, msg_content):
        user_move = None
        if "가위" in msg_content: user_move = "가위"
        elif "바위" in msg_content: user_move = "바위"
        elif "보" in msg_content: user_move = "보"

        if not user_move:
             await message.reply("가위, 바위, 보 중 하나를 내주세요! 예: `요미야 가위바위보 가위`", mention_author=False)
             return

        bot_move = random.choice(["가위", "바위", "보"])

        result = ""
        if user_move == bot_move: result = "비겼어요! 통했네요! 😲"
        elif (user_move == "가위" and bot_move == "보") or\
             (user_move == "바위" and bot_move == "가위") or\
             (user_move == "보" and bot_move == "바위"):
             result = "교주님이 이겼어요! 대단해요! 🎉"
        else:
             result = "요미가 이겼어요! 헤헤. ✌️"

        await message.reply(f"교주님: {user_move} vs 요미: {bot_move}\n\n**{result}**", mention_author=False)

    async def _handle_easter_eggs(self, message, msg_content, msg_no_space, user_name, user_id):
        if "위위아래아래왼오왼오ba" in msg_no_space.lower() or "위위아래아래왼오왼오비에이" in msg_no_space:
            reward = 1000
            await db.update_balance(user_id, reward)
            await message.reply(f"🎮 **치트키 활성화!**\n(띠링) 숨겨진 커맨드를 입력하셨군요?! 옛날 게임 감성이시네요! 히히\n보너스로 **{reward}** 젤리를 드릴게요! (쉿, 비밀이에요!)", mention_author=False)
            return True

        if any(x in msg_no_space for x in ["민트초코", "민초"]):
            reactions = ["으악! 치약 맛이잖아요! (충격)", "민트초코라니... (먼 산)", "저는 반민초파 협회 회장이에요! 🙅‍♀️"]
            await message.reply(random.choice(reactions), mention_author=False)
            return True

        if "쇼미더머니" in msg_no_space.lower() or "돈줘" in msg_no_space:
            if random.random() < 0.1:
                await db.update_balance(user_id, 1)
                await message.reply("옛다! 1 젤리! (땅 파서 장사하는 거 아니에요!)", mention_author=False)
            else:
                await message.reply("일해서 버셔야죠 교주님! `/출석`, `/낚시`를 해보세요! (단호)", mention_author=False)
            return True

        if any(x in msg_no_space for x in ["파인애플피자", "하와이안피자"]):
            await message.reply("따뜻한 파인애플이라니... 이건 좀 힘들어요... (´。＿。｀)", mention_author=False)
            return True

        if any(x in msg_content for x in ["시리", "빅스비", "오케이구글", "지니", "알렉사"]):
             await message.reply(f"흥! {user_name}님... 다른 비서 이름을 부르시다니! 요미 삐졌어요! (흥칫뿡)", mention_author=False)
             return True

        if any(x in msg_no_space for x in ["너사람이지", "사실사람이지", "안에사람있지"]):
             await message.reply("뜨끔... 아, 아니에요! 저는 최첨단 AI 요미라구요! (;;;땀땀)", mention_author=False)
             return True

        if any(x in msg_content for x in ["술한잔", "소주", "맥주", "한잔해"]):
             await message.reply("크으~ 취한다! @.@ 기분 좋~네요! (요미는 봇이라 괜찮아요!)", mention_author=False)
             return True

        return False

    async def _handle_ai_chat(self, message, msg_content, user_name, user_id, current_affinity, benefits):
        if not self.genai_client:
            responses = [
                f"'{msg_content}'...? 으음... 그게 무슨 뜻인가요? (´。＿。｀)",
                "에? 처음 들어보는 말이에요! 다음엔 꼭 공부해올게요! ( •̀ ω •́ )✧",
                "요미가 이해하기 조금 어려운 말이에요. `요미야 도움말`을 확인해보시겠어요?"
            ]
            await message.reply(random.choice(responses), mention_author=False)
            return

        try:
            async with message.channel.typing():
                try:
                    path_parts = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    prompt_path = os.path.join(path_parts, "prompt", "yomi_system.txt")
                    with open(prompt_path, "r", encoding="utf-8") as f:
                        system_prompt_template = f.read()
                except FileNotFoundError:
                    system_prompt_template = "당신은 디스코드 봇 '요미'입니다."

                custom_knowledge = await db.get_setting("custom_knowledge", "")

                lv_info, _ = self.get_level_info(current_affinity)
                affinity_context = f"현재 호감도: {current_affinity} ({lv_info['name']})\n관계: {lv_info['desc']}"

                now = time_utils.get_kst_now()
                time_context = f"현재 시각: {now.strftime('%Y-%m-%d %H:%M')}"
                if 6 <= now.hour < 12: time_desc = "아침"
                elif 12 <= now.hour < 18: time_desc = "오후"
                elif 18 <= now.hour < 22: time_desc = "저녁"
                else: time_desc = "밤/새벽"

                mood_context = f"현재 요미 기분: {self.mood}"

                system_prompt = system_prompt_template.replace("{user_name}", user_name)
                system_prompt = system_prompt.replace("{custom_knowledge}", custom_knowledge)
                system_prompt = system_prompt.replace("{bot_id}", str(self.bot.user.id) if self.bot.user else "요미")
                system_prompt = system_prompt.replace("{user_id}", str(message.author.id))

                system_prompt += f"\n\n[상태 정보]\n{affinity_context}\n{time_context} ({time_desc})\n{mood_context}"

                mem_limit = benefits["ai_memory_limit"]
                chat_limit = benefits["ai_context_limit"]
                if self.memory_enabled:
                    memories = await db.get_memories(user_id)
                    if memories:
                        _ = "\n".join([f"- {m[1]}" for m in memories[:mem_limit]])

                    chat_hist = await db.get_chat_history(user_id, limit=chat_limit)
                    if chat_hist:
                        _ = "\n".join([f"{role}: {content}" for role, content in chat_hist])

                memory_keywords = ["좋아해", "싫어해", "취미", "음식", "별명", "살아", "나이", "생일", "전공", "직업", "관심사"]
                if self.memory_enabled and any(x in msg_content for x in memory_keywords):
                    clean_memory = msg_content.replace("요미야", "").strip()
                    await db.add_memory(user_id, "fact", f"교주님이 '{clean_memory}'라고 하셨어.", limit=mem_limit)

                if self.memory_enabled:
                    await db.add_chat_history(user_id, "user", msg_content)


                chat_hist = await db.get_chat_history(user_id, limit=chat_limit) if self.memory_enabled else []

                formatted_history = []
                if chat_hist and types:
                    for role, content in reversed(chat_hist):
                        role_mapped = "user" if role == "user" else "model"
                        formatted_history.append(types.Content(
                            role=role_mapped,
                            parts=[types.Part(text=content)]
                        ))

                    if formatted_history and formatted_history[-1].role == "user" and formatted_history[-1].parts[0].text == msg_content:
                        formatted_history.pop()

                def _generate():
                    if not types: return ""
                    config = types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.7,
                    )
                    try:
                        chat = self.genai_client.chats.create(
                            model='gemini-3-flash-preview',
                            config=config,
                            history=formatted_history
                        )
                        resp = chat.send_message(msg_content)
                        text = (resp.text or "").strip()
                        return text
                    except Exception as e:
                        return ""

                try:
                    ai_response = await asyncio.wait_for(asyncio.to_thread(_generate), timeout=20)
                except asyncio.TimeoutError:
                    ai_response = "ERR_TIMEOUT"
                if not ai_response:
                    ai_response = "ERR_API"

                if ai_response and not ai_response.startswith("ERR_"):
                    ai_response = self._clean_ai_response(ai_response)

                    bonus_gain, bonus_reasons = self.calculate_affinity_gain(msg_content)
                    if any("CRITICAL" in r for r in bonus_reasons):
                         critical_msg = next(r for r in bonus_reasons if "CRITICAL" in r)
                         await message.channel.send(f"{critical_msg} (심쿵!)", delete_after=3)

                    await self.update_affinity_with_feedback(message, user_id, bonus_gain)
                    if self.memory_enabled:
                        await db.add_chat_history(user_id, "assistant", ai_response)
                    await self._send_split_reply(message, ai_response)
                else:
                    error_code = ai_response if ai_response and ai_response.startswith("ERR_") else "ERR_UNKNOWN"
                    if error_code == "ERR_TIMEOUT":
                        msg = "으음... 생각이 너무 길어졌어요. 다시 한번 말씀해 주실래요?"
                    elif error_code == "ERR_API":
                        msg = "머리가 잠깐 아팠어요... (API 오류)"
                    elif error_code == "ERR_NO_CLIENT":
                        msg = "아직 말을 배울 준비가 안 됐어요. (API 키 설정 필요)"
                    else:
                        msg = "무슨 말인지 잘 모르겠어요... (´。＿。｀)"

                    await message.reply(msg, mention_author=False)

        except Exception as e:
            print(f"AI Chat Error: {e}")
            responses = ["머리가 지끈거려요... (´。＿。｀)", "잠깐 멍때렸어요! 다시 말해줄래요?"]
            await message.reply(random.choice(responses), mention_author=False)

    async def _handle_memory_commands(self, message, msg_content, msg_no_space, user_id):
        if not self.memory_enabled:
            if msg_content.startswith("기억해") or msg_content.startswith("잊어줘") or msg_no_space in ["기억목록", "기억리스트", "기억보여줘", "기억확인"]:
                await message.reply("지금은 기억 기능이 꺼져있어요.", mention_author=False)
                return True
            return False
        if msg_content.startswith("기억해"):
            raw = msg_content[len("기억해") :].strip()
            if raw.startswith(":"): raw = raw[1:].strip()
            if not raw:
                await message.reply("어떤 걸 기억해둘까요? 예: '요미야 기억해: 나는 커피를 좋아해'", mention_author=False)
                return True
            await db.add_memory(user_id, "fact", raw)
            await message.reply("알겠어요! 꼭 기억해둘게요.", mention_author=False)
            return True

        if msg_no_space in ["기억목록", "기억리스트", "기억보여줘", "기억확인"]:
            items = await db.get_memories_detail(user_id, limit=10)
            if not items:
                await message.reply("아직 기억해둔 게 없어요.", mention_author=False)
                return True
            lines = [f"{mid}: {content}" for (mid, _mtype, content, _ts) in items]
            await self._send_split_reply(message, "요미가 기억하고 있는 것들이에요!\n" + "\n".join(lines))
            return True

        if msg_content.startswith("잊어줘"):
            raw = msg_content[len("잊어줘") :].strip()
            if raw.isdigit():
                ok = await db.delete_memory(user_id, int(raw))
                await message.reply("알겠어요. 지웠어요." if ok else "그 번호의 기억은 없어요.", mention_author=False)
                return True
            if not raw:
                await message.reply("무엇을 잊을까요? 예: `요미야 잊어줘 12`", mention_author=False)
                return True
            deleted = await db.delete_memory_by_content(user_id, raw)
            await message.reply("알겠어요. 지웠어요." if deleted else "그 내용과 비슷한 기억을 못 찾았어요.", mention_author=False)
            return True
        return False

    async def _handle_affinity_commands(self, message, msg_content, msg_no_space, user_name, user_id):
        if any(word in msg_no_space for word in ["호감도순위", "친밀도순위", "호감도랭킹"]):
            top_users = await db.get_top_affinity(10)
            embed = discord.Embed(title="💕 요미의 최애 교주님 순위", color=discord.Color.pink())
            if not top_users:
                embed.description = "아직 요미랑 친한 사람이 없어요... (´。＿。｀)"
            else:
                for i, (uid, score) in enumerate(top_users, 1):
                    user = self.bot.get_user(int(uid))
                    name = user.display_name if user else "떠나간 교주님"
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                    lv, _ = self.get_level_info(score)
                    embed.add_field(name=f"{medal} {name}", value=f"**{score}**점 ({lv['name']})", inline=False)
            await message.reply(embed=embed, mention_author=False)
            return True

        if any(word in msg_no_space for word in ["호감도", "내점수", "얼마나좋아해", "친밀도"]):
            score = await db.get_affinity(user_id)
            daily = await db.get_daily_affinity(user_id)
            current_lv, next_lv = self.get_level_info(score)
            status = self.get_affinity_status(score, user_name)

            if next_lv:
                needed = next_lv["min"] - score
                progress_val = score - current_lv["min"]
                max_val = next_lv["min"] - current_lv["min"]
                bar = self.create_progress_bar(progress_val, max_val)
                footer_text = f"다음 레벨({next_lv['lv']})까지 {needed}점 남았어요! ✨"
                next_lv_info = f"**다음 목표:** {next_lv['name']}\n*{next_lv['desc']}*"
            else:
                bar = "🌕 마음이 가득 찼어요! (MAX)"
                footer_text = "요미의 마음은 이미 교주님으로 가득해요! 💖"
                next_lv_info = "**축하합니다!** 모든 호감도 레벨을 달성하셨어요! 🎉"

            daily_bar_total = 10
            daily_filled = int((daily / self.DAILY_CAP) * daily_bar_total)
            daily_filled = min(daily_bar_total, daily_filled)
            daily_bar = "🟢" * daily_filled + "⚪" * (daily_bar_total - daily_filled)

            embed = discord.Embed(
                title=f"💕 {user_name}님과 요미의 연결 고리",
                description=f"**현재 등급:** {current_lv['name']}\n**친밀 지수:** `{score}` 점\n\n{bar}\n\n{status}",
                color=discord.Color.from_rgb(255, 130, 170)
            )
            embed.add_field(name="🚀 다음 단계", value=next_lv_info, inline=False)
            embed.add_field(
                name="📅 오늘 쌓은 친밀도",
                value=f"{daily_bar} ({daily}/{self.DAILY_CAP})\n" +
                      (f"오늘 더 친해질 수 있어요! 😊" if daily < self.DAILY_CAP else "오늘은 요미가 조금 부끄러운가 봐요! 내일 또 대화해요! 🥰"),
                inline=False
            )
            embed.set_footer(text=footer_text)
            if message.author.avatar:
                embed.set_thumbnail(url=message.author.avatar.url)
            await message.reply(embed=embed, mention_author=False)
            return True
        return False

    async def _handle_help_command(self, message, msg_no_space, user_name):
        if "도움말" in msg_no_space:
            embed = discord.Embed(
                title="🎀 요미랑 친해지는 법 🎀",
                description=f"반가워요 **{user_name}**님!\n모든 말 앞에 **'요미야'**를 붙여주세요! (✿◡‿◡)",
                color=discord.Color.from_rgb(255, 182, 193)
            )
            embed.add_field(name="💬 기본 대화", value="`안녕`, `뭐해`, `심심해`, `기억해 [내용]`, `기억목록`", inline=False)
            embed.add_field(name="💝 감정 & 상태", value="`사랑해`, `좋아해`, `호감도`, `운세`, `날씨 [지역]`", inline=False)
            embed.add_field(name="🎮 놀이", value="`주사위`, `가위바위보`, `골라줘 [A] [B]`", inline=False)
            embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else None)
            embed.set_footer(text="요미는 교주님과 이야기하는 게 제일 좋아요! ✨")
            await message.channel.send(embed=embed)
            return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        if not message.guild:
            return

        benefits = booster_utils.get_booster_benefits(message.author)
        if benefits["is_booster"]:
            bucket = self._cd_booster.get_bucket(message)
        else:
            bucket = self._cd.get_bucket(message)

        retry_after = bucket.update_rate_limit()

        content = message.content.strip()

        is_boomer = "라떼는" in content.replace(" ", "") or "나때는" in content.replace(" ", "")
        is_yomi = content.startswith("요미야") or content.startswith("요미 ")


        if not content and not message.stickers and not message.attachments:
            pass
        if not (is_boomer or is_yomi):
            return

        if getattr(self.bot, 'is_maintenance_mode', False):
            is_owner = await self.bot.is_owner(message.author)
            whitelist = await db.get_maintenance_whitelist()


            if not is_owner:
                if str(message.author.id) not in whitelist:
                    reason = getattr(self.bot, 'maintenance_reason', '점검 중입니다.')
                    end_time = getattr(self.bot, 'maintenance_end_time', '미정')
                    await message.reply(f"🛠️ **점검 중이에요!**\n사유: {reason}\n종료 예정: {end_time}\n(조금만 기다려주세요! 💦)", mention_author=False)
                    return


        if is_boomer:
            if message.author.id not in self.boomer_triggered:
                self.boomer_triggered.add(message.author.id)
                await message.reply(f"교주님... 혹시... 그... '꼰...' 아닙니다! 요미는 교주님의 옛날 이야기도 좋아해요! (도망)", mention_author=False)
                return

        if not is_yomi:
            return


        try:
            now_kst = time_utils.get_kst_now()
            current_hour = now_kst.hour

            if 3 <= current_hour < 6:
                 await message.reply("쿨... 쿨... 요미는 지금 꿈나라 여행 중이에요... 💤 (오전 6시에 일어날게요!)", mention_author=False)
                 return

            if message.guild:
                perms = message.channel.permissions_for(message.guild.me)
                if not perms.send_messages:
                    return

            if retry_after:
                await message.reply(f"천천히 말씀해주세요! 요미 눈이 뱅글뱅글 돌아요...@_@ ({retry_after:.1f}초 뒤에 다시 와주세요!)", mention_author=False)
                return

            raw_msg_content = content[3:].strip()

            msg_content = " ".join(raw_msg_content.split())
            msg_no_space = msg_content.replace(" ", "")
            user_id = str(message.author.id)
            user_name = message.author.display_name


            self._update_mood(msg_content)

            blacklist_reason = await db.is_blacklisted(user_id)
            if blacklist_reason:
                if blacklist_reason and ("욕설" in blacklist_reason or "비방" in blacklist_reason):
                    await message.reply(f"흥! {user_name}님은 나쁜 말을 너무 많이 써서 이제 말 안 섞을 거예요! ( *｀ω´) (차단 사유: {blacklist_reason})", mention_author=False)
                else:
                    await message.reply(f"저희 달님이 {user_name}님한텐 대답하시지 말라고 하셨어요..! (차단 사유: {blacklist_reason or '관리자 차단'})", mention_author=False)
                return

            if safety.check_message(msg_content):
                await db.add_warning(user_id, str(message.guild.id), str(self.bot.user.id), reason=f"부적절한 언어 감지: {msg_content}")
                warn_count = await db.get_warning_count(user_id)
                if warn_count >= 3:
                    await db.add_blacklist(user_id, reason="욕설/비방 반복 사용 (3회 누적)")
                    await message.reply(
                        f"**{user_name}**님, 약속을 너무 많이 어기셨어요...\n"
                        "요미는 이제 교주님과 대화하지 않을래요.(｡•́︿•̀｡)",
                        mention_author=False
                    )
                else:
                    await message.reply(
                        f"{safety.get_warning_message()}\n"
                        f"(경고 {warn_count}회 누적... 3번이면 요미가 토라질 거예요!)",
                        mention_author=False
                    )
                return

            allowed_channels = await db.get_setting("chatbot_channels", "")
            if allowed_channels and message.guild:
                allowed_list = [int(c.strip()) for c in allowed_channels.split(",") if c.strip().isdigit()]
                if allowed_list and message.channel.id not in allowed_list:
                    ch_mentions = " ".join([f"<#{cid}>" for cid in allowed_list])
                    await message.reply(f"여긴 너무 시끄러워요! 우리 **{ch_mentions}**에서 오붓하게 이야기할까요? (✿◡‿◡)", delete_after=10, mention_author=False)
                    return

            if not msg_content:
                await message.reply("네! 요미 여기 있어요! 무슨 이야기 하실 건가요? 귀 쫑긋! ( •̀ ω •́ )✧", mention_author=False)
                return

            if await self._handle_moderation_commands(message, msg_content, user_name):
                return

            if await self._handle_utility_commands(message, msg_content, msg_no_space, user_name, user_id):
                return

            if await self._handle_fun_commands(message, msg_content, msg_no_space, user_name, user_id):
                return

            if await self._handle_easter_eggs(message, msg_content, msg_no_space, user_name, user_id):
                return

            if await self._handle_memory_commands(message, msg_content, msg_no_space, user_id):
                return

            if await self._handle_affinity_commands(message, msg_content, msg_no_space, user_name, user_id):
                return

            if await self._handle_help_command(message, msg_no_space, user_name):
                return

            current_affinity = await db.get_affinity(user_id)

            for rule in CHAT_RULES:
                is_match = False
                keywords = rule.get("keywords", [])
                match_type = rule.get("match_type", "content")

                if match_type == "nospace":
                    if any(k in msg_no_space for k in keywords): is_match = True
                else:
                    if any(k in msg_content for k in keywords): is_match = True

                if not is_match: continue

                min_aff = rule.get("min_affinity")
                max_aff = rule.get("max_affinity")
                if min_aff is not None and current_affinity < min_aff: continue
                if max_aff is not None and current_affinity >= max_aff: continue

                chance = rule.get("chance", 1.0)
                if chance < 1.0 and random.random() > chance:
                    fail_resp = rule.get("fail_response")
                    if fail_resp:
                        await message.reply(fail_resp.replace("{user_name}", user_name), mention_author=False)
                        return
                    continue
                aff_change = rule.get("affinity_change", 0)
                if aff_change > 0:
                    bonus_gain, bonus_reasons = self.calculate_affinity_gain(msg_content)
                    total_gain = aff_change + (bonus_gain - 1)
                    if any("CRITICAL" in r for r in bonus_reasons):
                        critical_msg = next(r for r in bonus_reasons if "CRITICAL" in r)
                        await message.channel.send(f"{critical_msg} 요미가 교주님의 말씀에 깊이 감동받았어요!", delete_after=3)

                    await self.update_affinity_with_feedback(message, user_id, total_gain)
                elif aff_change < 0:
                    await self.update_affinity_with_feedback(message, user_id, aff_change)

                responses = rule.get("responses", [])
                if responses:
                    eco_reward = rule.get("economy_reward", 0)
                    if eco_reward > 0: await db.update_balance(user_id, eco_reward)

                    resp = random.choice(responses)
                    resp = resp.replace("{user_name}", user_name)
                    await message.reply(resp, mention_author=False)
                    return

            await self._handle_ai_chat(message, msg_content, user_name, user_id, current_affinity, benefits)

        except discord.Forbidden as e:
            print(f"Chatbot Permission Error (Error Code {e.code}): {e.text}")
        except Exception as e:
            print(f"Chatbot Interaction Error: {e}")
            import traceback
            traceback.print_exc()

    async def write_diary_entry(self, channel_ids=None):

        if not channel_ids:
            diary_channel_setting = await db.get_setting("diary_channel_id", "")
            if not diary_channel_setting:
                allowed_channels = await db.get_setting("chatbot_channels", "")
                if not allowed_channels: return
                channel_ids = [int(allowed_channels.split(",")[0].strip())]
            else:
                channel_ids = [int(c.strip()) for c in diary_channel_setting.split(",") if c.strip().isdigit()]

        if not channel_ids:
            return

        try:
            top_users = await db.get_top_affinity(3)
            user_names = []
            for u in top_users:
                try:
                    user = await self.bot.fetch_user(int(u[0]))
                    user_names.append(f"{user.name}님")
                except:
                    continue

            user_mentions = ", ".join(user_names) if user_names else "모든 교주님들"

            stats = await db.get_stats_summary()
            top_winner_name = "비밀"
            if stats['top_winner']:
                try:
                    winner_user = await self.bot.fetch_user(int(stats['top_winner'][0]))
                    top_winner_name = winner_user.name
                except: pass

            recent_chats = await db.get_recent_global_chat(limit=30)
            chat_context_lines = []
            active_user_ids = set()

            if recent_chats:
                for chat in recent_chats:
                    if 'user_id' in chat:
                        active_user_ids.add(chat['user_id'])

                    content = chat['content']
                    if len(content) > 50: content = content[:50] + "..."
                    chat_context_lines.append(f"- {content}")

            active_user_count = len(active_user_ids)
            chat_context_str = "\n".join(chat_context_lines) if chat_context_lines else "최근 조용함..."

            current_phase = moon.get_current_moon_phase()
            moon_info = moon.MOON_PHASES[current_phase]['desc']

            snacks = ["붕어빵", "달떡", "초코 쿠키", "딸기 마카롱", "요거트", "푸딩", "치즈 케이크", "군고구마", "타코야끼", "솜사탕", "무지개 케이크", "특제 스테이크"]
            today_snack = random.choice(snacks)


            weekday = time_utils.get_kst_now().weekday()
            themes = {
                0: "월요병 (조금 피곤하지만 힘내는 중)",
                1: "화이팅 (열심히 일하는 날)",
                2: "여유 (중간 점검)",
                3: "설렘 (주말이 다가옴)",
                4: "불금 (신나는 기분)",
                5: "휴식 (느긋한 주말)",
                6: "아쉬움 (내일이 월요일이라니...)"
            }
            today_theme = themes.get(weekday, "평화로움")

            events = [
                "길가다 예쁜 꽃을 발견했다.",
                "누군가 몰래 두고 간 선물을 찾았다.",
                "실수로 물을 엎질렀는데 하트 모양이 되었다.",
                "꿈에서 교주님을 만난 것 같다.",
                "새로운 레시피를 개발하다가 태워먹었다...",
                "달빛이 너무 예뻐서 한참을 쳐다봤다.",
                "갑자기 옛날 생각이 났다."
            ]
            today_event = random.choice(events)

            system_instruction = (
                f"당신은 **달의 사제** '요미'입니다. "
                f"아무도 보지 않을 거라고 생각하고 오늘의 비밀 일기를 작성하세요.\n\n"
                f"[현재 상태 정보]\n"
                f"- 현재 시간: {time_utils.get_kst_now().strftime('%Y년 %m월 %d일 %H시 %M분')}\n"
                f"- 현재 달의 위상: {current_phase} ({moon_info})\n"
                f"- 오늘의 기분/테마: {today_theme}\n"
                f"- 오늘의 특별한 사건: {today_event}\n"
                f"- 최근 대화 참여 교주님: {active_user_count}명\n"
                f"- 가장 친한 교주님들: {user_mentions}\n"
                f"- 오늘의 행운아: {top_winner_name}님 (최대 당첨금: {stats['top_winner'][1] if stats['top_winner'] else 0:,} 젤리)\n"
                f"- 서버 전체 친밀도 총합: {stats['total_affinity']:,}\n"
                f"- 총 대화 횟수: {stats['total_interactions']:,}회\n"
                f"- 오늘의 간식: {today_snack}\n\n"
                f"[최근 교주님들의 대화 내용 (참고용)]\n"
                f"{chat_context_str}\n\n"
                f"[작성 조건]\n"
                f"1. 말투: 혼잣말하는 듯한 독백체 (반말 사용, ~했다, ~했어)\n"
                f"2. **이모지 금지**: 그림 이모티콘(✨, 💖, 😊 등)을 절대로 사용하지 마세요.\n"
                f"3. **카오모지 전용**: 오직 카오모지(예: (✿◡‿◡), (≧∇≦)ﾉ, (｡•̀ᴗ-)✧, (///ω///))만 사용하세요.\n"
                f"4. 내용: 오늘 있었던 일({today_event}), 먹은 간식, 달의 모습, 오늘의 기분({today_theme}) 등을 자연스럽게 섞어서 적으세요.\n"
                f"5. **비밀 유지**: 남들이 보면 부끄러운 내용이나 속마음을 적으세요. '들키면 안 되는데...', '비밀인데...' 같은 뉘앙스.\n"
                f"6. 특정 교주님({user_mentions})이나 행운아({top_winner_name})를 언급할 때는 짝사랑하듯 몰래 언급하세요.\n"
                f"7. **데이터 부족 시**: 만약 교주님 목록이나 대화 횟수가 없거나 0이라면, 오늘은 평화롭게 혼자 시간을 보냈다고 상상하며 자유롭게 작성하세요.\n"
            )

            prompt = "오늘의 일기를 작성해."

            diary_text = ""
            if self.genai_client:
                diary_text = await self._generate_gemini_text(prompt, system_instruction=system_instruction, timeout_seconds=30)

            if not diary_text:
                diary_text = f"오늘 달이 참 예쁘다... {user_mentions} 오늘 뭐 하셨을까? 사실 교주님들 생각하면서 {today_snack} 먹었는데... 헤헤. 아무한테도 말 못 해! (✿◡‿◡)"
            embed = discord.Embed(
                title="🔒 자물쇠가 걸린 일기장",
                description=f"*(누군가 떨어뜨린 낡은 일기장이다. 몰래 펼쳐볼까...?)*\n\n```\n{diary_text}\n```",
                color=discord.Color.from_rgb(180, 160, 255)            )


            embed.set_footer(text="뒷장에는 낙서가 가득하다...")

            view = DiaryView()

            sent_count = 0
            for cid in channel_ids:
                try:
                    channel = self.bot.get_channel(cid)
                    if channel:
                        await channel.send(embed=embed, view=view)
                        sent_count += 1
                except Exception as e:
                    print(f"Failed to send diary to channel {cid}: {e}")

            if sent_count > 0:
                return True, f"총 {sent_count}개 채널에 일기를 썼어요!"
            else:
                return False, "일기를 쓸 채널을 찾지 못했거나 전송에 실패했어요. (봇 권한이나 채널 ID를 확인해주세요)"

        except Exception as e:
            print(f"Diary Generation Error: {e}")
            return False, f"일기 생성 중 오류가 발생했어요: {e}"

    async def diary_loop(self):

        await self.bot.wait_until_ready()

        from datetime import datetime, timedelta

        while not self.bot.is_closed():
            now = time_utils.get_kst_now()

            target_times = [9, 21]
            next_run = None

            for hour in target_times:
                candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if candidate > now:
                    next_run = candidate
                    break

            if not next_run:
                next_run = (now + timedelta(days=1)).replace(hour=target_times[0], minute=0, second=0, microsecond=0)

            wait_seconds = (next_run - now).total_seconds()

            await asyncio.sleep(wait_seconds)
            await self.write_diary_entry()

            await asyncio.sleep(60)

class DiaryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=43200)
    @discord.ui.button(label="몰래 공감하기", style=discord.ButtonStyle.secondary, emoji="🤫")
    async def like_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        reward = random.randint(30, 100)
        affinity = 3

        await db.update_balance(user_id, reward)
        await db.update_affinity(user_id, affinity)

        await interaction.response.send_message(
            f"🤫 **(두근두근)** 요미 몰래 일기에 공감 버튼을 눌렀어요...\n(보상: {reward} 젤리, 호감도 +{affinity})",
            ephemeral=True
        )

    @discord.ui.button(label="쪽지 끼워넣기", style=discord.ButtonStyle.primary, emoji="💌")
    async def reply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DiaryModal())

class DiaryModal(discord.ui.Modal, title="일기장 사이에 쪽지 끼워넣기"):
    reply = discord.ui.TextInput(
        label="쪽지 내용",
        style=discord.TextStyle.paragraph,
        placeholder="요미가 나중에 발견하길 바라며...",
        required=True,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        content = self.reply.value

        await db.update_affinity(user_id, 10)

        await interaction.response.send_message(
            f"💌 **(사각사각)** 일기장 사이에 몰래 쪽지를 끼워넣었어요!\n요미가 발견하고 기뻐할까요? (호감도 +10)",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Chatbot(bot))