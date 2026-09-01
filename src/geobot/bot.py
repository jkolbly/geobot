import discord
from discord.ext import commands
import pathlib
import aiohttp
import io
import typing
import logging

from . import geoguesser
from . import error

discord_handler = logging.FileHandler(
    filename="discord.log", encoding="utf-8", mode="a"
)

TOKEN_PATH = pathlib.Path(pathlib.Path(__file__).parent, "token")


async def get_image_bytes(image: discord.Attachment) -> io.BytesIO:
    async with aiohttp.ClientSession() as session:
        async with session.get(image.url) as response:
            return io.BytesIO(await response.read())


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
            return ctx.message.author.id in GEO.admins

        return commands.check(predicate)

    # Check for either subscribers or admin
    def subscriber_admin_only():
        async def predicate(ctx: commands.Context):
            return ctx.channel.id in GEO.admins or ctx.channel.id in GEO.subscribed

        return commands.check(predicate)

    @bot.hybrid_group()
    async def geo(ctx: commands.Context):
        pass

    @geo.command(description='Reply with "Pong!".')
    async def ping(ctx: commands.Context):
        await ctx.reply("Pong!")

    @geo.command(description="Sync app commands to all channels.")
    @admin_only()
    async def sync(ctx: commands.Context):
        if ctx.guild is not None:
            bot.tree.copy_global_to(guild=ctx.guild)  # type: ignore
        synced = await bot.tree.sync(guild=None)
        await ctx.reply(
            f"Synced commands/groups {', '.join('`' + s.name + '`' for s in synced)} to all channels."
        )

    @geo.command(name="subscribe", description="Subscribe this channel to geobot.")
    async def subscribe(ctx: commands.Context):
        if ctx.channel.id in GEO.subscribed:
            await ctx.reply("This channel is already subscribed to geobot.")
        else:
            GEO.subscribe(ctx.channel.id)
            await ctx.reply("This channel is now subscribed to the geobot!")

    @geo.command(
        name="unsubscribe", description="Unsubscribe this channel from geobot."
    )
    @subscriber_only()
    async def unsubscribe(ctx: commands.Context):
        GEO.unsubscribe(ctx.channel.id)
        await ctx.reply("This channel is now unsubscribed from the geobot!")

    @geo.command(name="guess", description="Submit a guess for a given image tag.")
    @discord.app_commands.describe(tag="The tag to guess for.")
    @discord.app_commands.describe(latitude="Latitude (in degrees) of guess.")
    @discord.app_commands.describe(longitude="Longitude (in degrees) of guess.")
    async def guess(ctx: commands.Context, tag: str, latitude: float, longitude: float):
        guess = GEO.new_guess(ctx.message, tag, latitude, longitude)
        await ctx.reply(f"You have guessed {guess.google_maps_linked_url()}.")

    @geo.command(name="list", description="List all active image tags.")
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
        await ctx.reply(f"Sent `{message}` to all subscribed channels.")

    @geo.command(name="message-admins", description="Send a message to all admins.")
    @discord.app_commands.describe(message="The message to send.")
    @admin_only()
    async def message_admins(ctx: commands.Context, message: str):
        await GEO.message_admins(message)
        await ctx.reply(f"Sent `{message}` to all admins.")

    @bot.command(
        name="image", description="Create an image tag for the attached image."
    )
    @discord.app_commands.describe(
        latitude="Latitude (in degrees) where image was taken."
    )
    @discord.app_commands.describe(
        longitude="Longitude (in degrees) where image was taken."
    )
    @discord.app_commands.describe(
        tag="The tag to use for this image. If not provided, one will be randomly generated."
    )
    async def create_image(
        ctx: commands.Context,
        latitude: float,
        longitude: float,
        tag: typing.Optional[str],
    ):
        images = [
            a
            for a in ctx.message.attachments
            if a.content_type is not None and a.content_type.startswith("image")
        ]
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
        data = await get_image_bytes(image)

        real_tag = await GEO.new_image(
            ctx.message.author.id, data, ext, latitude, longitude, tag
        )
        await ctx.reply(
            f"Created new image with tag `{real_tag}`.\nActual location: {geoguesser.google_maps_linked_url(latitude, longitude)}."
        )

    @geo.command(
        name="get-image", description="Resend the message containing an image."
    )
    @discord.app_commands.describe(tag="The tag of the image to send.")
    async def get_image(ctx: commands.Context, tag: str):
        image = GEO.get_image(tag)
        image_bytes = image.get_image_bytes()
        image.add_image_message(
            await ctx.reply(
                image.get_image_text(new=False),
                file=discord.File(image_bytes, image.filename),
            )
        )
        image.add_guesshint_message(await ctx.reply(image.get_image_guesshint()))
        await GEO.save()

    @geo.command(name="close", description="Close an image tag.")
    @discord.app_commands.describe(tag="The tag to close.")
    async def close_image(ctx: commands.Context, tag: str):
        await GEO.close_image(ctx.message.author.id, tag)
        await ctx.reply(f"Tag `{tag}` has been closed.")

    @geo.command(name="reset", description="Reset all scores.")
    @admin_only()
    async def reset_scores(ctx: commands.Context):
        await GEO.reset_scores()
        await ctx.reply(f"Scores have been reset.")

    @geo.command(name="guessers", description="List who has guessed a tag.")
    @discord.app_commands.describe(tag="The tag to list guessers of.")
    async def list_guessers(ctx: commands.Context, tag: str):
        guessers = GEO.get_guessers(tag)
        if len(guessers) > 0:
            await ctx.reply(
                f"The following people have guessed for tag `{tag}`:\n* {"\n* ".join([f"<@{guesser}>" for guesser in GEO.get_guessers(tag)])}"
            )
        else:
            await ctx.reply(f"Nobody has guessed for tag `{tag}`.")

    @geo.command(name="describe", description="Add a description to an image tag.")
    @discord.app_commands.describe(tag="The tag to describe.")
    @discord.app_commands.describe(description="Description of the tag.")
    @discord.app_commands.describe(
        image="Optional image to reveal when the tag is closed."
    )
    async def describe(
        ctx: commands.Context,
        tag: str,
        description: str,
        image: typing.Optional[discord.Attachment],
    ):
        img = GEO.get_image(tag, required_owner=ctx.message.author.id)
        img.description = description
        if image is not None:
            ext = image.filename.split(".")[-1]
            data = await get_image_bytes(image)
            img.clear_desc_images()
            img.add_desc_image(data, ext)
        GEO.save()
        await ctx.reply(f"Updated the description for tag `{tag}`.")

    @geo.group()
    async def trip(ctx: commands.Context):
        pass

    @trip.command(name="new", description="Create a new trip.")
    @discord.app_commands.describe(
        id="Unique ID of this trip. May contain letters, numbers, and dashes."
    )
    async def new_trip(ctx: commands.Context, id):
        await GEO.new_trip(id, player=ctx.message.author.id)
        await ctx.reply(
            f"Created and selected a new trip with ID `{id}`.\nRun `/geo trip subscribe {id}` in all channels that you want to receive images from this trip.\nTo add images to this trip, message Geobot `/image <lat> <long>` with your image attached."
        )

    @trip.command(name="select", description="Select a trip.")
    @discord.app_commands.describe(
        id="Unique ID of this trip. May contain letters, numbers, and dashes."
    )
    async def select_trip(ctx: commands.Context, id):
        await GEO.select_trip(ctx.message.author.id, id)
        await ctx.reply(f"Selected trip `{id}`.")

    @trip.command(name="subscribe", description="Subscribe this channel to a trip.")
    @discord.app_commands.describe(
        id="Unique ID of this trip. May contain letters, numbers, and dashes."
    )
    async def trip_subscribe(ctx: commands.Context, id):
        GEO.trip_subscribe(ctx.channel.id, id)
        await ctx.reply(f"This channel is now subscribed to trip `{id}`!")

    @trip.command(
        name="unsubscribe", description="Unsubscribe this channel from geobot."
    )
    @discord.app_commands.describe(
        id="Unique ID of this trip. May contain letters, numbers, and dashes."
    )
    async def trip_unsubscribe(ctx: commands.Context, id):
        GEO.trip_unsubscribe(ctx.channel.id, id)
        await ctx.reply(f"This channel is now unsubscribed from trip `{id}`!")

    @trip.command(name="scores", description="List current scores.")
    @discord.app_commands.describe(
        id="Unique ID of the trip. May contain letters, numbers, and dashes."
    )
    async def show_scores(ctx: commands.Context, id):
        trip = GEO.get_trip(id)
        ret_str = f"## Current scores for trip `{id}` are:"
        scores = trip.calc_scores()
        if len(scores) == 0:
            await ctx.reply(f"## There are no scores yet for trip `{id}`.")
            return
        for user, score in scores.items():
            ret_str += f"\n<@{user}>: {score}"
        await ctx.reply(ret_str)

    @bot.event
    async def on_command_error(ctx: commands.Context, err):
        await error.handle_error(ctx, err)

    token: str
    with open(TOKEN_PATH) as f:
        token = f.read().strip()

    bot.run(token, reconnect=True, log_handler=discord_handler)


if __name__ == "__main__":
    start()
