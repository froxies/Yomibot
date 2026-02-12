
import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
import asyncio
import sys
import os
import json
import sqlite3
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import io
import math
import time
from datetime import datetime
import utils.time_utils as time_utils
import aiosqlite

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils.db as db
import utils.moon_system as moon
import utils.booster_utils as booster_utils

class EnhancedFishingView(discord.ui.View):
    def __init__(self, user_id, bot, economy_cog, rod_level, biome_data, timeout=600):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.bot = bot
        self.economy_cog = economy_cog
        self.rod_level = rod_level
        self.biome_data = biome_data

        self.status = "waiting"
        self.reaction_time = 0
        self.bite_time = 0
        self.auto_mode = False
        self.msg = None
        self.settings_open = False

        self.remove_item(self.toggle_auto_fish)
        self.remove_item(self.change_rod_select)

    def reset_state(self):

        self.status = "waiting"
        self.reaction_time = 0
        self.bite_time = 0

        fish_btn = [x for x in self.children if isinstance(x, discord.ui.Button) and x.custom_id == "fish_button"][0]
        fish_btn.disabled = False
        fish_btn.label = "🎣 낚아채기!"
        fish_btn.style = discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("다른 사람의 낚시대입니다!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🎣 낚아채기!", style=discord.ButtonStyle.secondary, custom_id="fish_button", row=0)
    async def fish_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        now = time.time()

        if self.status == "waiting" or self.status == "nibble":
            self.status = "failed"
            button.style = discord.ButtonStyle.danger
            button.label = "너무 빨랐어요!"
            button.disabled = True
            await interaction.response.edit_message(view=self)
            self.stop()

        elif self.status == "biting":
            self.status = "caught"
            self.reaction_time = now - self.bite_time
            button.style = discord.ButtonStyle.success
            button.label = "성공!"
            button.disabled = True
            await interaction.response.edit_message(view=self)

        elif self.status == "escaped":
             self.status = "failed"
             button.style = discord.ButtonStyle.danger
             button.label = "놓쳤어요..."
             button.disabled = True
             await interaction.response.edit_message(view=self)

    @discord.ui.button(label="⚙️ 설정", style=discord.ButtonStyle.secondary, row=0)
    async def settings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.settings_open = not self.settings_open

        if self.settings_open:
            button.style = discord.ButtonStyle.primary
            self.add_item(self.toggle_auto_fish)
            self.add_item(self.change_rod_select)
        else:
            button.style = discord.ButtonStyle.secondary
            self.remove_item(self.toggle_auto_fish)
            self.remove_item(self.change_rod_select)

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="🔄 자동 낚시: OFF", style=discord.ButtonStyle.secondary, row=1, custom_id="auto_fish_btn")
    async def toggle_auto_fish(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.auto_mode = not self.auto_mode
        state = "ON" if self.auto_mode else "OFF"
        button.label = f"🔄 자동 낚시: {state}"
        button.style = discord.ButtonStyle.success if self.auto_mode else discord.ButtonStyle.secondary

        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"자동 낚시 모드가 **{state}**로 변경되었습니다.", ephemeral=True)

    @discord.ui.select(placeholder="낚시대 정보 확인", min_values=1, max_values=1, options=[
        discord.SelectOption(label="현재 낚시대 정보", value="info", description="사용 중인 낚시대의 성능을 확인합니다."),
    ], row=2, custom_id="rod_select")
    async def change_rod_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        rod_name = self.economy_cog.upgrades["fishing_rod"][self.rod_level]["name"]
        rod_desc = self.economy_cog.upgrades["fishing_rod"][self.rod_level]["desc"]
        await interaction.response.send_message(f"🎣 **현재 낚시대**: {rod_name}\n📜 {rod_desc}", ephemeral=True)

class Economy(commands.Cog):


    pet_group = app_commands.Group(name="펫", description="펫 시스템 관련 명령어입니다.")
    dungeon_group = app_commands.Group(name="던전", description="던전 시스템 관련 명령어입니다.")
    store_group = app_commands.Group(name="상점", description="상점 및 거래 관련 명령어입니다.")
    activity_group = app_commands.Group(name="활동", description="채집 및 생산 활동 관련 명령어입니다.")
    game_group = app_commands.Group(name="게임", description="도박 및 미니게임 관련 명령어입니다.")
    stock_group = app_commands.Group(name="투자", description="주식 및 부동산 관련 명령어입니다.")

    def __init__(self, bot):
        self.bot = bot
        self.currency_name = "젤리"
        self.currency_icon = "🍬"
        self.active_quiz_channels = set()

        self.pet_group = app_commands.Group(name="펫", description="펫 시스템 관련 명령어입니다.")
        self.dungeon_group = app_commands.Group(name="던전", description="던전 시스템 관련 명령어입니다.")

        self.load_game_data()
        self.stock_market_loop.start()

    def load_game_data(self):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            data_path = os.path.join(current_dir, '..', 'data', 'items.json')

            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.default_stocks = data.get("default_stocks", [])
                self.tycoon_buildings = data.get("tycoon_buildings", {})
                self.shop_items = data.get("shop_items", {})
                self.pet_shop_items = data.get("pet_shop_items", {})
                self.battle_items = data.get("battle_items", {})
                self.armor_items = data.get("armor_items", {})
                self.set_bonuses = data.get("set_bonuses", {})
                self.fishing_biomes = data.get("fishing_biomes", {})
                self.collectible_items = data.get("collectible_items", {})
                self.upgrades = data.get("upgrades", {})
        except Exception as e:
            print(f"Failed to load game data: {e}")
            self.default_stocks = []
            self.tycoon_buildings = {}
            self.shop_items = {}
            self.pet_shop_items = {}
            self.battle_items = {}
            self.armor_items = {}
            self.set_bonuses = {}
            self.fishing_biomes = {}
            self.collectible_items = {}
            self.upgrades = {}

    def cog_unload(self):
        self.stock_market_loop.cancel()

    @tasks.loop(minutes=30)
    async def stock_market_loop(self):

        await db.init_stock_market(self.default_stocks)

        stocks = await db.get_all_stocks()
        if not stocks: return

        for stock in stocks:
            change_percent = random.gauss(0, stock['volatility'])
            new_price = int(stock['price'] * (1 + change_percent))
            new_price = max(100, new_price)
            await db.update_stock_price(stock['stock_id'], new_price)

    @stock_market_loop.before_loop
    async def before_stock_loop(self):
        await self.bot.wait_until_ready()


    async def cog_load(self):

        self.market_update_loop.start()

    async def get_armor_level(self, user_id, item_name):
        return await db.get_armor_level(user_id, item_name)

    async def set_armor_level(self, user_id, item_name, level):
        await db.set_armor_level(user_id, item_name, level)

    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:

        try:
            items = list(self.shop_items.keys()) + list(self.pet_shop_items.keys()) + list(self.battle_items.keys()) + list(self.armor_items.keys())
            return [
                app_commands.Choice(name=item, value=item)
                for item in items if current.lower() in item.lower()
            ][:25]
        except Exception as e:
            print(f"Autocomplete Error: {e}")
            return []

    async def buy_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:

        category = interaction.namespace.category
        items = []

        if category == "affinity":
            items = list(self.shop_items.keys())
        elif category == "pet":
            items = list(self.pet_shop_items.keys())
        elif category == "battle":
            items = list(self.battle_items.keys())
        elif category == "armor":
            items = list(self.armor_items.keys())
        else:
            items = list(self.shop_items.keys()) + list(self.pet_shop_items.keys()) + list(self.battle_items.keys()) + list(self.armor_items.keys())

        return [
            app_commands.Choice(name=f"{item} ({self.get_item_price(item):,} 젤리)", value=item)
            for item in items if current.lower() in item.lower()
        ][:25]

    def get_item_price(self, item_name):
        all_shops = [self.shop_items, self.pet_shop_items, self.battle_items, self.armor_items]
        for shop in all_shops:
            if item_name in shop:
                return shop[item_name]["price"]
        return 0

    async def sell_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:

        user_id = str(interaction.user.id)
        inv = await db.get_inventory(user_id)
        category = interaction.namespace.category

        filtered_inv = []

        for item in inv:
            name = item['item_name']

            item_cat = "etc"
            if name in self.collectible_items:
                c_type = self.collectible_items[name].get("type")
                if c_type == "mineral": item_cat = "mineral"
                elif c_type in ["fish", "deep_sea_fish"]: item_cat = "fish"
                elif c_type == "wood": item_cat = "wood"
            elif name in self.armor_items:
                item_cat = "armor"
            elif name in self.battle_items:
                item_cat = "consumable"
            elif name in self.shop_items:
                item_cat = "etc"

            if category == "mineral" and item_cat == "mineral": filtered_inv.append(item)
            elif category == "fish" and item_cat == "fish": filtered_inv.append(item)
            elif category == "wood" and item_cat == "wood": filtered_inv.append(item)
            elif category == "armor" and item_cat == "armor": filtered_inv.append(item)
            elif category == "consumable" and item_cat == "consumable": filtered_inv.append(item)
            elif not category: filtered_inv.append(item)
        return [
            app_commands.Choice(name=f"{i['item_name']} ({i['amount']}개)", value=i['item_name'])
            for i in filtered_inv if current.lower() in i['item_name'].lower()
        ][:25]

    async def inventory_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:

        try:
            user_id = str(interaction.user.id)
            items = await db.get_inventory(user_id)
            return [
                app_commands.Choice(name=f"{item['item_name']} ({item['amount']}개)", value=item['item_name'])
                for item in items if current.lower() in item['item_name'].lower()
            ][:25]
        except Exception as e:
            print(f"Inventory Autocomplete Error: {e}")
            return []

    async def cog_unload(self):

        self.market_update_loop.cancel()

    @tasks.loop(minutes=30)
    async def market_update_loop(self):

        status = await db.get_market_status()

        for item_name, data in self.collectible_items.items():
            base_price = data['price']
            current_data = status.get(item_name)

            if current_data:
                current_price = current_data['current_price']
                volatility = 0.05
                if random.random() < 0.1:
                    volatility = 0.15

                change_pct = random.uniform(-volatility, volatility)

                if current_data['trend'] == 'up':
                    change_pct += 0.01
                elif current_data['trend'] == 'down':
                    change_pct -= 0.01

                new_price = int(current_price * (1 + change_pct))

                new_price = max(int(base_price * 0.5), min(new_price, int(base_price * 5.0)))

                if new_price > current_price:
                    new_trend = 'up'
                elif new_price < current_price:
                    new_trend = 'down'
                else:
                    new_trend = 'stable'

                real_change_pct = (new_price - current_price) / current_price * 100 if current_price else 0

            else:
                new_price = base_price
                new_trend = 'stable'
                real_change_pct = 0.0

            await db.update_market_price(item_name, new_price, new_trend, real_change_pct)

    @market_update_loop.before_loop
    async def before_market_loop(self):
        await self.bot.wait_until_ready()

    async def get_market_price(self, item_name: str) -> int:

        status = await db.get_market_status(item_name)
        if status:
            return status['current_price']

        if item_name in self.collectible_items:
            return self.collectible_items[item_name]['price']
        return 0

    async def get_affinity_bonus(self, user_id: str):

        affinity = await db.get_affinity(user_id)
        current_phase = moon.get_current_moon_phase()
        moon_info = moon.MOON_PHASES[current_phase]

        import math
        if affinity < 50:
            level = 0
        else:
            level = min(int(math.log(affinity / 50, 1.4) + 1), 1000)

        multiplier = (1.0 + (level * 0.1)) * moon_info['multi']
        chance_bonus = min(level * 0.5, 50.0)

        user_pets = await db.get_user_pets(user_id)
        for pet in user_pets:
            pet_type = pet['pet_type']
            pet_lv = pet['level']
            if pet_type in moon.PET_DATA:
                p_data = moon.PET_DATA[pet_type]
                bonus_val = p_data['base_bonus'] * pet_lv
                if p_data['type'] == "eco":
                    multiplier += bonus_val
                elif p_data['type'] == "chance":
                    chance_bonus += (bonus_val * 100)
        return multiplier, chance_bonus, current_phase

    @activity_group.command(name="낚시", description="낚시를 해서 물고기와 젤리를 획득합니다.")
    @app_commands.describe(location="낚시할 장소를 선택합니다.")
    @app_commands.choices(location=[
        app_commands.Choice(name="🏞️ 평화로운 호수 (Lv.0)", value="lake"),
        app_commands.Choice(name="🌊 거친 바다 (Lv.2)", value="ocean"),
        app_commands.Choice(name="⚓ 심해 (Lv.5)", value="deep_sea"),
        app_commands.Choice(name="🌌 은하수 호수 (Lv.8)", value="galaxy")
    ])
    async def fish(self, interaction: discord.Interaction, location: str = "lake"):

        await interaction.response.defer()

        try:
            user_id = str(interaction.user.id)

            benefits = booster_utils.get_booster_benefits(interaction.user)
            cooldown_time = 60 * benefits["cooldown_mult"]

            cooldown = await db.check_cooldown(user_id, "fish", cooldown_time)
            if cooldown > 0:
                return await interaction.followup.send(f"헤헤... 낚시는 조금만 쉬었다가 해요! 아직 {int(cooldown)}초 남았다구요! (｡•́︿•̀｡)")

            rod_level = await db.get_upgrade(user_id, "fishing_rod")
            max_rod_level = len(self.upgrades["fishing_rod"]) - 1
            rod_level = min(rod_level, max_rod_level)
            rod_info = self.upgrades["fishing_rod"][rod_level]

            biome_data = self.fishing_biomes.get(location)
            if not biome_data:
                return await interaction.followup.send("존재하지 않는 낚시터입니다.")

            if rod_level < biome_data["level_req"]:
                return await interaction.followup.send(f"🚫 이 낚시터는 **낚시대 레벨 {biome_data['level_req']}** 이상부터 입장할 수 있어요!\n현재 레벨: {rod_level}")

            if biome_data["cost"] > 0:
                if not await db.try_deduct_balance(user_id, biome_data["cost"]):
                     return await interaction.followup.send(f"🚫 입장료가 부족해요! (**{biome_data['cost']:,}** 젤리 필요)")

            collection = await db.get_fish_collection(user_id)
            if not collection:
                tut_embed = discord.Embed(title="🎣 낚시 가이드", description="요미 봇 낚시 시스템에 오신 것을 환영합니다!", color=discord.Color.green())
                tut_embed.add_field(name="1. 찌 던지기", value="명령어를 입력하면 찌를 던집니다.", inline=False)
                tut_embed.add_field(name="2. 입질 기다리기", value="`...` 물결이 치다가 `🐟` 물고기가 접근합니다.", inline=False)
                tut_embed.add_field(name="3. 낚아채기!", value="**입질이 왔어요!!!** 메시지와 함께 버튼이 붉게 변하면 즉시 버튼을 누르세요!", inline=False)
                tut_embed.add_field(name="Tip", value="낚시대 등급이 오르면 반응 시간이 여유로워지고 보상이 커집니다.", inline=False)
                await interaction.followup.send(embed=tut_embed, ephemeral=True)
                await asyncio.sleep(3)

            auto_count = 0
            max_auto = 10
            msg = None

            view = EnhancedFishingView(user_id, self.bot, self, rod_level, biome_data)

            while True:
                view.reset_state()

                embed = discord.Embed(title=f"🎣 {biome_data['name']}", description="찌를 던졌습니다... \n🌊 . . .", color=discord.Color.blue())
                embed.set_footer(text="찌가 깊이 들어가면 [낚아채기!] 버튼을 누르세요.")

                if msg:
                    await msg.edit(embed=embed, view=view)
                else:
                    msg = await interaction.followup.send(embed=embed, view=view)

                view.msg = msg

                wait_time = random.uniform(3.0, 7.0)
                start_wait = time.time()
                while time.time() - start_wait < wait_time:
                    await asyncio.sleep(0.5)
                    if view.status == "failed": break

                if view.status == "failed": return
                view.status = "biting"
                view.bite_time = time.time()

                embed.title = "🎣 입질이 왔어요!!!"
                embed.description = "**💦 첨벙!!! 지금 당장 낚아채세요!!!**"
                embed.color = discord.Color.red()
                fish_btn = [x for x in view.children if isinstance(x, discord.ui.Button) and x.custom_id == "fish_button"][0]
                fish_btn.style = discord.ButtonStyle.danger

                try:
                    await msg.edit(embed=embed, view=view)
                except:
                    return

                base_window = 1.5
                window_bonus = rod_level * 0.1
                biome_penalty = {"lake": 0, "ocean": 0.3, "deep_sea": 0.6, "galaxy": 0.8}.get(location, 0)

                final_window = max(0.5, base_window + window_bonus - biome_penalty)

                await asyncio.sleep(final_window)

                if view.status == "caught":
                    pass
                elif view.status == "biting":
                    view.status = "escaped"
                    fish_btn.disabled = True
                    fish_btn.label = "도망갔습니다..."
                    fish_btn.style = discord.ButtonStyle.secondary

                    embed.description = f"물고기가 도망갔습니다... 🐟💨\n(반응 시간: {final_window:.2f}초 초과)"
                    embed.color = discord.Color.dark_grey()
                    await msg.edit(embed=embed, view=view)

                    await db.update_cooldown(user_id, "fish")

                    if not view.auto_mode: return
                    await asyncio.sleep(2)
                    continue
                reaction_time = view.reaction_time

                multiplier, chance_bonus, phase = await self.get_affinity_bonus(user_id)

                rod_mults = [1.5, 2.0, 3.0, 5.0, 8.0, 12.0, 18.0, 25.0, 40.0, 70.0, 120.0]
                current_rod_mult = rod_mults[rod_level] if rod_level < len(rod_mults) else rod_mults[-1]

                available_fish = []
                for name, data in self.collectible_items.items():
                    if data.get("biome") == location or data.get("biome") == "all":
                         available_fish.append(name)

                if not available_fish:
                    available_fish = ["낡은 장화"]

                weights = []
                for f in available_fish:
                    grade = self.collectible_items[f].get("grade", "common")
                    base_w = {"trash": 50, "common": 100, "uncommon": 60, "rare": 30, "epic": 10, "legendary": 3, "mythic": 0.5}.get(grade, 10)

                    if grade in ["rare", "epic", "legendary", "mythic"]:
                        base_w *= (1 + chance_bonus/50.0)

                    weights.append(base_w)

                caught_fish_name = random.choices(available_fish, weights=weights, k=1)[0]
                fish_data = self.collectible_items[caught_fish_name]

                size_min = fish_data.get("size_min", 1.0)
                size_max = fish_data.get("size_max", 10.0)
                caught_size = random.triangular(size_min, size_max, (size_min + size_max)/2)
                caught_size = round(caught_size, 2)

                await db.update_fish_collection(user_id, caught_fish_name, caught_size)

                size_ratio = (caught_size - size_min) / (size_max - size_min) if size_max > size_min else 0
                size_bonus_mult = 1.0 + size_ratio

                base_price = fish_data["price"]
                market_price, trend_arrow = await db.get_current_market_price(caught_fish_name, base_price)

                jelly_reward = int((random.randint(10, 50) + (market_price * 0.05)) * multiplier * current_rod_mult * size_bonus_mult)

                await db.add_item(user_id, caught_fish_name, 1)
                await db.update_balance(user_id, jelly_reward)
                await db.update_cooldown(user_id, "fish")
                await db.update_game_stats(user_id, jelly_reward, True)

                ing_drop = ""
                if random.random() < 0.3:
                    await db.add_item(user_id, "작은 물고기", 1)
                    ing_drop += "\n🐟 **작은 물고기**를 낚았습니다!"

                grade = fish_data.get("grade", "common")

                grade_info = {
                    "trash": {"color": 0x595959, "emoji": "🗑️", "label": "쓰레기"},
                    "common": {"color": 0xB0B0B0, "emoji": "⚪", "label": "일반"},
                    "uncommon": {"color": 0x5D9C59, "emoji": "🟢", "label": "고급"},
                    "rare": {"color": 0x3498DB, "emoji": "🔵", "label": "희귀"},
                    "epic": {"color": 0x9B59B6, "emoji": "🟣", "label": "영웅"},
                    "legendary": {"color": 0xF1C40F, "emoji": "🟡", "label": "전설"},
                    "mythic": {"color": 0xE74C3C, "emoji": "🔴", "label": "신화"}
                }
                g_info = grade_info.get(grade, grade_info["common"])

                embed = discord.Embed(
                    title=f"🎣 {caught_fish_name} 획득!",
                    description=f"*{fish_data['desc']}*",
                    color=g_info["color"]
                )

                embed.add_field(
                    name=f"{g_info['emoji']} 등급",
                    value=f"**{g_info['label'].upper()}**",
                    inline=True
                )
                embed.add_field(
                    name="📏 크기",
                    value=f"**{caught_size}cm**",
                    inline=True
                )

                trend_emoji = {"up": "📈", "down": "📉", "stable": "➖"}.get(trend_arrow.strip(), "")
                embed.add_field(
                    name="💰 가치",
                    value=f"**{market_price:,}** 젤리 {trend_arrow}",
                    inline=True
                )

                embed.add_field(
                    name="🍬 획득 보상",
                    value=f"**+{jelly_reward:,}** 젤리",
                    inline=True
                )

                if size_ratio > 0.9:
                    embed.add_field(name="👑 월척!", value="초대형 크기입니다! (보너스 +100%)", inline=False)
                elif size_ratio < 0.1:
                    embed.add_field(name="👶 쪼꼬미", value="너무 작아요... (귀여움 +100%)", inline=False)

                if ing_drop:
                    embed.add_field(name="🍳 추가 발견", value=ing_drop.strip(), inline=False)

                footer_text = f"반응 속도: {reaction_time:.3f}초 | {biome_data['name']}"
                if view.auto_mode:
                    footer_text += f" | 자동 낚시 {auto_count + 1}/{max_auto}회"

                embed.set_footer(text=footer_text)

                await msg.edit(embed=embed, view=view)
                if view.auto_mode:
                    auto_count += 1
                    if auto_count >= max_auto:
                        await interaction.followup.send("자동 낚시 횟수 제한에 도달했습니다. (최대 10회)", ephemeral=True)
                        break
                    await asyncio.sleep(random.uniform(3.0, 5.0))
                    continue
                break
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"낚시 중 오류가 발생했습니다: {e}", ephemeral=True)




    @activity_group.command(name="낚시도감", description="낚시 도감과 수집 현황을 확인합니다.")
    async def fishing_collection(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        collection = await db.get_fish_collection(user_id)
        collection_map = {item['fish_name']: item for item in collection}

        all_fishes = []
        for name, data in self.collectible_items.items():
            if data.get("type") in ["fish", "deep_sea_fish"]:
                all_fishes.append(name)

        total_count = len(all_fishes)
        collected_count = len(collection_map)
        progress = (collected_count / total_count) * 100 if total_count > 0 else 0

        grade_order = {"common": 1, "uncommon": 2, "rare": 3, "epic": 4, "legendary": 5, "mythic": 6}

        all_fishes.sort(key=lambda x: (
            grade_order.get(self.collectible_items[x].get("grade", "common"), 0),
            self.collectible_items[x].get("price", 0)
        ))

        page_size = 6
        pages = [all_fishes[i:i + page_size] for i in range(0, len(all_fishes), page_size)]
        if not pages: pages = [[]]

        class CollectionView(discord.ui.View):
            def __init__(self, pages, collection_map, items_data, progress, total_cnt, user_id):
                super().__init__(timeout=60)
                self.pages = pages
                self.collection_map = collection_map
                self.items_data = items_data
                self.progress = progress
                self.total_cnt = total_cnt
                self.user_id = user_id
                self.current_page = 0

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                return str(interaction.user.id) == self.user_id

            def create_embed(self):
                embed = discord.Embed(title="🐟 낚시 도감", description=f"**수집률: {self.progress:.1f}%** ({len(self.collection_map)}/{self.total_cnt})", color=discord.Color.blue())

                current_items = self.pages[self.current_page]

                for fish_name in current_items:
                    data = self.items_data[fish_name]
                    grade = data.get("grade", "common").upper()

                    if fish_name in self.collection_map:
                        info = self.collection_map[fish_name]
                        max_len = info['max_length']
                        count = info['count']

                        medal = ""
                        if max_len >= data.get("size_max", 100) * 0.9: medal = "👑"

                        embed.add_field(
                            name=f"{medal} {fish_name} [{grade}]",
                            value=f"최대 크기: **{max_len}cm**\n잡은 횟수: {count}회",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name=f"❓ ??? [{grade}]",
                            value="아직 잡지 못했습니다.",
                            inline=True
                        )

                embed.set_footer(text=f"페이지 {self.current_page+1}/{len(self.pages)}")
                return embed

            @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
            async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page > 0:
                    self.current_page -= 1
                    await interaction.response.edit_message(embed=self.create_embed())
                else:
                    await interaction.response.defer()

            @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page < len(self.pages) - 1:
                    self.current_page += 1
                    await interaction.response.edit_message(embed=self.create_embed())
                else:
                    await interaction.response.defer()

        view = CollectionView(pages, collection_map, self.collectible_items, progress, total_count, user_id)
        await interaction.response.send_message(embed=view.create_embed(), view=view)

    @activity_group.command(name="채광", description="광산에서 광물을 캐서 아이템과 젤리를 획득합니다.")
    async def mine(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        benefits = booster_utils.get_booster_benefits(interaction.user)
        cooldown_time = 60 * benefits["cooldown_mult"]

        cooldown = await db.check_cooldown(user_id, "mine", cooldown_time)
        if cooldown > 0:
            return await interaction.response.send_message(f"영차 영차... 광질은 너무 힘들어요... {int(cooldown)}초만 쉬게 해주세요... ( 💧-_-)", ephemeral=True)

        await interaction.response.defer()

        pick_level = await db.get_upgrade(user_id, "pickaxe")
        max_pick_level = len(self.upgrades["pickaxe"]) - 1
        pick_level = min(pick_level, max_pick_level)
        pick_info = self.upgrades["pickaxe"][pick_level]

        pick_mults = [1.0, 1.2, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 35.0, 60.0]
        current_pick_mult = pick_mults[pick_level] if pick_level < len(pick_mults) else pick_mults[-1]

        multiplier, chance_bonus, phase = await self.get_affinity_bonus(user_id)

        ores = ["석탄", "구리", "철광석", "은광석", "금광석", "에메랄드", "루비", "다이아몬드", "요미나이트", "스타 다이아몬드", "블랙홀 조각"]


        weights = [1000, 600, 300, 100, 20, 5, 1, 0, 0, 0, 0]

        if pick_level >= 1: weights = [800, 600, 400, 150, 40, 10, 2, 0.5, 0, 0, 0]
        if pick_level >= 2: weights = [600, 500, 500, 200, 60, 20, 5, 1, 0, 0, 0]
        if pick_level >= 3: weights = [400, 400, 500, 300, 100, 40, 10, 2, 0.1, 0, 0]
        if pick_level >= 4: weights = [200, 300, 400, 400, 200, 80, 20, 5, 1, 0, 0]
        if pick_level >= 5: weights = [100, 200, 300, 400, 300, 150, 40, 10, 2, 0.1, 0]
        if pick_level >= 6: weights = [50, 100, 200, 300, 400, 250, 80, 20, 5, 1, 0]
        if pick_level >= 7: weights = [50, 80, 150, 250, 300, 200, 100, 50, 10, 2, 0.1]
        if pick_level >= 8: weights = [30, 50, 100, 200, 300, 250, 150, 80, 20, 5, 1]
        if pick_level >= 9: weights = [20, 40, 80, 150, 250, 300, 200, 100, 30, 8, 2]
        if pick_level >= 10: weights = [10, 20, 40, 80, 150, 250, 200, 100, 40, 10, 3]

        if chance_bonus > 0:
            boost = chance_bonus * 2
            weights[0] = max(0, weights[0] - boost)
            weights[-1] += boost * 0.05
            weights[-2] += boost * 0.1
            weights[-3] += boost * 0.2

        mined_item_name = random.choices(ores, weights=weights, k=1)[0]

        item_info = self.collectible_items.get(mined_item_name, {"price": 0, "desc": "알 수 없는 광물"})
        base_price = item_info["price"]

        market_price, trend_arrow = await db.get_current_market_price(mined_item_name, base_price)

        base_reward = random.randint(100, 500)
        jelly_reward = int(base_reward * multiplier * current_pick_mult)

        await db.add_item(user_id, mined_item_name, 1)
        await db.update_balance(user_id, jelly_reward)
        await db.update_cooldown(user_id, "mine")
        await db.update_game_stats(user_id, jelly_reward, True)

        ing_drop = ""
        if random.random() < 0.5:
            await db.add_item(user_id, "소금", 1)
            ing_drop += "\n🧂 **소금**을 캤습니다!"
        if random.random() < 0.5:
            await db.add_item(user_id, "빛나는 조각", 1)
            ing_drop += "\n✨ **빛나는 조각**을 발견했습니다!"
        if random.random() < 0.5:
            await db.add_item(user_id, "별가루", 1)
            ing_drop += "\n🌠 **별가루**를 얻었습니다!"

        color = discord.Color.green()
        special_msg = ""
        if base_price >= 50000:
            special_msg = "✨ **대박! 희귀한 광물을 발견했어요!**"
            color = discord.Color.gold()
        if mined_item_name in ["스타 다이아몬드", "블랙홀 조각"]:
             special_msg = "🌌 **우주의 기운이 담긴 광석입니다!**"
             color = discord.Color.dark_teal()

        embed = discord.Embed(title="⛏️ 광산", description="**채광에 성공했어요!**", color=color)
        embed.add_field(name="획득 광물", value=f"💎 **{mined_item_name}**", inline=False)
        embed.add_field(name="시장 가치", value=f"**{market_price:,}** 젤리 {trend_arrow}", inline=True)
        embed.add_field(name="채광 보상", value=f"**{jelly_reward:,}** 젤리", inline=True)

        if special_msg:
            embed.add_field(name="✨ 보너스", value=special_msg, inline=False)

        if ing_drop:
            embed.add_field(name="🍳 추가 재료", value=ing_drop.strip(), inline=False)

        embed.set_footer(text=f"장비: {pick_info['name']} (Lv.{pick_level}) | 시세는 실시간으로 변동됩니다.")
        await interaction.followup.send(embed=embed)

    async def use_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:

        user_id = str(interaction.user.id)
        inv = await db.get_inventory(user_id)
        category = interaction.namespace.category

        filtered_inv = []

        for item in inv:
            name = item['item_name']

            item_cat = "material"
            if name in self.pet_shop_items:
                p_type = self.pet_shop_items[name].get("type")
                if p_type == "pet_egg":
                    item_cat = "box"
                else:
                    item_cat = "consumable"
            elif name in self.battle_items:
                b_type = self.battle_items[name].get("type")
                if b_type == "buff":
                    item_cat = "buff"
                else:
                    item_cat = "consumable"
            elif name in self.shop_items:
                item_cat = "consumable"
            elif name in moon.RECIPES:
                item_cat = "consumable"

            if category == "consumable" and item_cat == "consumable": filtered_inv.append(item)
            elif category == "box" and item_cat == "box": filtered_inv.append(item)
            elif category == "buff" and item_cat == "buff": filtered_inv.append(item)
            elif category == "material" and item_cat == "material": filtered_inv.append(item)
            elif not category: filtered_inv.append(item)

        return [
            app_commands.Choice(name=f"{i['item_name']} ({i['amount']}개)", value=i['item_name'])
            for i in filtered_inv if current.lower() in i['item_name'].lower()
        ][:25]

    @store_group.command(name="사용", description="아이템을 사용하여 효과를 얻습니다.")
    @app_commands.describe(category="아이템 카테고리", item_name="사용할 아이템 이름")
    @app_commands.rename(category="카테고리", item_name="아이템")
    @app_commands.choices(category=[
        app_commands.Choice(name="🍬 소비용품 (음식/물약)", value="consumable"),
        app_commands.Choice(name="🥚 알/상자", value="box"),
        app_commands.Choice(name="⚡ 버프/특수", value="buff"),
        app_commands.Choice(name="🪵 재료/기타", value="material")
    ])
    @app_commands.autocomplete(item_name=use_autocomplete)
    async def use_item(self, interaction: discord.Interaction, category: str, item_name: str):

        user_id = str(interaction.user.id)

        inv = await db.get_inventory(user_id)
        inv_dict = {i['item_name']: i['amount'] for i in inv}

        target_item = item_name
        if item_name not in inv_dict:
            for inv_name in inv_dict.keys():
                if item_name.replace(" ", "") == inv_name.replace(" ", ""):
                    target_item = inv_name
                    break

        if target_item not in inv_dict or inv_dict[target_item] <= 0:
            return await interaction.response.send_message(f"가방에 '{item_name}' 아이템이 없습니다. (카테고리를 확인해주세요!)", ephemeral=True)

        item_name = target_item
        if item_name in self.pet_shop_items:
            p_type = self.pet_shop_items[item_name].get("type")
            if p_type == "pet_egg":
                if hasattr(self, 'hatch') and hasattr(self.hatch, 'callback'):
                     await self.hatch.callback(self, interaction, item_name)
                else:
                     await interaction.response.send_message("이 아이템은 '/부화' 명령어로 사용해주세요!", ephemeral=True)
                return
            elif p_type in ["pet_food", "pet_toy"]:
                 await interaction.response.send_message(f"🐾 **{item_name}**은(는) '/펫' 명령어 메뉴에서 펫에게 사용할 수 있어요!", ephemeral=True)
                 return


        effect_handled = False
        msg = ""

        if item_name in moon.RECIPES:
            recipe = moon.RECIPES[item_name]
            effect = recipe.get('effect')

            await db.remove_item(user_id, item_name, 1)

            affinity_val = recipe.get('value', 0)
            if affinity_val > 0:
                await db.update_affinity(user_id, affinity_val)
                msg_parts = [f"😋 **{item_name}**을(를) 먹었습니다! (호감도 +{affinity_val})"]
            else:
                msg_parts = [f"🥣 **{item_name}**을(를) 사용했습니다!"]

            effect_handled = True

            if effect == "scavenge_reset":
                await db.reset_cooldown(user_id, "scavenge")
                msg_parts.append("**탐색 쿨다운이 초기화**되었습니다!")

            elif effect == "hunt_reset":
                await db.reset_cooldown(user_id, "hunt")
                msg_parts.append("**사냥 쿨다운이 초기화**되었습니다!")

            elif effect == "cooldown_reset":
                await db.reset_cooldown(user_id, "mine")
                await db.reset_cooldown(user_id, "fish")
                await db.reset_cooldown(user_id, "chop")
                await db.reset_cooldown(user_id, "scavenge")
                msg_parts.append("**모든 활동(광질/낚시/벌목/탐색) 쿨다운이 초기화**되었습니다!")

            elif effect == "mining_reset":
                await db.reset_cooldown(user_id, "mine")
                msg_parts.append("**광질 쿨다운이 초기화**되었습니다!")

            elif effect == "fishing_reset":
                await db.reset_cooldown(user_id, "fish")
                msg_parts.append("**낚시 쿨다운이 초기화**되었습니다!")

            elif effect == "money_bag":
                money_amount = recipe.get('money', 0)
                if money_amount > 0:
                    await db.update_balance(user_id, money_amount)
                    msg_parts.append(f"**{money_amount:,}** 젤리를 획득했습니다!")

            elif effect == "god_bless":
                await db.reset_cooldown(user_id, "mine")
                await db.reset_cooldown(user_id, "fish")
                await db.reset_cooldown(user_id, "chop")
                await db.reset_cooldown(user_id, "scavenge")
                await db.reset_cooldown(user_id, "hunt")
                await db.reset_cooldown(user_id, "crime")
                await db.reset_cooldown(user_id, "daily")

                money_amount = recipe.get('money', 0)
                if money_amount > 0:
                    await db.update_balance(user_id, money_amount)

                msg_parts.append(f"**모든 쿨다운 완전 초기화** 및 **{money_amount:,}** 젤리 획득! ✨")

            elif effect == "expedition_buff":
                msg_parts.append("원정대 공격 시 자동으로 사용됩니다! (원정대 메뉴에서 공격해보세요)")

            elif effect == "fishing_buff":
                msg_parts.append("낚시할 때 자동으로 사용됩니다! (낚시를 해보세요)")

            elif effect == "random_effect":
                possible_effects = [
                    ("scavenge_reset", "탐색 쿨다운이 초기화되었습니다!"),
                    ("hunt_reset", "사냥 쿨다운이 초기화되었습니다!"),
                    ("mining_reset", "광질 쿨다운이 초기화되었습니다!"),
                    ("fishing_reset", "낚시 쿨다운이 초기화되었습니다!"),
                    ("money_small", "용돈을 주웠습니다! (+5,000 젤리)"),
                    ("nothing", "아무 일도 일어나지 않았습니다... (맛은 있네요!)")
                ]
                chosen_eff, eff_msg = random.choice(possible_effects)

                if chosen_eff == "scavenge_reset": await db.reset_cooldown(user_id, "scavenge")
                elif chosen_eff == "hunt_reset": await db.reset_cooldown(user_id, "hunt")
                elif chosen_eff == "mining_reset": await db.reset_cooldown(user_id, "mine")
                elif chosen_eff == "fishing_reset": await db.reset_cooldown(user_id, "fish")
                elif chosen_eff == "money_small": await db.update_balance(user_id, 5000)

                msg_parts.append(f"🎲 **랜덤 효과 발동!** {eff_msg}")

            elif effect == "furniture":
                if affinity_val > 0:
                    await db.update_affinity(user_id, -affinity_val)
                await db.add_item(user_id, item_name, 1)
                msg_parts = [f"🪑 **{item_name}**는 사용하는 것이 아니라 배치하는 아이템이에요!\n`/정원_관리` 명령어를 사용해주세요."]

            msg = "\n".join(msg_parts)

        elif item_name in self.shop_items:
            item_info = self.shop_items[item_name]

            if item_name == "막대사탕":
                await db.reset_cooldown(user_id, "scavenge")
                msg = f"🍭 **막대사탕**을 먹고 당이 충전되었어요! **탐색 쿨다운이 초기화**되었습니다!"
                effect_handled = True
            elif item_name == "초콜릿":
                await db.reset_cooldown(user_id, "hunt")
                msg = f"🍫 **초콜릿**을 먹고 에너지가 솟아납니다! **사냥 쿨다운이 초기화**되었습니다!"
                effect_handled = True
            elif item_name == "아이스크림":
                await db.reset_cooldown(user_id, "fish")
                msg = f"🍦 **아이스크림**을 먹고 머리가 띵~ 해졌어요! **낚시 쿨다운이 초기화**되었습니다!"
                effect_handled = True
            elif item_name == "케이크":
                await db.reset_cooldown(user_id, "chop")
                await db.reset_cooldown(user_id, "mine")
                msg = f"🍰 **케이크**를 든든하게 먹었습니다! **벌목 & 광질 쿨다운이 초기화**되었습니다!"
                effect_handled = True
            elif item_name == "달빛파편":
                await db.reset_cooldown(user_id, "crime")
                msg = f"🌙 **달빛파편**이 당신의 죄를 씻어줍니다... **범죄 쿨다운이 초기화**되었습니다! (조심하세요!)"
                effect_handled = True
            elif item_name == "별빛정수":
                await db.reset_cooldown(user_id, "daily")
                msg = f"✨ **별빛정수**의 힘으로 시간을 되돌립니다! **출석체크를 다시 할 수 있습니다!**"
                effect_handled = True
            elif item_name == "차원이동장치":
                all_possible_items = list(self.shop_items.keys()) + list(self.collectible_items.keys())
                if "차원이동장치" in all_possible_items: all_possible_items.remove("차원이동장치")

                random_item = random.choice(all_possible_items)
                random_amount = random.randint(1, 5)

                await db.add_item(user_id, random_item, random_amount)
                msg = f"🌀 **차원이동장치**를 가동했습니다! 차원 너머에서 **{random_item}** {random_amount}개가 떨어졌습니다!"
                effect_handled = True

            if "affinity" in item_info:
                amount_affinity = item_info["affinity"]

                if effect_handled:
                    await db.remove_item(user_id, item_name, 1)
                    await db.update_affinity(user_id, amount_affinity)
                    msg += f"\n(호감도 +{amount_affinity:,})"
                else:
                    await db.remove_item(user_id, item_name, 1)
                    await db.update_affinity(user_id, amount_affinity)
                    msg = f"🎁 **{item_name}**을(를) 선물했습니다! 요미의 기분이 좋아 보여요! (호감도 +{amount_affinity:,})"
                    effect_handled = True

            elif item_info.get("desc", "").find("재료") != -1 and not effect_handled:
                msg = f"🍳 **{item_name}**은(는) 요리 재료입니다! '/요리' 명령어를 사용해보세요."
                effect_handled = True

        elif item_name in self.battle_items:
            item_info = self.battle_items[item_name]
            msg = f"⚔️ **{item_name}**은(는) 던전 탐험 중에 자동으로 사용되거나, 던전 메뉴에서 사용할 수 있어요! ('/던전' 명령어)"
            effect_handled = True

        elif item_name in self.armor_items:
            msg = f"🛡️ **{item_name}**은(는) 장비 아이템입니다! '/장착 {item_name}' 명령어로 착용해보세요."
            effect_handled = True

        elif item_name in self.collectible_items:
            msg = f"💎 **{item_name}**은(는) 소중한 수집품이에요! 판매하거나 제작 재료로 사용해보세요."
            effect_handled = True

        if not effect_handled:
            return await interaction.response.send_message(f"음... '{item_name}'은(는) 어떻게 쓰는지 모르겠어요. 혹시 다른 용도가 아닐까요? 🤔", ephemeral=True)

        await interaction.response.send_message(msg)

    @pet_group.command(name="부화", description="펫 알을 부화시킵니다.")
    @app_commands.describe(item_name="부화할 펫 알 이름")
    @app_commands.rename(item_name="알")
    @app_commands.autocomplete(item_name=inventory_autocomplete)
    async def hatch(self, interaction: discord.Interaction, item_name: str):

        user_id = str(interaction.user.id)

        egg_info = self.pet_shop_items.get(item_name)
        if not egg_info or egg_info.get("type") != "pet_egg":
            return await interaction.response.send_message("이 아이템은 펫 알이 아니에요! (｡•́︿•̀｡)", ephemeral=True)

        inv = await db.get_inventory(user_id)
        inv_dict = {i['item_name']: i['amount'] for i in inv}

        if item_name not in inv_dict or inv_dict[item_name] <= 0:
            return await interaction.response.send_message(f"가방에 '{item_name}'이(가) 없어요.", ephemeral=True)

        await db.remove_item(user_id, item_name, 1)

        await interaction.response.send_message(f"🥚 **{item_name}**을(를) 품기 시작했어요... (따뜻해...)", ephemeral=False)
        msg = await interaction.original_response()

        await asyncio.sleep(1)
        await msg.edit(content=f"🥚 **{item_name}**이(가) 흔들리고 있어요! (꼼틀꼼틀)")
        await asyncio.sleep(1)
        await msg.edit(content=f"🥚 **{item_name}**에 금이 가기 시작했어요! (파사삭!)")
        await asyncio.sleep(1)

        grade = egg_info.get("grade")
        possible_pets = [name for name, data in moon.PET_DATA.items() if data.get("grade") == grade]

        if not possible_pets:
            await msg.edit(content=f"어라...? 알이 비어있었나 봐요... (오류: {grade} 등급 펫 없음)")
            await db.add_item(user_id, item_name, 1)
            return

        pet_name = random.choice(possible_pets)
        pet_data = moon.PET_DATA[pet_name]

        user_pets = await db.get_user_pets(user_id)
        existing_pet = next((p for p in user_pets if p['pet_type'] == pet_name), None)

        if existing_pet:
            xp_bonus = 100
            await db.update_pet_xp(user_id, pet_name, xp_bonus)
            await msg.edit(content=f"🎉 **{pet_name}** {pet_data['emoji']}이(가) 태어났어요!\n이미 함께하고 있는 친구네요! 경험치를 얻었습니다. (+{xp_bonus} XP)")
        else:
            await db.update_pet_xp(user_id, pet_name, 0)
            await msg.edit(content=f"🎉 **{pet_name}** {pet_data['emoji']}이(가) 태어났어요!\n새로운 친구가 생겼어요!\n\n> {pet_data['desc']}")

    @store_group.command(name="순위", description="젤리 및 호감도 순위를 확인합니다.")
    async def ranking(self, interaction: discord.Interaction):


        data_eco = await db.get_top_economy(100)
        data_aff = await db.get_top_affinity(100)

        class RankingView(discord.ui.View):
            def __init__(self, bot, economy_cog, data_eco, data_aff):
                super().__init__(timeout=60)
                self.bot = bot
                self.economy_cog = economy_cog
                self.page = 0
                self.mode = "economy"
                self.data_eco = data_eco
                self.data_aff = data_aff

            def create_embed(self):
                data = self.data_eco if self.mode == "economy" else self.data_aff
                title = "💰 자산 순위" if self.mode == "economy" else "💕 호감도 순위"
                color = discord.Color.gold() if self.mode == "economy" else discord.Color.from_rgb(255, 182, 193)

                items_per_page = 10
                max_pages = (len(data) - 1) // items_per_page + 1
                start = self.page * items_per_page
                end = start + items_per_page
                current_data = data[start:end]

                lines = []
                for i, (uid, val) in enumerate(current_data, start + 1):
                    user = self.bot.get_user(int(uid))
                    name = user.display_name if user else f"떠나간 교주님... ({uid})"
                    unit = self.economy_cog.currency_name if self.mode == "economy" else "💕"
                    lines.append(f"**{i}위.** {name}: `{val:,}` {unit}")

                if not lines: lines = ["아직 데이터가 없어요... 얼른 활동을 시작해보세요!"]

                embed = discord.Embed(title=f"🏆 요미네 명예의 전당 ({title}) 🏆", description="\n".join(lines), color=color)
                embed.set_footer(text=f"페이지 {self.page + 1} / {max_pages}")
                return embed

            @discord.ui.button(label="자산 순위", style=discord.ButtonStyle.primary)
            async def show_eco(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                self.mode = "economy"
                self.page = 0
                await btn_interaction.response.edit_message(embed=self.create_embed(), view=self)

            @discord.ui.button(label="호감도 순위", style=discord.ButtonStyle.success)
            async def show_aff(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                self.mode = "affinity"
                self.page = 0
                await btn_interaction.response.edit_message(embed=self.create_embed(), view=self)

            @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
            async def prev_page(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if self.page > 0:
                    self.page -= 1
                    await btn_interaction.response.edit_message(embed=self.create_embed(), view=self)
                else:
                    await btn_interaction.response.send_message("첫 페이지입니다!", ephemeral=True)

            @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
            async def next_page(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                data = self.data_eco if self.mode == "economy" else self.data_aff
                if (self.page + 1) * 10 < len(data):
                    self.page += 1
                    await btn_interaction.response.edit_message(embed=self.create_embed(), view=self)
                else:
                    await btn_interaction.response.send_message("마지막 페이지입니다!", ephemeral=True)

        view = RankingView(self.bot, self, data_eco, data_aff)
        await interaction.response.send_message(embed=view.create_embed(), view=view)

    @store_group.command(name="도감", description="수집한 아이템 도감을 확인합니다.")
    async def store_collection(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)
        inv = await db.get_inventory(user_id)
        user_inv = {i['item_name']: i['amount'] for i in inv}
        all_items = list(self.shop_items.keys())

        class CollectionView(discord.ui.View):
            def __init__(self, shop_items, user_inv):
                super().__init__(timeout=60)
                self.shop_items = shop_items
                self.user_inv = user_inv
                self.items_list = list(shop_items.keys())
                self.page = 0
                self.items_per_page = 6

            def create_embed(self):
                max_pages = (len(self.items_list) - 1) // self.items_per_page + 1
                start = self.page * self.items_per_page
                end = start + self.items_per_page
                current_items = self.items_list[start:end]

                embed = discord.Embed(title="📚 요미네 이념 백과사전", color=discord.Color.blue())
                collected = len([name for name in self.items_list if name in self.user_inv])
                total = len(self.items_list)
                embed.description = f"현재 수집 정도: **{collected}/{total}** ({ (collected/total*100):.1f}%)\n"

                for name in current_items:
                    info = self.shop_items[name]
                    status = f"✅ 보유 중 ({self.user_inv[name]}개)" if name in self.user_inv else "❌ 미보유"
                    embed.add_field(
                        name=f"{'✨ ' if name in self.user_inv else '🔒 '}{name}",
                        value=f"{status}\n*{info['desc']}*",
                        inline=True
                    )

                embed.set_footer(text=f"페이지 {self.page + 1} / {max_pages} | 모든 보물을 모아보세요!")
                return embed

            @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
            async def prev(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if self.page > 0:
                    self.page -= 1
                    await btn_interaction.response.edit_message(embed=self.create_embed(), view=self)
                else:
                    await btn_interaction.response.send_message("첫 페이지입니다!", ephemeral=True)

            @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
            async def next(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if (self.page + 1) * self.items_per_page < len(self.items_list):
                    self.page += 1
                    await btn_interaction.response.edit_message(embed=self.create_embed(), view=self)
                else:
                    await btn_interaction.response.send_message("마지막 페이지입니다!", ephemeral=True)

        view = CollectionView(self.shop_items, user_inv)
        await interaction.response.send_message(embed=view.create_embed(), view=view)

    @app_commands.command(name="내정보", description="나의 경제 상태와 요미와의 관계를 확인합니다.")
    async def myinfo_root(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            user_id = str(interaction.user.id)
            balance = await db.get_balance(user_id)
            affinity = await db.get_affinity(user_id)

            if affinity < 50: rank_text = "낯선 사람"
            elif affinity < 500: rank_text = "인사하는 사이"
            elif affinity < 3000: rank_text = "친구"
            elif affinity < 10000: rank_text = "베스트 프렌드"
            elif affinity < 50000: rank_text = "썸 타는 사이"
            elif affinity < 100000: rank_text = "연인"
            elif affinity < 1000000: rank_text = "운명의 단짝"
            else: rank_text = "영혼의 동반자"

            level = int((affinity / 100) ** 0.5) + 1
            xp = affinity % 100
            xp_max = 100 + (level * 10)

            embed = discord.Embed(
                title=f"📝 {interaction.user.display_name}님의 정보",
                description="요미와 함께한 소중한 기록들이에요! (✿◡‿◡)",
                color=discord.Color.from_rgb(255, 182, 193)            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

            pct = min(1.0, xp / xp_max)
            filled = int(15 * pct)
            bar = "🟩" * filled + "⬜" * (15 - filled)

            embed.add_field(name="💰 보유 자산", value=f"**{balance:,}** {self.currency_name}", inline=True)
            embed.add_field(name="🏆 요미와의 관계", value=f"**{rank_text}** (Lv.{level})", inline=True)
            embed.add_field(name=f"✨ 호감도 경험치 ({xp}/{xp_max})", value=f"`{bar}`", inline=False)


            embed.set_footer(text="Yomi Bot Economy System", icon_url=self.bot.user.display_avatar.url)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Profile Error: {e}")
            await interaction.followup.send("정보를 불러오는 중 오류가 발생했어요... (´;ω;｀)")

    @store_group.command(name="젤리선물", description="다른 유저에게 젤리를 보냅니다.")
    @app_commands.describe(receiver="젤리를 받을 유저를 선택해주세요.", amount="보낼 금액을 입력해주세요.")
    @app_commands.rename(receiver="유저", amount="금액")
    async def transfer(self, interaction: discord.Interaction, receiver: discord.User, amount: int):

        sender_id = str(interaction.user.id)
        receiver_id = str(receiver.id)

        if sender_id == receiver_id:
            await interaction.response.send_message("본인에게는 보낼 수 없어요! ( >﹏< )", ephemeral=True)
            return

        if receiver.bot:
            await interaction.response.send_message("봇에게는 젤리를 줄 수 없어요... (´。＿。｀)", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("1 젤리 이상만 보낼 수 있어요! (😠)", ephemeral=True)
            return

        if not await db.try_deduct_balance(sender_id, amount):
            bal = await db.get_balance(sender_id)
            await interaction.response.send_message(f"돈이 부족해요... 현재 **{bal:,}** 젤리밖에 없어요! (T_T)", ephemeral=True)
            return

        await db.update_balance(receiver_id, amount)

        embed = discord.Embed(
            title="🎁 젤리 선물 도착!",
            description=f"**{interaction.user.display_name}**님이 **{receiver.display_name}**님께 선물을 보냈어요!",
            color=discord.Color.brand_green()
        )
        embed.add_field(name="보낸 금액", value=f"**{amount:,}** {self.currency_name} {self.currency_icon}")
        embed.set_footer(text="두 분의 우정을 응원합니다! (✿◡‿◡)")

        await interaction.response.send_message(f"{receiver.mention}님, 선물이 도착했어요!", embed=embed)

    @activity_group.command(name="출석", description="매일 젤리를 받을 수 있는 출석체크! 호감도가 높으면 더 많이 받아요!")
    async def daily(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        if True:
            success, streak = await db.try_claim_daily(user_id)

            if success:
                base_reward = random.randint(300, 1000) * 10
                streak_bonus_mult = min(1.0, (streak // 7) * 0.1)
                streak_bonus = int(base_reward * streak_bonus_mult)

                affinity = await db.get_affinity(user_id)
                aff_bonus_mult = 1.0
                if affinity >= 3500:
                    aff_bonus_mult = 2.0
                elif affinity >= 1200:
                    aff_bonus_mult = 1.7
                elif affinity >= 700:
                    aff_bonus_mult = 1.5
                elif affinity >= 350:
                    aff_bonus_mult = 1.3
                elif affinity >= 150:
                    aff_bonus_mult = 1.2
                elif affinity >= 50:
                    aff_bonus_mult = 1.1
                final_reward = int((base_reward + streak_bonus) * aff_bonus_mult)

                msg_parts = []
                msg_parts.append(f"✅ **{streak}일 연속** 출석 체크 완료!")
                msg_parts.append(f"💰 기본 보상: {base_reward:,} 젤리")

                if streak_bonus > 0:
                    msg_parts.append(f"🔥 스트릭 보너스: +{streak_bonus:,} 젤리 (+{int(streak_bonus_mult*100)}%)")

                if aff_bonus_mult > 1.0:
                    msg_parts.append(f"💕 친밀도 보너스: x{aff_bonus_mult}배")

                if random.random() < 0.05:
                    final_reward = int(final_reward * 1.5)
                    msg_parts.append(f"✨ **대박!** 운이 엄청 좋네요! (1.5배!)")

                msg_parts.append(f"\n🎉 **총 획득:** **{final_reward:,}** {self.currency_name}")

                await db.update_balance(user_id, final_reward)
                await db.update_affinity(user_id, 2)

                await interaction.response.send_message("\n".join(msg_parts))
            else:
                await interaction.response.send_message(f"이미 오늘 출석을 하셨잖아요! 내일 또 와주세요! (현재 **{streak}일** 연속) ( •̀ ω •́ )✧")

    @activity_group.command(name="사냥", description="숲에서 몬스터를 사냥하고 젤리를 법니다. (3분 쿨타임)")
    async def hunt(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        benefits = booster_utils.get_booster_benefits(interaction.user)
        cooldown_time = 180 * benefits["cooldown_mult"]

        cooldown = await db.check_cooldown(user_id, "hunt", cooldown_time)
        if cooldown > 0:
            return await interaction.response.send_message(f"체력이 부족해요! **{int(cooldown // 60)}분 {int(cooldown % 60)}초** 뒤에 다시 사냥하러 가요! 🍖", ephemeral=True)

        await db.update_cooldown(user_id, "hunt")

        multiplier, chance_bonus, moon_phase = await self.get_affinity_bonus(user_id)

        monsters = [
            ("🟢 슬라임", 500, 2000, "탱글탱글한 슬라임을 잡았어요!"),
            ("🐺 굶주린 늑대", 2000, 5000, "무서운 늑대였지만 요미의 응원으로 이겼어요!"),
            ("🐗 멧돼지", 4000, 10000, "돌진하는 멧돼지를 잘 피해서 사냥 성공!"),
            ("🧙 고블린 약탈꾼", 5000, 15000, "고블린이 훔친 보따리를 되찾았습니다!"),
            ("🐲 **작은 드래곤**", 30000, 80000, "우와! 전설 속의 드래곤을 사냥했어요!!"),
            ("💨 아무것도 없음", 0, 0, "몬스터를 찾지 못하고 숲을 헤매기만 했어요...")
        ]

        weights = [40, 25, 15, 10, 2, 8]
        if chance_bonus > 0:
            weights[0] -= min(10, chance_bonus / 4)
            weights[5] -= min(5, chance_bonus / 5)
            weights[4] += chance_bonus / 3
            weights[3] += chance_bonus / 4

        monster = random.choices(monsters, weights=weights, k=1)[0]
        name, min_p, max_p, desc = monster

        if min_p == 0:
            await interaction.response.send_message(f"🏹 숲을 샅샅이 뒤졌지만... **{name}**. (´;ω;｀)\n{desc}")
            return

        reward = int(random.randint(min_p, max_p) * multiplier)
        await db.update_balance(user_id, reward)
        await db.update_game_stats(user_id, reward, True)

        ing_drop = ""
        if random.random() < 0.5:
            await db.add_item(user_id, "고기", 1)
            ing_drop += "\n🍖 **고기**를 얻었습니다!"
        if random.random() < 0.3:
            await db.add_item(user_id, "가죽", 1)
            ing_drop += "\n🧵 **가죽**을 획득했습니다! (대장간 재료)"
        if random.random() < 0.2:
            await db.add_item(user_id, "거미줄", 1)
            ing_drop += "\n🕸️ **거미줄**을 획득했습니다! (낚시대 재료)"
        if random.random() < 0.5:
            await db.add_item(user_id, "계란", 1)
            ing_drop += "\n🥚 **계란**을 발견했습니다!"
        if random.random() < 0.5:
            await db.add_item(user_id, "우유", 1)
            ing_drop += "\n🥛 **우유**를 얻었습니다!"
        if random.random() < 0.5:
            await db.add_item(user_id, "허브", 1)
            ing_drop += "\n🌿 **허브**를 채집했습니다!"
        if random.random() < 0.5:
            await db.add_item(user_id, "솜뭉치", 1)
            ing_drop += "\n☁️ **솜뭉치**를 얻었습니다!"

        embed = discord.Embed(
            title=f"⚔️ 사냥 성공: {name}",
            description=f"{desc}\n\n전리품: **{reward:,}** {self.currency_name} {self.currency_icon}",
            color=discord.Color.red()
        )
        if ing_drop:
            embed.add_field(name="🍳 추가 재료", value=ing_drop.strip(), inline=False)

        moon_desc = moon.MOON_PHASES[moon_phase]['desc']
        embed.set_footer(text=f"🌙 현재 달: {moon_phase} | {moon_desc}\n요미가 멀리서 박수치고 있어요! 🎉")

        await interaction.response.send_message(embed=embed)

    @hunt.error
    async def hunt_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"체력이 부족해요! **{int(error.retry_after // 60)}분 {int(error.retry_after % 60)}초** 뒤에 다시 사냥하러 가요! 🍖", ephemeral=True)


    @game_group.command(name="로또", description="500원으로 인생 역전! 즉석 복권을 긁습니다.")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.guild_id, i.user.id))
    async def lotto(self, interaction: discord.Interaction):

        price = 500
        user_id = str(interaction.user.id)

        if not await db.try_deduct_balance(user_id, price):
            await interaction.response.send_message(f"복권 한 장에 **{price}** {self.currency_name}인데... 돈이 부족해요! ( >﹏< )", ephemeral=True)
            return

        symbols = ["🍎", "🍊", "🍇", "🍒", "💎", "⭐", "7️⃣"]
        weights = [30, 25, 20, 15, 5, 4, 1]
        slots = random.choices(symbols, weights=weights, k=3)

        winnings = 0

        if slots[0] == slots[1] == slots[2]:
            s = slots[0]
            if s == "7️⃣": winnings = 5000000
            elif s == "⭐": winnings = 2500000
            elif s == "💎": winnings = 1000000
            elif s == "🍒": winnings = 500000
            elif s == "🍇": winnings = 200000
            elif s == "🍊": winnings = 100000
            elif s == "🍎": winnings = 50000

        elif slots[0] == slots[1] or slots[1] == slots[2] or slots[0] == slots[2]:
            if slots[0] == slots[1]: pair = slots[0]
            elif slots[1] == slots[2]: pair = slots[1]
            else: pair = slots[0]

            winnings = 10000
            if pair == "7️⃣":
                winnings = 50000
            if pair == "💎":
                winnings = 30000

        result_desc = ""
        if winnings > 0:
            await db.update_balance(user_id, winnings)
            result_desc = f"**당첨!** **{winnings:,}** {self.currency_name} 획득! 축하해요!"
            if winnings >= 10000:
                result_desc += "\n👑 오늘부로 부자가 되셨군요!"
        else:
            result_desc = "💸 **꽝...** 아쉽지만 다음 기회에..."

        await db.update_game_stats(user_id, winnings - price, winnings > 0)

        bal = await db.get_balance(user_id)
        embed = discord.Embed(title="🎰 요미네 즉석 복권", description=f"# {' '.join(slots)}\n\n{result_desc}", color=discord.Color.gold() if winnings > 0 else discord.Color.dark_gray())
        embed.set_footer(text=f"구매 비용: {price} {self.currency_name} | 남은 돈: {bal:,} {self.currency_name}")

        await interaction.response.send_message(embed=embed)

    @activity_group.command(name="구걸", description="돈을 구걸합니다... 성공 확률은?! (3분 쿨타임)")
    @app_commands.checks.cooldown(1, 180, key=lambda i: (i.guild_id, i.user.id))
    async def beg(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)
        multiplier, chance_bonus, moon_phase = await self.get_affinity_bonus(user_id)

        success_chance = 0.5 + (chance_bonus / 100)
        if random.random() < success_chance:
            amount = int(random.randint(500, 3000) * multiplier)
            await db.update_balance(user_id, amount)

            responses = [
                f"지나가던 행인이 **{amount:,}**원을 던져주었습니다.",
                f"요미가 몰래 **{amount:,}**원을 주머니에 넣어줬어요. (쉿!)",
                f"땅을 파다 **{amount:,}**원을 주웠습니다!"
            ]

            msg = random.choice(responses)
            if chance_bonus > 0:
                msg += f"\n*(💕 호감도 보너스로 성공 확률 {int(success_chance*100)}% 적용!)*"
            await interaction.response.send_message(msg)
        else:
            fail_responses = [
                "아쉽지만 오늘은 아무도 없나봐요... 다음에 다시 시도해보세요! (토닥토닥)",
                "요미: 교주님, 제가 응원할게요! 힘내세요! (파이팅!)",
                "동전은 아니지만, 행운의 병뚜껑을 찾았어요! 좋은 일이 생길 거예요!"
            ]
            await interaction.response.send_message(random.choice(fail_responses))

    @beg.error
    async def beg_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"체통을 지키세요... **{int(error.retry_after)}초** 뒤에 다시 하세요! (ㅡ_ㅡ)", ephemeral=True)

    @store_group.command(name="시세", description="수집 아이템의 시세 변동 그래프를 확인합니다.")
    @app_commands.describe(item_name="시세를 확인할 아이템 이름 (입력하지 않으면 전체 시세 목록을 보여줍니다)")
    async def market(self, interaction: discord.Interaction, item_name: str = None):


        await interaction.response.defer()

        if not item_name:
            status = await db.get_market_status()

            sorted_items = []
            for name, data in status.items():
                if name in self.collectible_items:
                    change = data.get('change_rate', 0.0)
                    sorted_items.append((name, change, abs(change)))

            sorted_items.sort(key=lambda x: x[2], reverse=True)
            top_movers = sorted_items[:4]
            if not top_movers:
                await interaction.followup.send("표시할 시세 데이터가 충분하지 않습니다.")
                return

            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=[f"{name} ({change:+.1f}%)" for name, change, _ in top_movers],
                vertical_spacing=0.15,
                horizontal_spacing=0.1
            )

            for idx, (name, change, _) in enumerate(top_movers):
                row = (idx // 2) + 1
                col = (idx % 2) + 1

                history = await db.get_price_history(name, limit=24)
                if not history: continue

                df = pd.DataFrame(history)
                df['timestamp'] = pd.to_datetime(df['timestamp'])

                line_color = '#FF4500' if change < 0 else '#00FF7F'
                fill_color = 'rgba(255, 69, 0, 0.2)' if change < 0 else 'rgba(0, 255, 127, 0.2)'

                fig.add_trace(go.Scatter(
                    x=df['timestamp'],
                    y=df['price'],
                    mode='lines',
                    name=name,
                    line=dict(color=line_color, width=3, shape='spline', smoothing=1.3),
                    fill='tozeroy',
                    fillcolor=fill_color
                ), row=row, col=col)

                last_price = df.iloc[-1]['price']
                fig.add_annotation(
                    x=df.iloc[-1]['timestamp'],
                    y=last_price,
                    text=f"{last_price:,}",
                    showarrow=False,
                    font=dict(size=10, color="white"),
                    bgcolor=line_color,
                    borderpad=2,
                    row=row, col=col
                )

            fig.update_layout(
                title=dict(
                    text="🔥 실시간 급변동 품목 TOP 4 🔥",
                    font=dict(size=24, family="Malgun Gothic", color="white"),
                    x=0.5,
                    xanchor='center'
                ),
                template="plotly_dark",
                paper_bgcolor='rgba(30, 30, 40, 1)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Malgun Gothic"),
                showlegend=False,
                margin=dict(l=40, r=40, t=80, b=40),
                height=600,
                width=800
            )

            img_bytes = fig.to_image(format="png", scale=2)
            buffer = io.BytesIO(img_bytes)
            buffer.seek(0)
            file = discord.File(buffer, filename="market_overview.png")

            embed = discord.Embed(
                title="📈 요미의 시장 시세표 (주요 변동)",
                description="현재 시장에서 가장 시세 변동이 큰 아이템들입니다.\n`/시세 [아이템명]`으로 개별 상세 그래프를 볼 수 있어요!",
                color=discord.Color.gold()
            )
            embed.set_image(url="attachment://market_overview.png")

            await interaction.followup.send(embed=embed, file=file)
            return

        if item_name not in self.collectible_items:
            await interaction.followup.send("존재하지 않는 아이템입니다! (수집 아이템만 시세가 존재합니다)", ephemeral=True)
            return

        history = await db.get_price_history(item_name, limit=24)
        if not history:
            current_price = await self.get_market_price(item_name)
            await interaction.followup.send(f"**{item_name}**의 시세 기록이 아직 충분하지 않습니다.\n현재 가격: {current_price:,} {self.currency_icon}")
            return

        df = pd.DataFrame(history)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        min_price = df['price'].min()
        max_price = df['price'].max()
        price_range = max_price - min_price
        y_min = max(0, min_price - (price_range * 0.1))
        y_max = max_price + (price_range * 0.1)

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['price'],
            mode='lines+markers',
            name=item_name,
            line=dict(color='#FF69B4', width=4, shape='spline', smoothing=1.3),
            marker=dict(size=8, color='#FFFFFF', line=dict(width=2, color='#FF69B4')),
            fill='tozeroy',
            fillcolor='rgba(255, 105, 180, 0.2)'        ))

        last_row = df.iloc[-1]
        fig.add_annotation(
            x=last_row['timestamp'],
            y=last_row['price'],
            text=f"{last_row['price']:,}",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor='#FF69B4',
            ax=0,
            ay=-40,
            font=dict(size=14, color="#FFFFFF", family="Malgun Gothic", weight="bold"),
            bgcolor="#FF69B4",
            bordercolor="#FFFFFF",
            borderwidth=1,
            borderpad=4,
            opacity=0.9
        )

        fig.update_layout(
            title=dict(
                text=f"📈 {item_name} 시세 변동 추이",
                font=dict(size=24, family="Malgun Gothic", color="white"),
                x=0.5,
                xanchor='center'
            ),
            xaxis=dict(
                title="시간",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                tickformat="%H:%M",
                tickfont=dict(color='white')
            ),
            yaxis=dict(
                title="가격 (젤리)",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                tickfont=dict(color='white'),
                range=[y_min, y_max]
            ),
            template="plotly_dark",
            font=dict(family="Malgun Gothic"),
            plot_bgcolor='rgba(0,0,0,0)',

paper_bgcolor='rgba(30, 30, 40, 1)',
margin=dict(l=60, r=40, t=80, b=60),
            showlegend=False
        )

        img_bytes = fig.to_image(format="png", width=800, height=500, scale=2)
        buffer = io.BytesIO(img_bytes)
        buffer.seek(0)

        file = discord.File(buffer, filename="market_chart.png")

        embed = discord.Embed(title=f"📊 {item_name} 시세 분석", color=discord.Color.gold())
        current_info = await db.get_market_status(item_name)

        if current_info:
            price = current_info['current_price']
            change = current_info['change_rate']
            trend = current_info['trend']
            trend_str = "상승세 🚀" if trend == 'up' else ("하락세 📉" if trend == 'down' else "보합세 ➖")

            embed.add_field(name="현재 가격", value=f"**{price:,}** {self.currency_icon}", inline=True)
            embed.add_field(name="변동률", value=f"**{change:+.2f}%**", inline=True)
            embed.add_field(name="시장 추세", value=trend_str, inline=True)

        embed.set_image(url="attachment://market_chart.png")

        await interaction.followup.send(embed=embed, file=file)

    @store_group.command(name="상점", description="아이템 상점을 엽니다.")
    async def shop(self, interaction: discord.Interaction):


        class ShopSelect(discord.ui.Select):
            def __init__(self, current_category):
                options = [
                    discord.SelectOption(label="호감도 아이템", value="affinity", description="요미에게 줄 선물!", default=(current_category=="affinity"), emoji="🎁"),
                    discord.SelectOption(label="펫 상점", value="pet", description="귀여운 펫과 용품들!", default=(current_category=="pet"), emoji="🐾"),
                    discord.SelectOption(label="전투 아이템", value="battle", description="던전/사냥에 필요한 물품!", default=(current_category=="battle"), emoji="⚔️"),
                    discord.SelectOption(label="장비 상점", value="armor", description="교주님을 위한 강력한 장비!", default=(current_category=="armor"), emoji="🛡️")
                ]
                super().__init__(placeholder="카테고리를 선택하세요", min_values=1, max_values=1, options=options, row=0)

            async def callback(self, interaction: discord.Interaction):
                self.view.current_category = self.values[0]
                self.view.page = 0
                self.view.update_items()

                self.view.clear_items()
                self.view.add_item(ShopSelect(self.view.current_category))
                self.view.add_buttons()

                await interaction.response.edit_message(embed=self.view.create_embed(), view=self.view)

        class ShopView(discord.ui.View):
            def __init__(self, categories, currency_icon):
                super().__init__(timeout=60)
                self.categories = categories
                self.currency_icon = currency_icon
                self.current_category = "affinity"
                self.page = 0
                self.items_per_page = 6
                self.items = []
                self.update_items()

                self.add_item(ShopSelect(self.current_category))
                self.add_buttons()

            def update_items(self):
                self.items = list(self.categories[self.current_category].items())

            def add_buttons(self):
                prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, custom_id="prev", row=1)
                prev_btn.callback = self.prev
                self.add_item(prev_btn)

                next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, custom_id="next", row=1)
                next_btn.callback = self.next
                self.add_item(next_btn)

            def create_embed(self):
                max_pages = (len(self.items) - 1) // self.items_per_page + 1
                if max_pages == 0: max_pages = 1
                start = self.page * self.items_per_page
                end = start + self.items_per_page
                current_items = self.items[start:end]

                category_names = {"affinity": "호감도 상점", "pet": "펫 상점", "battle": "전투 상점", "armor": "장비 상점"}
                title = f"🏪 요미의 {category_names.get(self.current_category, '상점')}"

                embed = discord.Embed(
                    title=title,
                    description=f"어서오세요! 필요한 물건을 골라보세요! (✿◡‿◡)\n구매는 `/구매 [아이템명]` 명령어를 사용해주세요.\n(현재 페이지 {self.page+1}/{max_pages})",
                    color=discord.Color.from_rgb(255, 182, 193)
                )

                for name, info in current_items:
                    desc = info.get('desc', '')
                    price = info.get('price', 0)
                    effect = ""
                    if 'affinity' in info:
                        effect = f"\n💕 호감도 +{info['affinity']:,}"
                    elif 'type' in info:
                        if info['type'] == 'pet_egg': effect = "\n🥚 펫 알"
                        elif info['type'] == 'pet_food': effect = "\n🍖 펫 간식"
                        elif info['type'] == 'consumable': effect = "\n🧪 소비 아이템"
                        elif info['type'] == 'buff': effect = "\n⚡ 버프 아이템"
                        elif info['type'] == 'ticket': effect = "\n🎫 입장권"
                    elif 'def' in info or 'atk' in info or 'hp' in info:
                        stats = []
                        if 'atk' in info: stats.append(f"⚔️ {info['atk']}")
                        if 'def' in info: stats.append(f"🛡️ {info['def']}")
                        if 'hp' in info: stats.append(f"❤️ {info['hp']}")
                        effect = "\n" + " ".join(stats)
                        if 'set' in info: effect += f"\n✨ {info['set']} 세트"

                    embed.add_field(
                        name=f"📦 {name}",
                        value=f"💰 **{price:,}** {self.currency_icon}{effect}\n*{desc}*",
                        inline=True
                    )

                embed.set_footer(text="카테고리를 선택하여 다른 상품도 구경해보세요! ✨")
                return embed

            async def prev(self, interaction: discord.Interaction):
                if self.page > 0:
                    self.page -= 1
                    await interaction.response.edit_message(embed=self.create_embed(), view=self)
                else:
                    await interaction.response.send_message("첫 페이지입니다!", ephemeral=True)

            async def next(self, interaction: discord.Interaction):
                if (self.page + 1) * self.items_per_page < len(self.items):
                    self.page += 1
                    await interaction.response.edit_message(embed=self.create_embed(), view=self)
                else:
                    await interaction.response.send_message("마지막 페이지입니다!", ephemeral=True)

        categories = {
            "affinity": self.shop_items,
            "pet": self.pet_shop_items,
            "battle": self.battle_items,
            "armor": self.armor_items
        }
        view = ShopView(categories, self.currency_icon)
        await interaction.response.send_message(embed=view.create_embed(), view=view)

    async def _get_equipped(self, user_id):
        return await db.get_equipped_armor(user_id) or {"head": None, "body": None, "legs": None, "feet": None, "weapon": None, "accessory": None}

    async def _update_equipped(self, user_id, slot, item_name):
        await db.update_equipped_armor(user_id, slot, item_name)

    async def calculate_stats(self, user_id):
        equipped = await db.get_equipped_armor(user_id) or {}
        stats = {"def": 0, "hp": 0, "atk": 0}

        for slot, item_name in equipped.items():
            if item_name and item_name in self.armor_items:
                item_data = self.armor_items[item_name]

                level = await self.get_armor_level(user_id, item_name)

                b_def = item_data.get("def", 0)
                b_hp = item_data.get("hp", 0)
                b_atk = item_data.get("atk", 0)

                multiplier = 1 + (level * 0.1)

                stats["def"] += int(b_def * multiplier)
                stats["hp"] += int(b_hp * multiplier)
                stats["atk"] += int(b_atk * multiplier)

        equipped_sets = {}
        for slot, item_name in equipped.items():
            if item_name and item_name in self.armor_items:
                set_name = self.armor_items[item_name].get("set")
                if set_name:
                    equipped_sets[set_name] = equipped_sets.get(set_name, 0) + 1

        for set_name, count in equipped_sets.items():
            if set_name in self.set_bonuses:
                bonus = self.set_bonuses[set_name]
                if count >= bonus["parts"]:
                    stats["def"] += bonus.get("bonus_def", 0)
                    stats["hp"] += bonus.get("bonus_hp", 0)
                    stats["atk"] += bonus.get("bonus_atk", 0)

        return stats

    @store_group.command(name="구매", description="상점에서 아이템을 구매합니다.")
    @app_commands.describe(category="구매할 아이템 카테고리", item_name="구매할 아이템", amount="구매할 개수")
    @app_commands.rename(category="카테고리", item_name="아이템", amount="개수")
    @app_commands.choices(category=[
        app_commands.Choice(name="🎁 호감도 아이템", value="affinity"),
        app_commands.Choice(name="🐾 펫 상점", value="pet"),
        app_commands.Choice(name="⚔️ 전투/소모품", value="battle"),
        app_commands.Choice(name="🛡️ 장비 상점", value="armor")
    ])
    @app_commands.autocomplete(item_name=buy_autocomplete)
    async def buy(self, interaction: discord.Interaction, category: str, item_name: str, amount: int = 1):

        try:
            if amount <= 0:
                await interaction.response.send_message("1개 이상의 수량을 입력해주세요! (😠)", ephemeral=True)
                return

            item_name = item_name.replace(" ", "")
            target_item = None
            item_info = None

            target_shops = []
            if category == "affinity": target_shops = [self.shop_items]
            elif category == "pet": target_shops = [self.pet_shop_items]
            elif category == "battle": target_shops = [self.battle_items]
            elif category == "armor": target_shops = [self.armor_items]
            else: target_shops = [self.shop_items, self.pet_shop_items, self.battle_items, self.armor_items]

            for shop in target_shops:
                for name, info in shop.items():
                    if item_name in name.replace(" ", "") or name.replace(" ", "") in item_name:
                        target_item = name
                        item_info = info
                        break
                if target_item: break

            if not target_item:
                await interaction.response.send_message(f"'{category}' 카테고리에서 '{item_name}'을(를) 찾을 수 없어요... (´。＿。｀)", ephemeral=True)
                return

            price_per_unit = item_info["price"]
            total_price = price_per_unit * amount
            user_id = str(interaction.user.id)
            balance = await db.get_balance(user_id)

            if not await db.try_deduct_balance(user_id, total_price):
                bal = await db.get_balance(user_id)
                await interaction.response.send_message(f"돈이 부족해요... 총 **{total_price:,}** 젤리가 필요한데, **{total_price - bal:,}** 젤리가 더 필요해요! ( >﹏< )", ephemeral=True)
                return

            await db.add_item(user_id, target_item, amount)

            await interaction.response.send_message(f"🎉 **{target_item}** {amount}개 구매 완료! 총 **{total_price:,}** 젤리를 사용했어요. 가방에 잘 넣어뒀어요! ( •̀ ω •́ )✧")

        except Exception as e:
            print(f"Buy Command Error: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("구매 처리 중 오류가 발생했어요... (´;ω;｀)", ephemeral=True)
                else:
                    await interaction.followup.send("구매 처리 중 오류가 발생했어요... (´;ω;｀)", ephemeral=True)
            except:
                pass

    @store_group.command(name="판매", description="가지고 있는 아이템을 판매하여 젤리를 법니다.")
    @app_commands.describe(category="판매할 아이템 카테고리", item_name="판매할 아이템", amount="판매할 개수")
    @app_commands.rename(category="카테고리", item_name="아이템", amount="개수")
    @app_commands.choices(category=[
        app_commands.Choice(name="💎 광물", value="mineral"),
        app_commands.Choice(name="🐟 물고기", value="fish"),
        app_commands.Choice(name="🌲 나무", value="wood"),
        app_commands.Choice(name="🛡️ 장비", value="armor"),
        app_commands.Choice(name="🧪 소비용품", value="consumable")
    ])
    @app_commands.autocomplete(item_name=sell_autocomplete)
    async def sell(self, interaction: discord.Interaction, category: str, item_name: str, amount: int = 1):

        try:
            user_id = str(interaction.user.id)

            if amount <= 0:
                await interaction.response.send_message("1개 이상의 수량을 입력해주세요! (😠)", ephemeral=True)
                return

            inv = await db.get_inventory(user_id)
            inv_dict = {i['item_name']: i['amount'] for i in inv}

            target_item_name = None
            for inv_name in inv_dict:
                if item_name.replace(" ", "") in inv_name.replace(" ", "") or inv_name.replace(" ", "") in item_name.replace(" ", ""):
                    target_item_name = inv_name
                    break

            if not target_item_name:
                await interaction.response.send_message(f"가방에 '{item_name}' 아이템이 없어요! (´。＿。｀)", ephemeral=True)
                return

            if inv_dict[target_item_name] < amount:
                await interaction.response.send_message(f"개수가 부족해요! 현재 **{inv_dict[target_item_name]}**개 가지고 있어요.", ephemeral=True)
                return

            price = 0

            all_shops = [self.shop_items, self.pet_shop_items, self.battle_items]

            if target_item_name in self.collectible_items:
                base_price = self.collectible_items[target_item_name]["price"]
                price, _ = await db.get_current_market_price(target_item_name, base_price)
            else:
                found_in_shop = False
                for shop in all_shops:
                    if target_item_name in shop:
                        price = int(shop[target_item_name]["price"] * 0.5)
                        found_in_shop = True
                        break

                if not found_in_shop:
                    await interaction.response.send_message(f"'{target_item_name}'은(는) 팔 수 없는 아이템이에요!", ephemeral=True)
                    return

            total_price = price * amount


            net_income = total_price
            if await db.remove_item(user_id, target_item_name, amount):
                await db.update_balance(user_id, net_income)

                await interaction.response.send_message(f"💰 **{target_item_name}** {amount}개를 팔아서 **{net_income:,}** 젤리를 벌었어요!\n(판매가: {total_price:,} 젤리)")
            else:
                await interaction.response.send_message("판매 처리 중 오류가 발생했어요...", ephemeral=True)

        except Exception as e:
            print(f"Sell Command Error: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("판매 처리 중 오류가 발생했어요... (´;ω;｀)", ephemeral=True)

    @store_group.command(name="가방", description="내 가방(인벤토리)을 확인합니다.")
    async def inventory(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)
        items = await db.get_inventory(user_id)

        if not items:
            await interaction.response.send_message("가방이 텅 비었어요... 상점에서 쇼핑이라도 할까요? (✿◡‿◡)", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎒 {interaction.user.display_name}님의 가방",
            color=discord.Color.blue()
        )

        desc_lines = []
        for item in items:
            desc_lines.append(f"📦 **{item['item_name']}** x {item['amount']}개")

        embed.description = "\n".join(desc_lines)
        embed.set_footer(text="`/선물 [아이템명]`으로 요미에게 선물을 줄 수 있어요!")

        await interaction.response.send_message(embed=embed)

    @store_group.command(name="선물", description="요미에게 선물을 주고 호감도를 올립니다.")
    @app_commands.describe(item_name="선물할 아이템을 선택해주세요.")
    @app_commands.rename(item_name="아이템")
    @app_commands.autocomplete(item_name=inventory_autocomplete)
    async def gift(self, interaction: discord.Interaction, item_name: str):

        user_id = str(interaction.user.id)

        inventory = await db.get_inventory(user_id)
        target_item = None

        has_item = False
        real_item_name = ""

        for inv_item in inventory:
            if item_name == inv_item['item_name']:
                target_item = self.shop_items.get(inv_item['item_name'])
                real_item_name = inv_item['item_name']
                has_item = True
                break

        if not has_item:
            for inv_item in inventory:
                if item_name in inv_item['item_name']:
                    target_item = self.shop_items.get(inv_item['item_name'])
                    real_item_name = inv_item['item_name']
                    has_item = True
                    break

        if not has_item:
            await interaction.response.send_message(f"**{item_name}**... 그건 가방에 없는 것 같은데요? (・_・;)", ephemeral=True)
            return

        if not target_item:
            await interaction.response.send_message("이건 제가 받을 수 없는 물건이에요...!")
            return

        if await db.remove_item(user_id, real_item_name, 1):
            affinity_bonus = target_item['affinity']

            chatbot_cog = self.bot.get_cog("Chatbot")

            await interaction.response.defer()

            if chatbot_cog:
                if affinity_bonus >= 3000:
                    msgs = [
                        f"💎 **{real_item_name}**...?! 이거 꿈 아니죠? 제, 제가 이런 걸 받아도 돼요? ㅠㅠ 교주님 사랑해요!! 평생 충성할게요!! 💖💖💖",
                        f"💍 세상에... **{real_item_name}**이라니... (기절) ... (벌떡) 감사합니다 교주님!! 가보로 남길게요!!! 💕",
                        f"🏰 **{real_item_name}**...!!! 교주님, 저랑 결혼... 아니, 아무것도 아니에요! 너무 고마워요! (얼굴 빨개짐)"
                    ]
                elif affinity_bonus >= 500:
                    msgs = [
                        f"💎 헉!! 세상에!! **{real_item_name}**?! 정말 저한테 주시는 건가요?! 너무 고마워요 교주님!! 평생 간직할게요!! 💖💖💖",
                        f"✨ 우와아아! **{real_item_name}**!! 저 이거 갖고 싶었던 거 어떻게 아셨어요? 교주님 최고! (와락)",
                        f"🎁 대박! **{real_item_name}** 선물이라니! 오늘 기념일인가요? 너무 행복해요! 헤헤."
                    ]
                elif affinity_bonus >= 100:
                    msgs = [
                        f"🎁 우와아! **{real_item_name}**네요! 정말 좋아해요! 잘 먹을게요! (오물오물) 💕",
                        f"🌸 **{real_item_name}**! 교주님 센스쟁이! 기분 날아갈 것 같아요~",
                        f"🧸 와! **{real_item_name}**! 너무 귀여워요! 감사합니다! (방방 뜀)"
                    ]
                else:
                    msgs = [
                        f"🍬 **{real_item_name}** 고마워요! 교주님이 주신 거라 더 맛있는 것 같아요! 헤헤.",
                        f"🍭 냠냠! **{real_item_name}** 잘 먹을게요! 교주님도 한 입 드실래요?",
                        f"🍫 **{real_item_name}**! 당 충전 완료! 힘이 나네요!"
                    ]

                msg = random.choice(msgs)


                await interaction.followup.send(msg)


                class FakeMessage:
                    def __init__(self, interaction):
                        self.author = interaction.user
                        self.channel = interaction.channel
                        self.created_at = interaction.created_at
                        self.guild = interaction.guild
                        self.content = "gift command"

                fake_msg = FakeMessage(interaction)
                await chatbot_cog.update_affinity_with_feedback(fake_msg, user_id, affinity_bonus, bypass_cap=True)

            else:
                await db.update_affinity(user_id, affinity_bonus)
                await interaction.followup.send(f"**{real_item_name}** 선물 고마워요! (호감도 +{affinity_bonus})")
        else:
            await interaction.response.send_message("어라? 가방에서 물건을 꺼내다가 떨어뜨렸나요? (오류 발생)", ephemeral=True)

    @game_group.command(name="도박", description="돈을 걸고 주사위 게임을 합니다.")
    @app_commands.describe(amount="걸고 싶은 금액 (또는 '올인')")
    @app_commands.rename(amount="금액")
    async def gamble(self, interaction: discord.Interaction, amount: str):

        user_id = str(interaction.user.id)

        benefits = booster_utils.get_booster_benefits(interaction.user)
        cooldown_time = 3 * benefits["cooldown_mult"]

        cooldown = await db.check_cooldown(user_id, "gamble", cooldown_time)
        if cooldown > 0:
             return await interaction.response.send_message(f"잠시만요! 주사위를 줍고 있어요... ( {cooldown:.1f}초 )", ephemeral=True)

        current_balance = await db.get_balance(user_id)

        if amount in ["올인", "all", "전부", "allin"]:
            bet_amount = current_balance
        else:
            try:
                bet_amount = int(amount)
            except ValueError:
                return await interaction.response.send_message("금액은 숫자로 적어주세요! (또는 '올인')", ephemeral=True)

        if bet_amount <= 0:
            return await interaction.response.send_message("0보다 큰 금액을 걸어야죠! (😠)", ephemeral=True)

        if not await db.try_deduct_balance(user_id, bet_amount):
            return await interaction.response.send_message(f"젤리가 부족해요! 현재 **{await db.get_balance(user_id):,}** 젤리 가지고 있어요.", ephemeral=True)

        await db.update_cooldown(user_id, "gamble")

        embed = discord.Embed(title="🎲 주사위 굴리는 중...", description="두근두근...", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await asyncio.sleep(0.5)

        user_roll = random.randint(1, 100)
        bot_roll = random.randint(1, 100)
        result_embed = discord.Embed(title="🎲 승부 결과!", color=discord.Color.gold())
        result_embed.add_field(name=f"{interaction.user.display_name}", value=f"🎲 **{user_roll}**", inline=True)
        result_embed.add_field(name="VS", value="⚡", inline=True)
        result_embed.add_field(name="요미", value=f"🎲 **{bot_roll}**", inline=True)

        final_msg = ""

        if user_roll > bot_roll:

            gross_profit = bet_amount
            total_payout = bet_amount + gross_profit
            await db.update_balance(user_id, total_payout)
            await db.update_game_stats(user_id, gross_profit, True)
            final_msg = f"🎉 **승리!** 축하합니다!\n배팅한 **{bet_amount:,}** 젤리의 2배인 **{total_payout:,}** 젤리를 획득했습니다!"

            result_embed.color = discord.Color.green()
        else:
            await db.update_game_stats(user_id, 0, False)
            if user_roll == bot_roll:
                final_msg = f"😅 **무승부...지만 패배!**\n요미가 이겼다고 우기네요... **{bet_amount:,}** 젤리를 잃었습니다."
            else:
                final_msg = f"😭 **패배...** 아쉽네요...\n**{bet_amount:,}** 젤리를 잃었습니다."
            result_embed.color = discord.Color.red()

        result_embed.description = final_msg

        class GambleView(discord.ui.View):
            def __init__(self, user_id, bet_amount):
                super().__init__(timeout=60)
                self.user_id = user_id
                self.bet_amount = bet_amount

            @discord.ui.button(label="다시 하기 (같은 금액)", style=discord.ButtonStyle.primary, emoji="🔄")
            async def replay(self, b_interaction: discord.Interaction, button: discord.ui.Button):
                if str(b_interaction.user.id) != self.user_id:
                    return await b_interaction.response.send_message("본인의 게임만 재시작할 수 있어요!", ephemeral=True)

                if not await db.try_deduct_balance(self.user_id, self.bet_amount):
                    return await b_interaction.response.send_message("젤리가 부족해요!", ephemeral=True)

                await b_interaction.response.defer()
                await b_interaction.edit_original_response(embed=discord.Embed(title="🎲 주사위 굴리는 중...", description="두근두근...", color=discord.Color.gold()), view=None)
                await asyncio.sleep(0.5)

                u_roll = random.randint(1, 100)
                b_roll = random.randint(1, 100)
                new_embed = discord.Embed(title="🎲 승부 결과!", color=discord.Color.gold())
                new_embed.add_field(name=f"{b_interaction.user.display_name}", value=f"🎲 **{u_roll}**", inline=True)
                new_embed.add_field(name="VS", value="⚡", inline=True)
                new_embed.add_field(name="요미", value=f"🎲 **{b_roll}**", inline=True)

                f_msg = ""
                if u_roll > b_roll:

                    gross_profit = self.bet_amount
                    total_payout = self.bet_amount + gross_profit
                    await db.update_balance(self.user_id, total_payout)
                    await db.update_game_stats(self.user_id, gross_profit, True)
                    f_msg = f"🎉 **승리!** 축하합니다!\n**{total_payout:,}** 젤리를 획득했습니다!"

                    new_embed.color = discord.Color.green()
                else:
                    await db.update_game_stats(self.user_id, 0, False)
                    if u_roll == b_roll:
                        f_msg = f"😅 **무승부...지만 패배!**\n요미가 이겼다고 우기네요... **{self.bet_amount:,}** 젤리를 잃었습니다."
                    else:
                        f_msg = f"😭 **패배...** 아쉽네요...\n**{self.bet_amount:,}** 젤리를 잃었습니다."
                    new_embed.color = discord.Color.red()

                new_embed.description = f_msg
                await b_interaction.edit_original_response(embed=new_embed, view=self)

        await msg.edit(embed=result_embed, view=GambleView(user_id, bet_amount))

    @activity_group.command(name="요미찾기", description="3x3 상자 속에 숨은 요미를 찾아보세요! (1분 쿨타임)")
    async def find_yomi(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        benefits = booster_utils.get_booster_benefits(interaction.user)
        cooldown_time = 60 * benefits["cooldown_mult"]

        cooldown = await db.check_cooldown(user_id, "find_yomi", cooldown_time)
        if cooldown > 0:
            return await interaction.response.send_message(f"요미가 숨을 곳을 찾고 있어요! **{int(cooldown)}초** 뒤에 다시 찾아보세요! 📦", ephemeral=True)

        await db.update_cooldown(user_id, "find_yomi")

        multiplier, chance_bonus, _ = await self.get_affinity_bonus(user_id)
        base_reward = 20000
        yomi_index = random.randint(0, 8)

        show_hint = False
        hint_idx = -1

        if chance_bonus >= 5 and random.random() < 0.2:
            show_hint = True
            hint_idx = yomi_index

        embed = discord.Embed(title="📦 요미 찾기!", description="요미가 9개의 상자 중 하나에 숨었어요!\n요미를 찾으면 **대박 보상**을 드려요!", color=discord.Color.orange())
        if show_hint:
            embed.set_footer(text="💡 힌트: 어라? 상자 옆에 고양이 발자국이...?")

        class YomiView(discord.ui.View):
            def __init__(self, correct_idx, hint_idx):
                super().__init__(timeout=60)
                self.correct_idx = correct_idx
                self.hint_idx = hint_idx

                for i in range(9):
                    label = "📦"
                    style = discord.ButtonStyle.secondary
                    if i == self.hint_idx:
                        label = "📦🐾"
                    self.add_item(YomiButton(i, label, style))

        class YomiButton(discord.ui.Button):
            def __init__(self, index, label, style):
                super().__init__(label=label, style=style, row=index // 3)
                self.index = index

            async def callback(self, btn_interaction: discord.Interaction):
                if str(btn_interaction.user.id) != user_id:
                    return await btn_interaction.response.send_message("본인의 게임만 참여할 수 있어요!", ephemeral=True)

                view: YomiView = self.view

                for child in view.children:
                    child.disabled = True
                    if child.index == view.correct_idx:
                        child.label = "🐱"
                        child.style = discord.ButtonStyle.success
                    else:
                        child.label = "💨"
                        child.style = discord.ButtonStyle.secondary

                if self.index == view.correct_idx:
                    reward = int(base_reward * multiplier)

                    is_gold = False
                    if random.random() < 0.05:
                        reward *= 5
                        is_gold = True

                    await db.update_balance(user_id, reward)
                    await db.update_game_stats(user_id, reward, True)

                    if is_gold:
                        res_embed = discord.Embed(title="🌟 황금 요미 발견!!! 🌟", description=f"대박!! 전설의 황금 요미를 찾았어요!!\n보상: **{reward:,}** 젤리 (5배!)", color=discord.Color.gold())
                    else:
                        res_embed = discord.Embed(title="🎉 찾았다!!", description=f"상자 속에서 자고 있던 요미를 찾았어요!\n보상: **{reward:,}** 젤리", color=discord.Color.green())

                    res_embed.set_image(url="https://media1.tenor.com/m/mXk5k_c-1XAAAAAC/cat-box.gif")
                else:
                    await db.update_game_stats(user_id, 0, False)
                    res_embed = discord.Embed(title="💨 꽝!", description=f"아무것도 없네요... 요미는 **{view.correct_idx+1}번** 상자에 있었어요.", color=discord.Color.red())

                await btn_interaction.response.edit_message(embed=res_embed, view=view)

        await interaction.response.send_message(embed=embed, view=YomiView(yomi_index, hint_idx))

    @find_yomi.error
    async def find_yomi_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"요미가 아직 숨을 준비가 안 됐대요! **{int(error.retry_after)}초** 뒤에 다시 찾아주세요! (✿◡‿◡)", ephemeral=True)

    @store_group.command(name="장비뽑기", description="젤리를 사용하여 장비를 무작위로 획득합니다. (1회 100,000 젤리)")
    @app_commands.describe(count="뽑기 횟수 (1회 또는 10회)")
    @app_commands.rename(count="횟수")
    @app_commands.choices(count=[
        app_commands.Choice(name="1회 뽑기 (10만 젤리)", value=1),
        app_commands.Choice(name="10+1회 뽑기 (100만 젤리)", value=11)
    ])
    async def draw_equipment(self, interaction: discord.Interaction, count: int):

        user_id = str(interaction.user.id)
        cost_per_draw = 100000

        real_count = 10 if count == 11 else 1
        total_cost = cost_per_draw * real_count
        if not await db.try_deduct_balance(user_id, total_cost):
             return await interaction.response.send_message(f"젤리가 부족해요! **{total_cost:,}** 젤리가 필요합니다.", ephemeral=True)

        await interaction.response.send_message(f"🎁 **두근두근 장비 뽑기 진행 중...** (소모: {total_cost:,} 젤리)")
        await asyncio.sleep(2)

        rarities = ["common", "rare", "epic", "legendary", "mythical"]
        weights = [50, 30, 15, 4, 1]

        drawn_items = []

        pool = {"common": [], "rare": [], "epic": [], "legendary": [], "mythical": []}
        for name, info in self.armor_items.items():
            r = info.get("rarity", "common")
            pool[r].append(name)

        loop_count = count
        highest_rarity_drawn = "common"
        rarity_rank = {"common": 0, "rare": 1, "epic": 2, "legendary": 3, "mythical": 4}

        for _ in range(loop_count):
            rarity = random.choices(rarities, weights=weights, k=1)[0]
            if not pool[rarity]: rarity = "common"
            item = random.choice(pool[rarity])
            drawn_items.append((rarity, item))
            await db.add_item(user_id, item, 1)

            if rarity_rank[rarity] > rarity_rank[highest_rarity_drawn]:
                highest_rarity_drawn = rarity

        color = discord.Color.blue()
        if highest_rarity_drawn == "mythical": color = discord.Color.purple()
        elif highest_rarity_drawn == "legendary": color = discord.Color.gold()

        embed = discord.Embed(title="🎁 장비 뽑기 결과!", color=color)

        desc_lines = []
        for rarity, item in drawn_items:
            emoji = ""
            if rarity == "mythical": emoji = "🌟 [신화]"
            elif rarity == "legendary": emoji = "🟠 [전설]"
            elif rarity == "epic": emoji = "🟣 [에픽]"
            elif rarity == "rare": emoji = "🔵 [희귀]"
            else: emoji = "⚪ [일반]"

            desc_lines.append(f"{emoji} **{item}**")

        if len(desc_lines) > 15:
            hidden = len(desc_lines) - 15
            desc_lines = desc_lines[:15]
            desc_lines.append(f"...외 {hidden}개")

        embed.description = "\n".join(desc_lines)
        if highest_rarity_drawn in ["legendary", "mythical"]:
            embed.set_footer(text="축하합니다! 대박이네요!")
        else:
            embed.set_footer(text="다음엔 더 좋은 게 나올 거예요!")

        await interaction.edit_original_response(content=None, embed=embed)

    @activity_group.command(name="대장간", description="장비를 강화하여 더 강력하게 만듭니다.")
    async def forge(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        embed = discord.Embed(title="⚒️ 요미의 대장간", description="무엇을 강화하시겠어요?", color=discord.Color.dark_orange())
        embed.add_field(name="⛏️ 도구 강화", value="낚시대, 곡괭이, 도끼, 검을 강화합니다.\n(젤리 소모)", inline=False)
        embed.add_field(name="🛡️ 방어구 강화", value="착용 중인 방어구를 강화합니다.\n(젤리 + 광물 소모)", inline=False)

        class ForgeView(discord.ui.View):
            def __init__(self, cog, parent_interaction):
                super().__init__(timeout=60)
                self.cog = cog
                self.parent_interaction = parent_interaction

            @discord.ui.button(label="도두/무기 강화", style=discord.ButtonStyle.secondary, emoji="⛏️")
            async def tool_upgrade(self, b_interaction: discord.Interaction, button: discord.ui.Button):
                if b_interaction.user.id != interaction.user.id: return
                await self.show_tool_upgrade(b_interaction)

            @discord.ui.button(label="방어구 강화", style=discord.ButtonStyle.primary, emoji="🛡️")
            async def armor_upgrade(self, b_interaction: discord.Interaction, button: discord.ui.Button):
                if b_interaction.user.id != interaction.user.id: return
                await self.show_armor_upgrade(b_interaction)

            async def show_tool_upgrade(self, i: discord.Interaction):
                async def get_gear_info(gear_type):
                    lv = await db.get_upgrade(user_id, gear_type)
                    upgrades = self.cog.upgrades[gear_type]
                    curr_item = upgrades[lv]

                    text = f"**현재:** {curr_item['name']} (Lv.{lv})\n"

                    if lv + 1 < len(upgrades):
                        next_item = upgrades[lv + 1]
                        prob = max(10, 100 - (lv * 5))
                        if lv < 3: prob = 100

                        text += f"**다음:** {next_item['name']} (Lv.{lv+1})\n"
                        text += f"**자료:** {next_item['price']:,} 젤리\n"
                        text += f"**확률:** {prob}%\n"
                    else:
                        text += "**✨ 최대 강화! ✨**"
                    return text, lv, (lv + 1 < len(upgrades))

                embed = discord.Embed(title="⚒️ 도구/무기 강화", color=discord.Color.blue())
                rod_text, rod_lv, rod_can = await get_gear_info("fishing_rod")
                pick_text, pick_lv, pick_can = await get_gear_info("pickaxe")
                axe_text, axe_lv, axe_can = await get_gear_info("axe")
                sword_text, sword_lv, sword_can = await get_gear_info("sword")

                embed.add_field(name="🎣 낚시대", value=rod_text, inline=False)
                embed.add_field(name="⛏️ 곡괭이", value=pick_text, inline=False)
                embed.add_field(name="🪓 도끼", value=axe_text, inline=False)
                embed.add_field(name="⚔️ 검", value=sword_text, inline=False)

                gear_status = {
                    "fishing_rod": {"level": rod_lv, "can": rod_can},
                    "pickaxe": {"level": pick_lv, "can": pick_can},
                    "axe": {"level": axe_lv, "can": axe_can},
                    "sword": {"level": sword_lv, "can": sword_can},
                }
                view = ToolUpgradeView(self.cog, user_id, gear_status)
                await i.response.edit_message(embed=embed, view=view)

            async def show_armor_upgrade(self, i: discord.Interaction):
                equipped = await self.cog._get_equipped(user_id)

                embed = discord.Embed(title="🛡️ 방어구 강화", description="강화할 장비를 선택해주세요.\n강화 시 능력치가 **10%** 씩 상승합니다!\n*강화에는 젤리와 광물이 필요합니다.*", color=discord.Color.gold())

                slots_kr = {"head": "머리", "body": "몸통", "legs": "다리", "feet": "발", "accessory": "장신구"}
                valid_items = []

                for slot, item_name in equipped.items():
                    if not item_name: continue
                    if slot == "weapon": continue

                    curr_lv = await self.cog.get_armor_level(user_id, item_name)

                    cost_jelly = 5000 * (curr_lv + 1)
                    mat = "철광석"
                    cost_mat = curr_lv + 1

                    if curr_lv >= 10:
                        mat = "다이아몬드 결정"
                        cost_mat = curr_lv - 9
                    elif curr_lv >= 5:
                        mat = "순금 주괴"
                        cost_mat = curr_lv - 4

                    embed.add_field(name=f"{slots_kr.get(slot)}: {item_name} (+{curr_lv})",
                                    value=f"비용: {cost_jelly:,} 젤리 + {mat} {cost_mat}개\n성공 확률: {max(5, 100 - curr_lv*5) if curr_lv < 5 else (max(50, 90-(curr_lv-5)*10) if curr_lv < 10 else max(5, 45-(curr_lv-10)*5))}%",
                                    inline=False)

                    valid_items.append((slot, item_name, curr_lv, cost_jelly, mat, cost_mat))

                if not valid_items:
                    embed.description = "장착 중인 방어구가 없습니다! 장비를 먼저 장착해주세요."

                view = ArmorUpgradeView(self.cog, user_id, valid_items)
                await i.response.edit_message(embed=embed, view=view)

        class ToolUpgradeView(discord.ui.View):
            def __init__(self, cog, target_user_id, gear_status):
                super().__init__(timeout=60)
                self.cog = cog
                self.target_user_id = target_user_id
                self.gear_status = gear_status

                self.add_buttons()

            def add_buttons(self):
                for type_key, label, emoji in [("fishing_rod", "낚시대", "🎣"), ("pickaxe", "곡괭이", "⛏️"), ("axe", "도끼", "🪓"), ("sword", "검", "⚔️")]:
                    status = self.gear_status.get(type_key, {"level": 0, "can": True})
                    can = status["can"]

                    btn = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary if can else discord.ButtonStyle.secondary, disabled=not can)
                    btn.type_key = type_key
                    btn.callback = self.make_callback(type_key)
                    self.add_item(btn)

            def make_callback(self, gear_type):
                async def callback(b_int: discord.Interaction):
                    if str(b_int.user.id) != self.target_user_id: return

                    user_id = str(b_int.user.id)
                    curr_lv = await db.get_upgrade(user_id, gear_type)
                    upgrades = self.cog.upgrades[gear_type]

                    if curr_lv + 1 >= len(upgrades):
                         return await b_int.response.send_message("이미 최고 레벨입니다!", ephemeral=True)

                    req_mat = None
                    req_amt = 0

                    if gear_type == "fishing_rod":
                        req_mat = "거미줄"
                        req_amt = (curr_lv + 1) * 2
                    elif gear_type == "pickaxe":
                        req_mat = "참나무"
                        req_amt = (curr_lv + 1) * 3
                    elif gear_type == "axe":
                        req_mat = "철광석"
                        req_amt = (curr_lv + 1) * 2
                    elif gear_type == "sword":
                        req_mat = "철광석"
                        req_amt = (curr_lv + 1) * 5

                    inv = await db.get_inventory(user_id)
                    inv_dict = {i['item_name']: i['amount'] for i in inv}
                    mat_count = inv_dict.get(req_mat, 0)

                    if mat_count < req_amt:
                         return await b_int.response.send_message(f"재료가 부족해요! **{req_mat}** {req_amt}개가 필요합니다.\n(현재: {mat_count}개)", ephemeral=True)

                    next_item = upgrades[curr_lv + 1]
                    price = next_item['price']

                    if not await db.try_deduct_balance(user_id, price):
                        return await b_int.response.send_message(f"젤리가 부족해요! **{price:,}** 젤리가 필요합니다.", ephemeral=True)

                    await db.remove_item(user_id, req_mat, req_amt)

                    await b_int.response.defer()
                    await b_int.edit_original_response(embed=discord.Embed(title="⚒️ 땅땅땅!...", description=f"대장장이 요미가 망치질을 합니다...\n(재료 소모: {req_mat} -{req_amt}개)", color=discord.Color.orange()), view=None)
                    await asyncio.sleep(1.5)

                    prob = max(10, 100 - (curr_lv * 5))
                    if curr_lv < 3: prob = 100

                    success = random.randint(1, 100) <= prob

                    final_embed = discord.Embed(title="⚒️ 강화 결과", color=discord.Color.green())

                    if success:
                        await db.set_upgrade(user_id, gear_type, curr_lv + 1)
                        final_embed.title = "✨ 강화 성공!!"
                        final_embed.description = f"축하합니다! **{next_item['name']}**(으)로 강화되었습니다!\n(현재 Lv.{curr_lv + 1})"
                    else:
                        final_embed.title = "💥 강화 실패..."
                        final_embed.description = f"으악! 손이 미끄러졌어요...\n재료와 돈이 사라졌습니다... (성공 확률: {prob}%)"
                        final_embed.color = discord.Color.red()

                    await b_int.edit_original_response(embed=final_embed, view=None)
                return callback

        class ArmorUpgradeView(discord.ui.View):
            def __init__(self, cog, target_user_id, items):
                super().__init__(timeout=60)
                self.cog = cog
                self.target_user_id = target_user_id

                for slot, name, lv, cost, mat, mat_cost in items:
                     self.add_item(ArmorButton(name, lv, cost, mat, mat_cost, cog, target_user_id))

        class ArmorButton(discord.ui.Button):
            def __init__(self, item_name, lv, cost, mat, mat_cost, cog, user_id):
                super().__init__(label=f"{item_name} (+{lv})", style=discord.ButtonStyle.success)
                self.item_name = item_name
                self.cost = cost
                self.mat = mat
                self.mat_cost = mat_cost
                self.cog = cog
                self.user_id = user_id
                self.lv = lv

            async def callback(self, b_int: discord.Interaction):
                if str(b_int.user.id) != self.user_id: return

                if not await db.try_deduct_balance(self.user_id, self.cost):
                     return await b_int.response.send_message(f"젤리가 부족해요! (**{self.cost:,}** 젤리 필요)", ephemeral=True)

                inv = await db.get_inventory(self.user_id)
                inv_dict = {i['item_name']: i['amount'] for i in inv}
                if inv_dict.get(self.mat, 0) < self.mat_cost:
                    await db.update_balance(self.user_id, self.cost)
                    return await b_int.response.send_message(f"재료가 부족해요! (**{self.mat}** {self.mat_cost}개 필요)", ephemeral=True)

                if not await db.remove_item(self.user_id, self.mat, self.mat_cost):
                     await db.update_balance(self.user_id, self.cost)
                     return await b_int.response.send_message("재료 소모 중 오류가 발생했습니다.", ephemeral=True)


                success_rate = 100
                is_danger = False

                if self.lv < 5:
                    success_rate = 100
                elif self.lv < 10:
                    success_rate = max(50, 90 - (self.lv - 5) * 10)
                else:
                    success_rate = max(5, 45 - (self.lv - 10) * 5)
                    is_danger = True

                if random.randint(1, 100) <= success_rate:
                    await self.cog.set_armor_level(self.user_id, self.item_name, self.lv + 1)
                    await b_int.response.send_message(f"🎉 **강화 성공!** **{self.item_name}** (+{self.lv+1})이 되었습니다! (성공률: {success_rate}%)", ephemeral=True)
                else:
                    msg = f"🔨 깡! **강화 실패...** (성공률: {success_rate}%)"
                    if is_danger:
                        inv = await db.get_inventory(self.user_id)
                        inv_dict = {i['item_name']: i['amount'] for i in inv}
                        has_scroll = inv_dict.get("강화 보호 주문서", 0) > 0

                        if has_scroll:
                            await db.remove_item(self.user_id, "강화 보호 주문서", 1)
                            msg += "\n🛡️ **강화 보호 주문서**가 파괴를 막았습니다! (하락 방지)"
                        else:
                            new_lv = max(10, self.lv - 1)
                            await self.cog.set_armor_level(self.user_id, self.item_name, new_lv)
                            msg += f"\n📉 **등급 하락!** (+{self.lv} -> +{new_lv})"
                    else:
                        msg += "\n다행히 등급은 유지되었습니다."

                    await b_int.response.send_message(msg, ephemeral=True)

        await interaction.response.send_message(embed=embed, view=ForgeView(self, interaction))




    @activity_group.command(name="범죄", description="요미 몰래 나쁜 짓을 해서 돈을 멉니다... (성공 시 큰 보상, 실패 시 벌금!)")
    @app_commands.checks.cooldown(1, 1800, key=lambda i: (i.guild_id, i.user.id))
    async def crime(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        embed = discord.Embed(title="🚨 범죄 계획", description="정말 나쁜 짓을 하실 건가요...?\n\n**[위험 요소]**\n- 🚓 경찰에 잡히면 벌금을 냅니다!\n- 💔 요미의 호감도가 떨어집니다!\n- 💸 성공하면 큰 돈을 벌 수 있습니다.", color=discord.Color.red())

        class CrimeView(discord.ui.View):
            def __init__(self, economy_cog):
                super().__init__(timeout=30)
                self.economy_cog = economy_cog
                self.value = None
                self.processing = False

            @discord.ui.button(label="범죄 저지르기", style=discord.ButtonStyle.danger, emoji="😈")
            async def confirm(self, b_interaction: discord.Interaction, button: discord.ui.Button):
                if b_interaction.user.id != interaction.user.id:
                    return await b_interaction.response.send_message("본인만 선택할 수 있어요!", ephemeral=True)

                if self.processing:
                    return await b_interaction.response.send_message("처리 중입니다...", ephemeral=True)
                self.processing = True

                for child in self.children: child.disabled = True
                await interaction.edit_original_response(view=self)

                crimes = [
                    ("🍭 아이 캔디 훔치기", 1000, 3000, 0.5, "아이의 사탕을 뺏었습니다... 맛있네요", 5),
                    ("💰 편의점 알바비 횡령", 5000, 15000, 0.5, "계산대에서 슬쩍 돈을 챙겼습니다!", 20),
                    ("💎 금은방 털기", 50000, 200000, 0.5, "경비원들을 피해 귀금속을 훔쳤습니다!!", 100)
                ]

                crime_name, min_p, max_p, success_rate, success_msg, affinity_penalty = random.choice(crimes)

                await db.update_affinity(user_id, -affinity_penalty)

                if random.random() < success_rate:
                    reward = random.randint(min_p, max_p)
                    await db.update_balance(user_id, reward)

                    await b_interaction.response.send_message(f"🚨 **{crime_name} 성공!**\n{success_msg}\n보상: **{reward:,}** 젤리\n💔 호감도: **-{affinity_penalty}**")
                else:
                    penalty = random.randint(min_p, max_p // 2)
                    await db.update_balance(user_id, -penalty)
                    await b_interaction.response.send_message(f"🚔 **{crime_name} 실패!**\n경찰에게 잡혀 벌금 **{penalty:,}** 젤리를 냈습니다... (´;ω;｀)\n💔 호감도: **-{affinity_penalty}**")

            @discord.ui.button(label="착하게 살기", style=discord.ButtonStyle.success, emoji="😇")
            async def cancel(self, b_interaction: discord.Interaction, button: discord.ui.Button):
                if b_interaction.user.id != interaction.user.id:
                    return await b_interaction.response.send_message("본인만 선택할 수 있어요!", ephemeral=True)

                if self.processing:
                    return await b_interaction.response.send_message("처리 중입니다...", ephemeral=True)
                self.processing = True

                for child in self.children: child.disabled = True
                await interaction.edit_original_response(view=self)

                await b_interaction.response.send_message("휴... 다행이에요! 요미는 착한 교주님이 좋아요! (호감도 변동 없음)", ephemeral=True)

        await interaction.response.send_message(embed=embed, view=CrimeView(self))

    @activity_group.command(name="제작", description="재료를 가공하여 상위 재료를 만듭니다.")
    @app_commands.describe(item_name="제작할 아이템 (강철/순금/다이아)", amount="제작할 개수")
    @app_commands.rename(item_name="아이템", amount="수량")
    @app_commands.choices(item_name=[
        app_commands.Choice(name="강철 주괴 (철광석 5개)", value="강철 주괴"),
        app_commands.Choice(name="순금 주괴 (금광석 5개)", value="순금 주괴"),
        app_commands.Choice(name="다이아몬드 결정 (다이아몬드 5개)", value="다이아몬드 결정")
    ])
    async def craft(self, interaction: discord.Interaction, item_name: str, amount: int = 1):

        user_id = str(interaction.user.id)

        recipes = {
            "강철 주괴": {"ing": "철광석", "cost": 5},
            "순금 주괴": {"ing": "금광석", "cost": 5},
            "다이아몬드 결정": {"ing": "다이아몬드", "cost": 5}
        }

        recipe = recipes.get(item_name)
        if not recipe: return

        req_ing = recipe['ing']
        cost_per = recipe['cost']
        total_cost = cost_per * amount

        inv = await db.get_inventory(user_id)
        inv_dict = {i['item_name']: i['amount'] for i in inv}

        if inv_dict.get(req_ing, 0) < total_cost:
            return await interaction.response.send_message(f"재료가 부족해요! **{req_ing}** {total_cost}개가 필요합니다.", ephemeral=True)

        await db.remove_item(user_id, req_ing, total_cost)
        await db.add_item(user_id, item_name, amount)

        await interaction.response.send_message(f"⚒️ **제작 성공!** {req_ing} {total_cost}개를 사용하여 **{item_name}** {amount}개를 만들었습니다!")

    @store_group.command(name="장비", description="착용 중인 장비를 확인하고 관리(변경/해제)합니다.")
    async def my_armor(self, interaction: discord.Interaction):


        class EquipmentSelect(discord.ui.Select):
            def __init__(self, items, slot_name, view_ref):
                options = []
                options.append(discord.SelectOption(label="장착 해제", value="unequip", description=f"현재 착용한 {slot_name} 장비를 해제합니다.", emoji="🚫"))

                for item in items:
                    stats = []
                    item_data = view_ref.cog.armor_items.get(item['item_name'], {})
                    if 'atk' in item_data: stats.append(f"공{item_data['atk']}")
                    if 'def' in item_data: stats.append(f"방{item_data['def']}")

                    desc = ", ".join(stats) if stats else "능력치 없음"
                    options.append(discord.SelectOption(label=item['item_name'], value=item['item_name'], description=desc, emoji="🛡️"))

                options = options[:25]

                super().__init__(placeholder="장착할 아이템을 선택하세요", min_values=1, max_values=1, options=options)
                self.view_ref = view_ref
                self.slot_name = slot_name

            async def callback(self, interaction: discord.Interaction):
                selected = self.values[0]
                user_id = str(interaction.user.id)

                if selected == "unequip":
                    current_equipped = await self.view_ref.cog._get_equipped(user_id)
                    current_item = current_equipped.get(self.view_ref.target_slot)
                    if current_item:
                        await self.view_ref.cog._update_equipped(user_id, self.view_ref.target_slot, None)
                        await db.add_item(user_id, current_item, 1)
                        await interaction.response.send_message(f"✅ **{current_item}** 장착을 해제했습니다.", ephemeral=True)
                    else:
                        await interaction.response.send_message("해제할 장비가 없어요.", ephemeral=True)
                else:

                    if not await db.remove_item(user_id, selected, 1):
                        return await interaction.response.send_message("아이템이 가방에서 사라졌어요!", ephemeral=True)

                    current_equipped = await self.view_ref.cog._get_equipped(user_id)
                    old_item = current_equipped.get(self.view_ref.target_slot)

                    if old_item:
                        await db.add_item(user_id, old_item, 1)

                    await self.view_ref.cog._update_equipped(user_id, self.view_ref.target_slot, selected)
                    await interaction.response.send_message(f"⚔️ **{selected}**을(를) 장착했습니다!", ephemeral=True)

                self.view_ref.mode = "main"
                await self.view_ref.update_message(interaction)

        class SlotSelect(discord.ui.Select):
            def __init__(self, view_ref):
                options = [
                    discord.SelectOption(label="머리 (Head)", value="head", emoji="🧢"),
                    discord.SelectOption(label="몸통 (Body)", value="body", emoji="👕"),
                    discord.SelectOption(label="다리 (Legs)", value="legs", emoji="👖"),
                    discord.SelectOption(label="발 (Feet)", value="feet", emoji="👞"),
                    discord.SelectOption(label="장신구 (Accessory)", value="accessory", emoji="💍"),
                ]
                super().__init__(placeholder="변경할 부위를 선택하세요", min_values=1, max_values=1, options=options)
                self.view_ref = view_ref

            async def callback(self, interaction: discord.Interaction):
                selected_slot = self.values[0]
                self.view_ref.target_slot = selected_slot
                self.view_ref.mode = "select_item"
                await self.view_ref.update_message(interaction)

        class EquipmentManagerView(discord.ui.View):
            def __init__(self, cog, user_id):
                super().__init__(timeout=180)
                self.cog = cog
                self.user_id = str(user_id)

                self.mode = "main"
                self.target_slot = None

            async def get_main_embed(self):
                equipped = await self.cog._get_equipped(self.user_id)
                stats = await self.cog.calculate_stats(self.user_id)

                embed = discord.Embed(title=f"🛡️ 장비 관리", color=discord.Color.blue())

                stats_text = f"⚔️ 공격력: **{stats['atk']}**\n🛡️ 방어력: **{stats['def']}**\n❤️ 추가 체력: **{stats['hp']}**"
                embed.add_field(name="전투 능력치", value=stats_text, inline=True)

                slots_kr = {"head": "머리", "body": "몸통", "legs": "다리", "feet": "발", "accessory": "장신구"}
                equip_text = ""

                sword_lv = await db.get_upgrade(self.user_id, "sword")
                sword_name = "기본 검"
                if sword_lv < len(self.cog.upgrades["sword"]):
                    sword_name = self.cog.upgrades["sword"][sword_lv]["name"]
                equip_text += f"**무기 (강화)**: {sword_name} (Lv.{sword_lv})\n"

                for slot in ["head", "body", "legs", "feet", "accessory"]:
                    name = equipped.get(slot) or "없음"
                    equip_text += f"**{slots_kr[slot]}**: {name}\n"

                embed.add_field(name="착용 상태", value=equip_text, inline=False)

                set_counts = {}
                for slot, name in equipped.items():
                    if name and name in self.cog.armor_items:
                        s = self.cog.armor_items[name].get("set")
                        if s: set_counts[s] = set_counts.get(s, 0) + 1

                sets_active = []
                for s, c in set_counts.items():
                    if s in self.cog.set_bonuses and c >= self.cog.set_bonuses[s]["parts"]:
                        sets_active.append(f"✨ {self.cog.set_bonuses[s]['name']}")

                if sets_active:
                    embed.add_field(name="활성화된 세트", value="\n".join(sets_active), inline=False)

                embed.set_footer(text="아래 버튼을 눌러 장비를 변경하세요.")
                return embed

            async def update_message(self, interaction: discord.Interaction):
                self.clear_items()

                if self.mode == "main":
                    btn = discord.ui.Button(label="장비 변경", style=discord.ButtonStyle.primary, emoji="⚙️")
                    async def change_callback(i: discord.Interaction):
                        if str(i.user.id) != self.user_id: return

                        self.clear_items()
                        self.add_item(SlotSelect(self))

                        back = discord.ui.Button(label="취소", style=discord.ButtonStyle.secondary)
                        async def back_cb(bi: discord.Interaction):
                            self.mode = "main"
                            await self.update_message(bi)
                        back.callback = back_cb
                        self.add_item(back)

                        await i.response.edit_message(embed=await self.get_main_embed(), view=self)

                    btn.callback = change_callback
                    self.add_item(btn)

                    embed = await self.get_main_embed()
                    if not interaction.response.is_done():
                        await interaction.response.edit_message(embed=embed, view=self)
                    else:
                        await interaction.edit_original_response(embed=embed, view=self)

                elif self.mode == "select_item":
                    items = await db.get_inventory(self.user_id)
                    valid_items = []
                    for i in items:
                        idata = self.cog.armor_items.get(i['item_name'])
                        if idata and idata.get('slot') == self.target_slot:
                            valid_items.append(i)

                    if not valid_items:
                        self.add_item(EquipmentSelect([], self.target_slot, self))
                    else:
                        self.add_item(EquipmentSelect(valid_items, self.target_slot, self))

                    back = discord.ui.Button(label="뒤로가기", style=discord.ButtonStyle.secondary)
                    async def back_cb_2(bi: discord.Interaction):
                        self.mode = "main"
                        await self.update_message(bi)
                    back.callback = back_cb_2
                    self.add_item(back)

                    embed = discord.Embed(title=f"🛡️ {self.target_slot.upper()} 장비 선택", description="장착할 아이템을 선택해주세요.", color=discord.Color.blue())
                    await interaction.response.edit_message(embed=embed, view=self)

        view = EquipmentManagerView(self, interaction.user.id)
        await interaction.response.send_message(embed=await view.get_main_embed(), view=view)

    @crime.error
    async def economy_cooldown_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            m, s = divmod(int(error.retry_after), 60)
            h, m = divmod(m, 60)
            time_str = f"{h}시간 " if h > 0 else ""
            time_str += f"{m}분 " if m > 0 else ""
            time_str += f"{s}초"
            await interaction.response.send_message(f"아직은 준비가 안 됐어요! **{time_str}** 뒤에 다시 시도해주세요. (✿◡‿◡)", ephemeral=True)

    @gamble.error
    async def gamble_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"주사위 다시 굴리려면 **{error.retry_after:.1f}초**만 기다려주세요!", ephemeral=True)

    @game_group.command(name="블랙잭", description="요미와 함께 블랙잭 게임을 합니다!")
    @app_commands.describe(bet="걸고 싶은 금액")
    @app_commands.rename(bet="금액")
    async def blackjack(self, interaction: discord.Interaction, bet: int):

        user_id = str(interaction.user.id)
        balance = await db.get_balance(user_id)

        if bet < 500:
            await interaction.response.send_message("최소 배팅 금액은 500 젤리입니다!", ephemeral=True)
            return

        if not await db.try_deduct_balance(user_id, bet):
            await interaction.response.send_message("돈이 부족해요! ( >﹏< )", ephemeral=True)
            return

        deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        random.shuffle(deck)

        user_hand = [deck.pop(), deck.pop()]
        yomi_hand = [deck.pop(), deck.pop()]

        def get_score(hand):
            score = sum(hand)
            if score > 21 and 11 in hand:
                hand[hand.index(11)] = 1
                return get_score(hand)
            return score

        class BlackjackView(discord.ui.View):
            def __init__(self, user_id, user_hand, yomi_hand, deck, bet, economy_cog):
                super().__init__(timeout=60)
                self.user_id = int(user_id)
                self.user_hand = user_hand
                self.yomi_hand = yomi_hand
                self.deck = deck
                self.bet = bet
                self.economy_cog = economy_cog
                self.game_finished = False

            def create_embed(self, hide_yomi=True):
                user_score = get_score(self.user_hand)
                yomi_score = get_score(self.yomi_hand) if not hide_yomi else "?"

                yomi_display = f"🃏 {' '.join(['[ ? ]' if hide_yomi and i > 0 else f'[{card}]' for i, card in enumerate(self.yomi_hand)])}"
                user_display = f"🃏 {' '.join([f'[{card}]' for card in self.user_hand])}"

                embed = discord.Embed(title="🃏 요미와 블랙잭!", color=discord.Color.blue())
                embed.add_field(name=f"🐱 요미의 패 ({yomi_score})", value=yomi_display, inline=False)
                embed.add_field(name=f"👤 교주님의 패 ({user_score})", value=user_display, inline=False)
                embed.set_footer(text=f"배팅액: {self.bet:,} 젤리 | 21을 넘지 않고 요미보다 높으면 승리!")
                return embed

            @discord.ui.button(label="히트 (Hit)", style=discord.ButtonStyle.primary)
            async def hit(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if btn_interaction.user.id != self.user_id:
                    await btn_interaction.response.send_message("본인의 게임만 조작할 수 있어요!", ephemeral=True)
                    return

                self.user_hand.append(self.deck.pop())
                score = get_score(self.user_hand)

                if score > 21:
                    self.game_finished = True
                    for child in self.children: child.disabled = True
                    embed = self.create_embed(hide_yomi=False)
                    embed.description = "💥 **버스트!** 21을 넘었습니다. 패배하셨어요... ( Ĭ ^ Ĭ )"
                    embed.color = discord.Color.red()
                    await db.update_game_stats(str(self.user_id), 0, False)
                    await btn_interaction.response.edit_message(embed=embed, view=self)
                else:
                    await btn_interaction.response.edit_message(embed=self.create_embed())

            @discord.ui.button(label="스테이 (Stay)", style=discord.ButtonStyle.success)
            async def stay(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if btn_interaction.user.id != self.user_id:
                    await btn_interaction.response.send_message("본인의 게임만 조작할 수 있어요!", ephemeral=True)
                    return

                self.game_finished = True
                for child in self.children: child.disabled = True

                user_score = get_score(self.user_hand)
                while get_score(self.yomi_hand) < 17:
                    self.yomi_hand.append(self.deck.pop())

                yomi_score = get_score(self.yomi_hand)

                embed = self.create_embed(hide_yomi=False)
                if yomi_score > 21:
                    winnings = self.bet * 2
                    await db.update_balance(str(self.user_id), winnings)
                    await db.update_game_stats(str(self.user_id), winnings, True)
                    embed.description = f"🎉 **요미 버스트!** 교주님이 승리하셨습니다! **{winnings:,}** 젤리 획득!"
                    embed.color = discord.Color.gold()
                elif user_score > yomi_score:
                    winnings = self.bet * 2
                    await db.update_balance(str(self.user_id), winnings)
                    await db.update_game_stats(str(self.user_id), winnings, True)
                    embed.description = f"🎉 **승리!** 교주님의 패가 더 높습니다! **{winnings:,}** 젤리 획득!"
                    embed.color = discord.Color.gold()
                elif user_score < yomi_score:
                    await db.update_game_stats(str(self.user_id), 0, False)
                    embed.description = "😭 **패배...** 요미의 패가 더 높네요. 다음엔 이길 수 있을 거예요!"
                    embed.color = discord.Color.red()
                else:
                    await db.update_balance(str(self.user_id), self.bet)
                    embed.description = "🤝 **무승부!** 배팅한 금액을 그대로 돌려드립니다."
                    embed.color = discord.Color.light_gray()

                await btn_interaction.response.edit_message(embed=embed, view=self)

        view = BlackjackView(user_id, user_hand, yomi_hand, deck, bet, self)
        await interaction.response.send_message(embed=view.create_embed(), view=view)

    @game_group.command(name="경마", description="요미들의 달리기 시합! 우승할 요미에게 배팅하세요!")
    @app_commands.describe(bet="걸고 싶은 금액", target="배팅할 요미 번호")
    @app_commands.rename(bet="금액", target="요미번호")
    @app_commands.choices(target=[
        app_commands.Choice(name="1번 빨강 딸기요미", value=1),
        app_commands.Choice(name="2번 파랑 바다요미", value=2),
        app_commands.Choice(name="3번 초록 풀잎요미", value=3),
        app_commands.Choice(name="4번 노랑 바나나요미", value=4),
        app_commands.Choice(name="5번 보라 포도요미", value=5)
    ])
    async def racing(self, interaction: discord.Interaction, bet: int, target: int):

        user_id = str(interaction.user.id)
        balance = await db.get_balance(user_id)

        if bet < 500:
            await interaction.response.send_message("최소 배팅 금액은 500 젤리입니다!", ephemeral=True)
            return
        if not (1 <= target <= 5):
            await interaction.response.send_message("1번부터 5번 사이의 요미를 선택해주세요! (1: 빨강, 2: 파랑, 3: 초록, 4: 노랑, 5: 보라)", ephemeral=True)
            return
        if balance < bet:
            await interaction.response.send_message("돈이 부족해요! (T_T)", ephemeral=True)
            return

        await db.update_balance(user_id, -bet)
        await interaction.response.send_message(f"🏇 **{target}번 요미**에게 **{bet:,}** 젤리를 배팅하셨습니다! 경주가 곧 시작됩니다!")

        runners = [
            {"id": 1, "emoji": "🔴", "pos": 0, "name": "딸기요미"},
            {"id": 2, "emoji": "🔵", "pos": 0, "name": "바다요미"},
            {"id": 3, "emoji": "🟢", "pos": 0, "name": "풀잎요미"},
            {"id": 4, "emoji": "🟡", "pos": 0, "name": "바나나요미"},
            {"id": 5, "emoji": "🟣", "pos": 0, "name": "포도요미"}
        ]

        track_length = 15
        finishers = []

        message = await interaction.followup.send("🏁 **경주 준비... 출발!**")

        for _ in range(20):

            pass


        target_wins = random.random() < 0.5
        winner_id = target if target_wins else random.choice([r["id"] for r in runners if r["id"] != target])

        for _ in range(20):
            for runner in runners:
                if runner["pos"] < track_length:
                    move = random.randint(1, 3)
                    if runner["id"] == winner_id:
                        move += 1
                    runner["pos"] += move

            pass

        winner_determined = False

        for r in runners: r["pos"] = 0
        finishers = []

        is_player_lucky = random.random() < 0.5

        for _ in range(20):
            for runner in runners:
                if runner["pos"] < track_length:
                    move = random.randint(1, 3)

                    if is_player_lucky and runner["id"] == target:
                        move += 2
                    elif not is_player_lucky and runner["id"] != target:
                        if runner["id"] == (target % 5) + 1:
                            move += 2

                    runner["pos"] += move
                    if runner["pos"] >= track_length:
                        runner["pos"] = track_length
                        if runner["id"] not in [r["id"] for r in finishers]:
                            finishers.append(runner)

            lines = []
            for r in runners:
                track = ["="] * track_length
                if r["pos"] < track_length:
                    track[r["pos"]] = r["emoji"]
                else:
                    track[track_length-1] = "🏁"
                lines.append(f"{r['id']}. {''.join(track)} {r['emoji'] if r['pos'] < track_length else ''}")

            embed = discord.Embed(title="🏇 요미 레이스 중!", description="\n".join(lines), color=discord.Color.blue())
            await message.edit(content=None, embed=embed)

            if len(finishers) >= 1:
                break
            await asyncio.sleep(1.2)

        winner = finishers[0]
        is_win = winner["id"] == target

        result_embed = discord.Embed(title="🏆 시합 종료!", color=discord.Color.gold() if is_win else discord.Color.red())
        result_embed.description = f"금메달은 **{winner['id']}번 {winner['name']}**!! 🥇\n\n"

        if is_win:
            winnings = bet * 2
            await db.update_balance(user_id, winnings)
            await db.update_game_stats(user_id, winnings, True)
            result_embed.description += f"🎉 **축하합니다!** 교주님이 선택한 요미가 1등을 했어요!\n**{winnings:,}** 젤리를 획득하셨습니다!"
        else:
            await db.update_game_stats(user_id, 0, False)
            result_embed.description += f"😭 아쉽네요... 다음 시합을 노려보세요!"

        await message.edit(embed=result_embed)

    @game_group.command(name="도전", description="매일 한 번 운을 시험합니다. 큰 보상을 얻을 수도 있지만 돈을 잃을 수도 있어요!")
    @app_commands.checks.cooldown(1, 86400, key=lambda i: (i.guild_id, i.user.id))
    async def daily_gamble(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        outcomes = [
            ("대박 상자", 0.5, 200000, "상자 안에서 엄청난 양의 젤리가 쏟아져 나옵니다!"),
            ("평범한 상자", 15.0, 10000, "적당한 용돈을 얻었습니다."),
            ("텅 빈 상자", 60.0, 0, "상자가 비어있네요..."),
            ("함정 상자", 20.0, -20000, "상자를 열자마자 젤리를 도둑맞았습니다!"),
            ("잭팟!!", 0.1, 1000000, "전설의 잭팟!! 요미가 방방 뜁니다! ✨")
        ]

        weights = [o[1] for o in outcomes]
        outcome = random.choices(outcomes, weights=weights, k=1)[0]
        name, _, amount, desc = outcome

        await db.update_balance(user_id, amount)

        color = discord.Color.gold() if amount > 50000 else (discord.Color.red() if amount < 0 else discord.Color.light_gray())
        embed = discord.Embed(title=f"🎁 오늘의 도전 결과: {name}", description=desc, color=color)
        embed.add_field(name="결과", value=f"**{amount:,}** 젤리" if amount != 0 else "없음")
        embed.set_footer(text="내일 다시 도전할 수 있어요!")

        await interaction.response.send_message(embed=embed)

    @daily_gamble.error
    async def daily_gamble_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            h = int(error.retry_after // 3600)
            m = int((error.retry_after % 3600) // 60)
            await interaction.response.send_message(f"오늘의 운세는 이미 확인하셨어요! **{h}시간 {m}분** 뒤에 다시 오세요! (✿◡‿◡)", ephemeral=True)

    @game_group.command(name="초성퀴즈", description="제시된 초성을 보고 단어를 맞혀보세요! (30초 제한)")
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.guild_id)
    async def initial_quiz(self, interaction: discord.Interaction):

        if interaction.channel_id in self.active_quiz_channels:
            return await interaction.response.send_message("이미 이 채널에서 퀴즈가 진행 중입니다!", ephemeral=True)

        self.active_quiz_channels.add(interaction.channel_id)

        try:
            category = random.choice(list(quiz_data.QUIZ_DATA.keys()))
            word = random.choice(quiz_data.QUIZ_DATA[category])
            initials = hangul.get_initials(word)

            reward = random.randint(500, 1500)

            embed = discord.Embed(title="🧩 초성 퀴즈!", description=f"주제: **{category}**", color=discord.Color.blue())
            embed.add_field(name="문제", value=f"## **{initials}**", inline=False)
            embed.add_field(name="보상", value=f"🍬 **{reward}** 젤리", inline=False)
            embed.set_footer(text="정답을 채팅으로 입력하세요! (제한시간 30초)")

            await interaction.response.send_message(embed=embed)

            def check(m):
                return m.channel.id == interaction.channel.id and not m.author.bot and m.content.strip() == word

            try:
                msg = await self.bot.wait_for('message', check=check, timeout=30.0)

                await db.update_balance(str(msg.author.id), reward)
                await db.update_game_stats(str(msg.author.id), reward, True)

                success_embed = discord.Embed(title="🎉 정답입니다!", description=f"정답은 **{word}** 였습니다!", color=discord.Color.green())
                success_embed.add_field(name="우승자", value=f"{msg.author.mention}", inline=True)
                success_embed.add_field(name="획득 보상", value=f"🍬 **{reward:,}** 젤리", inline=True)

                await interaction.followup.send(embed=success_embed)

            except asyncio.TimeoutError:
                fail_embed = discord.Embed(title="⏰ 시간 초과!", description=f"아무도 정답을 맞히지 못했습니다.\n정답은 **{word}** 였습니다.", color=discord.Color.red())
                await interaction.followup.send(embed=fail_embed)

        except Exception as e:
            print(f"Quiz Error: {e}")
            await interaction.followup.send("퀴즈 진행 중 오류가 발생했습니다.", ephemeral=True)
        finally:
            self.active_quiz_channels.remove(interaction.channel_id)

    @initial_quiz.error
    async def initial_quiz_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            s = int(error.retry_after)
            await interaction.response.send_message(f"잠시만 기다려주세요! **{s}초** 뒤에 다시 시작할 수 있어요.", ephemeral=True)

    @activity_group.command(name="벌목", description="숲에서 나무를 베어 목재와 젤리를 획득합니다. (5분 쿨타임)")
    async def woodcutting(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        benefits = booster_utils.get_booster_benefits(interaction.user)
        cooldown_time = 300 * benefits["cooldown_mult"]

        cooldown = await db.check_cooldown(user_id, "woodcutting", cooldown_time)
        if cooldown > 0:
            m = int(cooldown // 60)
            s = int(cooldown % 60)
            return await interaction.response.send_message(f"헉... 팔이 너무 아파요... **{m}분 {s}초**만 쉬었다가 해요... ( 🌲-_-)", ephemeral=True)

        await db.update_cooldown(user_id, "woodcutting")

        multiplier, chance_bonus, phase = await self.get_affinity_bonus(user_id)

        woods = ["참나무", "자작나무", "단풍나무", "소나무", "고목", "흑단나무", "세계수 가지", "황금 사과"]

        axe_level = await db.get_upgrade(user_id, "axe")

        if axe_level == 0:
            weights = [50, 30, 15, 4, 0.9, 0.09, 0.01, 0]
        elif axe_level == 1: weights = [40, 30, 20, 8, 1.8, 0.18, 0.02, 0]
        elif axe_level == 2: weights = [30, 25, 25, 15, 4, 0.8, 0.2, 0.05]
        elif axe_level == 3: weights = [20, 20, 30, 20, 8, 2, 0.5, 0.1]
        elif axe_level == 4: weights = [10, 15, 25, 30, 15, 4, 1, 0.5]
        else:
            weights = [5, 10, 20, 30, 25, 8, 3, 1]

        if chance_bonus > 0:
            boost = chance_bonus * 0.1
            weights[0] = max(0, weights[0] - boost)
            weights[4] += boost * 0.5
            weights[5] += boost * 0.3

        got_wood_name = random.choices(woods, weights=weights, k=1)[0]

        item_info = self.collectible_items.get(got_wood_name, {"price": 0, "desc": "알 수 없는 목재"})
        base_price = item_info["price"]

        market_price, trend_arrow = await db.get_current_market_price(got_wood_name, base_price)

        jelly_reward = int(random.randint(10, 50) * multiplier)

        await db.add_item(user_id, got_wood_name, 1)
        await db.update_balance(user_id, jelly_reward)
        await db.update_cooldown(user_id, "woodcutting")
        await db.update_game_stats(user_id, jelly_reward, True)

        color = discord.Color.green()
        special_msg = ""
        if base_price >= 10000:
            special_msg = "✨ **신비한 기운이 느껴져요! 대박!**"
            color = discord.Color.gold()

        embed = discord.Embed(title="🪓 숲속의 벌목장", description="**벌목에 성공했어요!**", color=color)
        embed.add_field(name="획득 목재", value=f"🪵 **{got_wood_name}**", inline=False)
        embed.add_field(name="시장 가치", value=f"**{market_price:,}** 젤리 {trend_arrow}", inline=True)
        embed.add_field(name="벌목 보상", value=f"**{jelly_reward:,}** 젤리", inline=True)

        if special_msg:
             embed.add_field(name="✨ 보너스", value=special_msg, inline=False)

        if ing_drop:
            embed.add_field(name="🍳 추가 재료", value=ing_drop.strip(), inline=False)

        embed.set_footer(text=f"도끼 레벨: {axe_level} | 시세는 실시간으로 변동됩니다.")
        await interaction.response.send_message(embed=embed)

    @activity_group.command(name="아르바이트", description="아르바이트를 하여 숙련도를 쌓고 돈을 법니다. (10분 쿨타임)")
    async def part_time_job(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        benefits = booster_utils.get_booster_benefits(interaction.user)
        cooldown_time = 600 * benefits["cooldown_mult"]

        cooldown = await db.check_cooldown(user_id, "part_time_job", cooldown_time)
        if cooldown > 0:
            m = int(cooldown // 60)
            s = int(cooldown % 60)
            return await interaction.response.send_message(f"아직은 준비가 안 됐어요! **{m}분 {s}초** 뒤에 다시 시도해주세요. (✿◡‿◡)", ephemeral=True)

        jobs_data = {
            "convenience": {"name": "편의점", "emoji": "🏪", "desc": "물건의 순서를 기억해서 계산해주세요!", "type": "memory", "tasks": ["🍎", "🍇", "🍞", "🥛", "☕"]},
            "bakery": {"name": "요미네 빵집", "emoji": "🥖", "desc": "빵 포장 순서를 헷갈리면 안 돼요!", "type": "memory", "tasks": ["🥯", "🥐", "🥨", "🧁", "🍩"]},
            "cafe": {"name": "별빛 카페", "emoji": "☕", "desc": "주문 금액을 정확하게 계산해주세요!", "type": "math"},
            "logistics": {"name": "물류 창고", "emoji": "📦", "desc": "상자의 종류를 잘 보고 분류해주세요!", "type": "memory", "tasks": ["📦", "📁", "🗄️", "🧹", "🗑️"]}
        }

        class JobSelect(discord.ui.Select):
            def __init__(self):
                options = []
                for key, data in jobs_data.items():
                    options.append(discord.SelectOption(label=data["name"], value=key, emoji=data["emoji"], description=data["desc"]))
                super().__init__(placeholder="아르바이트를 선택해주세요!", min_values=1, max_values=1)

            async def callback(self, select_interaction: discord.Interaction):
                if select_interaction.user.id != int(user_id):
                    return await select_interaction.response.send_message("자신의 알바만 선택할 수 있어요!", ephemeral=True)

                selected_job_key = self.values[0]
                job_info = jobs_data[selected_job_key]

                await start_job(select_interaction, selected_job_key, job_info)

        view = discord.ui.View()
        view.add_item(JobSelect())

        await interaction.response.send_message("어떤 일을 하시겠어요? (직업별로 숙련도가 쌓여요!)", view=view, ephemeral=True)

        async def start_job(intr, job_key, job_info):
            await db.update_cooldown(user_id, "part_time_job")

            db_job = await db.get_job_info(user_id, job_info["name"])
            level = db_job["level"]

            if job_info["type"] == "memory":
                tasks = job_info["tasks"]
                count = min(3 + (level // 5), 5)
                target_sequence = random.sample(tasks, count) if count <= len(tasks) else random.choices(tasks, k=count)

                job_view = MemoryJobView(user_id, target_sequence, job_info["name"], self, level)
                await intr.response.edit_message(content=None, embed=job_view.create_embed(), view=job_view)

            elif job_info["type"] == "math":
                a = random.randint(10, 50 * level)
                b = random.randint(10, 50 * level)
                ans = a + b
                problem = f"{a} + {b} = ?"

                options = [ans, ans + random.randint(1, 10), ans - random.randint(1, 10), ans + 10]
                random.shuffle(options)

                job_view = MathJobView(user_id, problem, ans, options, job_info["name"], self, level)
                await intr.response.edit_message(content=None, embed=job_view.create_embed(), view=job_view)


        class MemoryJobView(discord.ui.View):
            def __init__(self, user_id, target_sequence, job_name, economy_cog, level):
                super().__init__(timeout=30)
                self.user_id = int(user_id)
                self.target_sequence = target_sequence
                self.current_idx = 0
                self.job_name = job_name
                self.economy_cog = economy_cog
                self.level = level

                if "편의점" in job_name:
                    possible_tasks = jobs_data["convenience"]["tasks"]
                elif "빵집" in job_name:
                    possible_tasks = jobs_data["bakery"]["tasks"]
                else:
                    possible_tasks = jobs_data["logistics"]["tasks"]

                btn_tasks = list(possible_tasks)
                random.shuffle(btn_tasks)

                for task in btn_tasks:
                    btn = discord.ui.Button(label=task, style=discord.ButtonStyle.secondary, custom_id=task)
                    btn.callback = self.check_task
                    self.add_item(btn)

            def create_embed(self):
                seq_display = " ".join([f"**[{t}]**" if i < self.current_idx else t for i, t in enumerate(self.target_sequence)])
                embed = discord.Embed(title=f"Lv.{self.level} {self.job_name} 업무 중...", description=f"주어진 순서대로 버튼을 눌러주세요!\n\n순서: {seq_display}", color=discord.Color.blue())
                return embed

            async def check_task(self, btn_interaction: discord.Interaction):
                if btn_interaction.user.id != self.user_id:
                    return await btn_interaction.response.send_message("본인의 업무만 수행할 수 있어요!", ephemeral=True)

                selected = btn_interaction.data["custom_id"]
                if selected == self.target_sequence[self.current_idx]:
                    self.current_idx += 1
                    if self.current_idx == len(self.target_sequence):
                        await self.finish_job(btn_interaction, True)
                    else:
                        await btn_interaction.response.edit_message(embed=self.create_embed())
                else:
                    await self.finish_job(btn_interaction, False)

            async def finish_job(self, interaction, success):
                for child in self.children: child.disabled = True

                if success:
                    base_reward = random.randint(5000, 10000)

                    level_bonus = self.level * 1000
                    reward = base_reward + level_bonus

                    multiplier, _, _ = await self.economy_cog.get_affinity_bonus(str(self.user_id))
                    final_reward = int(reward * multiplier)

                    new_level, is_levelup = await db.update_job_xp(str(self.user_id), self.job_name, 10)
                    await db.update_balance(str(self.user_id), final_reward)

                    msg = f"완벽하게 처리하셨네요!\n\n💰 보상: **{final_reward:,}** 젤리 (Lv.{self.level} 보너스 +{level_bonus})"
                    if is_levelup:
                        msg += f"\n🆙 **축하합니다! {self.job_name} 레벨이 {new_level}(으)로 올랐습니다!**"

                    embed = discord.Embed(title=f"✅ {self.job_name} 완료!", description=msg, color=discord.Color.green())
                    await interaction.response.edit_message(embed=embed, view=self)
                else:
                    embed = discord.Embed(title=f"❌ {self.job_name} 실패", description="실수를 하는 바람에 사장님께 혼났어요... 보상이 없습니다.", color=discord.Color.red())
                    await interaction.response.edit_message(embed=embed, view=self)
                self.stop()

        class MathJobView(discord.ui.View):
            def __init__(self, user_id, problem, answer, options, job_name, economy_cog, level):
                super().__init__(timeout=30)
                self.user_id = int(user_id)
                self.answer = answer
                self.job_name = job_name
                self.economy_cog = economy_cog
                self.level = level
                self.problem = problem

                for opt in options:
                    btn = discord.ui.Button(label=str(opt), style=discord.ButtonStyle.primary, custom_id=str(opt))
                    btn.callback = self.check_answer
                    self.add_item(btn)

            def create_embed(self):
                embed = discord.Embed(title=f"Lv.{self.level} {self.job_name} 업무 중...", description=f"다음 계산을 수행하세요!\n\n# {self.problem}", color=discord.Color.gold())
                return embed

            async def check_answer(self, btn_interaction: discord.Interaction):
                if btn_interaction.user.id != self.user_id:
                    return await btn_interaction.response.send_message("본인의 업무만 수행할 수 있어요!", ephemeral=True)

                selected = int(btn_interaction.data["custom_id"])

                for child in self.children: child.disabled = True

                if selected == self.answer:
                    base_reward = random.randint(6000, 12000)
                    level_bonus = self.level * 1200
                    reward = base_reward + level_bonus

                    multiplier, _, _ = await self.economy_cog.get_affinity_bonus(str(self.user_id))
                    final_reward = int(reward * multiplier)

                    new_level, is_levelup = await db.update_job_xp(str(self.user_id), self.job_name, 15)
                    await db.update_balance(str(self.user_id), final_reward)

                    msg = f"정확하게 계산하셨네요!\n\n💰 보상: **{final_reward:,}** 젤리 (Lv.{self.level} 보너스 +{level_bonus})"
                    if is_levelup:
                        msg += f"\n🆙 **축하합니다! {self.job_name} 레벨이 {new_level}(으)로 올랐습니다!**"

                    embed = discord.Embed(title=f"✅ {self.job_name} 완료!", description=msg, color=discord.Color.green())
                    await btn_interaction.response.edit_message(embed=embed, view=self)
                else:
                    embed = discord.Embed(title=f"❌ {self.job_name} 실패", description=f"틀렸습니다... 정답은 {self.answer}였어요.", color=discord.Color.red())
                    await btn_interaction.response.edit_message(embed=embed, view=self)
                self.stop()

    @activity_group.command(name="탐색", description="다양한 장소를 탐색하여 아이템이나 젤리를 얻습니다. (10분 쿨타임)")
    async def scavenge(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)

        benefits = booster_utils.get_booster_benefits(interaction.user)
        cooldown_time = 600 * benefits["cooldown_mult"]

        cooldown = await db.check_cooldown(user_id, "scavenge", cooldown_time)
        if cooldown > 0:
            m = int(cooldown // 60)
            s = int(cooldown % 60)
            return await interaction.response.send_message(f"아직은 준비가 안 됐어요! **{m}분 {s}초** 뒤에 다시 시도해주세요. (✿◡‿◡)", ephemeral=True)

        await db.update_cooldown(user_id, "scavenge")

        locs = [
            ("🏙️ 도시 골목", 1000, 5000, "누군가 흘린 동전을 주웠습니다!"),
            ("🏖️ 한적한 해변", 3000, 8000, "모래사장에서 반짝이는 조개를 발견했어요."),
            ("🏕️ 버려진 캠핑장", 5000, 12000, "텐트 안에서 젤리 봉지를 찾았습니다."),
            ("🏛️ 오래된 박물관", 8000, 20000, "관리인이 수고했다며 팁을 주었습니다."),
            ("🌌 달빛 공원", 20000, 50000, "달빛 아래서 은은하게 빛나는 보석을 주웠습니다!")
        ]

        name, min_p, max_p, msg = random.choice(locs)
        reward = random.randint(min_p, max_p)
        await db.update_balance(user_id, reward)

        ing_drop = ""
        possible_ings = ["밀가루", "설탕", "식초", "크림", "레몬", "초콜릿", "물", "우유", "솜뭉치"]
        if random.random() < 0.5:
            found_ing = random.choice(possible_ings)
            await db.add_item(user_id, found_ing, 1)
            ing_drop += f"\n🥡 **{found_ing}**을(를) 찾았습니다!"

        embed = discord.Embed(title=f"🔎 {name} 탐색 결과", description=f"{msg}\n보상: **{reward:,}** 젤리", color=discord.Color.teal())
        if ing_drop:
            embed.add_field(name="🍳 추가 재료", value=ing_drop.strip(), inline=False)

        await interaction.response.send_message(embed=embed)

    @crime.error
    async def gather_cooldown_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            m, s = divmod(int(error.retry_after), 60)
            await interaction.response.send_message(f"아직은 준비가 안 됐어요! **{m}분 {s}초** 뒤에 다시 시도해주세요. (✿◡‿◡)", ephemeral=True)


    @stock_group.command(name="주식", description="요미 증권 시장 현황을 확인합니다.")
    async def stock(self, interaction: discord.Interaction):

        await interaction.response.defer()

        stocks = await db.get_all_stocks()
        if not stocks:
            await db.init_stock_market(self.default_stocks)
            stocks = await db.get_all_stocks()

        embed = discord.Embed(title="📈 요미 증권 시장", color=discord.Color.blue())
        embed.description = "30분마다 주가가 변동됩니다! (투자는 본인의 책임...)"

        for stock in stocks:
            change = stock['price'] - stock['previous_price']
            change_pct = (change / stock['previous_price']) * 100 if stock['previous_price'] > 0 else 0

            emoji = "🔺" if change > 0 else "🔻" if change < 0 else "➖"
            color_code = "+ " if change > 0 else "- " if change < 0 else ""

            embed.add_field(
                name=f"{emoji} {stock['name']} ({stock['stock_id']})",
                value=f"```diff\n{color_code}{stock['price']:,} 젤리 ({change_pct:+.2f}%)\n```",
                inline=True
            )

        embed.set_footer(text="명령어: /매수 [종목코드] [개수], /매도 [종목코드] [개수]")
        await interaction.followup.send(embed=embed)

    @stock_group.command(name="매수", description="주식을 구매합니다.")
    @app_commands.describe(stock_id="종목 코드 (예: YOMI)", amount="구매할 주식 수")
    async def buy_stock(self, interaction: discord.Interaction, stock_id: str, amount: int):

        if amount <= 0:
            return await interaction.response.send_message("1주 이상 구매해야 해요!", ephemeral=True)

        stock = await db.get_stock(stock_id.upper())
        if not stock:
            return await interaction.response.send_message("그런 종목은 없어요! `/주식` 명령어로 확인해보세요.", ephemeral=True)

        success, msg = await db.trade_stock(str(interaction.user.id), stock_id.upper(), amount, stock['price'], True)

        if success:
            await interaction.response.send_message(f"📈 **{stock['name']}** {amount}주 매수 완료! (총 {amount * stock['price']:,} 젤리)")
        else:
            await interaction.response.send_message(f"매수 실패: {msg}", ephemeral=True)

    @stock_group.command(name="매도", description="주식을 판매합니다.")
    @app_commands.describe(stock_id="종목 코드 (예: YOMI)", amount="판매할 주식 수")
    async def sell_stock(self, interaction: discord.Interaction, stock_id: str, amount: int):

        if amount <= 0:
            return await interaction.response.send_message("1주 이상 판매해야 해요!", ephemeral=True)

        stock = await db.get_stock(stock_id.upper())
        if not stock:
            return await interaction.response.send_message("그런 종목은 없어요!", ephemeral=True)

        success, msg = await db.trade_stock(str(interaction.user.id), stock_id.upper(), amount, stock['price'], False)

        if success:
            await interaction.response.send_message(f"📉 **{stock['name']}** {amount}주 매도 완료! (총 {amount * stock['price']:,} 젤리 획득)")
        else:
            await interaction.response.send_message(f"매도 실패: {msg}", ephemeral=True)

    @stock_group.command(name="내주식", description="보유 중인 주식 현황을 확인합니다.")
    async def mystocks(self, interaction: discord.Interaction):

        user_stocks = await db.get_user_stocks(str(interaction.user.id))
        if not user_stocks:
            return await interaction.response.send_message("보유 중인 주식이 없어요! `/주식` 시장에서 투자해보세요.", ephemeral=True)

        embed = discord.Embed(title="💼 나의 주식 포트폴리오", color=discord.Color.gold())
        total_value = 0
        total_profit = 0

        for s_id, data in user_stocks.items():
            stock_info = await db.get_stock(s_id)
            if not stock_info: continue

            current_price = stock_info['price']
            avg_price = data['average_price']
            amount = data['amount']

            current_val = current_price * amount
            profit = current_val - (avg_price * amount)
            profit_pct = (profit / (avg_price * amount)) * 100

            total_value += current_val
            total_profit += profit

            emoji = "🔴" if profit > 0 else "🔵" if profit < 0 else "⚪"

            embed.add_field(
                name=f"{stock_info['name']} ({amount}주)",
                value=f"평단가: {int(avg_price):,} | 현재가: {current_price:,}\n수익: {emoji} {int(profit):,} ({profit_pct:+.1f}%)",
                inline=False
            )

        embed.description = f"총 평가 자산: **{total_value:,}** 젤리\n총 수익: **{int(total_profit):,}** 젤리"
        await interaction.response.send_message(embed=embed)


    @stock_group.command(name="타이쿤", description="나의 가게들을 관리합니다.")
    async def tycoon(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)
        user_buildings = await db.get_tycoon_buildings(user_id)

        embed = discord.Embed(title="🏗️ 나만의 가게 관리", description="건물을 짓고 수익을 얻어보세요!", color=discord.Color.green())

        total_income_per_hour = 0

        if not user_buildings:
            embed.description += "\n\n아직 보유한 건물이 없어요! `/건설` 명령어로 시작해보세요."
        else:
            now = time.time()
            for b_type, data in user_buildings.items():
                if b_type not in self.tycoon_buildings: continue

                info = self.tycoon_buildings[b_type]
                level = data['level']
                income = int(info['base_income'] * (info['income_mult'] ** (level - 1)))
                interval = info['interval']
                last_coll = data['last_collection']

                elapsed = now - last_coll

                max_acc_time = interval * 24
                elapsed = min(elapsed, max_acc_time)

                income_per_sec = income / interval
                current_money = int(income_per_sec * elapsed)

                hourly_income = int(income * (3600 / interval))
                total_income_per_hour += hourly_income

                status = "🟢 수금 가능" if current_money > 0 else "⚪ 준비 중"

                embed.add_field(
                    name=f"{info['name']} (Lv.{level})",
                    value=f"수익: {hourly_income:,}/시간\n쌓인 돈: **{current_money:,}** 젤리\n상태: {status}",
                    inline=False
                )

        embed.set_footer(text=f"총 시간당 수익: {total_income_per_hour:,} 젤리 | 명령어: /수금, /건설")
        await interaction.response.send_message(embed=embed)

    @stock_group.command(name="건설", description="건물을 짓거나 업그레이드합니다.")
    @app_commands.describe(building_type="건물 종류")
    @app_commands.choices(building_type=[
        app_commands.Choice(name="🥕 유기농 농장 (기본)", value="farm"),
        app_commands.Choice(name="🍞 갓 구운 빵집", value="bakery"),
        app_commands.Choice(name="🏭 젤리 가공 공장", value="factory"),
        app_commands.Choice(name="🏦 요미 은행", value="bank"),
    ])
    async def build(self, interaction: discord.Interaction, building_type: str):

        user_id = str(interaction.user.id)
        if building_type not in self.tycoon_buildings:
            return await interaction.response.send_message("존재하지 않는 건물이에요!", ephemeral=True)

        info = self.tycoon_buildings[building_type]
        user_buildings = await db.get_tycoon_buildings(user_id)

        current_level = 0
        if building_type in user_buildings:
            current_level = user_buildings[building_type]['level']

        cost = int(info['base_cost'] * (info['upgrade_mult'] ** current_level))

        embed = discord.Embed(title=f"🏗️ {info['name']} 건설/업그레이드", color=discord.Color.blue())
        embed.description = f"현재 레벨: Lv.{current_level} -> Lv.{current_level + 1}\n비용: **{cost:,}** 젤리"
        embed.set_footer(text="건설하시겠습니까?")

        view = ConfirmBuildView(user_id, building_type, cost)
        await interaction.response.send_message(embed=embed, view=view)

    @stock_group.command(name="수금", description="모든 가게에서 수익을 거둡니다.")
    async def collect_tycoon(self, interaction: discord.Interaction):

        user_id = str(interaction.user.id)
        user_buildings = await db.get_tycoon_buildings(user_id)

        if not user_buildings:
            return await interaction.response.send_message("수금할 건물이 없어요!", ephemeral=True)

        total_collected = 0
        now = time.time()

        for b_type, data in user_buildings.items():
            if b_type not in self.tycoon_buildings: continue

            info = self.tycoon_buildings[b_type]
            level = data['level']
            income = int(info['base_income'] * (info['income_mult'] ** (level - 1)))
            interval = info['interval']
            last_coll = data['last_collection']

            elapsed = now - last_coll
            max_acc_time = interval * 24
            elapsed = min(elapsed, max_acc_time)

            income_per_sec = income / interval
            amount = int(income_per_sec * elapsed)

            if amount > 0:
                total_collected += amount
                await db.update_tycoon_building(user_id, b_type, level, now)

        if total_collected > 0:
            await db.update_balance(user_id, total_collected)
            await interaction.response.send_message(f"💰 모든 가게를 돌며 **{total_collected:,}** 젤리를 수금했습니다! 부자 되세요!", ephemeral=False)
        else:
            await interaction.response.send_message("아직 수익이 쌓이지 않았어요... 조금 더 기다려주세요!", ephemeral=True)

    @activity_group.command(name="정원", description="나만의 정원을 가꾸고 관리합니다.")
    @app_commands.describe(user="정원을 구경할 교주님 (비워두면 내 정원)")
    @app_commands.rename(user="교주")
    async def garden(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer()
        target_user = user or interaction.user
        user_id = str(target_user.id)

        items = await db.get_garden_items(user_id)

        grid = [["⬜" for _ in range(3)] for _ in range(3)]

        embed = discord.Embed(
            title=f"🌙 {target_user.display_name}님의 달빛 정원",
            description="가구를 배치하여 정원을 아름답게 꾸며보세요!\n아래 버튼을 눌러 정원을 관리할 수 있습니다.",
            color=discord.Color.green()
        )

        if not items:
            embed.description += "\n\n🏚️ *아직 정원이 텅 비어있네요...*"
        else:
            for item in items:
                pos = item['position'] - 1
                if 0 <= pos < 9:
                    row = pos // 3
                    col = pos % 3

                    emoji = "📦"
                    name = item['item_id']
                    if "의자" in name: emoji = "🪑"
                    elif "책상" in name or "테이블" in name: emoji = "桌"
                    elif "침대" in name: emoji = "🛏️"
                    elif "화분" in name or "꽃" in name: emoji = "🪴"
                    elif "조명" in name or "램프" in name: emoji = "💡"
                    elif "인형" in name: emoji = "🧸"
                    elif "카펫" in name: emoji = "🧶"

                    grid[row][col] = emoji

        grid_str = ""
        for row in grid:
            grid_str += " ".join(row) + "\n"

        embed.add_field(name="🏡 배치도", value=f"```\n{grid_str}\n```", inline=False)

        list_str = []
        if items:
            for item in items:
                list_str.append(f"{item['position']}번: {item['item_id']}")
            embed.add_field(name="📋 배치 목록", value="\n".join(list_str), inline=False)

        view = ConsolidatedGardenView(user_id, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    @activity_group.command(name="레시피", description="요미의 요리책을 펼쳐 보유한 재료와 만들 수 있는 요리를 확인합니다.")
    @app_commands.describe(search="검색할 레시피 이름 (선택)")
    @app_commands.rename(search="검색")
    async def recipe_book(self, interaction: discord.Interaction, search: str = None):
        user_inv = await db.get_inventory(str(interaction.user.id))
        inv_dict = {item['item_name']: item['amount'] for item in user_inv}

        embed = discord.Embed(title="🍳 요미의 비밀 레시피 북", description="맛있는 요리를 만들어보세요! 재료를 모아오면 요미가 만들어드릴게요! (≧◡≦)", color=discord.Color.orange())

        found = False
        for name, data in moon.RECIPES.items():
            if search and search not in name:
                continue

            found = True
            ingredients_str = []
            can_cook_count = 9999

            for ing, amt in data['ingredients'].items():
                user_amt = inv_dict.get(ing, 0)
                status = "✅" if user_amt >= amt else "❌"
                ingredients_str.append(f"{status} **{ing}**: {amt}개 (보유: {user_amt})")

                if amt > 0:
                    current_can_make = user_amt // amt
                    if current_can_make < can_cook_count:
                        can_cook_count = current_can_make

            if can_cook_count == 9999: can_cook_count = 0
            desc = f"**📖 설명:** {data['result_desc']}\n**🧂 필요 재료:**\n" + "\n".join(ingredients_str)

            name_suffix = ""
            if can_cook_count > 0:
                name_suffix = f" (✨ {can_cook_count}개 제작 가능!)"

            embed.add_field(name=f"🍲 {name}{name_suffix}", value=desc, inline=False)

        if not found:
            embed.description = "검색 결과가 없어요... 다른 이름으로 찾아볼까요? (｡•́︿•̀｡)"

        await interaction.response.send_message(embed=embed)

    @activity_group.command(name="요리", description="재료를 조합하여 새로운 아이템을 만듭니다.")
    @app_commands.describe(recipe_name="만들 요리 이름", count="만들 개수 (기본 1개)")
    async def cook(self, interaction: discord.Interaction, recipe_name: str, count: int = 1):
        if count < 1:
            return await interaction.response.send_message("장난치지 마세요~! 최소 1개는 만들어야죠! ( `ω´ )", ephemeral=True)

        if recipe_name not in moon.RECIPES:
            recipes_list = ", ".join(moon.RECIPES.keys())
            return await interaction.response.send_message(f"그런 레시피는 처음 들어봐요! 요미가 아는 건 이런 것들이에요: {recipes_list} ( 🍳 )", ephemeral=True)

        recipe = moon.RECIPES[recipe_name]
        user_inv = await db.get_inventory(str(interaction.user.id))
        inv_dict = {item['item_name']: item['amount'] for item in user_inv}

        missing = []
        for ing, amt in recipe['ingredients'].items():
            needed = amt * count
            if inv_dict.get(ing, 0) < needed:
                missing.append(f"{ing} ({inv_dict.get(ing, 0)}/{needed})")

        if missing:
            return await interaction.response.send_message(f"재료가 모자라요... 힝... {count}개를 만들려면 더 필요해요:\n{', '.join(missing)} (｡•́︿•̀｡)", ephemeral=True)

        await interaction.response.send_message(f"🍳 **{recipe_name}** 요리 중... 재료를 다듬는 중이에요! (사각사각)")
        await asyncio.sleep(1.5)
        await interaction.edit_original_response(content=f"🔥 **{recipe_name}** 요리 중... 불 조절에 집중하고 있어요! (화르륵)")
        await asyncio.sleep(1.5)

        items_to_deduct = {ing: amt * count for ing, amt in recipe['ingredients'].items()}
        if not await db.try_deduct_items(str(interaction.user.id), items_to_deduct):
             await interaction.edit_original_response(content=f"❌ 재료가 부족하거나 사라졌어요! (누군가 훔쳐갔나 봐요!)", embed=None)
             return

        success_roll = random.random()

        if success_roll < 0.05:
            await db.add_item(str(interaction.user.id), "검게 탄 요리", count)

            embed = discord.Embed(
                title="🍳 요리 실패...",
                description=f"앗... 잠깐 딴생각 하다가 태워버렸어요... ㅠㅠ\n**검게 탄 요리** {count}개를 획득했습니다.",
                color=discord.Color.dark_grey()
            )
            await interaction.edit_original_response(content="", embed=embed)

        elif success_roll > 0.95:
            bonus_count = count * 2
            await db.add_item(str(interaction.user.id), recipe_name, bonus_count)

            embed = discord.Embed(
                title="✨ 대성공! ✨",
                description=f"와! 정말 완벽하게 만들어졌어요! 맛도 두 배, 양도 두 배!\n**{recipe_name}** {bonus_count}개를 획득했습니다! (2배)",
                color=discord.Color.gold()
            )
            await interaction.edit_original_response(content="", embed=embed)

        else:
            await db.add_item(str(interaction.user.id), recipe_name, count)

            embed = discord.Embed(
                title="🍳 요리 성공!",
                description=f"보글보글... 짜잔! 🍳 **{recipe_name}** {count}개 완성! 정말 맛있어 보여요! (😋)\n\n{recipe['result_desc']}",
                color=discord.Color.green()
            )
            await interaction.edit_original_response(content="", embed=embed)

    @cook.autocomplete('recipe_name')
    async def recipe_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=name, value=name)
            for name in moon.RECIPES.keys() if current.lower() in name.lower()
        ][:25]

    @dungeon_group.command(name="입장", description="나만의 던전을 탐험하고 성장합니다.")
    @app_commands.describe(use_ticket="던전 입장권을 사용해 특수 던전에 입장합니다. 보상 3배, 난이도 1.5배.")
    async def dungeon(self, interaction: discord.Interaction, use_ticket: bool = False):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        saved_run = await db.get_dungeon_run(user_id)
        if saved_run:
            embed = discord.Embed(
                title="🗂️ 저장된 전투 발견",
                description="이전에 진행 중이던 던전이 있어요. 이어서 진행할까요?",
                color=discord.Color.blurple()
            )
            view = DungeonResumeView(self, user_id, saved_run, use_ticket)
            await interaction.followup.send(embed=embed, view=view)
            return
        is_special = False
        if use_ticket:
            ok = await self.consume_dungeon_ticket(interaction, user_id)
            if not ok:
                return
            is_special = True
        await self.start_dungeon_session(interaction, user_id, is_special, True)

    @dungeon_group.command(name="기록", description="최근 던전 전투 기록을 확인합니다.")
    async def dungeon_records(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        records = await db.get_dungeon_records(user_id, 5)
        if not records:
            return await interaction.followup.send("아직 던전 기록이 없습니다.", ephemeral=True)
        embed = discord.Embed(
            title="📜 던전 전투 기록",
            color=discord.Color.teal()
        )
        for record in records:
            stage, result, reward, drops, duration, is_special, reason, created_at = record
            result_text = "승리" if result == "win" else "패배"
            mode_text = "특수" if is_special else "일반"
            time_text = datetime.fromtimestamp(created_at, tz=time_utils.KST).strftime("%m/%d %H:%M")
            drop_text = drops if drops else "없음"
            reason_text = f" ({reason})" if reason else ""
            value = f"결과: {result_text}{reason_text}\n보상: {reward:,} 젤리\n전리품: {drop_text}\n시간: {int(duration)}초\n모드: {mode_text}\n일시: {time_text}"
            embed.add_field(name=f"Stage {stage}", value=value, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @dungeon_group.command(name="즐겨찾기", description="즐겨찾기한 던전을 확인하고 입장합니다.")
    async def dungeon_favorites(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        favorites = await db.get_dungeon_favorites(user_id)
        if not favorites:
            return await interaction.followup.send("즐겨찾기한 던전이 없습니다.", ephemeral=True)
        view = DungeonFavoriteView(self, user_id, favorites)
        embed = discord.Embed(
            title="⭐ 즐겨찾기 던전",
            description="입장할 던전을 선택해주세요.",
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @dungeon_group.command(name="즐겨찾기추가", description="던전을 즐겨찾기에 추가합니다.")
    @app_commands.describe(stage="즐겨찾기할 스테이지", use_ticket="특수 던전으로 즐겨찾기합니다.")
    async def add_dungeon_favorite(self, interaction: discord.Interaction, stage: int, use_ticket: bool = False):
        if stage < 1:
            return await interaction.response.send_message("스테이지는 1 이상이어야 합니다.", ephemeral=True)
        user_id = str(interaction.user.id)
        await db.add_dungeon_favorite(user_id, stage, 1 if use_ticket else 0)
        mode_text = "특수" if use_ticket else "일반"
        await interaction.response.send_message(f"Stage {stage} ({mode_text}) 즐겨찾기에 추가되었습니다.", ephemeral=True)

    @dungeon_group.command(name="즐겨찾기삭제", description="즐겨찾기한 던전을 삭제합니다.")
    @app_commands.describe(stage="삭제할 스테이지", use_ticket="특수 던전 즐겨찾기 삭제 여부")
    async def remove_dungeon_favorite(self, interaction: discord.Interaction, stage: int, use_ticket: bool = False):
        if stage < 1:
            return await interaction.response.send_message("스테이지는 1 이상이어야 합니다.", ephemeral=True)
        user_id = str(interaction.user.id)
        await db.remove_dungeon_favorite(user_id, stage, 1 if use_ticket else 0)
        mode_text = "특수" if use_ticket else "일반"
        await interaction.response.send_message(f"Stage {stage} ({mode_text}) 즐겨찾기에서 삭제되었습니다.", ephemeral=True)

    async def consume_dungeon_ticket(self, interaction: discord.Interaction, user_id: str) -> bool:
        inv = await db.get_inventory(user_id)
        inv_dict = {i['item_name']: i['amount'] for i in inv}
        if inv_dict.get("던전 입장권", 0) <= 0:
            msg = "던전 입장권이 부족합니다!"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False
        await db.remove_item(user_id, "던전 입장권", 1)
        return True

    async def start_dungeon_from_saved(self, interaction: discord.Interaction, data: dict, use_followup: bool):
        user_id = str(interaction.user.id)
        settings = await db.get_dungeon_settings(user_id)
        log_mode = settings.get("log_mode", "summary")
        auto_retry = settings.get("auto_retry", 0)
        pets = await db.get_user_pets(user_id)
        view = DungeonView(
            self,
            user_id,
            data.get("stage", 1),
            data.get("p_atk", 10),
            data.get("p_def", 0),
            data.get("p_hp", 100),
            data.get("p_max_hp", 100),
            data.get("p_mp", 100),
            data.get("p_max_mp", 100),
            data.get("m_hp", 100),
            data.get("m_max_hp", 100),
            data.get("m_atk", 1),
            data.get("m_name", "몬스터"),
            data.get("potions", 0),
            data.get("mp_potions", 0),
            data.get("buffs", 0),
            data.get("revives", 0),
            bool(data.get("is_special", 0)),
            pets,
            log_mode,
            auto_retry,
            data.get("update_progress", True)
        )
        embed = view.get_embed()
        if use_followup:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    async def start_dungeon_session(self, interaction: discord.Interaction, user_id: str, is_special: bool, use_followup: bool, stage_override: int = None, update_progress: bool = True):
        progress = await db.get_dungeon_progress(user_id)
        current_stage = progress if isinstance(progress, int) else progress.get('stage', 1)
        stage = stage_override if stage_override is not None else current_stage
        player_atk = 10
        player_hp = 100
        player_mp = 100
        player_def = 0
        sword_lv = await db.get_upgrade(user_id, "sword")
        multipliers = [1.0, 1.5, 2.0, 3.5, 6.0, 15.0]
        mult = multipliers[sword_lv] if sword_lv < len(multipliers) else multipliers[-1]
        player_atk = int(player_atk * mult)
        player_hp = int(player_hp * (1 + sword_lv * 0.2))
        equipped = await db.get_equipped_armor(user_id)
        economy_cog = interaction.client.get_cog("Economy")
        set_counts = {}
        if equipped and economy_cog:
            armor_items = economy_cog.armor_items
            for slot, item_name in equipped.items():
                if not item_name or item_name not in armor_items:
                    continue
                item_data = armor_items[item_name]
                player_atk += item_data.get('atk', 0)
                player_hp += item_data.get('hp', 0)
                player_def += item_data.get('def', 0)
                set_name = item_data.get('set')
                if set_name:
                    set_counts[set_name] = set_counts.get(set_name, 0) + 1
            set_bonuses = economy_cog.set_bonuses
            for set_name, count in set_counts.items():
                if set_name in set_bonuses and count >= set_bonuses[set_name]['parts']:
                    bonus = set_bonuses[set_name]
                    player_atk += bonus.get('bonus_atk', 0)
                    player_hp += bonus.get('bonus_hp', 0)
                    player_def += bonus.get('bonus_def', 0)
        m_idx = (stage - 1) % 35 + 1
        m_data = MONSTERS.get(m_idx, MONSTERS[1])
        monster_hp = int(stage * 60 * m_data['hp_scale'])
        monster_atk = int(stage * 3 * m_data['atk_scale'])
        is_boss = (stage % 10 == 0)
        if is_boss:
            monster_hp = int(monster_hp * 1.5)
            monster_atk = int(monster_atk * 1.2)
        if is_special:
            monster_hp = int(monster_hp * 1.5)
            monster_atk = int(monster_atk * 1.5)
        title_prefix = "🔥 특수 던전 • " if is_special else ""
        description = f"{m_data['emoji']} **{m_data['name']}** 등장\n전투에서 승리하면 다음 스테이지가 열립니다."
        if not update_progress:
            description = f"{m_data['emoji']} **{m_data['name']}** 등장\n전투 결과가 진행도에 영향을 주지 않습니다."
        settings = await db.get_dungeon_settings(user_id)
        log_mode = settings.get("log_mode", "summary")
        auto_retry = settings.get("auto_retry", 0)
        pets = await db.get_user_pets(user_id)
        pet_count = len(pets)
        reward_mult = 3 if is_special else 1
        reward_amount = stage * 1000 * reward_mult
        boss_tag = "보스전" if is_boss else "일반전"
        special_tag = "보상 3배 · 난이도 1.5배" if is_special else "보상 1배"
        est_turns = max(1, math.ceil(monster_hp / max(1, player_atk)))
        est_time = f"{est_turns*6}초±"
        inv = await db.get_inventory(user_id)
        inv_dict = {i['item_name']: i['amount'] for i in inv}
        potions = inv_dict.get("HP 물약", 0)
        mp_potions = inv_dict.get("MP 물약", 0)
        buffs = inv_dict.get("공격력 증폭제", 0)
        revives = inv_dict.get("부활의 돌", 0)
        tickets = inv_dict.get("던전 입장권", 0)
        embed = discord.Embed(
            title=f"{title_prefix}🏰 던전 탐험 시작 (Stage {stage})",
            description=description,
            color=discord.Color.purple() if is_special else (discord.Color.dark_red() if is_boss else discord.Color.dark_grey())
        )
        embed.add_field(name="전투 요약", value=f"전투 유형: {boss_tag}\n보상 배율: {special_tag}\n예상 보상: **{reward_amount:,} 젤리**\n예상 소요: {est_time}", inline=False)
        embed.add_field(name="내 상태", value=f"⚔️ 공격력 {player_atk}\n🛡️ 방어력 {player_def}\n❤️ 체력 {player_hp}/{player_hp}\n💧 마력 {player_mp}/{player_mp}", inline=True)
        embed.add_field(name="적 정보", value=f"🩸 체력 {monster_hp}\n💥 공격력 {monster_atk}", inline=True)
        embed.add_field(name="동행", value=f"펫 {pet_count}마리", inline=True)
        embed.add_field(name="입장 정보", value=f"입장권 {tickets}개\n모드 솔로 • 매칭 없음", inline=True)
        embed.add_field(name="준비 아이템", value=f"🧪 HP {potions}\n💧 MP {mp_potions}\n⚡ 증폭제 {buffs}\n👼 부활 {revives}", inline=True)
        embed.add_field(name="보상 미리보기", value="기본 10%: HP 물약, 철광석\n보스/특수 10%: 강철 주괴, 가죽, 금광석\n보스 20%: 영혼석(미구현)", inline=False)
        view = DungeonView(self, user_id, stage, player_atk, player_def, player_hp, player_hp, player_mp, player_mp, monster_hp, monster_hp, monster_atk, m_data['name'], potions, mp_potions, buffs, revives, is_special, pets, log_mode, auto_retry, update_progress)
        if use_followup:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    @pet_group.command(name="목록", description="나의 펫들을 확인하고 관리합니다.")
    async def pets(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        pets = await db.get_user_pets(user_id)

        embed = discord.Embed(
            title=f"🐾 {interaction.user.name}님의 펫 히스토리",
            description="교주님을 지켜주는 든든한 친구들이에요!",
            color=discord.Color.teal()
        )

        if not pets:
            embed.description += "\n\n아직 함께하는 펫이 없어요. 이벤트를 통해 펫을 만날 수 있어요!"
        else:
            for pet in pets:
                data = moon.PET_DATA.get(pet['pet_type'], {"emoji": "🐾", "desc": "신비로운 펫입니다."})
                embed.add_field(
                    name=f"{data['emoji']} {pet['pet_type']} (Lv.{pet['level']})",
                    value=f"{data['desc']}\nXP: {pet['xp']}/{(pet['level']*100)}",
                    inline=False
                )

        embed.set_footer(text="/놀아주기 명령어로 펫과 놀아주고 경험치를 얻을 수 있어요!")
        await interaction.response.send_message(embed=embed)

    @pet_group.command(name="놀아주기", description="펫과 놀아주고 경험치를 획득합니다.")
    @app_commands.describe(pet_type="놀아줄 펫 종류")
    @app_commands.rename(pet_type="펫_종류")
    async def play_with_pet(self, interaction: discord.Interaction, pet_type: str):
        user_id = str(interaction.user.id)

        benefits = booster_utils.get_booster_benefits(interaction.user)
        cooldown_time = 3600 * benefits["cooldown_mult"]

        remaining = await db.check_cooldown(user_id, "play_spirit", cooldown_time)
        if remaining > 0:
            return await interaction.response.send_message(f"펫들이 지쳤어요... {int(remaining//60)}분 {int(remaining%60)}초 뒤에 다시 놀아주세요! 💤", ephemeral=True)

        pets = await db.get_user_pets(user_id)
        target_pet = next((p for p in pets if p['pet_type'] == pet_type), None)

        if not target_pet:
            return await interaction.response.send_message(f"어라? **{pet_type}** 펫은 아직 교주님과 함께하지 않는데요? (｡•́︿•̀｡)", ephemeral=True)

        cost = 50
        balance = await db.get_balance(user_id)
        if balance < cost:
            return await interaction.response.send_message(f"놀아주려면 간식이 필요해요... (필요: {cost} 젤리)", ephemeral=True)

        await db.update_balance(user_id, -cost)
        xp_gain = random.randint(15, 30)
        await db.update_pet_xp(user_id, pet_type, xp_gain)
        await db.update_cooldown(user_id, "play_spirit")

        pets_updated = await db.get_user_pets(user_id)
        updated_pet = next((p for p in pets_updated if p['pet_type'] == pet_type), None)
        level_up_msg = ""
        if updated_pet['level'] > target_pet['level']:
            level_up_msg = f"\n🎉 **레벨 업!** 이제 {updated_pet['level']}레벨이 되었어요!"

        data = moon.PET_DATA.get(pet_type, {"emoji": "🐾"})
        messages = [
            f"{data['emoji']} **{pet_type}**와(과) 공놀이를 했어요! 아주 즐거워하네요!",
            f"{data['emoji']} **{pet_type}**에게 맛있는 간식을 줬어요! 냠냠!",
            f"{data['emoji']} **{pet_type}**를(을) 쓰담쓰담 해줬어요. 기분이 좋아 보여요!",
        ]

        embed = discord.Embed(
            title=f"🐾 즐거운 시간",
            description=f"{random.choice(messages)}\n\n✨ **XP +{xp_gain}** 획득!{level_up_msg}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @play_with_pet.autocomplete('pet_type')
    async def play_pet_autocomplete(self, interaction: discord.Interaction, current: str):
        user_id = str(interaction.user.id)
        pets = await db.get_user_pets(user_id)
        return [
            app_commands.Choice(name=p['pet_type'], value=p['pet_type'])
            for p in pets if current.lower() in p['pet_type'].lower()
        ]

    @pet_group.command(name="먹이주기", description="펫에게 맛있는 먹이를 주고 대량의 경험치를 얻습니다.")
    @app_commands.describe(pet_type="먹이를 줄 펫 종류", food_name="줄 먹이 이름 (보유한 아이템)")
    @app_commands.rename(pet_type="펫_종류", food_name="먹이_이름")
    async def feed_pet(self, interaction: discord.Interaction, pet_type: str, food_name: str):
        user_id = str(interaction.user.id)

        pets = await db.get_user_pets(user_id)
        target_pet = next((p for p in pets if p['pet_type'] == pet_type), None)

        if not target_pet:
            return await interaction.response.send_message(f"어라? **{pet_type}** 펫은 아직 교주님과 함께하지 않는데요? (｡•́︿•̀｡)", ephemeral=True)

        inv = await db.get_inventory(user_id)
        item = next((i for i in inv if i['item_name'] == food_name), None)

        if not item or item['amount'] < 1:
            return await interaction.response.send_message(f"**{food_name}** 아이템이 없어요! 상점이나 탐색에서 얻어주세요.", ephemeral=True)

        xp_gain = 0

        if food_name == "펫 간식":
            xp_gain = 100
        elif food_name == "펫 장난감":
            xp_gain = 300
        elif food_name in self.collectible_items:
            c_item = self.collectible_items[food_name]
            if c_item.get("type") == "fish":
                xp_gain = int(c_item['price'] / 100)
            elif c_item.get("type") == "deep_sea_fish":
                xp_gain = int(c_item['price'] / 200)
            elif c_item.get("type") in ["material", "wood", "mineral"]:
                xp_gain = 5
            else:
                xp_gain = 20
        elif food_name in self.shop_items:
            xp_gain = 30
        else:
            xp_gain = 10

        if xp_gain <= 0: xp_gain = 1

        await db.remove_item(user_id, food_name, 1)
        await db.update_pet_xp(user_id, pet_type, xp_gain)

        pets_updated = await db.get_user_pets(user_id)
        updated_pet = next((p for p in pets_updated if p['pet_type'] == pet_type), None)
        level_up_msg = ""
        if updated_pet['level'] > target_pet['level']:
            level_up_msg = f"\n🎉 **레벨 업!** 이제 {updated_pet['level']}레벨이 되었어요!"

        data = moon.PET_DATA.get(pet_type, {"emoji": "🐾"})

        embed = discord.Embed(
            title=f"🍖 냠냠쩝쩝",
            description=f"{data['emoji']} **{pet_type}**에게 **{food_name}**을(를) 줬어요!\n아주 맛있게 먹네요!\n\n✨ **XP +{xp_gain}** 획득!{level_up_msg}",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)

    @feed_pet.autocomplete('pet_type')
    async def feed_pet_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.play_pet_autocomplete(interaction, current)

    @feed_pet.autocomplete('food_name')
    async def feed_food_autocomplete(self, interaction: discord.Interaction, current: str):
        user_id = str(interaction.user.id)
        inv = await db.get_inventory(user_id)
        edible = []
        for item in inv:
            name = item['item_name']
            if name in ["펫 간식", "펫 장난감"] or\
               (name in self.collectible_items and self.collectible_items[name].get("type") in ["fish", "deep_sea_fish"]) or\
               name in ["고기", "우유", "계란", "딸기", "쌀", "호박", "레몬", "아몬드", "꿀", "초콜릿"]:
               edible.append(item)

        return [
            app_commands.Choice(name=f"{i['item_name']} ({i['amount']}개)", value=i['item_name'])
            for i in edible if current.lower() in i['item_name'].lower()
        ][:25]

    @store_group.command(name="명예의전당", description="역대 최고의 교주님들을 기리는 공간입니다.")
    async def hall_of_fame(self, interaction: discord.Interaction):
        await interaction.response.defer()

        top_eco = await db.get_top_economy(50)
        top_aff = await db.get_top_affinity(50)

        view = HallOfFameView(top_eco, top_aff, self.bot)
        await interaction.followup.send(embed=view.get_embed(), view=view)

class ConfirmBuildView(discord.ui.View):
    def __init__(self, user_id, building_type, cost):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.building_type = building_type
        self.cost = cost

    @discord.ui.button(label="건설하기", style=discord.ButtonStyle.green, emoji="🔨")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("본인의 건물만 지을 수 있어요!", ephemeral=True)

        if await db.try_deduct_balance(self.user_id, self.cost):
            buildings = await db.get_tycoon_buildings(self.user_id)
            current_level = 0
            if self.building_type in buildings:
                current_level = buildings[self.building_type]['level']

            new_level = current_level + 1
            await db.update_tycoon_building(self.user_id, self.building_type, new_level, time.time())

            await interaction.response.edit_message(content=f"🎉 **건설 완료!** (Lv.{new_level})", embed=None, view=None)
        else:
            await interaction.response.send_message("돈이 부족해요!", ephemeral=True)

    @discord.ui.button(label="취소", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id: return
        await interaction.response.edit_message(content="건설을 취소했습니다.", embed=None, view=None)

MONSTERS = {
    1:  {"name": "슬라임", "emoji": "💧", "hp_scale": 1.0, "atk_scale": 1.0},
    2:  {"name": "고블린", "emoji": "👺", "hp_scale": 1.2, "atk_scale": 1.1},
    3:  {"name": "스켈레톤", "emoji": "💀", "hp_scale": 1.5, "atk_scale": 1.3},
    4:  {"name": "오크", "emoji": "👹", "hp_scale": 2.0, "atk_scale": 1.5},
    5:  {"name": "트롤", "emoji": "🧟", "hp_scale": 2.5, "atk_scale": 1.8},
    6:  {"name": "골렘", "emoji": "🗿", "hp_scale": 3.0, "atk_scale": 2.0},
    7:  {"name": "와이번", "emoji": "🐲", "hp_scale": 4.0, "atk_scale": 2.5},
    8:  {"name": "다크나이트", "emoji": "🦇", "hp_scale": 5.0, "atk_scale": 3.0},
    9:  {"name": "리치", "emoji": "🧙", "hp_scale": 6.0, "atk_scale": 3.5},
    10: {"name": "드래곤", "emoji": "🔥", "hp_scale": 10.0, "atk_scale": 5.0},
    11: {"name": "아이언 골렘", "emoji": "🤖", "hp_scale": 4.0, "atk_scale": 2.2},
    12: {"name": "그리폰", "emoji": "🦅", "hp_scale": 4.5, "atk_scale": 2.8},
    13: {"name": "뱀파이어", "emoji": "🧛", "hp_scale": 5.0, "atk_scale": 3.2},
    14: {"name": "지옥견", "emoji": "🐕‍🦺", "hp_scale": 5.5, "atk_scale": 3.5},
    15: {"name": "데스 나이트", "emoji": "⚔️", "hp_scale": 6.5, "atk_scale": 4.0},
    16: {"name": "크라켄", "emoji": "🦑", "hp_scale": 8.0, "atk_scale": 4.5},
    17: {"name": "피닉스", "emoji": "🐦🔥", "hp_scale": 7.0, "atk_scale": 5.0},
    18: {"name": "베히모스", "emoji": "🐗", "hp_scale": 12.0, "atk_scale": 4.0},
    19: {"name": "마왕의 그림자", "emoji": "👤", "hp_scale": 9.0, "atk_scale": 5.5},
    20: {"name": "마왕", "emoji": "😈", "hp_scale": 15.0, "atk_scale": 7.0},
    21: {"name": "서큐버스", "emoji": "💋", "hp_scale": 10.0, "atk_scale": 6.0},
    22: {"name": "인큐버스", "emoji": "👿", "hp_scale": 10.0, "atk_scale": 6.0},
    23: {"name": "듀라한", "emoji": "🎃", "hp_scale": 11.0, "atk_scale": 6.5},
    24: {"name": "바실리스크", "emoji": "🐍", "hp_scale": 12.0, "atk_scale": 6.5},
    25: {"name": "만티코어", "emoji": "🦁", "hp_scale": 13.0, "atk_scale": 7.0},
    26: {"name": "키메라", "emoji": "🦁🐍", "hp_scale": 14.0, "atk_scale": 7.0},
    27: {"name": "히드라", "emoji": "🐲🐲", "hp_scale": 16.0, "atk_scale": 7.5},
    28: {"name": "타락천사", "emoji": "👼🖤", "hp_scale": 18.0, "atk_scale": 8.0},
    29: {"name": "고대 드래곤", "emoji": "🐉", "hp_scale": 20.0, "atk_scale": 9.0},
    30: {"name": "세계의 포식자", "emoji": "🪐", "hp_scale": 30.0, "atk_scale": 10.0},
    31: {"name": "공허의 감시자", "emoji": "👁️", "hp_scale": 35.0, "atk_scale": 11.0},
    32: {"name": "심연의 군주", "emoji": "👑", "hp_scale": 40.0, "atk_scale": 12.0},
    33: {"name": "혼돈의 기사", "emoji": "🛡️", "hp_scale": 45.0, "atk_scale": 13.0},
    34: {"name": "절망의 화신", "emoji": "☠️", "hp_scale": 50.0, "atk_scale": 14.0},
    35: {"name": "종말의 짐승", "emoji": "🦖", "hp_scale": 60.0, "atk_scale": 15.0},
}

class ConsolidatedGardenView(discord.ui.View):
    def __init__(self, user_id, viewer_id):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.viewer_id = viewer_id

        if str(user_id) != str(viewer_id):
            self.clear_items()
            return

    @discord.ui.button(label="가구 배치", style=discord.ButtonStyle.primary, emoji="🪑")
    async def place_furniture(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.user_id):
            return await interaction.response.send_message("자신의 정원만 관리할 수 있어요!", ephemeral=True)

        inv = await db.get_inventory(self.user_id)
        furniture_keywords = ["가구", "인형", "카펫", "화분", "조명", "침대", "책상", "의자"]
        furniture_options = []

        for item in inv:
            if any(k in item['item_name'] for k in furniture_keywords):
                furniture_options.append(discord.SelectOption(
                    label=f"{item['item_name']} ({item['amount']}개)",
                    value=item['item_name'],
                    emoji="📦"
                ))

        if not furniture_options:
            return await interaction.response.send_message("배치할 수 있는 가구가 없어요! 상점에서 가구를 구매해보세요.", ephemeral=True)

        if len(furniture_options) > 25:
            furniture_options = furniture_options[:25]

        view = GardenPlaceView(self.user_id, furniture_options)
        await interaction.response.send_message("배치할 가구를 선택해주세요.", view=view, ephemeral=True)

    @discord.ui.button(label="가구 회수", style=discord.ButtonStyle.danger, emoji="🧹")
    async def remove_furniture(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.user_id):
            return await interaction.response.send_message("자신의 정원만 관리할 수 있어요!", ephemeral=True)

        current_items = await db.get_garden_items(self.user_id)
        if not current_items:
            return await interaction.response.send_message("회수할 가구가 없어요!", ephemeral=True)

        options = []
        for item in current_items:
            options.append(discord.SelectOption(
                label=f"{item['item_id']} (위치: {item['position']})",
                value=f"{item['item_id']}:{item['position']}",
                emoji="📍"
            ))

        if len(options) > 25:
             options = options[:25]

        view = GardenRemoveView(self.user_id, options)
        await interaction.response.send_message("회수할 가구를 선택해주세요.", view=view, ephemeral=True)


class GardenPlaceView(discord.ui.View):
    def __init__(self, user_id, options):
        super().__init__(timeout=60)
        self.user_id = user_id

        self.select = discord.ui.Select(placeholder="가구 선택...", min_values=1, max_values=1, options=options)
        self.select.callback = self.item_callback
        self.add_item(self.select)

    async def item_callback(self, interaction: discord.Interaction):
        selected_item = self.select.values[0]
        view = GardenPositionView(self.user_id, selected_item)
        await interaction.response.edit_message(content=f"**{selected_item}**을(를) 어디에 배치할까요?", view=view)


class GardenPositionView(discord.ui.View):
    def __init__(self, user_id, item_name):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.item_name = item_name

        options = [discord.SelectOption(label=f"{i}번 구역", value=str(i)) for i in range(1, 10)]
        self.select = discord.ui.Select(placeholder="위치 선택...", min_values=1, max_values=1, options=options)
        self.select.callback = self.pos_callback
        self.add_item(self.select)

    async def pos_callback(self, interaction: discord.Interaction):
        position = int(self.select.values[0])

        current_items = await db.get_garden_items(self.user_id)
        occupied = next((i for i in current_items if i['position'] == position), None)

        swap_msg = ""

        try:
            async with aiosqlite.connect(db.DB_FILE) as conn:
                if occupied:
                    old_item = occupied['item_id']
                    await conn.execute("DELETE FROM user_garden WHERE user_id = ? AND position = ?", (self.user_id, position))
                    await db.add_item(self.user_id, old_item, 1)
                    swap_msg = f"\n(기존 **{old_item}** 회수됨)"

                await db.remove_item(self.user_id, self.item_name, 1)
                await conn.execute(
                    "INSERT OR REPLACE INTO user_garden (user_id, item_id, position) VALUES (?, ?, ?)",
                    (self.user_id, self.item_name, position),
                )
                await conn.commit()

            await interaction.response.edit_message(content=f"✨ **{self.item_name}**을(를) {position}번 구역에 배치했습니다!{swap_msg}", view=None)

        except Exception as e:
            await interaction.response.send_message(f"오류가 발생했습니다: {e}", ephemeral=True)


class GardenRemoveView(discord.ui.View):
    def __init__(self, user_id, options):
        super().__init__(timeout=60)
        self.user_id = user_id

        self.select = discord.ui.Select(placeholder="회수할 가구 선택...", min_values=1, max_values=1, options=options)
        self.select.callback = self.callback
        self.add_item(self.select)

    async def callback(self, interaction: discord.Interaction):
        value = self.select.values[0]
        item_name, pos_str = value.split(":")
        position = int(pos_str)

        async with aiosqlite.connect(db.DB_FILE) as conn:
            await conn.execute("DELETE FROM user_garden WHERE user_id = ? AND item_id = ? AND position = ?", (self.user_id, item_name, position))
            await conn.commit()

        await db.add_item(self.user_id, item_name, 1)

        await interaction.response.edit_message(content=f"🧹 **{item_name}** (위치: {position})을(를) 회수했습니다!", view=None)


class HallOfFameView(discord.ui.View):
    def __init__(self, data_eco, data_aff, bot):
        super().__init__(timeout=60)
        self.data_eco = data_eco
        self.data_aff = data_aff
        self.bot = bot
        self.page = 0
        self.mode = "economy"
    def get_embed(self):
        data = self.data_eco if self.mode == "economy" else self.data_aff
        title = "💰 자산 순위" if self.mode == "economy" else "💕 호감도 순위"
        color = discord.Color.gold() if self.mode == "economy" else discord.Color.from_rgb(255, 182, 193)

        items_per_page = 10
        max_pages = (len(data) - 1) // items_per_page + 1
        start = self.page * items_per_page
        end = start + items_per_page
        current_data = data[start:end]

        lines = []
        for i, (uid, val) in enumerate(current_data, start + 1):
            user = self.bot.get_user(int(uid))
            name = user.display_name if user else f"Unknown ({uid})"
            unit = "젤리" if self.mode == "economy" else "💕"
            lines.append(f"**{i}위.** {name}: `{val:,}` {unit}")

        if not lines: lines = ["데이터가 없습니다."]

        embed = discord.Embed(title=f"🏆 명예의 전당 ({title})", description="\n".join(lines), color=color)
        embed.set_footer(text=f"페이지 {self.page + 1} / {max_pages}")
        return embed

    @discord.ui.button(label="자산 순위", style=discord.ButtonStyle.primary)
    async def show_eco(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.mode = "economy"
        self.page = 0
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="호감도 순위", style=discord.ButtonStyle.success)
    async def show_aff(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.mode = "affinity"
        self.page = 0
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.send_message("첫 페이지입니다.", ephemeral=True)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = self.data_eco if self.mode == "economy" else self.data_aff
        if (self.page + 1) * 10 < len(data):
            self.page += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.send_message("마지막 페이지입니다.", ephemeral=True)

class DungeonResumeView(discord.ui.View):
    def __init__(self, cog, user_id, saved_data, use_ticket):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.saved_data = saved_data
        self.use_ticket = use_ticket

    @discord.ui.button(label="이어하기", style=discord.ButtonStyle.green)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id: return
        await self.cog.start_dungeon_from_saved(interaction, self.saved_data, use_followup=False)

    @discord.ui.button(label="포기하기", style=discord.ButtonStyle.red)
    async def discard(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id: return
        await db.delete_dungeon_run(self.user_id)

        is_special = False
        if self.use_ticket:
            if await self.cog.consume_dungeon_ticket(interaction, self.user_id):
                is_special = True
            else:
                return

        await self.cog.start_dungeon_session(interaction, self.user_id, is_special, use_followup=False, update_progress=True)

class DungeonFavoriteView(discord.ui.View):
    def __init__(self, cog, user_id, favorites):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id

        options = []
        for stage, is_special in favorites:
            mode = "특수" if is_special else "일반"
            options.append(discord.SelectOption(label=f"Stage {stage} ({mode})", value=f"{stage}:{is_special}"))

        self.add_item(DungeonFavoriteSelect(options))

class DungeonFavoriteSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="던전 선택...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        stage, is_special = val.split(":")
        stage = int(stage)
        is_special = int(is_special)

        view: DungeonFavoriteView = self.view

        if is_special:
            if not await view.cog.consume_dungeon_ticket(interaction, view.user_id):
                return

        await view.cog.start_dungeon_session(interaction, view.user_id, bool(is_special), use_followup=False, stage_override=stage, update_progress=False)

class DungeonView(discord.ui.View):
    def __init__(self, cog, user_id, stage, p_atk, p_def, p_hp, p_max_hp, p_mp, p_max_mp, m_hp, m_max_hp, m_atk, m_name, potions, mp_potions, buffs, revives, is_special, pets, log_mode, auto_retry, update_progress):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.stage = stage
        self.p_atk = p_atk
        self.p_def = p_def
        self.p_hp = p_hp
        self.p_max_hp = p_max_hp
        self.p_mp = p_mp
        self.p_max_mp = p_max_mp
        self.m_hp = m_hp
        self.m_max_hp = m_max_hp
        self.m_atk = m_atk
        self.m_name = m_name
        self.potions = potions
        self.mp_potions = mp_potions
        self.buffs = buffs
        self.revives = revives
        self.is_special = is_special
        self.pets = pets
        self.log_mode = log_mode
        self.auto_retry = auto_retry
        self.update_progress = update_progress
        self.logs = []

        self.update_buttons()

    def update_buttons(self):
        self.children[2].disabled = self.potions <= 0
        self.children[2].label = f"HP 물약 ({self.potions})"

    def get_embed(self):
        color = discord.Color.purple() if self.is_special else discord.Color.red()
        embed = discord.Embed(title=f"⚔️ Stage {self.stage} vs {self.m_name}", color=color)

        p_ratio = self.p_hp / self.p_max_hp
        p_bar = "🟩" * int(p_ratio * 10) + "⬜" * (10 - int(p_ratio * 10))

        m_ratio = self.m_hp / self.m_max_hp
        m_bar = "🟥" * int(m_ratio * 10) + "⬜" * (10 - int(m_ratio * 10))

        embed.add_field(name="교주님", value=f"❤️ {self.p_hp}/{self.p_max_hp}\n{p_bar}\n⚔️ {self.p_atk} 🛡️ {self.p_def}", inline=True)
        embed.add_field(name="VS", value="⚡", inline=True)
        embed.add_field(name=f"{self.m_name}", value=f"❤️ {self.m_hp}/{self.m_max_hp}\n{m_bar}\n⚔️ {self.m_atk}", inline=True)

        if self.logs:
            log_str = "\n".join(self.logs[-5:])
            embed.add_field(name="전투 로그", value=f"```\n{log_str}\n```", inline=False)

        return embed

    async def save_state(self):
        data = {
            "stage": self.stage,
            "p_atk": self.p_atk, "p_def": self.p_def, "p_hp": self.p_hp, "p_max_hp": self.p_max_hp,
            "p_mp": self.p_mp, "p_max_mp": self.p_max_mp,
            "m_hp": self.m_hp, "m_max_hp": self.m_max_hp, "m_atk": self.m_atk, "m_name": self.m_name,
            "potions": self.potions, "mp_potions": self.mp_potions, "buffs": self.buffs, "revives": self.revives,
            "is_special": int(self.is_special), "update_progress": self.update_progress
        }
        await db.save_dungeon_run(self.user_id, data)

    @discord.ui.button(label="공격", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def attack(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id: return

        dmg = max(1, self.p_atk - 0)
        crit = random.random() < 0.1
        if crit: dmg = int(dmg * 1.5)

        self.m_hp = max(0, self.m_hp - dmg)
        self.logs.append(f"⚔️ {self.m_name}에게 {dmg}의 피해! {'(치명타!)' if crit else ''}")

        if self.m_hp <= 0:
            await self.win(interaction)
            return

        await self.monster_turn(interaction)

    async def monster_turn(self, interaction):
        m_dmg = max(1, self.m_atk - self.p_def)
        dodge = random.random() < 0.05
        if dodge:
            self.logs.append(f"💨 {self.m_name}의 공격을 회피했습니다!")
        else:
            self.p_hp = max(0, self.p_hp - m_dmg)
            self.logs.append(f"🩸 {self.m_name}에게 {m_dmg}의 피해를 입었습니다.")

        if self.p_hp <= 0:
            if self.revives > 0:
                self.revives -= 1
                self.p_hp = self.p_max_hp // 2
                self.logs.append("👼 부활의 돌을 사용하여 부활했습니다!")
                await db.remove_item(self.user_id, "부활의 돌", 1)
            else:
                await self.lose(interaction)
                return

        await self.save_state()
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="스킬", style=discord.ButtonStyle.primary, emoji="⚡")
    async def skill(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id: return
        dmg = int(self.p_atk * 2.5)
        self.m_hp = max(0, self.m_hp - dmg)
        self.logs.append(f"⚡ 강타! {self.m_name}에게 {dmg}의 피해!")

        if self.m_hp <= 0:
            await self.win(interaction)
            return
        await self.monster_turn(interaction)

    @discord.ui.button(label="물약", style=discord.ButtonStyle.success, emoji="🧪")
    async def potion(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id: return
        if self.potions > 0:
            self.potions -= 1
            heal = 50
            self.p_hp = min(self.p_max_hp, self.p_hp + heal)
            self.logs.append(f"🧪 HP 물약 사용! 체력 {heal} 회복.")
            await db.remove_item(self.user_id, "HP 물약", 1)
            await self.save_state()
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.send_message("물약이 없습니다!", ephemeral=True)

    @discord.ui.button(label="도망", style=discord.ButtonStyle.secondary, emoji="🏃")
    async def flee(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id: return
        await db.delete_dungeon_run(self.user_id)
        await interaction.response.edit_message(content="🏃 도망쳤습니다...", embed=None, view=None)

    async def win(self, interaction):
        await db.delete_dungeon_run(self.user_id)

        reward_mult = 3 if self.is_special else 1
        reward = self.stage * 1000 * reward_mult
        await db.update_balance(self.user_id, reward)

        drops = []
        if random.random() < 0.3:
            await db.add_item(self.user_id, "철광석", 1)
            drops.append("철광석")

        drop_text = ", ".join(drops) if drops else "없음"

        embed = discord.Embed(title="🎉 승리!", description=f"**{self.m_name}** 처치!\n보상: {reward:,} 젤리\n전리품: {drop_text}", color=discord.Color.green())

        if self.update_progress:
            await db.update_dungeon_progress(self.user_id, self.stage + 1)
            embed.set_footer(text=f"다음 스테이지({self.stage + 1})가 개방되었습니다!")

        await db.add_dungeon_record(self.user_id, self.stage, "win", reward, drop_text, 0, self.is_special, "Clear")

        await interaction.response.edit_message(embed=embed, view=None)

    async def lose(self, interaction):
        await db.delete_dungeon_run(self.user_id)
        embed = discord.Embed(title="💀 패배...", description=f"**{self.m_name}**에게 쓰러졌습니다...\n강해져서 다시 돌아오세요.", color=discord.Color.dark_grey())
        await db.add_dungeon_record(self.user_id, self.stage, "loss", 0, "", 0, self.is_special, "Dead")
        await interaction.response.edit_message(embed=embed, view=None)

async def setup(bot):
    await bot.add_cog(Economy(bot))
