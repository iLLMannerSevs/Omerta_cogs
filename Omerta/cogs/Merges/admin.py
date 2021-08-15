import logging

import discord
from aiohttp import ClientSession
from discord import Embed
from discord.ext import commands


class Admin(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.logger.info(f'The Extension was loaded successfully')

    @commands.group(name='admin', description='Manages the Gameserver.')
    @commands.has_any_role('Bot Admin', 'Bot Administrator', 'Admin', 'Administrator', 'Administration')
    @commands.has_guild_permissions(administrator=True)
    @commands.guild_only()
    async def admin(self, ctx: commands.Context) -> discord.Message:
        if ctx.invoked_subcommand is None:
            embed = Embed(title='__**Invalid Command Usage**__',
                        description='Following Commands are available:', color=0Xbb1e1e)

            subcommands = self.admin.walk_commands()

            for subcommand in subcommands:
                scName = subcommand.name
                scUsage = subcommand.usage
                scDescription = subcommand.description

                if scUsage is None:
                    scUsage = ''

                embed.add_field(name=f'__**{scName}**__',
                                value=f'_{scDescription}_\n```\n!admin {scName} {scUsage}```',
                                inline=False)

            embed.set_footer(text='<> = Required | [] = Optional', icon_url=ctx.author.avatar_url)

            return await ctx.send(embed=embed)

    @admin.command(name='unlink', description='Unlinks a Discord Account from a Ingame Profile.')
    async def unlink(self, ctx: commands.Context, member: discord.Member) -> discord.Message:
        async with self.bot.dbs.acquire() as conn:
            query_unlink_all = f'UPDATE "{self.bot.service_id}" SET discord_id = $1 WHERE discord_id = $2;'
            await conn.execute(query_unlink_all, 0, member.id)
        return await ctx.send(
            f'```\nUnlinked all Accounts from {member.name}#{member.discriminator}.```')

    @admin.command(name='link', description='Links a Discord Account to a Ingame Profile.')
    async def link(self, ctx: commands.Context, member: discord.Member, *, ign: str) -> discord.Message:
        async with self.bot.dbs.acquire() as conn:
            query_check = f'SELECT * FROM "{self.bot.service_id}" WHERE player_name = $1;'
            check = await conn.fetchrow(query_check, ign)
            if not check:
                return await ctx.send(f'```\nThere is no Record for {ign} on {self.bot.service_id}```')
            else:
                query_unlink_old = f'UPDATE "{self.bot.service_id}" SET discord_id = $1 WHERE discord_id = $2;'
                await conn.execute(query_unlink_old, 0, member.id)
                if check['discord_id'] == ctx.author.id:
                    return await ctx.send(
                        f'```\n{check["player_name"]} is already linked to {member.name}#{member.discriminator} on {self.bot.service_id}.```')
                else:
                    query = f'UPDATE "{self.bot.service_id}" SET discord_id = $1 WHERE player_name = $2;'
                    await conn.execute(query, member.id, ign)
                    return await ctx.send(
                        f'```\nLinked {ign} to {member.name}#{member.discriminator} on {self.bot.service_id}.```')

    @admin.command(name='restart', description='Restarts/Starts the Server.', aliases=['start'])
    async def restart(self, ctx: commands.Context) -> discord.Message:
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            params = {
                'message': f'Restart trough Administration Bot. User: {ctx.author.name}#{ctx.author.discriminator} ({ctx.author.id})'}
            async with sess.post(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers/restart',
                                headers=headers, params=params) as res:
                if res.status != 200:
                    return await ctx.send(
                        f'```\nNitrado API Error. Failed to restart the Server. (Response Status Code: {res.status})```')
                else:
                    return await ctx.send(f'```\nThe Server will be restarted now.```')

    @admin.command(name='stop', description='Stops the Server.')
    async def stop(self, ctx: commands.Context) -> discord.Message:
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            params = {
                'message': f'Stop trough Administration Bot. User: {ctx.author.name}#{ctx.author.discriminator} ({ctx.author.id})'}
            async with sess.post(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers/stop',
                                headers=headers, params=params) as res:
                if res.status != 200:
                    return await ctx.send(
                        f'```\nNitrado API Error. Failed to stop the Server. (Response Status Code: {res.status})```')
                else:
                    return await ctx.send(f'```\nThe Server will be stopped now.```')

    @admin.command(name='usage', description='Shows the Usage of the Server from a specified amount of Time.',
            usage='[Hours]')
    async def usage(self, ctx: commands.Context, hours: int = None) -> discord.Message:
        if hours is None:
            time = 24
        else:
            time = int(hours)
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            params = {'hours': time}
            async with sess.get(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers/stats',
                                headers=headers, params=params) as res:
                if res.status != 200:
                    return await ctx.send(
                        f'```\nNitrado API Error. Failed to request Usage from the Server. (Response Status Code: {res.status})```')
                else:
                    json = await res.json()
                    cpu_usage_values = json['data']['stats']['cpuUsage']
                    ram_usage_values = json['data']['stats']['memoryUsage']
                    cpu_values: list[float] = []
                    ram_values: list[float] = []
                    for (x, _) in cpu_usage_values:
                        if x is None:
                            cpu_values.append(0.0)
                        else:
                            cpu_values.append(x)
                    for (x, _) in ram_usage_values:
                        if x is None:
                            ram_values.append(0.0)
                        else:
                            ram_values.append(x)
                    cpu_usage = round(sum(cpu_values) / len(cpu_values), 2)
                    ram_usage = round(sum(ram_values) / len(ram_values), 2)

                    embed = Embed(title=f'__**Usage for the last {time} hours**__', color=0X000001,
                                timestamp=ctx.message.created_at)
                    embed.add_field(name='**Average CPU Usage**', value=f'```\n{cpu_usage}%```', inline=False)
                    embed.add_field(name='**Average RAM Usage**', value=f'```\n{ram_usage}MB```', inline=False)
                    return await ctx.send(embed=embed)

    @admin.command(name='info', description='Shows detailed Information of the Server.',
                aliases=['status', 'information', 'server'])
    async def info(self, ctx: commands.Context) -> discord.Message:
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            async with sess.get(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers',
                                headers=headers) as res:
                if res.status != 200:
                    return await ctx.send(
                        f'```\nNitrado API Error. Failed to request Information from the Server. (Response Status Code: {res.status})```')
                else:
                    json = await res.json()
                    status = json['data']['gameserver']['status']
                    serverName = json['data']['gameserver']['settings']['config']['hostname']
                    slots = json['data']['gameserver']['slots']
                    try:
                        playerCurrent = json['data']['gameserver']['query']['player_current']
                    except KeyError:
                        playerCurrent = 0
                    serverMap = json['data']['gameserver']['query']['map']
                    dayzMap = 'Chernarus' if serverMap == 'dayzOffline.chernarusplus' else 'Livonia'
                    hmLinux = json['data']['gameserver']['hostsystems']['linux']['status']
                    hmWindows = json['data']['gameserver']['hostsystems']['windows']['status']
                    upToDate = '✔' if json['data']['gameserver']['game_specific'][
                                        'update_status'] == 'up_to_date' else '❌'
                    password_str = json['data']['gameserver']['settings']['config']['password']
                    password = str(password_str) if not password_str == '' else 'No Password'
                    dayTimeFactor = json['data']['gameserver']['settings']['config'][
                        'serverTimeAcceleration']
                    nightTimeFactor = json['data']['gameserver']['settings']['config'][
                        'serverNightTimeAcceleration']
                    dayTime = float(round(24.0 / float(
                        dayTimeFactor), 2))
                    nightTime = float(round(12.0 / (float(dayTimeFactor) * float(nightTimeFactor)), 2))
                    thirdPerson = '✔' if json['data']['gameserver']['settings']['config'][
                                            'disable3rdPerson'] == '0' else '❌'
                    crossHair = '✔' if json['data']['gameserver']['settings']['config'][
                                        'disableCrosshair'] == '0' else '❌'
                    mnk = '✔' if json['data']['gameserver']['settings']['config'][
                                    'enableMouseAndKeyboard'] == '1' else '❌'
                    wl = '✔' if json['data']['gameserver']['settings']['config'][
                                    'enableWhitelist'] == '1' else '❌'
                    brightNight = '✔' if json['data']['gameserver']['settings']['config'][
                                            'lightingConfig'] == '0' else '❌'
                    bd = '✔' if json['data']['gameserver']['settings']['config'][
                                    'disableBaseDamage'] == '0' else '❌'
                    cd = '✔' if json['data']['gameserver']['settings']['config'][
                                    'disableContainerDamage'] == '0' else '❌'

                    embed = Embed(title=f'__**Server Information**__',
                                timestamp=ctx.message.created_at, color=0X000001)
                    embed.add_field(name='__**Server Name**__', value=f'```\n{serverName}```',
                                    inline=False)
                    embed.add_field(name='__**Server Status**__', value=f'```\n{status}```',
                                    inline=False)
                    embed.add_field(name='__**Host-System Status (Linux)**__', value=f'```\n{hmLinux}```',
                                    inline=False)
                    embed.add_field(name='__**Host-System Status (Windows)**__',
                                    value=f'```\n{hmWindows}```',
                                    inline=False)
                    embed.add_field(name='__**Online**__', value=f'```\n({playerCurrent}/{slots})```',
                                    inline=False)
                    embed.add_field(name='__**Server is up to date**__', value=f'```\n{upToDate}```',
                                    inline=False)
                    embed.add_field(name='__**Map**__', value=f'```\n{dayzMap}```',
                                    inline=False)
                    embed.add_field(name='__**Password**__', value=f'```\n{password}```',
                                    inline=False)
                    embed.add_field(name='__**Daytime**__', value=f'```\n{dayTime}h```',
                                    inline=False)
                    embed.add_field(name='__**Nighttime**__', value=f'```\n{nightTime}h```',
                                    inline=False)
                    embed.add_field(name='__**Third Person**__', value=f'```\n{thirdPerson}```',
                                    inline=False)
                    embed.add_field(name='__**Cross Hair**__', value=f'```\n{crossHair}```',
                                    inline=False)
                    embed.add_field(name='__**Mouse and Keyboard**__', value=f'```\n{mnk}```',
                                    inline=False)
                    embed.add_field(name='__**Whitelist**__', value=f'```\n{wl}```',
                                    inline=False)
                    embed.add_field(name='__**Brighter Night**__', value=f'```\n{brightNight}```',
                                    inline=False)
                    embed.add_field(name='__**Base Damage**__', value=f'```\n{bd}```',
                                    inline=False)
                    embed.add_field(name='__**Container Damage**__', value=f'```\n{cd}```',
                                    inline=False)

                    return await ctx.send(embed=embed)

    @admin.command(name='ping', description='Shows the Location off one / all Player/s (only when Online).',
                    usage='[IGN]')
    async def ping(self, ctx: commands.Context, ign: str = None) -> discord.Message:
        if ign is None:
            if self.bot.dayz_map is None:
                dayz_map = 'chernarus'
            else:
                dayz_map = self.bot.dayz_map.lower()
            async with self.bot.dbs.acquire() as con:
                query = f'SELECT player_name, last_pos_x, last_pos_z FROM "{self.bot.service_id}" WHERE online = $1;'
                online = await con.fetch(query, True)
            if not online:
                return await ctx.send(f'```\nNo one is online on {self.bot.service_id}.```')
            else:
                embed = Embed(title=f'__**Player List | {self.bot.service_id}**__', color=0X000001,
                            timestamp=ctx.message.created_at, description='')
                for x in online:
                    name = x['player_name']
                    x_coord = x['last_pos_x']
                    z_coord = x['last_pos_z']
                    if dayz_map == 'livonia':
                        iz_url = f'https://www.izurvive.com/livonia/#location={x_coord};{z_coord}'
                    else:
                        iz_url = f'https://www.izurvive.com/#location={x_coord};{z_coord}'
                    if x_coord and z_coord is None:
                        embed.description += f'\n`{name}` | /'
                    else:
                        embed.description += f'\n`{name}` | [{x_coord} / {z_coord}]({iz_url})'
                return await ctx.send(embed=embed)
        else:
            if self.bot.dayz_map is None:
                dayz_map = 'chernarus'
            else:
                dayz_map = self.bot.dayz_map.lower()
            async with self.bot.dbs.acquire() as con:
                query = f'SELECT player_name, last_pos_x, last_pos_z FROM "{self.bot.service_id}" WHERE online = $1 AND player_name = $2;'
                online = await con.fetchrow(query, True, ign)
            if not online:
                return await ctx.send(f'\n```{ign} is not online on {self.bot.service_id}.```')
            else:
                embed = Embed(title=f'__**{ign} | {self.bot.service_id}**__', color=0X000001,
                            timestamp=ctx.message.created_at, description='')
                name = online['player_name']
                x_coord = online['last_pos_x']
                z_coord = online['last_pos_z']
                if dayz_map == 'livonia':
                    iz_url = f'https://www.izurvive.com/livonia/#location={x_coord};{z_coord}'
                else:
                    iz_url = f'https://www.izurvive.com/#location={x_coord};{z_coord}'
                if x_coord and z_coord is None:
                    embed.description += f'\n`{name}` | /'
                else:
                    embed.description += f'\n`{name}` | [{x_coord} / {z_coord}]({iz_url})'
                return await ctx.send(embed=embed)

    @admin.command(name='online', description='Shows the Names of all Players online.')
    async def online(self, ctx: commands.Context) -> discord.Message:
        async with self.bot.dbs.acquire() as conn:
            query = f'SELECT player_name FROM "{self.bot.service_id}" WHERE online = $1;'
            online = await conn.fetch(query, True)
        if not online:
            return await ctx.send(f'```\nNo one is online on {self.bot.service_id}.```')
        else:
            embed = Embed(title=f'__**Online List | {self.bot.service_id}**__', color=0X000001,
                        timestamp=ctx.message.created_at, description='')
            for player in online:
                embed.description += f'\n```{player["player_name"]}```'
            return await ctx.send(embed=embed)

    @admin.command(name='toggle', description='Toggles a Killfeed Module.',
                usage='<Conlogs/Build/Keepstarted/Autolb/Location>')
    async def toggle(self, ctx: commands.Context, module: str) -> discord.Message:
        if module.lower() not in ['conlogs', 'build', 'keepstarted', 'autolb', 'location']:
            return await ctx.send(
                '```\nInvalid Module provided.\nAvailable Modules: conlogs, build, keepstarted, autolb, location | Not case-sensitive```')

        else:
            if module.lower() == 'conlogs':
                async with self.bot.db.acquire() as conn:
                    query = f'SELECT con_logs, con_logs_channel FROM service;'
                    data = await conn.fetchrow(query)
                currentState = data['con_logs']
                currentChannelID = data['con_logs_channel']
                if currentState is False:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET con_logs = $1'
                        await conn.execute(query, True)
                    conLogsChannel = self.bot.get_channel(int(currentChannelID))
                    msg = f'Enabled Connection Logs.'
                    if conLogsChannel is None:
                        msg += f' You have not set a Channel yet. Do this with following command:\n`!conlogs`'
                    return await ctx.send(msg)
                else:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET con_logs = $1'
                        await conn.execute(query, False)
                    return await ctx.send('Disabled Connection Logs.')

            if module.lower() == 'build':
                async with self.bot.db.acquire() as conn:
                    query = f'SELECT build_feed, build_feed_channel FROM service;'
                    data = await conn.fetchrow(query)
                currentState = data['build_feed']
                currentChannelID = data['build_feed_channel']
                if currentState is False:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET build_feed = $1'
                        await conn.execute(query, True)
                    conLogsChannel = self.bot.get_channel(int(currentChannelID))
                    msg = f'Enabled Build Feed.'
                    if conLogsChannel is None:
                        msg += f' You have not set a Channel yet. Do this with following command:\n`!build`'
                    return await ctx.send(msg)
                else:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET build_feed = $1'
                        await conn.execute(query, False)
                    return await ctx.send('Disabled Build Feed.')

            if module.lower() == 'keepstarted':
                async with self.bot.db.acquire() as conn:
                    query = f'SELECT keepstarted FROM service;'
                    data = await conn.fetchrow(query)
                currentState = data['keepstarted']
                if currentState is False:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET keepstarted = $1'
                        await conn.execute(query, True)
                    return await ctx.send('Enabled Keep Started.')
                else:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET keepstarted = $1'
                        await conn.execute(query, False)
                    return await ctx.send('Disabled Keep Started.')

            if module.lower() == 'autolb':
                async with self.bot.db.acquire() as conn:
                    query = f'SELECT auto_lb, webhook_url FROM service;'
                    data = await conn.fetchrow(query)
                currentState = data['auto_lb']
                currentWebhookURL = data['webhook_url']
                if currentState is False:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET auto_lb = $1'
                        await conn.execute(query, True)
                    msg = f'Enabled auto Leaderboard.'
                    if currentWebhookURL is None:
                        msg += f' You have not created a Webhook URL for the auto Leaderboard. Do this with following Command:\n`!webhook`'
                    else:
                        async with ClientSession() as sess:
                            async with sess.get(f'{currentWebhookURL}') as res:
                                if res.status != 200:
                                    msg += f' You have not created a Webhook URL for the auto Leaderboard. Do this with following Command:\n`!webhook`'
                                else:
                                    json = await res.json()
                                    channelID = int(json['channel_id'])
                                    channel = self.bot.get_channel(channelID)
                                    if channel is None:
                                        msg += f' You have not created a Webhook URL for the auto Leaderboard. Do this with following Command:\n`!webhook`'
                                    else:
                                        pass

                    return await ctx.send(msg)
                else:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET auto_lb = $1'
                        await conn.execute(query, False)
                    return await ctx.send('Disabled auto Leaderboard.')

            if module.lower() == 'location':
                async with self.bot.db.acquire() as conn:
                    query = f'SELECT location FROM service;'
                    data = await conn.fetchrow(query)
                currentState = data['location']
                if currentState is False:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET location = $1'
                        await conn.execute(query, True)
                    return await ctx.send('Enabled Location.')
                else:
                    async with self.bot.db.acquire() as conn:
                        query = 'UPDATE service SET location = $1'
                        await conn.execute(query, False)
                    return await ctx.send('Disabled Location.')


def setup(bot) -> None:
    bot.add_cog(Admin(bot))
