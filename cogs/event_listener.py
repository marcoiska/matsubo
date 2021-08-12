"""Event Listener Cog

Discord Bot Cog that scraps the web for events, and then posts them on defined channels.
"""

import os
import discord
from discord import colour
from discord.ext import commands, tasks
from itertools import cycle
import datetime, pytz
import asyncio
from cogs.utils import database as db
from cogs.utils.event import Event
from cogs.utils.event_scrapper import getEvents

SLEEP_STATUS = cycle([f"Counting 🐑... {i} {'💤' if i%2 else ''}" for i in range(1, 10)])
POST_TIMES = [datetime.time(hour=10, minute=0, second=0, tzinfo=pytz.timezone('Asia/Tokyo')), 
              datetime.time(hour=20, minute=0, second=0, tzinfo=pytz.timezone('Asia/Tokyo'))]
SCRAP_SOURCES = {
    'Web:TokyoCheapo': {
        'footer': 'TOKYO CHEAPO',
        'icon': 'https://community.tokyocheapo.com/uploads/db1536/original/1X/91a0a0ee35d00aaa338a0415496d40f3a5cb298e.png',
        'thumbnail': 'https://cdn.cheapoguides.com/wp-content/themes/cheapo_theme/assets/img/logos/tokyocheapo/logo.png'
    },
    'Web:JapanCheapo': {
        'footer': 'JAPAN CHEAPO',
        'icon': 'https://pbs.twimg.com/profile_images/1199468429553455104/GdCZbc-R_400x400.png',
        'thumbnail': 'https://cdn.cheapoguides.com/wp-content/themes/cheapo_theme/assets/img/logos/japancheapo/logo.png'
    }
}


class EventListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loop_scrapNotify.start()
        self.countingSheeps.start()

    @tasks.loop(seconds=10)
    async def countingSheeps(self):
        """Counts sheeps. Very handy, because it shows the bot is still running."""
        await self.bot.change_presence(status=discord.Status.idle, activity=discord.Game(next(SLEEP_STATUS)))
    def cog_unload(self):
        self.countingSheeps.cancel()
    @countingSheeps.before_loop
    async def before_countingSheeps(self):
        await self.bot.wait_until_ready()
    @countingSheeps.after_loop
    async def on_countingSheeps_cancel(self):
        if self.countingSheeps.is_being_cancelled():
            await self.bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name='Internet', type=discord.ActivityType.listening))
        pass

    @tasks.loop(hours=1)
    async def loop_scrapNotify(self):
        """[Background task] Scraps web at specified times and notifies all subscribed channels."""
        currentTime = datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo'))
        dt = datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo')).replace(hour=POST_TIMES[0].hour, minute=POST_TIMES[0].minute, second=POST_TIMES[0].second) + datetime.timedelta(days=1) - currentTime
        for time in POST_TIMES:
            postTime = datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo')).replace(hour=time.hour, minute=time.minute, second=time.second)
            if postTime > currentTime:
                dt = postTime - currentTime
                break
        print(f"Next Web-scrapping in {dt.seconds}s")
        await asyncio.sleep(dt.seconds)
        await self.scrapEvents()
        await self.notifyAllChannels()
    @loop_scrapNotify.before_loop
    async def before_loop_scrapNotify(self):
        await self.bot.wait_until_ready()
    

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def scrap(self, ctx):
        """(ADMIN ONLY) Searches the web for new events, and posts updates to all subscibed channels."""
        await ctx.send(f"Scanning the web... this might take a while. Come back later again.")
        await self.scrapEvents()
        await self.notifyAllChannels()

    async def scrapEvents(self):
        """Searches the web for new events, and puts them into the database"""
        self.countingSheeps.cancel()
        await asyncio.sleep(3)

        print("Scrapping events...")
        await self.bot.change_presence(status=discord.Status.online, activity=discord.Game('Scrapping the web...'))
        events = getEvents()
        # print("Found the following events:")
        # for event in events:
        #    print(event)
        db.eventDB.insertEvents(events)

        await asyncio.sleep(3) #bugfix: wait before change_presence is called too fast!
        self.countingSheeps.start()
        print("Finished scrapping events!")
        pass

    async def notifyAllChannels(self):
        """Notify all subscribed channels of new events"""
        chvs = db.discordDB.getAllChannelVisibility()
        for chv in chvs:
            channel_id = chv[0]
            topics = chv[1]
            #print(f"Channel-ID: {channel_id};  Topics: {topics}")
            events = db.eventDB.getEvents(
                visibility=topics,
                from_date=datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo')).date(),
                until_date=datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo')).date()+datetime.timedelta(weeks=1)
            )
            channel = self.bot.get_channel(channel_id)
            await self.notifyChannel(channel, events)
        print("Notified all channels!")

    async def notifyChannel(self, channel : commands.TextChannelConverter, events : list[Event]):
        """Notify channel of new events"""
        print(f"Notifying channel #{channel}:{channel.id} of new events")
        messages, idx = await self.findEventMessages(channel, events)
        for i, event in enumerate(events):
            if i in idx:
                # Update the message with new event details
                message = messages[idx.index(i)]
                #TODO: Only edit if embed has changed -> check by hash()
                message.edit(embed=self.getEmbed(event))
                print(f'Edited event in message: {event.name} [{event.id}] -> Message-ID:{message.id}')
            else:
                if event.status.lower() in ['cancelled','canceled']:
                    continue
                await channel.send(content=f'***{event.name} [{event.id}]***', embed=self.getEmbed(event))
                print(f'Posted event to channel: {event.name} [{event.id}] -> #{channel}:{channel.id}')
            await asyncio.sleep(2)
        pass

    async def findEventMessages(self, channel: commands.TextChannelConverter, events: list[Event]) -> tuple[list[discord.Message],list[int]]:
        """Finds messages in given channel of given events. Returns messages and the indices of the events in the provided list."""
        messages = []
        idx = []
        async for message in channel.history(limit=200):
            print(f"len(embed):{len(message.embeds)}, Message:\n{message}")
            if not len(message.embeds):
                continue
            print('Enter2')
            if message.author is not self.bot.user:
                continue
            print('Enter3')
            embed = message.embeds[0]
            #TODO

            print(message)
        return messages, idx

    def getEmbed(self, event: Event) -> discord.Embed:
        """Returns discord.Embed object of given event"""
        embed = discord.Embed(
            title=event.name,
            colour=discord.Colour(0xd69d37),
            url=event.url,
            description=f"```{event.description}```\nFind out more [here]({event.url}).",
            timestamp=event.date_added if event.date_added else datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo'))
        )

        # Set event image
        if event.img:
            embed.set_image(url=event.img)

        # Set author
        embed.set_author(
            name=os.getenv("BOT_NAME", 'Matsubo'),
            url=os.getenv("BOT_URL", 'https://github.com/makokaz/matsubo'),
            icon_url=os.getenv("BOT_ICON_URL", 'https://discord.com/assets/f9bb9c4af2b9c32a2c5ee0014661546d.png')
        )

        # Set footer & thumbnail
        if event.source in SCRAP_SOURCES.keys():
            embed.set_footer(
                text=SCRAP_SOURCES[event.source]['footer'],
                icon_url=SCRAP_SOURCES[event.source]['icon']
            )
            embed.set_thumbnail(url=SCRAP_SOURCES[event.source]['thumbnail'])
        else:
            embed.set_footer(text=[event.source])

        # Add field: Date
        embed.add_field(name='\u200B', value=f':date: ***{event.getDateRange()}***', inline=True)
        # Add field: Time
        embed.add_field(name='\u200B', value=f':clock10: ***{event.getTimeRange()}***', inline=True)
        # Add field: Cost
        embed.add_field(name='\u200B', value=f':coin: ***{event.cost}***', inline=True)
        # Add field: Location
        loc_string = ''
        if event.status.lower() == 'online':
            loc_string += f"[ONLINE]({event.url}), "
        for location in event.location.split(', '):
            loc_string += f"[{location}](https://www.google.com/maps/search/?api=1&query={location.replace(' ','%')}), "
        loc_string = loc_string.rstrip(', ')
        if loc_string == '':
            loc_string = '---'
        embed.add_field(name='\u200B', value=f":round_pushpin: ***{loc_string}***", inline=True)
        
        return embed

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def subscribe(self, ctx, *topics):
        """Subscribes channel the message was sent in. Will post events to this channel."""
        topics = set(topics)
        topics_all = topics | db.discordDB.getChannelVisibility(ctx.channel.id)
        db.discordDB.updateChannel(ctx.channel.id, list(topics_all))
        await ctx.send(f"Subscribed the following new topics: {topics}\nAll subscribed topics of this channel: {topics_all}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def unsubscribe(self, ctx, *topics):
        """Unsubscribes topics from the channel the message was sent in. If no topics are given, the entire channel will be unsubscribed."""
        if len(topics):
            topics = set(topics)
            topics_new = db.discordDB.getChannelVisibility(ctx.channel.id) - topics
        else:
            topics_new = None
        if topics_new:
            db.discordDB.updateChannel(ctx.channel.id, list(topics_new))
            await ctx.send(f"Unsubscribed the following topics: {topics}\nAll subscribed topics of this channel: {topics_new}")
        else:
            db.discordDB.removeChannel(ctx.channel.id)
            await ctx.send("Unsubscribed channel from all topics")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def getSubscribedTopics(self, ctx):
        """Returns topics this channel is subscribed to."""
        topics_all = db.discordDB.getChannelVisibility(ctx.channel.id)
        if topics_all:
            await ctx.send(f"All subscribed topics of this channel: {topics_all}")
        else:
            await ctx.send("This channel has no subscribtions")


def setup(bot):
    bot.add_cog(EventListener(bot))