import discord
from discord.ext import commands
import pathlib
import aiohttp
import io
import typing
import logging

from . import geoguesser
from . import error

discord_handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="a")

TOKEN_PATH = pathlib.Path(pathlib.Path(__file__).parent, "token")

def start():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    bot = commands.Bot(command_prefix="/", intents=intents)

    GEO: geoguesser.Geoguesser = geoguesser.Geoguesser(bot)

    # Check for only subscribed channels
    def subscriber_only():
        async def predicate(ctx: commands.Context):
            if ctx.channel.id not in GEO.subscribed:
                raise error.SubscriberOnly()
            return True
        return commands.check(predicate)
        
    # Check for only channels with admin privileges
    def admin_only():
        async def predicate(ctx: commands.Context):
            return ctx.channel.id in GEO.admins
        return commands.check(predicate)

    # Check for either subscribers or adming
    def subscriber_admin_only():
        async def predicate(ctx: commands.Context):
            return ctx.channel.id in GEO.admins or ctx.channel.id in GEO.subscribed
        return commands.check(predicate)

    @bot.hybrid_group()    
    async def geo(ctx: commands.Context):
        pass

    @geo.command(description="Reply with \"Pong!\".")
    async def ping(ctx: commands.Context):
        await ctx.reply("Pong!")

    @geo.command(description="Sync app commands to all channels.")
    @admin_only()
    async def sync(ctx: commands.Context):
        if ctx.guild is not None:
            bot.tree.copy_global_to(guild=ctx.guild) # type: ignore
        synced = await bot.tree.sync(guild=None)
        await ctx.reply(f"Synced commands/groups {', '.join('`' + s.name + '`' for s in synced)} to all channels.")

    @geo.command(name="subscribe", description="Subscribe this channel to geobot.")
    async def subscribe(ctx: commands.Context):
        if ctx.channel.id in GEO.subscribed:
            await ctx.reply("This channel is already subscribed to geobot.")
        else:
            GEO.subscribe(ctx.channel.id)
            await ctx.reply("This channel is now subscribed to the geobot!")

    @geo.command(name="unsubscribe", description="Unsubscribe this channel from geobot.")
    @subscriber_only()
    async def unsubscribe(ctx: commands.Context):
        GEO.unsubscribe(ctx.channel.id)
        await ctx.reply("This channel is now unsubscribed from the geobot!")

    @geo.command(name="guess", description="Submit a guess for a given image tag.")
    @discord.app_commands.describe(tag="The tag to guess for.")
    @discord.app_commands.describe(latitude="Latitude (in degrees) of guess.")
    @discord.app_commands.describe(longitude="Longitude (in degrees) of guess.")
    @subscriber_only()
    async def guess(ctx: commands.Context, tag: str, latitude: float, longitude: float):
        guess = GEO.new_guess(ctx.message, tag, latitude, longitude)
        await ctx.reply(
            f"You have guessed {guess.google_maps_linked_url()}."
        )

    @geo.command(name="list", description="List all active image tags.")
    @subscriber_admin_only()
    async def list_active(ctx: commands.Context):
        if len(GEO.images) > 0:
            tags_str = ", ".join(f"`{tag}`" for tag in GEO.images)
            await ctx.reply(f"Active tags: {tags_str}.")
        else:
            await ctx.reply(f"There are no active tags.")

    @geo.command(name="message-all", description="Send a message to all subscribers.")
    @discord.app_commands.describe(message="The message to send.")
    @admin_only()
    async def message_all(ctx: commands.Context, message: str):
        await GEO.message_subscribers(message)
            
    @bot.command(name="image", description="Create an image tag for the attached image.")
    @discord.app_commands.describe(latitude="Latitude (in degrees) where image was taken.")
    @discord.app_commands.describe(longitude="Longitude (in degrees) where image was taken.")
    @discord.app_commands.describe(tag="The tag to use for this image. If not provided, one will be randomly generated.")
    @admin_only()
    async def create_image(ctx: commands.Context, latitude: float, longitude: float, tag: typing.Optional[str]):
        images = [a for a in ctx.message.attachments if a.content_type is not None and a.content_type.startswith("image")]
        if len(images) == 0:
            await ctx.reply("Please attach an image.")
            return
        if len(images) > 1:
            await ctx.reply("Please attach exactly one image.")
            return
        
        if tag is not None and not tag.isalnum():
            await ctx.reply("Image tags must be alphanumeric.")
            return
        
        if tag is not None and tag in GEO.images:
            await ctx.reply(f"Tag `{tag}` is already in use.")
            return
            
        image = images[0]
        ext = image.filename.split(".")[-1]

        async with aiohttp.ClientSession() as session:
            async with session.get(image.url) as response:
                data = io.BytesIO(await response.read())
                real_tag = await GEO.new_image(data, ext, latitude, longitude, tag)
                await ctx.reply(
                    f"Created new image with tag `{real_tag}`.\nActual location: {geoguesser.google_maps_linked_url(latitude, longitude)}."
                )

    @geo.command(name="close", description="Close an image tag.")
    @discord.app_commands.describe(tag="The tag to close.")
    @subscriber_admin_only()
    async def close_image(ctx: commands.Context, tag: str):
        await GEO.close_image(tag)
        await ctx.reply(f"Tag `{tag}` has been closed.")

    @geo.command(name="reset", description="Reset all scores.")
    @admin_only()
    async def reset_scores(ctx: commands.Context):
        await GEO.reset_scores()
        await ctx.reply(f"Scores have been reset.")

    @geo.command(name="scores", description="List current scores.")
    @subscriber_admin_only()
    async def show_scores(ctx: commands.Context):
        ret_str = "## Current scores are:"
        for user,score in GEO.scores.items():
            ret_str += f"\n<@{user}>: {score}"
        await ctx.reply(ret_str)

    @geo.group()
    async def map(ctx: commands.Context):
        pass

    @map.command(name="reset", description="Reset map to world map default.")
    async def reset_map(ctx: commands.Context):
        GEO.set_maxdist()
        await ctx.reply(f"Maximum map distance has been set to {GEO.maxdist} (world map default).")

    @map.command(name="set", description="Reset map to the given max distance (diagonal length of map rectangle).")
    @discord.app_commands.describe(maxdist="Diagonal length of the map rectangle.")
    async def set_map(ctx: commands.Context, maxdist: float):
        GEO.set_maxdist(maxdist)
        await ctx.reply(f"Maximum map distance has been set to {GEO.maxdist}.")

    @bot.event
    async def on_command_error(ctx: commands.Context, err):
        await error.handle_error(ctx, err)

    token: str
    with open(TOKEN_PATH) as f:
        token = f.read().strip()

    bot.run(token, reconnect=True, log_handler=discord_handler)

if __name__ == "__main__":
    start()