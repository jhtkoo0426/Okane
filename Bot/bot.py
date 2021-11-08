import re
from config import *
import numpy as np
import pandas as pd
import scipy as sc
import alpaca_trade_api as tradeapi
from alpaca_trade_api import TimeFrame, TimeFrameUnit
import logging


# This class communicates between the Alpaca Trade API and Okane.
# https://github.com/alpacahq/alpaca-trade-api-python

# Logger to get all messages from different components.
logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)

class Bot:
    def __init__(self):
        # URLs
        self.BASE_URL = "https://paper-api.alpaca.markets"
        self.DATA_BASE_URL = "https://data.alpaca.markets"

        # Instantiate REST API
        self.api = tradeapi.REST(API_KEY, SECRET_KEY, self.BASE_URL, api_version='v2')

    # Simple order w/o stop loss.
    def simple_order(self, symbol, qty, side, type, time_in_force):
        self.api.submit_order(
            symbol=symbol,
            side=side,
            type=type,
            qty=qty,
            time_in_force=time_in_force
        )

    # Advanced order w/ stop loss.
    def advanced_order(self, symbol, qty, side, type, time_in_force, order_class, take_profit, stop_loss):
        self.api.submit_order(
            symbol=symbol,
            side=side,
            type=type,
            qty=qty,
            time_in_force=time_in_force,
            order_class=order_class,
            take_profit=take_profit,
            stop_loss=stop_loss
        )

    # "Analysis" Methods
    # Get all symbols on the NASDAQ.
    def getAllSymbols(self):
        active_assets = self.api.list_assets(status='active')
        nasdaq_symbols = [a.symbol for a in active_assets if a.exchange == 'NASDAQ']
        return nasdaq_symbols

    # Returns the bars
    def getBars(self, symbol, timeframe, start, end):
        if timeframe == "Minute":
            return self.api.get_bars(symbol, TimeFrame.Minute, start, end, adjustment='raw').df
        elif timeframe.__contains__("Minutes"):
            duration = re.search('(\d+)Minute', timeframe).group(1)
            return self.api.get_bars(symbol, TimeFrame(int(duration), TimeFrameUnit.Minute), start, end,
                                     adjustment='raw').df
        elif timeframe == "Hour":
            return self.api.get_bars(symbol, TimeFrame.Hour, start, end, adjustment='raw').df
        elif timeframe == "Day":
            return self.api.get_bars(symbol, TimeFrame.Day, start, end, adjustment='raw').df

    # def analyseSymbol():
    # model = Model()
    # Run model on given symbol

    # Get the top 5 performing symbols and trade them.


# Test Code - Do NOT run this unless you want to execute the order.
bot = Bot()
print(bot.getBars("AAPL", "Day", "2021-06-08", "2021-06-08"))

