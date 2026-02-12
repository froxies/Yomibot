
import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import sys
import os

import utils.db as db

class Interaction(commands.Cog):


    def __init__(self, bot):
        self.bot = bot

    async def update_affinity(self, interaction: discord.Interaction, amount: int):

        user_id = str(interaction.user.id)
        db.update_affinity(user_id, amount)
        return

    @app_commands.command(name="가위바위보", description="요미와 가위바위보 대결! 젤리를 걸 수도 있어요.")
    @app_commands.describe(choice="가위, 바위, 보 중 하나를 선택하세요.", bet="걸고 싶은 젤리 금액 (기본: 0)")
    @app_commands.rename(choice="선택", bet="금액")
    @app_commands.choices(choice=[
        app_commands.Choice(name="가위 ✌️", value="scissors"),
        app_commands.Choice(name="바위 ✊", value="rock"),
        app_commands.Choice(name="보 🖐️", value="paper"),
    ])
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str], bet: int = 0):

        user_choice = choice.value
        user_id = str(interaction.user.id)

        if bet < 0:
            return await interaction.response.send_message("배팅 금액은 0 이상이어야 해요! (😠)", ephemeral=True)

        if bet > 0:
            if not await db.try_deduct_balance(user_id, bet):
                current_balance = await db.get_balance(user_id)
                return await interaction.response.send_message(f"젤리가 부족해요! 현재 **{current_balance:,}** 젤리를 가지고 있어요.", ephemeral=True)

        await interaction.response.send_message("✌️ **가위...**")
        msg = await interaction.original_response()
        await asyncio.sleep(0.8)
        await msg.edit(content="✊ **바위...**")
        await asyncio.sleep(0.8)


        choices = ["scissors", "rock", "paper"]



        winning_move = ""
        losing_move = ""
        if user_choice == "scissors":
            winning_move = "rock"
            losing_move = "paper"
        elif user_choice == "rock":
            winning_move = "paper"
            losing_move = "scissors"
        else:
            winning_move = "scissors"
            losing_move = "rock"

        outcome_weights = [20, 35, 45]
        bot_choice = random.choices([losing_move, user_choice, winning_move], weights=outcome_weights, k=1)[0]

        emoji_map = {"scissors": "✌️", "rock": "✊", "paper": "🖐️"}
        korean_map = {"scissors": "가위", "rock": "바위", "paper": "보"}

        result = "draw"
        if user_choice == bot_choice:
            result = "draw"
        elif (user_choice == "rock" and bot_choice == "scissors") or \
             (user_choice == "scissors" and bot_choice == "paper") or \
             (user_choice == "paper" and bot_choice == "rock"):
            result = "win"
        else:
            result = "lose"

        embed = discord.Embed(title="✌️ 가위바위보 대결! ✊", color=discord.Color.blue())
        embed.add_field(name=f"{interaction.user.display_name}", value=f"{emoji_map[user_choice]} **{korean_map[user_choice]}**", inline=True)
        embed.add_field(name="VS", value="⚡", inline=True)
        embed.add_field(name="요미", value=f"{emoji_map[bot_choice]} **{korean_map[bot_choice]}**", inline=True)

        final_msg = ""

        if result == "win":
            profit = int(bet * 1.9)
            if bet > 0:
                await db.update_balance(user_id, profit)
                await db.update_game_stats(user_id, profit - bet, True)
                final_msg = f"🎉 **와아! 이겼어요!**\n배팅한 **{bet:,}** 젤리의 1.9배인 **{profit:,}** 젤리를 획득했습니다!"
            else:
                final_msg = "🎉 **와아! 이겼어요!**\n(다음엔 젤리를 걸어보세요!)"

            embed.color = discord.Color.green()
            embed.description = final_msg + "\n*(💕 호감도 +3)*"
            await db.update_affinity(user_id, 3)

        elif result == "draw":
            if bet > 0:
                await db.update_balance(user_id, bet)
                final_msg = f"🤝 **비겼네요!**\n배팅한 **{bet:,}** 젤리를 돌려드립니다."
            else:
                final_msg = "🤝 **비겼네요!** 다시 한 번 해봐요!"

            embed.color = discord.Color.light_grey()
            embed.description = final_msg + "\n*(💕 호감도 +1)*"
            await db.update_affinity(user_id, 1)

        else:
            if bet > 0:
                await db.update_game_stats(user_id, 0, False)
                final_msg = f"😭 **제가 이겼어요!**\n배팅한 **{bet:,}** 젤리는 제가 가져갈게요! 냠냠!"
            else:
                final_msg = "✌️ **제가 이겼어요!** 헤헤, 제가 좀 하죠?"

            embed.color = discord.Color.red()
            embed.description = final_msg + "\n*(💕 호감도 +1)*"
            await db.update_affinity(user_id, 1)

        class RPSView(discord.ui.View):
            def __init__(self, user_id, last_bet, user_choice_val):
                super().__init__(timeout=60)
                self.user_id = user_id
                self.last_bet = last_bet
                self.user_choice_val = user_choice_val
                self.processing = False

            @discord.ui.button(label="다시 하기 (같은 조건)", style=discord.ButtonStyle.primary, emoji="🔄")
            async def replay(self, b_interaction: discord.Interaction, button: discord.ui.Button):
                if str(b_interaction.user.id) != self.user_id:
                    return await b_interaction.response.send_message("본인만 재대결할 수 있어요!", ephemeral=True)

                if self.processing:
                    return await b_interaction.response.send_message("처리 중입니다...", ephemeral=True)
                self.processing = True

                if self.last_bet > 0:
                    if not await db.try_deduct_balance(self.user_id, self.last_bet):
                        self.processing = False
                        return await b_interaction.response.send_message("젤리가 부족해서 재대결을 할 수 없어요!", ephemeral=True)

                await b_interaction.response.defer()


                await b_interaction.edit_original_response(content="✌️ **가위...**", embed=None, view=None)
                await asyncio.sleep(0.8)
                await b_interaction.edit_original_response(content="✊ **바위...**")
                await asyncio.sleep(0.8)

                w_move = ""
                l_move = ""
                usr_c = self.user_choice_val

                if usr_c == "scissors":
                    w_move = "rock"
                    l_move = "paper"
                elif usr_c == "rock":
                    w_move = "paper"
                    l_move = "scissors"
                else:
                    w_move = "scissors"
                    l_move = "rock"

                weights = [20, 35, 45]
                bot_c = random.choices([l_move, usr_c, w_move], weights=weights, k=1)[0]

                res = "draw"
                if usr_c == bot_c: res = "draw"
                elif (usr_c == "rock" and bot_c == "scissors") or \
                     (usr_c == "scissors" and bot_c == "paper") or \
                     (usr_c == "paper" and bot_c == "rock"): res = "win"
                else: res = "lose"

                new_embed = discord.Embed(title="✌️ 가위바위보 재대결! ✊", color=discord.Color.blue())
                new_embed.add_field(name=f"{b_interaction.user.display_name}", value=f"{emoji_map[usr_c]} **{korean_map[usr_c]}**", inline=True)
                new_embed.add_field(name="VS", value="⚡", inline=True)
                new_embed.add_field(name="요미", value=f"{emoji_map[bot_c]} **{korean_map[bot_c]}**", inline=True)

                f_msg = ""
                if res == "win":
                    p = int(self.last_bet * 1.9)
                    if self.last_bet > 0:
                        await db.update_balance(self.user_id, p)
                        await db.update_game_stats(self.user_id, p - self.last_bet, True)
                        f_msg = f"🎉 **와아! 이겼어요!**\n**{p:,}** 젤리를 획득했습니다!"
                    else: f_msg = "🎉 **와아! 이겼어요!**"
                    new_embed.color = discord.Color.green()
                    await db.update_affinity(self.user_id, 3)
                elif res == "draw":
                    if self.last_bet > 0:
                        await db.update_balance(self.user_id, self.last_bet)
                        f_msg = f"🤝 **비겼네요!**\n배팅한 젤리를 돌려드립니다."
                    else: f_msg = "🤝 **비겼네요!**"
                    new_embed.color = discord.Color.light_grey()
                    await db.update_affinity(self.user_id, 1)
                else:
                    if self.last_bet > 0:
                        await db.update_game_stats(self.user_id, 0, False)
                        f_msg = f"😭 **제가 이겼어요!**\n냠냠! 젤리 잘 먹겠습니다!"
                    else: f_msg = "✌️ **제가 이겼어요!**"
                    new_embed.color = discord.Color.red()
                    await db.update_affinity(self.user_id, 1)

                new_embed.description = f_msg + "\n*(💕 호감도 획득)*"

                await b_interaction.edit_original_response(content="🖐️ **보!!**", embed=new_embed, view=self)

        await msg.edit(content="🖐️ **보!!**", embed=embed, view=RPSView(user_id, bet, user_choice))

    @app_commands.command(name="산책", description="요미와 함께 산책을 떠나요! (10분 쿨타임)")
    @app_commands.checks.cooldown(1, 600, key=lambda i: (i.guild_id, i.user.id))
    async def walk(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)
        affinity = await db.get_affinity(user_id)

        locations = [
            {"name": "동네 공원", "desc": "한적한 공원이에요. 새들이 지저귀네요.", "affinity": 5, "min_affinity": 0, "color": discord.Color.green()},
            {"name": "번화가", "desc": "사람들이 많은 거리! 맛있는 냄새가 나요.", "affinity": 8, "min_affinity": 50, "color": discord.Color.orange()},
            {"name": "해변", "desc": "철썩이는 파도 소리... 마음이 편안해져요.", "affinity": 12, "min_affinity": 150, "color": discord.Color.blue()},
            {"name": "놀이공원", "desc": "와아! 놀이공원이에요! 관람차 타러 가요!", "affinity": 20, "min_affinity": 350, "color": discord.Color.purple()},
            {"name": "달맞이 언덕", "desc": "달이 가장 잘 보이는 언덕... 우리 둘뿐이에요. (✿◡‿◡)", "affinity": 30, "min_affinity": 700, "color": discord.Color.dark_blue()}
        ]

        available = [loc for loc in locations if affinity >= loc["min_affinity"]]
        if not available: available = [locations[0]]
        destination = random.choice(available)

        events = [
            "함께 아이스크림을 나눠 먹었어요. 🍦",
            "예쁜 꽃을 발견해서 머리에 꽂아주었어요. 🌸",
            "길 잃은 고양이를 도와주었어요. 🐱",
            "벤치에 앉아서 도란도란 이야기를 나누었어요. 💬",
            "손을 잡고 걸었어요. 조금 부끄럽네요... 😳",
            "멋진 풍경을 배경으로 사진을 찍었어요. 📸"
        ]
        event = random.choice(events)

        await self.update_affinity(interaction, destination["affinity"])

        embed = discord.Embed(
            title=f"🚶‍♀️ {destination['name']} 산책",
            description=f"{destination['desc']}\n\n✨ **{event}**",
            color=destination['color']
        )
        embed.set_footer(text=f"즐거운 시간이었어요! (호감도 +{destination['affinity']})")
        if interaction.user.avatar:
            embed.set_thumbnail(url=interaction.user.avatar.url)

        await interaction.response.send_message(embed=embed)

    @walk.error
    async def walk_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            minutes = int(error.retry_after // 60)
            seconds = int(error.retry_after % 60)
            await interaction.response.send_message(f"조금만 쉬었다가 가요! 다리가 아파요... (｡•́︿•̀｡)\n({minutes}분 {seconds}초 뒤에 가능)", ephemeral=True)

    @app_commands.command(name="쓰담쓰담", description="요미를 쓰담쓰담 해줘요. (1분 쿨타임)")
    @app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id, i.user.id))
    async def pat(self, interaction: discord.Interaction):

        await self.update_affinity(interaction, 2)

        responses = [
            "에헤헤... 기분 좋아요... (✿◡‿◡)",
            "교주님 손길은 따뜻하네요...",
            "부끄럽지만... 더 해주세요...!",
            "골골송을 부를 것 같아요... 냥?",
            "(지긋이 바라본다) 사랑해요, 교주님."
        ]

        await interaction.response.send_message(f"👋 **{interaction.user.display_name}**님이 요미를 쓰담쓰담 해주었어요.\n\n요미: {random.choice(responses)} (호감도 +2)")

    @pat.error
    async def pat_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"너무 많이 만지면 부끄러워요...! ///// ({int(error.retry_after)}초 뒤에)", ephemeral=True)

    @app_commands.command(name="퀴즈", description="요미가 내는 간단한 퀴즈를 맞추고 호감도를 올려보세요!")
    async def quiz(self, interaction: discord.Interaction):

        quizzes = [
            {"q": "요미가 가장 좋아하는 사람은 누구일까요?", "a": ["교주님", "너", "나", "사용자", interaction.user.display_name], "hint": "바로 당신!"},
            {"q": "사과가 웃으면?", "a": ["풋사과"], "hint": "풋..."},
            {"q": "왕이 넘어지면?", "a": ["킹콩"], "hint": "킹...콩!"},
            {"q": "바나나가 웃으면?", "a": ["바나나킥"], "hint": "과자 이름 같아요."},
            {"q": "세상에서 가장 뜨거운 바다는?", "a": ["열바다"], "hint": "화날 때..."},
            {"q": "요미의 생일은 언제일까요?", "a": ["1월 1일", "모름", "비밀"], "hint": "사실 정해지지 않았어요... (1월 1일로 칠까요?)"},
             {"q": "세상에서 가장 추운 바다는?", "a": ["썰렁해"], "hint": "아재개그..."}
        ]

        quiz = random.choice(quizzes)

        class QuizModal(discord.ui.Modal, title='요미의 퀴즈 시간!'):
            answer = discord.ui.TextInput(label='정답은?', placeholder='정답을 입력해주세요!')

            async def on_submit(self, interaction: discord.Interaction):
                if any(ans in self.answer.value for ans in quiz['a']):
                    await db.update_affinity(str(interaction.user.id), 5)
                    await interaction.response.send_message(f"🎉 **정답이에요!** 대단해요 교주님! (호감도 +5)")
                else:
                    await interaction.response.send_message(f"땡! 틀렸어요... 정답은 **{quiz['a'][0]}** 였답니다! (바보... 😋)")

        await interaction.response.send_modal(QuizModal())

async def setup(bot):
    await bot.add_cog(Interaction(bot))
