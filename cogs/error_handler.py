import discord
from discord.ext import commands
from discord import app_commands

class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _send_ephemeral(self, interaction: discord.Interaction, content: str):
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True)
        else:
            await interaction.response.send_message(content, ephemeral=True)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):

        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(f"🚫 권한이 부족해요! ({', '.join(error.missing_permissions)})", delete_after=10)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ 조금만 기다려주세요! {int(error.retry_after)}초 뒤에 다시 시도할 수 있어요.", delete_after=10)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("🚫 올바르지 않은 값이 입력되었어요. 다시 확인해주세요.", delete_after=10)
        elif isinstance(error, commands.NoPrivateMessage):
             await ctx.send("🚫 이 명령어는 서버에서만 사용할 수 있어요.", delete_after=10)
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("🚫 이 명령어를 사용할 수 없어요.", delete_after=10)
        else:
            print(f"Unhandled error in {ctx.command}: {error}")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):

        if isinstance(error, app_commands.CommandOnCooldown):
            await self._send_ephemeral(interaction, f"⏳ 조금만 기다려주세요! {int(error.retry_after)}초 뒤에 다시 시도할 수 있어요.")
        elif isinstance(error, app_commands.MissingPermissions):
            await self._send_ephemeral(interaction, f"🚫 권한이 부족해요! ({', '.join(error.missing_permissions)})")
        elif isinstance(error, app_commands.CheckFailure):
            await self._send_ephemeral(interaction, "🚫 이 명령어를 사용할 수 없어요.")
        else:
            print(f"App command error: {error}")
            await self._send_ephemeral(interaction, "❌ 오류가 발생했어요. 잠시 후 다시 시도해주세요.")

    def cog_load(self):
        tree = self.bot.tree
        self._old_tree_error = tree.on_error
        tree.on_error = self.on_app_command_error

    def cog_unload(self):
        tree = self.bot.tree
        tree.on_error = self._old_tree_error

async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
