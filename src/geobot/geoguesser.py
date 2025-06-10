import discord
from discord.ext import commands
import json
import pathlib
import io
import typing
from geopy import distance
import os
import math

from . import tagbank
from . import error

OWNER_CHANNEL = 1373110407249657958
WORLD_MAXDIST = 14916862

PARENT_PATH = pathlib.Path(__file__).parent
DATA_PATH = pathlib.Path(PARENT_PATH, "data")
JSON_PATH = pathlib.Path(DATA_PATH, "data.json")
IMAGES_PATH = pathlib.Path(DATA_PATH, "images")

# The information needed to uniquely ID a message
class MessageID():
    channel_id: int
    message_id: int

    def __init__(self, message: typing.Optional[discord.Message] = None, channel_id: int = 0, message_id: int = 0):
        if message is None:
            self.channel_id = channel_id
            self.message_id = message_id
        else:
            self.channel_id = message.channel.id
            self.message_id = message.id

    def as_ser(self) -> dict:
        return {
            "channel": self.channel_id,
            "message": self.message_id,
        }
    
    async def get_message(self, bot: commands.Bot) -> discord.Message:
        channel = await get_channel(bot, self.channel_id)
        return await channel.fetch_message(self.message_id)
    
    @classmethod
    def from_ser(cls, ser: dict) -> typing.Self:
        return cls(
            channel_id = ser["channel"],
            message_id = ser["message"]
        )
    
async def get_channel(bot: commands.Bot, id: int) -> typing.Union[discord.TextChannel, discord.DMChannel]:
    channel = await bot.fetch_channel(id)
    if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.DMChannel):
        return channel
    else:
        raise TypeError(f"Subscribed channel {id} is not a TextChannel or DMChannel (is {type(channel)})")
    
def google_maps_url(lat: float, long: float):
    return f"https://www.google.com/maps/search/?api=1&query={lat}%2C{long}"

def google_maps_linked_url(lat: float, long: float):
    return f"[{print_coord_tuple(lat, long)}]( {google_maps_url(lat, long)} )"

def print_coord_tuple(lat: float, long: float):
    return f"{lat:.7f}, {long:.7f}"

class Guess():
    latitude: float
    longitude: float
    message: MessageID

    def __init__(self, lat: float, long: float, message: MessageID):
        self.latitude = lat
        self.longitude = long
        self.message = message

    def google_maps_url(self):
        return google_maps_url(self.latitude, self.longitude)
    
    def google_maps_linked_url(self):
        return google_maps_linked_url(self.latitude, self.longitude)
    
    def as_ser(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "message": self.message.as_ser()
        }
    
    @classmethod
    def from_ser(cls, ser: dict) -> typing.Self:
        return cls(
            ser["latitude"],
            ser["longitude"],
            MessageID.from_ser(ser["message"])
        )

class ImageGame():
    # Image filename
    filename: str

    latitude: float
    longitude: float

    # Game tag
    tag: str

    # The messages containing the image
    image_messages: list[MessageID]
    # The messages that say the command for guessing
    guesshint_messages: list[MessageID]

    # Maps users to guesses
    guesses: dict[int, Guess]

    def __init__(
            self,
            lat: float,
            long: float,
            tag: str,
            filename: str,
            image_messages: list[MessageID],
            guesshint_messages: list[MessageID],
            guesses: dict[int, Guess] | None = None
        ):
        self.latitude = lat
        self.longitude = long
        self.tag = tag
        self.filename = filename
        self.image_messages = image_messages
        self.guesshint_messages = guesshint_messages
        self.guesses = {} if guesses is None else guesses

    def as_ser(self) -> dict:
        return {
            "filename": self.filename,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "tag": self.tag,
            "image_messages": [m.as_ser() for m in self.image_messages],
            "guesshint_messages": [m.as_ser() for m in self.guesshint_messages],
            "guesses": { user: guess.as_ser() for user,guess in self.guesses.items() }
        }
    
    @classmethod
    def from_ser(cls, ser: dict) -> typing.Self:
        return cls(
            lat = ser["latitude"],
            long = ser["longitude"],
            tag = ser["tag"],
            filename = ser["filename"],
            image_messages = [ MessageID.from_ser(id) for id in ser["image_messages"] ],
            guesshint_messages = [ MessageID.from_ser(id) for id in ser["guesshint_messages"] ],
            guesses = { int(user): Guess.from_ser(guess) for user, guess in ser["guesses"].items() }
        )

class Geoguesser():
    # Channels subscribed to the game
    subscribed: set[int]
    # Channels with admin privileges
    admins: set[int]

    bot: commands.Bot

    # Maps image tags to active image games
    images: dict[str, ImageGame]
    closed_images: list[ImageGame]

    tag_bank: tagbank.TagBank

    # Maps player IDs to scores since last reset
    scores: dict[int, int]

    # Largest distance on current map
    maxdist: float

    def __init__(self, bot):
        self.bot = bot

        try:
            self.load()
        except FileNotFoundError:
            self.subscribed = set()
            self.admins = set([OWNER_CHANNEL])
            self.images = {}
            self.closed_images = []
            self.scores = {}
            self.maxdist = WORLD_MAXDIST

        self.tag_bank = tagbank.TagBank()

    def subscribe(self, id):
        self.subscribed.add(id)
        self.save()

    def unsubscribe(self, id):
        self.subscribed.remove(id)
        self.save()

    def save(self):
        data = {
            "subscribed": list(self.subscribed),
            "admins": list(self.admins),
            "images": { k:v.as_ser() for k,v in self.images.items() },
            "closed_images": [ img.as_ser() for img in self.closed_images ],
            "scores": self.scores,
            "maxdist": self.maxdist
        }
        with open(JSON_PATH, "w+") as f:
            json.dump(data, f, indent=4)

    def load(self):
        with open(JSON_PATH) as f:
            data = json.load(f)
            self.subscribed = set(data["subscribed"])
            self.admins = set(data["admins"])
            self.images = { tag: ImageGame.from_ser(ser) for tag, ser in data["images"].items() }
            self.closed_images = [ ImageGame.from_ser(ser) for ser in data["closed_images"] ]
            self.scores = { int(k):v for k,v in data["scores"].items() }
            self.maxdist = data["maxdist"]

    async def message_subscribers(self, *send_args, **send_kwargs) -> list[discord.Message]:
        return await self.message_channels(self.subscribed, *send_args, **send_kwargs)
    
    async def message_admins(self, *send_args, **send_kwargs) -> list[discord.Message]:
        return await self.message_channels(self.admins, *send_args, **send_kwargs)
    
    async def message_channels(self, channels: typing.Iterable[int], *send_args, **send_kwargs) -> list[discord.Message]:
        messages: list[discord.Message] = []
        for id in channels:
            channel = await get_channel(self.bot, id)
            messages.append(await channel.send(*send_args, **send_kwargs))
        return messages
            
    async def new_image(self, image_bytes: io.BytesIO, image_ext: str, latitude: float, longitude: float, tag: typing.Optional[str]) -> str:
        real_tag = self.generate_tag() if tag is None else tag

        filename = real_tag + "." + image_ext
        with open(pathlib.Path(IMAGES_PATH, filename), "wb+") as f:
            f.write(image_bytes.getbuffer())

        messages: list[discord.Message] = []
        for id in self.subscribed:
            channel = await get_channel(self.bot, id)
            image_bytes.seek(0)
            messages.append(
                await channel.send(
                    content=f"# New image to guess:\n### Image tag: `{real_tag}`",
                    file=discord.File(image_bytes, filename)
                )
            )
        image_messages: list[MessageID] = [MessageID(message=message) for message in messages]

        guess_command = f"/geo guess {real_tag} <lat> <long>"
        guesshint_messages = await self.message_subscribers(
            content=f"### To guess, run `{guess_command}`\nSubmissions are **open**! 🟩"
        )
        guesshint_messages = [MessageID(message=message) for message in guesshint_messages]

        img = ImageGame(latitude, longitude, real_tag, filename, image_messages, guesshint_messages)
        self.images[real_tag] = img

        self.save()

        return real_tag

    def generate_tag(self) -> str:
        return self.tag_bank.get_tag(self.images)
    
    def new_guess(self, message: discord.Message, tag: str, lat: float, long: float) -> Guess:
        if tag not in self.images:
            raise error.UnknownTag(tag, self.images.keys())
        image = self.images[tag]

        dist = distance.distance((lat, long), (image.latitude, image.longitude)).meters

        guess = Guess(lat, long, MessageID(message=message))
        image.guesses[message.author.id] = guess

        self.save()

        return guess
    
    async def close_image(self, tag: str):
        if tag not in self.images:
            raise error.UnknownTag(tag, self.images.keys())
        image = self.images.pop(tag)
        self.closed_images.append(image)

        for msg in image.guesshint_messages:
            message = await msg.get_message(self.bot)
            await message.edit(content="Submissions are **closed**! 🟥")

        result_msg = f"Submissions have closed for tag `{tag}`.\n## Guesses:"
        for user,guess in image.guesses.items():
            dist = distance.distance((guess.latitude, guess.longitude), (image.latitude, image.longitude))
            score = self.calc_score(dist.meters)
            self.add_score(user, score)
            dist_str = f"{dist.meters:.1f}m" if dist.meters < 1000 else f"{dist.kilometers:.1f}km"
            result_msg += f"\n<@{user}> guessed {print_coord_tuple(guess.latitude, guess.longitude)} ({dist_str}, score +{score})."
        
        result_msg += f"\n### The actual location was {google_maps_linked_url(image.latitude, image.longitude)}."

        for msg in image.image_messages:
            message = await msg.get_message(self.bot)
            await message.reply(result_msg)
        
        self.save()

        os.remove(pathlib.Path(IMAGES_PATH, image.filename))

    def calc_score(self, distance: float) -> int:
        return round(5000 * math.exp(-10 * distance / self.maxdist))

    async def reset_scores(self):
        self.scores = {}
        await self.message_subscribers("Scores have been reset.")
        self.save()

    def add_score(self, user: int, score: int):
        if user not in self.scores:
            self.scores[user] = 0
        self.scores[user] += score

    def set_maxdist(self, maxdist: float=WORLD_MAXDIST):
        self.maxdist = maxdist
        self.save()