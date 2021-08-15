import io
import logging
import re

import discord
from aiohttp import ClientSession
from discord import Embed, File
from discord.ext import commands


class Banlist(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.logger.info(f'The Extension was loaded successfully')

    @commands.group(name='banlist', description='Manages the Banlist of the Server', aliases=['bl'])
    @commands.has_any_role('Admin','Administration* (C)', 'Chat Moderator (D)', 'Lead Moderator (G)', 'Staff (A)', 'Gameserver Lead')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    async def banlist(self, ctx: commands.Context) -> discord.Message:
        if ctx.invoked_subcommand is None:
            embed = Embed(title='__**Invalid Command Usage**__',
                        description='Following Commands are available:', color=0Xbb1e1e)

            subcommands = self.banlist.walk_commands()

            for subcommand in subcommands:
                scName = subcommand.name
                scUsage = subcommand.usage
                scDescription = subcommand.description

                if scUsage is None:
                    scUsage = ''

                embed.add_field(name=f'__**{scName}**__',
                                value=f'_{scDescription}_\n```\n!banlist {scName} {scUsage}```',
                                inline=False)

            embed.set_footer(text='<> = Required | [] = Optional', icon_url=ctx.author.avatar_url)

            return await ctx.send(embed=embed)

    @banlist.command(name='show', description='Shows the Banlist of the Server.')
    async def show(self, ctx: commands.Context) -> discord.Message:
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            async with sess.get(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers',
                                headers=headers) as res:
                if res.status != 200:
                    return await ctx.send(
                        f'```\nNitrado API Error. Failed to request Information from the Server. (Response Status Code: {res.status})```')
                else:
                    json = await res.json()
                    bl = json['data']['gameserver']['settings']['general']['bans']
                    embed = Embed(title=f'__**Banlist**__', color=0X000001,
                                timestamp=ctx.message.created_at, description=f'')
                    embed.set_footer(icon_url=ctx.author.avatar_url, text=ctx.author.name)
                    if bl == '':
                        embed.description += '`Empty`'
                        return await ctx.send(embed=embed)
                    else:
                        blList = bl.split()
                        embed.description += f'Banlist User Count: {len(blList)}'
                        for userName in blList:
                            embed.description += f'\n`• {userName}`'
                        if len(embed.description) > 2000:
                            embed.description = re.sub(r'`+', '', embed.description)
                            banlistFile = io.BytesIO(embed.description.encode('utf-8'))
                            return await ctx.send(
                                f'```\nThe Banlist of the Server is too long to send it trough a '
                                f'Embed.```',
                                file=File(banlistFile, 'banlist.txt'))
                        else:
                            return await ctx.send(embed=embed)

    @banlist.command(name='add', description='Adds a User to the Banlist of a Server.', usage='<User>')
    async def add(self, ctx: commands.Context, ign: str) -> discord.Message:
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            async with sess.get(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers',
                                headers=headers) as res:
                if res.status != 200:
                    return await ctx.send(
                        f'```\nNitrado API Error. Failed to request Information from the Server. (Response Status Code: {res.status})```')
                else:
                    json = await res.json()
                    bl = json['data']['gameserver']['settings']['general']['bans']
                    if re.search(f'{ign}', bl):
                        return await ctx.send(f'{ign} is already on the Banlist of the Server.')
                    else:
                        if bl == '':
                            value = f'{ign}'
                        else:
                            value = f'{bl}\r{ign}'
                        params = {'category': 'general', 'key': 'bans', 'value': value}
                        async with sess.post(
                                f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers/settings',
                                headers=headers, params=params) as response:
                            if response.status != 200:
                                return await ctx.send(
                                    f'```\nNitrado API Error while trying to Update the Banlist. (Status Code: {res.status})```')
                            else:
                                return await ctx.send(f'Added {ign} to the Banlist of the Server.')

    @banlist.command(name='remove', description='Removes a User from the Banlist of the Server.', usage='<User>')
    async def remove(self, ctx: commands.Context, ign: str) -> discord.Message:
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            async with sess.get(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers',
                                headers=headers) as res:
                if res.status != 200:
                    return await ctx.send(
                        f'```\nNitrado API Error. Failed to request Information from the Server. (Response Status Code: {res.status})```')
                else:
                    json = await res.json()
                    bl = json['data']['gameserver']['settings']['general']['bans']
                    if not re.search(f'{ign}', bl):
                        return await ctx.send(f'{ign} is not on the Banlist of the Server.')
                    else:
                        bl = bl.strip()
                        bl = re.sub(rf'{ign}', '', bl)
                        bl = re.sub('\n+', '\r', bl)
                        bl = re.sub('\n', '\r', bl)
                        bl = re.sub('\r+', '\r', bl)
                        bl = re.sub('\r\n+', '\r', bl)
                        bl = re.sub('\n\n+', '\r', bl)
                        bl = re.sub('\r\r+', '\r', bl)
                        bl = re.sub('\n', '\r', bl)
                        bl = bl.strip()

                        value = f'{bl}'

                        params = {'category': 'general', 'key': 'bans', 'value': value}
                        async with sess.post(
                                f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers/settings',
                                headers=headers, params=params) as resp:
                            if resp.status != 200:
                                return await ctx.send(
                                    f'```\nNitrado API Error while trying to Update the Banlist. (Status Code: {resp.status})```')
                            else:
                                return await ctx.send(
                                    f'Removed {ign} from the Banlist of the Server.')


def setup(bot) -> None:
    bot.add_cog(Banlist(bot))
