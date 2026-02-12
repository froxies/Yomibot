import discord
from discord import app_commands
from discord.ext import commands
from utils import db
import json
from typing import Optional, List
from datetime import datetime
import re
def resolve_emoji(bot, emoji_str: str) -> Optional[str]:
    if not emoji_str:
        return None
    custom_emoji_pattern = re.compile(r'<(a?):(\w+):(\d+)>')
    if custom_emoji_pattern.match(emoji_str):
        return emoji_str
    if emoji_str.startswith(':') and emoji_str.endswith(':'):
        emoji_name = emoji_str[1:-1]
        for emoji in bot.emojis:
            if emoji.name == emoji_name:
                return str(emoji)
    return emoji_str
class SelfRoleButton(discord.ui.Button):
    def __init__(self, role_id: int, label: str, emoji: Optional[str] = None):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"self_role:{role_id}",
            emoji=emoji
        )
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.custom_id.split(":")[1])
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("어라? 이 역할이 서버에서 사라진 것 같아요... (｡•́︿•̀｡)", ephemeral=True)
            return
        if role in interaction.user.roles:
            try:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(f"✅ **{role.name}** 역할을 가져갔어요! 다시 필요하면 말씀해주세요! (✿◡‿◡)", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("힝... 역할을 뺏을 권한이 없어요. 제 역할 순위가 더 낮나봐요! ( >﹏< )", ephemeral=True)
        else:
            try:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"✅ **{role.name}** 역할을 드렸어요! 재미있게 즐겨주세요! (≧∇≦)ﾉ", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("힝... 저한테 이 역할을 줄 수 있는 권한이 없어요. 제 역할 순위가 더 낮나봐요! ( >﹏< )", ephemeral=True)
class SelfRoleSelect(discord.ui.Select):
    def __init__(self, roles_data):
        options = []
        for data in roles_data:
            emoji = data.get('emoji')
            options.append(discord.SelectOption(
                label=data['label'],
                value=str(data['role_id']),
                emoji=emoji,
                description="클릭하여 선택 (다중 선택 가능)"
            ))
        super().__init__(placeholder="원하는 역할을 선택하세요... ✨", min_values=0, max_values=len(options), options=options, custom_id="self_role_select")
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        added = []
        removed = []
        selected_ids = [int(val) for val in self.values]
        managed_role_ids = [int(opt.value) for opt in self.options]
        for role_id in managed_role_ids:
            role = interaction.guild.get_role(role_id)
            if not role: continue
            if role_id in selected_ids:
                if role not in interaction.user.roles:
                    try:
                        await interaction.user.add_roles(role)
                        added.append(role.name)
                    except: pass
            else:
                if role in interaction.user.roles:
                    try:
                        await interaction.user.remove_roles(role)
                        removed.append(role.name)
                    except: pass
        msg = []
        if added: msg.append(f"✅ 추가됨: {', '.join(added)}")
        if removed: msg.append(f"🗑️ 제거됨: {', '.join(removed)}")
        if not msg:
            msg.append("변경된 사항이 없어요!")
        await interaction.followup.send("\n".join(msg), ephemeral=True)
class SelfRoleView(discord.ui.View):
    def __init__(self, roles_data: List[dict], style: str = 'button'):
        super().__init__(timeout=None)
        if style == 'select':
            self.add_item(SelfRoleSelect(roles_data))
        else:
            for data in roles_data:
                self.add_item(SelfRoleButton(
                    role_id=data['role_id'],
                    label=data['label'],
                    emoji=data.get('emoji')
                ))
class RoleCreationView(discord.ui.View):
    def __init__(self, bot, interaction, missing_roles, preset_data):
        super().__init__(timeout=60)
        self.bot = bot
        self.original_interaction = interaction
        self.missing_roles = missing_roles
        self.preset_data = preset_data
        self.value = False
    @discord.ui.button(label="네! 만들어주세요! (자동 생성)", style=discord.ButtonStyle.green, emoji="🛠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("이 버튼은 명령어를 실행한 사람만 누를 수 있어요!", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        created_count = 0
        for role_name in self.missing_roles:
            try:
                import random
                color = discord.Color.from_rgb(random.randint(150, 255), random.randint(150, 255), random.randint(150, 255))
                await interaction.guild.create_role(name=role_name, color=color, reason="요미 봇 게임 역할 자동 생성")
                created_count += 1
            except discord.Forbidden:
                await interaction.followup.send("으앙, 권한이 없어서 역할을 못 만들었어요... 봇의 권한을 확인해주세요!", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"오류가 발생했어요: {e}", ephemeral=True)
                return
        await interaction.followup.send(f"✅ 뚝딱뚝딱! **{created_count}**개의 역할을 새로 만들었어요! 이제 패널을 생성할게요!", ephemeral=True)
        self.value = True
        self.stop()
    @discord.ui.button(label="아니요, 괜찮아요", style=discord.ButtonStyle.grey, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("이 버튼은 명령어를 실행한 사람만 누를 수 있어요!", ephemeral=True)
            return
        await interaction.response.send_message("알겠어요! 작업이 취소되었어요.", ephemeral=True)
        self.value = False
        self.stop()
class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    @app_commands.command(name="역할지급", description="버튼을 눌러 역할을 받을 수 있는 메시지를 만들어요! (≧∇≦)ﾉ")
    @app_commands.describe(
        title="메시지 제목 (예: FPS / 액션)",
        description="메시지 설명 (예: 버튼을 누르면 역할이 지급됩니다.)",
        role1="역할 1", emoji1="역할 1의 이모지",
        role2="역할 2", emoji2="역할 2의 이모지",
        role3="역할 3", emoji3="역할 3의 이모지",
        role4="역할 4", emoji4="역할 4의 이모지",
        role5="역할 5", emoji5="역할 5의 이모지",
        role6="역할 6", emoji6="역할 6의 이모지",
        role7="역할 7", emoji7="역할 7의 이모지",
        role8="역할 8", emoji8="역할 8의 이모지",
        role9="역할 9", emoji9="역할 9의 이모지",
        role10="역할 10", emoji10="역할 10의 이모지",
        image_url="이미지 URL (선택 사항)",
        color="임베드 색상 (Hex 코드, 예: #ff0000)",
        style="스타일 (버튼/선택메뉴)"
    )
    @app_commands.rename(
        title="제목", description="설명", image_url="이미지_주소", color="색상", style="스타일",
        role1="역할1", emoji1="이모지1", role2="역할2", emoji2="이모지2",
        role3="역할3", emoji3="이모지3", role4="역할4", emoji4="이모지4",
        role5="역할5", emoji5="이모지5", role6="역할6", emoji6="이모지6",
        role7="역할7", emoji7="이모지7", role8="역할8", emoji8="이모지8",
        role9="역할9", emoji9="이모지9", role10="역할10", emoji10="이모지10"
    )
    @app_commands.choices(style=[
        app_commands.Choice(name="버튼 (기본)", value="button"),
        app_commands.Choice(name="선택 메뉴 (드롭다운)", value="select")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def self_role(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        role1: discord.Role,
        emoji1: Optional[str] = None,
        role2: Optional[discord.Role] = None,
        emoji2: Optional[str] = None,
        role3: Optional[discord.Role] = None,
        emoji3: Optional[str] = None,
        role4: Optional[discord.Role] = None,
        emoji4: Optional[str] = None,
        role5: Optional[discord.Role] = None,
        emoji5: Optional[str] = None,
        role6: Optional[discord.Role] = None,
        emoji6: Optional[str] = None,
        role7: Optional[discord.Role] = None,
        emoji7: Optional[str] = None,
        role8: Optional[discord.Role] = None,
        emoji8: Optional[str] = None,
        role9: Optional[discord.Role] = None,
        emoji9: Optional[str] = None,
        role10: Optional[discord.Role] = None,
        emoji10: Optional[str] = None,
        image_url: Optional[str] = None,
        color: Optional[str] = None,
        style: app_commands.Choice[str] = None
    ):
        role_pairs = [
            (role1, emoji1), (role2, emoji2), (role3, emoji3), (role4, emoji4), (role5, emoji5),
            (role6, emoji6), (role7, emoji7), (role8, emoji8), (role9, emoji9), (role10, emoji10)
        ]
        roles_data = []
        for role, emoji in role_pairs:
            if role is None:
                continue
            resolved_emoji = resolve_emoji(self.bot, emoji)
            roles_data.append({
                'role_id': role.id,
                'label': role.name,
                'emoji': resolved_emoji
            })
        embed_color = discord.Color.blue()
        if color:
            try:
                if color.startswith("#"):
                    embed_color = discord.Color(int(color[1:], 16))
                else:
                    embed_color = discord.Color(int(color, 16))
            except:
                pass
        embed = discord.Embed(
            title=title,
            description=description,
            color=embed_color
        )
        if image_url:
            embed.set_image(url=image_url)
        embed.set_footer(text=f"{interaction.guild.name} • 요미의 역할 센터")
        view_style = style.value if style else "button"
        view = SelfRoleView(roles_data, style=view_style)
        await interaction.response.send_message("✅ 역할 지급 메시지를 생성 중이에요...", ephemeral=True)
        message = await interaction.channel.send(embed=embed, view=view)
        await db.add_self_role_message(
            str(message.id),
            str(interaction.channel.id),
            str(interaction.guild.id),
            json.dumps(roles_data),
            style=view_style
        )
    @app_commands.command(name="게임역할", description="게임 관련 역할을 지급하는 메시지를 생성해요! (설정된 프리셋)")
    @app_commands.checks.has_permissions(administrator=True)
    async def game_roles(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        preset = [
            ("리그 오브 레전드", ":G_001:"),
            ("발로란트", ":Jb_004:"),
            ("배틀그라운드", ":Jb_002:"),
            ("오버워치 2", ":Jb_009:"),
            ("로블록스", ":roblox:"),
            ("트릭컬 리바이브", ":trical:"),
            ("디아블로", ":Jb_019:"),
            ("GTA 5", ":Gb_015:"),
            ("스타크래프트", ":Gb_014:"),
            ("마인크래프트", ":minecraft:")
        ]
        roles_data = []
        not_found = []
        for role_name, emoji_str in preset:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if not role:
                not_found.append(role_name)
                continue
            resolved_emoji = resolve_emoji(self.bot, emoji_str)
            roles_data.append({
                'role_id': role.id,
                'label': role.name,
                'emoji': resolved_emoji
            })
        if not roles_data:
            await interaction.followup.send("힝... 역할을 하나도 찾지 못했어요. 역할 이름이 정확한지 확인해주세요!", ephemeral=True)
            return
        if not_found:
            await interaction.followup.send(f"⚠️ 다음 역할은 찾지 못해서 제외되었어요: {', '.join(not_found)}", ephemeral=True)
        embed = discord.Embed(
            title="게임",
            description="아래 버튼을 눌러 역할을 지급받아주세요!",
            color=discord.Color.blue()
        )
        embed.set_image(url="https://iili.io/fSGyh6Q.md.jpg")
        embed.set_footer(text=f"{interaction.guild.name} • 요미의 역할 센터")
        view = SelfRoleView(roles_data)
        message = await interaction.channel.send(embed=embed, view=view)
        await db.add_self_role_message(
            str(message.id),
            str(interaction.channel.id),
            str(interaction.guild.id),
            json.dumps(roles_data)
        )
        await interaction.followup.send("✅ 게임 역할 지급 메시지가 생성되었어요! ( •̀ ω •́ )✧", ephemeral=True)
    @app_commands.command(name="역할지급삭제", description="역할 지급 메시지를 데이터베이스에서 삭제해요. (메시지는 직접 지워주세요!)")
    @app_commands.describe(message_id="삭제할 메시지의 ID")
    @app_commands.rename(message_id="메시지_id")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_self_role(self, interaction: discord.Interaction, message_id: str):
        try:
            await db.delete_self_role_message(message_id)
            await interaction.response.send_message(f"✅ 메시지 ID `{message_id}`에 대한 정보를 데이터베이스에서 삭제했어요! ( •̀ ω •́ )✧", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"힝... 정보를 삭제하지 못했어요: {e}", ephemeral=True)
    @app_commands.command(name="고정역할설정", description="나갔다 들어온 유저의 역할을 자동으로 복구할지 설정해요.")
    @app_commands.choices(action=[
        app_commands.Choice(name="켜기", value="on"),
        app_commands.Choice(name="끄기", value="off")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def sticky_role_config(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        is_enabled = "True" if action.value == "on" else "False"
        await db.set_guild_setting(str(interaction.guild.id), "sticky_roles_enabled", is_enabled)
        await interaction.response.send_message(f"✅ 고정 역할 기능이 **{action.name}** 상태로 설정되었어요!", ephemeral=True)
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.bot: return
        is_enabled = await db.get_guild_setting(str(member.guild.id), "sticky_roles_enabled")
        if is_enabled != "True": return
        role_ids = [str(r.id) for r in member.roles if r != member.guild.default_role and not r.managed]
        if role_ids:
            await db.set_sticky_roles(str(member.guild.id), str(member.id), role_ids)
    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot: return
        is_enabled = await db.get_guild_setting(str(member.guild.id), "sticky_roles_enabled")
        if is_enabled != "True": return
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
    await bot.add_cog(Roles(bot))