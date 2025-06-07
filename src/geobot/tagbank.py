import pathlib
import random
import typing
import os

from . import error

PARENT_PATH = pathlib.Path(__file__).parent
DATA_PATH = pathlib.Path(PARENT_PATH, "data")
WORDS_PATH = pathlib.Path(DATA_PATH, "WORDS.txt")
MAX_SELECT_ITERATIONS = 1000

class TagBank():
    tags: list[str]
    words_file: os.PathLike

    def __init__(self, words_file: typing.Optional[os.PathLike] = None):
        self.words_file = WORDS_PATH if words_file is None else words_file
        self.load()

    def load(self):
        with open(self.words_file) as f:
            self.tags = [line.strip() for line in f.readlines() if len(line.strip()) > 0]

    def get_tag(self, exclude: typing.Optional[typing.Iterable[str]]) -> str:
        if exclude is None:
            return random.choice(self.tags)
        else:
            for i in range(MAX_SELECT_ITERATIONS):
                choice = random.choice(self.tags)
                if choice not in exclude:
                    return choice
            raise error.TagSelectFailure()
        