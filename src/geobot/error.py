from discord.ext import commands
import traceback
import sys
import typing

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

async def handle_error(ctx: commands.Context, error):
    if isinstance(error, SubscriberOnly):
        await ctx.reply(f"This channel is not subscribed to the geobot.\nRun `/geo subscribe` to subscribe.")
    elif isinstance(error, AdminOnly):
        await ctx.reply(f"This channel does not have geobot admin privileges.")
    elif isinstance(error, commands.errors.CommandInvokeError):
        if isinstance(error.original, TagSelectFailure):
            await ctx.reply(f"Failed to generate a tag. Try supplying an unused tag.")
        elif isinstance(error.original, UnknownTag):
            available_tags_str = ", ".join(f"`{tag}`" for tag in error.original.available_tags)
            await ctx.reply(f"`{error.original.tag}` is not the tag of an active geo image.\nActive tags are: {available_tags_str}.")
        else:
            print(f"Unknown exception while executing command {ctx.command}", file=sys.stderr)
            traceback.print_exception(type(error.original), error.original, error.original.__traceback__, file=sys.stderr)
    elif isinstance(error, commands.errors.CheckFailure):
        await ctx.reply(f"This channel doesn't have permission to run command {ctx.command}.")
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.reply(f"Not enough arguments to command `{ctx.command}`.")
    elif isinstance(error, commands.errors.BadArgument) and ctx.command is not None:
        await ctx.reply(f"Incorrect arguments to command `{ctx.command}`.")
    else:
        print(f"Ignoring exception in command {ctx.command}", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)