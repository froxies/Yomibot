import discord
from discord.ext import commands
import aiohttp
import datetime
import utils.time_utils as time_utils
import sys
import os
import utils.db as db
class AdvancedLogging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    async def send_log(self, guild, embed):
        webhook_url = await db.get_guild_setting(str(guild.id), "log_webhook_url")
        if not webhook_url:
            log_channel_id = await db.get_guild_setting(str(guild.id), "log_channel")
            if log_channel_id:
                channel = guild.get_channel(int(log_channel_id))
                if channel:
                    try:
                        await channel.send(embed=embed)
                    except:
                        pass
            return
        async with aiohttp.ClientSession() as session:
            try:
                webhook = discord.Webhook.from_url(webhook_url, session=session)
                await webhook.send(embed=embed, username="요미 로그 시스템", avatar_url=self.bot.user.display_avatar.url)
            except discord.NotFound:
                await db.set_guild_setting(str(guild.id), "log_webhook_url", "")
            except Exception as e:
                print(f"Log Webhook Error: {e}")
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return
        embed = discord.Embed(title="🗑️ 메시지 삭제됨", color=discord.Color.red(), timestamp=time_utils.get_kst_now())
        embed.set_author(name=f"{message.author} ({message.author.id})", icon_url=message.author.display_avatar.url)
        embed.add_field(name="채널", value=message.channel.mention, inline=True)
        content = message.content
        if not content:
            content = "(내용 없음 / 이미지 또는 임베드)"
        if len(content) > 1000:
            content = content[:1000] + "..."
        embed.add_field(name="내용", value=content, inline=False)
        if message.attachments:
            files = "\n".join([a.filename for a in message.attachments])
            embed.add_field(name="첨부파일", value=files, inline=False)
        await self.send_log(message.guild, embed)
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return
        embed = discord.Embed(title="✏️ 메시지 수정됨", color=discord.Color.orange(), timestamp=time_utils.get_kst_now())
        embed.set_author(name=f"{before.author} ({before.author.id})", icon_url=before.author.display_avatar.url)
        embed.add_field(name="채널", value=before.channel.mention, inline=True)
        embed.add_field(name="이동", value=f"[메시지로 이동]({before.jump_url})", inline=True)
        before_content = before.content if before.content else "(내용 없음)"
        after_content = after.content if after.content else "(내용 없음)"
        if len(before_content) > 1000: before_content = before_content[:1000] + "..."
        if len(after_content) > 1000: after_content = after_content[:1000] + "..."
        embed.add_field(name="수정 전", value=before_content, inline=False)
        embed.add_field(name="수정 후", value=after_content, inline=False)
        await self.send_log(before.guild, embed)
    @commands.Cog.listener()
    async def on_member_join(self, member):
        embed = discord.Embed(title="📥 멤버 입장", color=discord.Color.green(), timestamp=time_utils.get_kst_now())
        embed.set_author(name=f"{member} ({member.id})", icon_url=member.display_avatar.url)
        created_at = member.created_at.strftime("%Y-%m-%d %H:%M:%S")
        embed.add_field(name="계정 생성일", value=created_at, inline=False)
        embed.set_footer(text=f"현재 멤버 수: {member.guild.member_count}명")
        await self.send_log(member.guild, embed)
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        embed = discord.Embed(title="📤 멤버 퇴장", color=discord.Color.dark_grey(), timestamp=time_utils.get_kst_now())
        embed.set_author(name=f"{member} ({member.id})", icon_url=member.display_avatar.url)
        joined_at = member.joined_at.strftime("%Y-%m-%d %H:%M:%S") if member.joined_at else "알 수 없음"
        embed.add_field(name="가입일", value=joined_at, inline=False)
        if member.joined_at:
            period = (time_utils.get_kst_now() - time_utils.to_kst(member.joined_at)).days
            embed.add_field(name="활동 기간", value=f"{period}일", inline=True)
        embed.set_footer(text=f"현재 멤버 수: {member.guild.member_count}명")
        await self.send_log(member.guild, embed)
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        if before.channel is None and after.channel is not None:
            embed = discord.Embed(title="🔊 음성 채널 입장", color=discord.Color.blue(), timestamp=time_utils.get_kst_now())
            embed.set_author(name=f"{member}", icon_url=member.display_avatar.url)
            embed.add_field(name="채널", value=after.channel.name, inline=False)
            await self.send_log(member.guild, embed)
        elif before.channel is not None and after.channel is None:
            embed = discord.Embed(title="🔇 음성 채널 퇴장", color=discord.Color.dark_blue(), timestamp=time_utils.get_kst_now())
            embed.set_author(name=f"{member}", icon_url=member.display_avatar.url)
            embed.add_field(name="채널", value=before.channel.name, inline=False)
            await self.send_log(member.guild, embed)
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            embed = discord.Embed(title="↔️ 음성 채널 이동", color=discord.Color.blue(), timestamp=time_utils.get_kst_now())
            embed.set_author(name=f"{member}", icon_url=member.display_avatar.url)
            embed.add_field(name="이전 채널", value=before.channel.name, inline=True)
            embed.add_field(name="현재 채널", value=after.channel.name, inline=True)
            await self.send_log(member.guild, embed)
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed = discord.Embed(title="🆕 채널 생성됨", color=discord.Color.green(), timestamp=time_utils.get_kst_now())
        embed.add_field(name="채널명", value=f"{channel.name} ({channel.mention})", inline=False)
        embed.add_field(name="카테고리", value=channel.category.name if channel.category else "없음", inline=True)
        await self.send_log(channel.guild, embed)
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed = discord.Embed(title="🗑️ 채널 삭제됨", color=discord.Color.red(), timestamp=time_utils.get_kst_now())
        embed.add_field(name="채널명", value=channel.name, inline=False)
        embed.add_field(name="카테고리", value=channel.category.name if channel.category else "없음", inline=True)
        await self.send_log(channel.guild, embed)
async def setup(bot):
    await bot.add_cog(AdvancedLogging(bot))