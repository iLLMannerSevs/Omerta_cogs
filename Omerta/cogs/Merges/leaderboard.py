import asyncio
import logging
import time

import discord
from aiohttp import ClientSession
from discord import Embed
from discord import Webhook, AsyncWebhookAdapter
from discord.ext import commands
from discord.ext import tasks as task


class Leaderboard(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.logger.info(f'Extension was loaded successfully')
        self.post_lb.start()

    @task.loop(minutes=5)
    async def post_lb(self) -> None:
        await self.run_loop()

    async def run_loop(self) -> None:
        tasks = []

        async with self.bot.db.acquire() as conn:
            query = 'SELECT * FROM service;'
            service = await conn.fetchrow(query)

        autoLB = service['auto_lb']
        webhookURL = service['webhook_url']

        if autoLB is True and webhookURL is not None:
            tasks.append(self.leaderboard(webhookURL))

        await asyncio.gather(*tasks)

    async def leaderboard(self, webhook_url: str) -> None or discord.WebhookMessage:
        """
            Posts the Leaderboard

        Parameters
        ----------
        webhook_url : str
            The Webhook URL for the Leaderboard Channel
        """
        async with ClientSession() as sess:
            headers = {'Authorization': f'Bearer {self.bot.nitrado_token}'}
            async with sess.get(f'https://api.nitrado.net/services/{self.bot.service_id}/gameservers',
                                headers=headers) as res:
                if res.status != 200:
                    return
                json = await res.json()
                serverName = json['data']['gameserver']['settings']['config']['hostname']

            async with sess.get(f'{webhook_url}') as res:
                if res.status != 200:
                    return
                json = await res.json()
                channelID = json['channel_id']

        channel = self.bot.get_channel(int(channelID))
        if channel is None:
            return

        async with self.bot.dbs.acquire() as conn:
            queryLength = f'SELECT * FROM "{self.bot.service_id}"'
            players = await conn.fetch(queryLength)

            queryKillData = f'SELECT "player_name", kills FROM "{self.bot.service_id}" WHERE kills > 0 ORDER BY kills DESC LIMIT 15;'
            killData = await conn.fetch(queryKillData)

            querySnipeData = f'SELECT "player_name", "longest_kill_distance" FROM "{self.bot.service_id}" WHERE "longest_kill_distance" > 0 ORDER BY "longest_kill_distance" DESC LIMIT 15;'
            snipeData = await conn.fetch(querySnipeData)

            queryDeathData = f'SELECT "player_name", "pvp_deaths" FROM "{self.bot.service_id}" WHERE "pvp_deaths" > 0 ORDER BY "pvp_deaths" DESC LIMIT 15;'
            deathData = await conn.fetch(queryDeathData)

        updateTime = time.ctime()
        infoEmbed = Embed(title=f'__**Leaderboard Update :-1:**__', color=0X000001, author='Nialta', icon_url='https://i.postimg.cc/HWJpYQR3/Startmenu-black-red.png',
                            description=f'Server: **`{serverName}`**\nUpdated at: **{updateTime} (UTC+2)**\nPlayers: **{len(players)}**')
        killEmbed = Embed(title=f'__** ☥ ⭜ Most Kills ♔ ⸖**__', color=0XFFFFFF)
        for index, playerData in enumerate(killData):
            rank = index + 1
            kills = playerData['kills']
            playerName = playerData['player_name']

            killEmbed.add_field(name=f'**{rank}. {playerName}**', value=f'```\n{kills} Kills```')
        snipeEmbed = Embed(title=f'__**⸭ ⴲ ⯐  Farthest Confirmed Kill ⯐ ⴲ ⸭**__', color=0XFFFFFF)
        for index, playerData in enumerate(snipeData):
            rank = index + 1
            distance = playerData['longest_kill_distance']
            playerName = playerData['player_name']

            snipeEmbed.add_field(name=f'**{rank}. {playerName}**', value=f'```\n{distance}m```')
        deathEmbed = Embed(title=f'__**☣  "You are dead." - Red Screen Appearances ☣**__',
                        color=0XFFFFFF)
        for index, playerData in enumerate(deathData):
            rank = index + 1
            deaths = playerData['pvp_deaths']
            playerName = playerData['player_name']

            deathEmbed.add_field(name=f'**{rank}. {playerName}**', value=f'```\n{deaths} deaths```')
        await channel.purge()
        async with ClientSession() as sess:
            webhook = Webhook.from_url(f'{webhook_url}', adapter=AsyncWebhookAdapter(sess))
            await webhook.send(embeds=[infoEmbed, killEmbed, snipeEmbed, deathEmbed], username=self.bot.user.name,
                            avatar_url=self.bot.user.avatar_url)


def setup(bot) -> None:
    bot.add_cog(Leaderboard(bot))
