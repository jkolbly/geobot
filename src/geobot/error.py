from discord.ext import commands
from discord import app_commands
import traceback
import sys
import typing
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler("error.log")
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)


class SubscriberOnly(commands.CheckFailure):
    pass


class AdminOnly(commands.CheckFailure):
    pass


class TagSelectFailure(Exception):
    pass


class UnknownTag(Exception):
    tag: str
    available_tags: typing.Iterable[str]

    def __init__(self, tag: str, available_tags: typing.Iterable[str]):
        self.tag = tag
        self.available_tags = available_tags


class InvalidTripId(Exception):
    id: str

    def __init__(self, id: str):
        self.id = id


class DuplicateTripID(Exception):
    id: str

    def __init__(self, id: str):
        self.id = id


class UnknownTripId(Exception):
    id: str

    def __init__(self, id: str):
        self.id = id


class NoTripSelected(Exception):
    pass


class NotTripOwner(Exception):
    id: str

    def __init__(self, id: str):
        self.id = id


class NotTripSubscriber(Exception):
    id: str

    def __init__(self, id: str):
        self.id = id


async def handle_error(ctx: commands.Context, error):
    if isinstance(error, SubscriberOnly):
        await ctx.reply(
            f"This channel is not subscribed to the geobot.\nRun `/geo subscribe` to subscribe."
        )
    elif isinstance(error, AdminOnly):
        await ctx.reply(f"This channel does not have geobot admin privileges.")
    elif isinstance(error, commands.errors.HybridCommandError):
        await handle_error(ctx, error.original)
    elif isinstance(error, commands.errors.CommandInvokeError) or isinstance(
        error, app_commands.errors.CommandInvokeError
    ):
        if isinstance(error.original, TagSelectFailure):
            await ctx.reply(f"Failed to generate a tag. Try supplying an unused tag.")
        elif isinstance(error.original, UnknownTag):
            available_tags_str = ", ".join(
                f"`{tag}`" for tag in error.original.available_tags
            )
            await ctx.reply(
                f"`{error.original.tag}` is not the tag of an active geo image.\n"
                + (
                    "There are no active tags."
                    if len(error.original.available_tags) == 0
                    else f"Active tags are: {available_tags_str}."
                )
            )
        elif isinstance(error.original, InvalidTripId):
            await ctx.reply(
                f"`{error.original.id}` is not a valid trip ID. Trip IDs can only contain letters, numbers, and dashes."
            )
        elif isinstance(error.original, DuplicateTripID):
            await ctx.reply(f"`{error.original.id}` is already the ID of a trip.")
        elif isinstance(error.original, UnknownTripId):
            await ctx.reply(f"`{error.original.id}` is not the ID of a trip.")
        elif isinstance(error.original, NoTripSelected):
            await ctx.reply(
                f"You must select a trip to perform this action.\nRun `/geo trip select <trip ID>` to select a trip.\nIf you are performing this action on images made on or before 8/20/2026, run `/geo trip select default`."
            )
        elif isinstance(error.original, NotTripOwner):
            await ctx.reply(
                f"You can only perform this action when you are an owner of your selected trip. You are not an owner of trip `{id}`."
            )
        elif isinstance(error.original, NotTripSubscriber):
            await ctx.reply(
                f"This channel is not subscribed to trip `{id}`. Subscribe with `/geo trip subscribe {id}`"
            )
        else:
            logger.exception(
                f"Unknown exception while executing command {ctx.command}",
                exc_info=(
                    type(error.original),
                    error.original,
                    error.original.__traceback__,
                ),
            )
    elif isinstance(error, commands.errors.CheckFailure):
        await ctx.reply(
            f"This channel doesn't have permission to run command {ctx.command}."
        )
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.reply(f"Not enough arguments to command `{ctx.command}`.")
    elif isinstance(error, commands.errors.BadArgument) and ctx.command is not None:
        await ctx.reply(f"Incorrect arguments to command `{ctx.command}`.")
    else:
        logger.exception(
            f"Ignoring exception in command {ctx.command}",
            exc_info=(type(error), error, error.__traceback__),
        )
