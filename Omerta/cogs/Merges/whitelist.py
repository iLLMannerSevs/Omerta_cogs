import io
import logging
import re

import discord
from aiohttp import ClientSession
from discord import Embed, File
from discord.ext import commands


class Whitelist(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.logger.info(f'The Extension was loaded successfully')

    @commands.group(name='whitelist', description='Manages the Whitelist of the Server', aliases=['wl'])
    #  @commands.has_any_role('Bot Admin', 'Bot Administrator', 'Admin', 'Administrator', 'Administration', 'Bot Mod',
    #                    'Moderator', 'Bot Moderator', 'Moderation')
    #   @commands.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    async def whitelist(self, ctx: commands.Context) -> discord.Message:
        if ctx.invoked_subcommand is None:
            embed = Embed(title='__**Invalid Command Usage**__',
                        description='Following Commands are available:', color=0Xbb1e1e)

            subcommands = self.whitelist.walk_commands()

            for subcommand in subcommands:
                scName = subcommand.name
                scUsage = subcommand.usage
                scDescription = subcommand.description

                if scUsage is None:
                    scUsage = ''

                embed.add_field(name=f'__**{scName}**__',
                                value=f'_{scDescription}_\n```\n!whitelist {scName} {scUsage}```',
                                inline=False)

            embed.set_footer(text='<> = Required | [] = Optional', icon_url=ctx.author.avatar_url)

            return await ctx.send(embed=embed)

    @whitelist.command(name='show', description='Shows the Whitelist of the Server.')
    async def show(self, ctx: commands.Context) -> discord.Message:
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            async with sess.get(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers',
                                headers=headers) as res:
                if res.status != 200:
                    return await ctx.send(
                    embed = Embed(title=f'\n » Nitrapi Error RSC »',
                                timestamp=ctx.message.created_at, description=f'\n Nitrado API Error. Failed to request Information from the Server. (RSC: {res.status})'))
                else:
                    json = await res.json()
                    wl = json['data']['gameserver']['settings']['general']['whitelist']
                    embed = Embed(title=f'__**Whitelist**__', color=0X000001,
                                timestamp=ctx.message.created_at, description=f'')
                    embed.set_footer(icon_url=ctx.author.avatar_url, text=ctx.author.name)
                    if wl == '':
                        embed.description += '`Empty`'
                        return await ctx.send(embed=embed)
                    else:
                        wlList = wl.split()
                        embed.description += f'Whitelist User Count: {len(wlList)}'
                        for userName in wlList:
                            embed.description += f' \n > • {user Name}'
                        if len(embed.description) > 2000:
                            embed.description = re.sub(r'+', '', embed.description)
                            whitelistFile = io.BytesIO(embed.description.encode('utf-8'))
                            return await ctx.send(
                                f'```\nThe Whitelist of the Server is too long to send it trough a '
                                f'Embed.```',
                                file=File(whitelistFile, 'whitelist.txt'))
                        else:
                            return await ctx.send(embed=embed)

    @whitelist.command(name='add', description='Adds a User to the Whitelist of a Server.', usage='<User>')
    async def add(self, ctx: commands.Context, *, ign: str) -> discord.Message:
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            async with sess.get(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers',
                                headers=headers) as res:
                if res.status != 200:
                    return await ctx.send(
                        f'```\nNitrado API Error. Failed to request Information from the Server. (Response Status Code: {res.status})```')
                else:
                    json = await res.json()
                    wl = json['data']['gameserver']['settings']['general']['whitelist']
                    if re.search(f'{ign}', wl):
                        return await ctx.send(f'{ign} is already on the Whitelist of the Server.')
                    else:
                        if wl == '':
                            value = f'{ign}'
                        else:
                            value = f'{wl}\n{ign}'
                        params = {'category': 'general', 'key': 'whitelist', 'value': 'value'}
                        async with sess.post(
                                f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers/settings',
                                headers=headers, params=params) as response:
                            if response.status != 200:
                                return await ctx.send(
                                    f'```\nNitrado API Error while trying to Update the Whitelist. (Status Code: {res.status})```')
                            else:
                                return await ctx.send(f'Added {ign} to the Whitelist of the Server.')

    @whitelist.command(name='remove', description='Removes a User from the Whitelist of the Server.', usage='<User>')
    async def remove(self, ctx: commands.Context, *, ign: str) -> discord.Message:
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            async with sess.get(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers',
                                headers=headers) as res:
                if res.status != 200:
                    return await ctx.send(
                        f'```\nNitrado API Error. Failed to request Information from the Server. (Response Status Code: {res.status})```')
                else:
                    json = await res.json()
                    wl = json['data']['gameserver']['settings']['general']['whitelist']
                    if not re.search(f'{ign}', wl):
                        return await ctx.send(f'{ign} is not on the Whitelist of the Server.')
                    else:
                        wl = wl.strip()
                        wl = re.sub(rf'{ign}', '', wl)
                        wl = re.sub('\n+', '\r', wl)
                        wl = re.sub('\n', '\r', wl)
                        wl = re.sub('\r+', '\r', wl)
                        wl = re.sub('\r\n+', '\r', wl)
                        wl = re.sub('\n\n+', '\r', wl)
                        wl = re.sub('\r\r+', '\r', wl)
                        wl = re.sub('\n', '\r', wl)
                        wl = wl.strip()

                        value = f'{wl}'

                        params = {'category': 'general', 'key': 'whitelist', 'value': value}
                        async with sess.post(
                                f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers/settings',
                                headers=headers, params=params) as resp:
                            if resp.status != 200:
                                return await ctx.send(
                                    f'```\nNitrado API Error while trying to Update the Whitelist. (Status Code: {resp.status})```')
                            else:
                                return await ctx.send(
                                    f'Removed {ign} from the Whitelist of the Server.')


def setup(bot) -> None:
    bot.add_cog(Whitelist(bot))
