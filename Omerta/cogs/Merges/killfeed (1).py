import asyncio
import logging
import re
from math import sqrt
import datetime

import discord
from aiofiles import open
from aiohttp import ClientSession
from discord.ext import commands
from discord.ext import tasks as task


class Killfeed(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.read_lines = {f"{self.bot.service_id}": []}
        self.last_logfile = ""

    async def get_zones(self) -> list:
        async with self.bot.dbz.acquire() as conn:
            query = f'SELECT * FROM "{self.bot.service_id}";'
            zones = await conn.fetch(query)

        return zones

    async def increment(self, key: str, playerID: str, value: int) -> bool:
        async with self.bot.dbs.acquire() as conn:
            queryIncrement = f"""UPDATE "{self.bot.service_id}" SET {key} = {key} + {value} WHERE player_id = '{playerID}'"""
            increment = await conn.execute(queryIncrement)

        if not increment:
            return False

        return True

    async def reset(self, key: str, playerID: str) -> bool:
        async with self.bot.dbs.acquire() as conn:
            queryReset = (
                f'UPDATE "{self.bot.service_id}" SET {key} = $1 WHERE player_id = $2;'
            )
            reset = await conn.execute(queryReset, 0, playerID)
            if not reset:
                return False

            return True

    async def set_status(
        self, playerID: str, playerName: str, onlineStatus: bool
    ) -> bool:
        async with self.bot.dbs.acquire() as conn:
            querySetStatus = f'UPDATE "{self.bot.service_id}" SET (online, player_name) = ($1, $2) WHERE player_id = $3;'
            setStatus = await conn.execute(
                querySetStatus, onlineStatus, playerName, playerID
            )
            if not setStatus:
                return False

            return True

    async def insert_player(self, playerName: str, playerID: str) -> bool:
        async with self.bot.dbs.acquire() as conn:
            queryInsertPlayer = f'INSERT INTO "{self.bot.service_id}" (player_id, player_name, online) VALUES ($1, $2, $3) ON CONFLICT (player_id) DO UPDATE SET (player_name, online) = ($2, $3);'
            insertPlayer = await conn.execute(
                queryInsertPlayer, playerID, playerName, True
            )
            if not insertPlayer:
                return False

            return True

    async def calculate_online_time(self, playerID: str, logoTime: str) -> None:
        async with self.bot.dbs.acquire() as conn:
            query = (
                f'SELECT last_login FROM "{self.bot.service_id}" WHERE player_id = $1;'
            )
            lastLoginDB = await conn.fetchval(query, playerID)

        timeLastLogin = datetime.datetime.strptime(
            str(lastLoginDB), "%Y-%m-%d %H:%M:%S"
        )
        timeLogout = datetime.datetime.strptime(logoTime, "%Y-%m-%d %H:%M:%S")
        playtime = (timeLogout - timeLastLogin).total_seconds()
        await self.increment("playtime", playerID, int(playtime))

    @commands.command(hidden=True, name="logout")
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def logout(self, ctx: commands.Context):
        if not ctx.author.id == ctx.guild.owner_id:
            return
        async with open("cache/logFileCache.txt", mode="w") as f:
            for line in self.read_lines[self.bot.service_id]:
                if "AdminLog" in line:
                    continue
                await f.write(line)

        async with open("cache/logBeginningCache.txt", mode="w") as f:
            text = self.last_logfile
            text = re.sub(r"\n\s*\n", "\n", text, re.MULTILINE)
            await f.write(text)

        return (
            await ctx.send("Successfully saved Cache to log.txt. Logging out now."),
            await self.bot.change_presence(status=discord.Status.invisible),
            await self.bot.close(),
        )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        async with open("cache/logFileCache.txt", mode="r") as f:
            cachedLogFile = await f.read()
            self.read_lines[self.bot.service_id] = cachedLogFile.splitlines()

        async with open("cache/logBeginningCache.txt", mode="r") as f:
            cachedLogFileBeginning = await f.read()
            self.last_logfile = cachedLogFileBeginning

        self.logger.info(f"The Extension was loaded successfully")
        self.check_logs.start()

    async def loop(self) -> None:
        tasks = []
        log = await self.download_log()
        if log is True:
            tasks.append(self.check_logfile(self.bot.dayz_map))
        else:
            pass
        await asyncio.gather(*tasks)

    @task.loop(minutes=2)
    async def check_logs(self) -> None:
        await self.loop()

    async def download_log(self) -> bool:
        async with ClientSession() as sess:
            headers = {"Authorization": f"Bearer {self.bot.nitrado_token}"}
            async with sess.get(
                f"https://api.nitrado.net/services/{self.bot.service_id}/gameservers",
                headers=headers,
            ) as res:
                if res.status != 200:
                    self.logger.error(
                        f"Failed to download the Log File for {self.bot.service_id}"
                    )
                    return False

                else:
                    json = await res.json()

                    username = json["data"]["gameserver"]["username"]
                    game = json["data"]["gameserver"]["game"].lower()

                    if game == "dayzps":
                        log_path = "dayzps/config/DayZServer_PS4_x64.ADM"

                    elif game == "dayzxb":
                        log_path = "dayzxb/config/DayZServer_X1_x64.ADM"

                    else:
                        self.logger.error(f"PC Servers are not supported")
                        return False

                    async with sess.get(
                        f"https://api.nitrado.net/services/{self.bot.service_id}/gameservers/file_server/download?file=/games/{username}/noftp/{log_path}",
                        headers=headers,
                    ) as resp:
                        if resp.status != 200:
                            self.logger.error(
                                f"Failed to download the Log File for {self.bot.service_id}"
                            )
                            return False

                        else:
                            json = await resp.json()

                            url = json["data"]["token"]["url"]

                            async with sess.get(f"{url}", headers=headers) as response:
                                if response.status != 200:
                                    self.logger.error(
                                        f"Failed to download the Log File for {self.bot.service_id}"
                                    )
                                    return False

                                else:
                                    async with open(
                                        f"./logs/{self.bot.service_id}.adm", mode="wb+"
                                    ) as file:
                                        await file.write(await response.read())
                                        await file.close()

                                    self.logger.info(
                                        f"Downloaded Log for {self.bot.service_id} successfully"
                                    )
                                    return True

    async def check_logfile(self, dayz_map: str) -> None:
        self.logger.info(f"Checking the Log for {self.bot.service_id}")

        async with self.bot.db.acquire() as conn:
            query = "SELECT * FROM service;"
            serviceData = await conn.fetchrow(query)

        if self.bot.service_id not in self.read_lines:
            self.read_lines[self.bot.service_id] = []

        async with open(f"./logs/{self.bot.service_id}.adm", mode="r") as file:
            async for line in file:
                if f"{str(line.strip())}" in self.read_lines[self.bot.service_id]:
                    print("Double")
                    continue

                if "AdminLog" in line:
                    if self.last_logfile not in str(line):
                        print("New Log")
                        self.last_logfile = str(line)
                        self.read_lines[self.bot.service_id] = []

                self.read_lines[self.bot.service_id].append(str(line).strip())

                if (
                    "Player" in line
                    and not "Unknown/Dead Entity" in line
                    and not "PlayerList log" in line
                    and not "Unknown" in line
                ):
                    playerID = (
                        str(re.search(r"id=(.*?\s)", line).group(1))
                        .replace(")", "")
                        .replace("=", "")
                    )
                    playerID = re.sub(r"\s+", "", playerID, re.MULTILINE)
                    playerName = str(re.search(r'[\'"](.*?)[\'"]', line).group(1))
                    time = str(re.search("(\\d+:\\d+:\\d+)", line).group(1))

                    if (
                        not "is connected" in line
                        and not "has been disconnected" in line
                        and "pos" in line
                        and not "killed by Player" in line
                        and not "hit by" in line
                        and not "died." in line
                        and not "is unconscious" in line
                        and not "regained consciousness" in line
                    ):
                        locationLog = (
                            str(re.search(r"pos=<(.*?)>", line).group(1))
                            .replace(" ", "")
                            .split(",")
                        )
                        x = float(locationLog[0])
                        z = float(locationLog[1])

                        await self.insert_player(playerName, playerID)

                        zones = await self.get_zones()

                        if not not zones:
                            for zone in zones:
                                zoneCoordX = zone["x_coord"]
                                zoneCoordZ = zone["z_coord"]
                                zoneRadius = zone["radius"]
                                zoneWhitelist = zone["no_alert"]
                                zoneName = zone["name"]
                                zoneID = zone["id"]
                                zoneChannelID = int(zone["channel"])

                                a = zoneCoordX - x
                                b = zoneCoordZ - z
                                c = round(sqrt(a * a + b * b), 2)

                                if c < zoneRadius and not playerName in zoneWhitelist:
                                    if dayz_map == "livonia":
                                        mapURL = f"[{x}, {z}](https://www.izurvive.com/livonia/#location={x};{z})"
                                    else:
                                        mapURL = f"[{x}, {z}](https://www.izurvive.com/#location={x};{z})"

                                    channel = self.bot.get_channel(zoneChannelID)
                                    if channel is None:
                                        pass

                                    if 0 < c < 2:
                                        distanceText = "meter"
                                    else:
                                        distanceText = "meters"

                                    embed = discord.Embed(
                                        title=f"**:rotating_light: Zone Alarm | {zoneName} :rotating_light:**",
                                        description=f"_A Player was detected within {c} {distanceText} of the Zone {zoneName}._",
                                        color=0xDA0C0C,
                                    )

                                    embed.add_field(
                                        name="__**Player IGN**__",
                                        value=f"```\n{playerName}```",
                                        inline=False,
                                    )
                                    embed.add_field(
                                        name="__**Server Time**__",
                                        value=f"```\n{time}```",
                                        inline=False,
                                    )
                                    embed.add_field(
                                        name="__**Player Location**__",
                                        value=f"{mapURL}",
                                        inline=False,
                                    )

                                    embed.set_footer(
                                        text=f"{zoneName} | {zoneID}",
                                        icon_url=self.bot.user.avatar_url,
                                    )

                                    channel = self.bot.get_channel(860231409369481217)
                                    await channel.send(embed=embed)

                        async with self.bot.dbs.acquire() as conn:
                            query = f"""INSERT INTO "{self.bot.service_id}" (player_id, player_name, last_pos_x, last_pos_z, online) 
                                        VALUES ($1, $2, $3, $4, $5) ON CONFLICT (player_id) DO UPDATE 
                                        SET (player_name, last_pos_x, last_pos_z, online) = ($2, $3, $4, $5);"""
                            await conn.execute(
                                query, playerID, playerName, float(x), float(z), True
                            )

                    if "placed" in line:
                        await self.insert_player(playerName, playerID)
                        if serviceData["build_feed"] is True:
                            locationLog = (
                                str(re.search(r"pos=<(.*?)>", line).group(1))
                                .replace(" ", "")
                                .split(",")
                            )
                            x = float(locationLog[0])
                            z = float(locationLog[1])
                            placedItem = str(re.search(r"placed (.*)", line).group(1))

                            if dayz_map == "livonia":
                                mapURL = f"[{x}, {z}](https://www.izurvive.com/livonia/#location={x};{z})"
                            else:
                                mapURL = f"[{x}, {z}](https://www.izurvive.com/#location={x};{z})"

                            embed = discord.Embed(
                                title="**:tools: Placement Log :tools:**",
                                color=0xB4BB05,
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Item**__",
                                value=f"```\n{placedItem}```",
                                inline=False,
                            )
                            embed.add_field(
                                name="__**Player Location**__",
                                value=f"{mapURL}",
                                inline=False,
                            )

                            embed.set_footer(
                                text="Placement Log", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["build_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))
                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                    if "built" in line and "with" in line:
                        await self.insert_player(playerName, playerID)
                        if serviceData["build_feed"] is True:
                            locationLog = (
                                str(re.search(r"pos=<(.*?)>", line).group(1))
                                .replace(" ", "")
                                .split(",")
                            )
                            x = float(locationLog[0])
                            z = float(locationLog[1])
                            builtPart = str(
                                re.search(r"built (.*?) with", line).group(1)
                            )
                            if builtPart == "#STR_CFGVEHICLES_CONSTRUCTION_PART_GATE":
                                builtPart = "Gate"
                            builtTool = str(re.search(r"with (.*)", line).group(1))

                            if dayz_map == "livonia":
                                mapURL = f"[{x}, {z}](https://www.izurvive.com/livonia/#location={x};{z})"
                            else:
                                mapURL = f"[{x}, {z}](https://www.izurvive.com/#location={x};{z})"

                            embed = discord.Embed(
                                title="**:hammer: Building Log :hammer:**",
                                color=0x1C9C15,
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Part**__",
                                value=f"```\n{builtPart}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Tool**__",
                                value=f"```\n{builtTool}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Player Location**__",
                                value=f"{mapURL}",
                                inline=False,
                            )

                            embed.set_footer(
                                text="Building Log", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["build_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))
                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                    if "dismantled" in line and "with" in line:
                        await self.insert_player(playerName, playerID)
                        if serviceData["build_feed"] is True:
                            locationLog = (
                                str(re.search(r"pos=<(.*?)>", line).group(1))
                                .replace(" ", "")
                                .split(",")
                            )
                            x = float(locationLog[0])
                            z = float(locationLog[1])
                            dismantledPart = str(
                                re.search(r"dismantled (.*?) with", line).group(1)
                            )
                            if (
                                dismantledPart
                                == "#STR_CFGVEHICLES_CONSTRUCTION_PART_GATE"
                            ):
                                dismantledPart = "Gate"
                            dismantledTool = str(re.search(r"with (.*)", line).group(1))

                            if dayz_map == "livonia":
                                mapURL = f"[{x}, {z}](https://www.izurvive.com/livonia/#location={x};{z})"
                            else:
                                mapURL = f"[{x}, {z}](https://www.izurvive.com/#location={x};{z})"

                            embed = discord.Embed(
                                title="**:axe: Dismantling Log :axe:**",
                                color=0xDA0C0C,
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Part**__",
                                value=f"```\n{dismantledPart}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Tool**__",
                                value=f"```\n{dismantledTool}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Player Location**__",
                                value=f"{mapURL}",
                                inline=False,
                            )

                            embed.set_footer(
                                text="Dismantling Log",
                                icon_url=self.bot.user.avatar_url,
                            )

                            channelID = serviceData["build_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))
                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                    if "is connected" in line:
                        await self.insert_player(playerName, playerID)
                        loginTime = f"{str(datetime.date.today())} {time}"
                        async with self.bot.dbs.acquire() as conn:
                            query = f'UPDATE "{self.bot.service_id}" SET last_login = $1 WHERE player_id = $2;'
                            await conn.execute(query, loginTime, playerID)
                        await self.set_status(playerID, playerName, True)

                        if serviceData["con_logs"] is True:
                            embed = discord.Embed(
                                title="**:globe_with_meridians: New Connect :globe_with_meridians:**",
                                description="_A Player joined the Server._",
                                color=0x1C9C15,
                            )
                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            embed.set_footer(
                                text="Connection Log", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["con_logs_channel"]
                            channel = self.bot.get_channel(int(channelID))
                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                    if "has been disconnected" in line and not "Unknown" in line:
                        await self.insert_player(playerName, playerID)
                        logoutTime = f"{str(datetime.date.today())} {time}"
                        await self.set_status(playerID, playerName, False)
                        await self.calculate_online_time(playerID, logoutTime)

                        if serviceData["con_logs"] is True:
                            async with self.bot.dbs.acquire() as conn:
                                query = f'SELECT last_login FROM "{self.bot.service_id}" WHERE player_id = $1;'
                                lastLoginDB = await conn.fetchval(query, playerID)

                            timeLastLogin = datetime.datetime.strptime(
                                str(lastLoginDB), "%Y-%m-%d %H:%M:%S"
                            )
                            timeLogout = datetime.datetime.strptime(
                                logoutTime, "%Y-%m-%d %H:%M:%S"
                            )
                            playtime = (timeLogout - timeLastLogin).total_seconds()

                            m, s = divmod(playtime, 60)
                            h, m = divmod(m, 60)
                            if int(h) == 0 and int(m) == 0:
                                if 0 < s < 2:
                                    timeString = f"{s} second"
                                else:
                                    timeString = f"{s} seconds"
                            elif int(h) == 0 and int(m) != 0:
                                if 0 < m < 2:
                                    if 0 < s < 2:
                                        timeString = f"{m} minute and {s} second"
                                    else:
                                        timeString = f"{m} minute and {s} seconds"
                                else:
                                    if 0 < s < 2:
                                        timeString = f"{m} minutes and {s} second"
                                    else:
                                        timeString = f"{m} minutes and {s} seconds"
                            else:
                                if 0 < h < 2:
                                    if 0 < m < 2:
                                        if 0 < s < 2:
                                            timeString = (
                                                f"{h} hour, {m} minute and {s} second"
                                            )
                                        else:
                                            timeString = (
                                                f"{h} hour, {m} minute and {s} seconds"
                                            )
                                    else:
                                        if 0 < s < 2:
                                            timeString = (
                                                f"{h} hour, {m} minutes and {s} second"
                                            )
                                        else:
                                            timeString = (
                                                f"{h} hour, {m} minutes and {s} seconds"
                                            )

                                else:
                                    if 0 < m < 2:
                                        if 0 < s < 2:
                                            timeString = (
                                                f"{h} hours, {m} minute and {s} second"
                                            )
                                        else:
                                            timeString = (
                                                f"{h} hours, {m} minute and {s} seconds"
                                            )
                                    else:
                                        if 0 < s < 2:
                                            timeString = (
                                                f"{h} hours, {m} minutes and {s} second"
                                            )
                                        else:
                                            timeString = f"{h} hours, {m} minutes and {s} seconds"

                            embed = discord.Embed(
                                title="**:globe_with_meridians: New Disconnect :globe_with_meridians:**",
                                description="_A Player left the Server._",
                                color=0xDA0C0C,
                            )
                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Playtime**__",
                                value=f"```\n{timeString}```",
                                inline=False,
                            )

                            embed.set_footer(
                                text="Connection Log",
                                icon_url=self.bot.user.avatar_url,
                            )

                        channelID = serviceData["con_logs_channel"]
                        channel = self.bot.get_channel(int(channelID))
                        if channel is None:
                            pass

                        try:
                            await channel.send(embed=embed)
                            await asyncio.sleep(2)
                        except discord.Forbidden or discord.HTTPException:
                            pass

                    elif (
                        "(DEAD)" in line
                        or "committed suicide" in line
                        and not "Survivor"
                    ):
                        locationLog = (
                            str(re.search(r"pos=<(.*?)>", line).group(1))
                            .replace(" ", "")
                            .split(",")
                        )
                        x = float(locationLog[0])
                        z = float(locationLog[1])

                        if dayz_map == "livonia":
                            mapURL = f"[{x}, {z}](https://www.izurvive.com/livonia/#location={x};{z})"
                        else:
                            mapURL = f"[{x}, {z}](https://www.izurvive.com/#location={x};{z})"

                        if "committed suicide" in line:
                            await self.increment("pve_deaths", playerID, 1)

                            embed = discord.Embed(
                                title="**:skull_crossbones: Suicide :skull_crossbones:**",
                                color=0xDA0C0C,
                                description="_Someone committed Suicide._",
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            if serviceData["location"] is True:
                                embed.add_field(
                                    name="__**Player Location**__",
                                    value=f"{mapURL}",
                                    inline=False,
                                )

                            embed.set_footer(
                                text="PvE Feed", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["pve_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))

                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                        if "killed by Player" in line:
                            killerName = str(
                                re.search(r'killed by Player "(.*?)"', line).group(1)
                            )
                            killerID = (
                                re.findall(r"id=(.*?\s)", line)[1]
                                .replace(")", "")
                                .replace("=", "")
                                .replace(" ", "")
                            )
                            weapon = str(
                                re.search(r" with (.*) from", line).group(1)
                                or re.search(r"with (.*)", line).group(1)
                            )
                            currentLineIndex = len(self.read_lines[self.bot.service_id])
                            hitLine = self.read_lines[self.bot.service_id][
                                currentLineIndex - 2
                            ]
                            if not "from" in line and not "meters" in line:
                                distance = 0.0
                            else:
                                try:
                                    distance = round(
                                        float(
                                            re.search(
                                                r"from ([0-9.]+) meters", line
                                            ).group(1)
                                        ),
                                        2,
                                    )
                                except AttributeError:
                                    distance = 0.0
                            bodyPart = str(
                                re.search(r"into (.*?) for", hitLine)
                                .group(1)
                                .split("(")[0]
                            )
                            damageValue = str(
                                re.search(r"for (.*?) damage", hitLine).group(1)
                            )

                            # Update Killer's Data
                            async with self.bot.db.acquire() as conn:
                                query = f'SELECT longest_kill_distance, longest_kill_weapon FROM "{self.bot.service_id}" WHERE player_id = $1'
                                killerData = await conn.fetchrow(query, killerID)

                            await self.increment("kills", killerID, 1)
                            await self.increment("killstreak", killerID, 1)
                            await self.reset("deathstreak", killerID)
                            if float(killerData["longest_kill_distance"]) <= distance:
                                async with self.bot.dbs.acquire() as conn:
                                    query = f'UPDATE "{self.bot.service_id}" SET (longest_kill_distance, longest_kill_weapon) = ($1, $2) WHERE player_id = $3;'
                                    await conn.execute(
                                        query, float(distance), weapon, killerID
                                    )

                            # Update Victim's Data
                            await self.increment("pvp_deaths", playerID, 1)
                            await self.increment("deathstreak", playerID, 1)
                            await self.reset("killstreak", killerID)

                            embed = discord.Embed(
                                title="**:skull_crossbones: PvP Kill :skull_crossbones:**",
                                color=0xDA0C0C,
                                description=f"_`{playerName}` was killed by `{killerName}`._",
                            )

                            embed.add_field(
                                name="__**Killer IGN**__",
                                value=f"```\n{killerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Victim IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Kill Data**__",
                                value=f"```\nHit: {bodyPart}\nDamage: {damageValue}\nWeapon: {weapon}\nDistance: {distance}m```",
                                inline=False,
                            )
                            if serviceData["location"] is True:
                                embed.add_field(
                                    name="__**Kill Location**__",
                                    value=f"{mapURL}",
                                    inline=False,
                                )

                            embed.set_footer(
                                text="PvP Feed", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["pvp_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))

                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                        if "bled out" in line:
                            await self.increment("pve_deaths", playerID, 1)

                            embed = discord.Embed(
                                title="**:drop_of_blood: Suicide :drop_of_blood:**",
                                color=0xDA0C0C,
                                description="_Someone bled out._",
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            if serviceData["location"] is True:
                                embed.add_field(
                                    name="__**Player Location**__",
                                    value=f"{mapURL}",
                                    inline=False,
                                )

                            embed.set_footer(
                                text="PvE Feed", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["pve_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))

                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                        if (
                            "Animal_CanisLupus_Grey" in line
                            or "Animal_CanisLupus_White" in line
                        ):
                            await self.increment("pve_deaths", playerID, 1)

                            embed = discord.Embed(
                                title="**:wolf: Bear Death :wolf:**",
                                color=0xDA0C0C,
                                description="_Someone was killed by a Wolf._",
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            if serviceData["location"] is True:
                                embed.add_field(
                                    name="__**Player Location**__",
                                    value=f"{mapURL}",
                                    inline=False,
                                )

                            embed.set_footer(
                                text="PvE Feed", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["pve_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))

                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                        if "Animal_UrsusArctos" in line or "Brown Bear" in line:
                            await self.increment("pve_deaths", playerID, 1)

                            embed = discord.Embed(
                                title="**:bear: Bear Death :bear:**",
                                color=0xDA0C0C,
                                description="_Someone was killed by a Bear._",
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            if serviceData["location"] is True:
                                embed.add_field(
                                    name="__**Player Location**__",
                                    value=f"{mapURL}",
                                    inline=False,
                                )

                            embed.set_footer(
                                text="PvE Feed", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["pve_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))

                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                        if "hit by FallDamage" in line:
                            await self.increment("pve_deaths", playerID, 1)

                            embed = discord.Embed(
                                title="**:skull_crossbones: Fall Death :skull_crossbones:**",
                                color=0xDA0C0C,
                                description="_Someone fell to his Death._",
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            if serviceData["location"] is True:
                                embed.add_field(
                                    name="__**Player Location**__",
                                    value=f"{mapURL}",
                                    inline=False,
                                )

                            embed.set_footer(
                                text="PvE Feed", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["pve_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))

                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                        if (
                            "died." in line
                            and not "killed by Player" in line
                            and not "bled out" in line
                        ):
                            await self.increment("pve_deaths", playerID, 1)

                            embed = discord.Embed(
                                title="**:skull_crossbones: Death :skull_crossbones:**",
                                color=0xDA0C0C,
                                description="_Someone died._",
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            if serviceData["location"] is True:
                                embed.add_field(
                                    name="__**Player Location**__",
                                    value=f"{mapURL}",
                                    inline=False,
                                )

                            embed.set_footer(
                                text="PvE Feed", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["pve_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))

                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

                        if "killed by ZmbM" in line:
                            await self.increment("pve_deaths", playerID, 1)

                            embed = discord.Embed(
                                title="**:man_zombie: Zombie Death :man_zombie:**",
                                color=0xDA0C0C,
                                description="_Someone was killed by a Zombie._",
                            )

                            embed.add_field(
                                name="__**Player IGN**__",
                                value=f"```\n{playerName}```",
                                inline=False,
                            )

                            embed.add_field(
                                name="__**Server Time**__",
                                value=f"```\n{time}```",
                                inline=False,
                            )

                            if serviceData["location"] is True:
                                embed.add_field(
                                    name="__**Player Location**__",
                                    value=f"{mapURL}",
                                    inline=False,
                                )

                            embed.set_footer(
                                text="PvE Feed", icon_url=self.bot.user.avatar_url
                            )

                            channelID = serviceData["pve_feed_channel"]
                            channel = self.bot.get_channel(int(channelID))

                            if channel is None:
                                pass

                            try:
                                await channel.send(embed=embed)
                                await asyncio.sleep(2)
                            except discord.Forbidden or discord.HTTPException:
                                pass

        logging.info(f"Finished Checking the Log for {self.bot.service_id}")


def setup(bot) -> None:
    bot.add_cog(Killfeed(bot))
