# Perform simple analysis on stocks by calculating indicators
from Bot import bot
import btalib


class Indicator:
    def __init__(self):
        self.bot = bot.bot

    # def movingAverage(self, symbol):
        # Get the bars for a symbol
