import json
import re

import requests

from config import *
import numpy as np
import pandas as pd
import scipy as sc
import alpaca_trade_api as tradeapi
from alpaca_trade_api import TimeFrame, TimeFrameUnit
import logging
import time
import datetime
import websocket

# This class communicates between the Alpaca Trade API and Okane. It grabs data that the bot needs, but
# the data is not processed in this bot class.
# https://github.com/alpacahq/alpaca-trade-api-python

# Logger to get all messages from different components.
logging.basicConfig(
    filename='errlog.log',
    level=logging.WARNING,
    format='%(asctime)s:%(levelname)s:%(message)s',
)


class Bot:
    def __init__(self):
        # URLs
        self.BASE_URL = "https://paper-api.alpaca.markets"
        self.DATA_BASE_URL = "https://data.alpaca.markets"
        self.STREAM_URL = "wss://data.alpaca.markets/stream"
        self.HEADERS = {
            'APCA-API-KEY-ID': API_KEY,
            'APCA-API-SECRET-KEY': SECRET_KEY
        }
        self.BARS_URL = "https://data.alpaca.markets/v1/bars"

        # Instantiate REST API
        self.api = tradeapi.REST(API_KEY, SECRET_KEY, self.BASE_URL, api_version='v2')

        # For trading with live data:
        # connection = tradeapi.stream2.StreamConn(
        #     API_KEY,
        #     SECRET_KEY,
        #     base_url=self.BASE_URL,
        #     data_url=self.DATA_BASE_URL,
        #     data_stream='alpacadatav1',
        # )

    # Websocket functions
    def stream_websocket(self):
        ws = websocket.WebSocketApp(self.STREAM_URL, on_open=self.on_open, on_message=self.on_message)
        ws.run_forever()

    def on_open(self, ws):
        print("Websocket opened.")

        # Authenticate
        auth_data = {
            "action": "authenticate",
            "data": {"key_id": API_KEY, "secret_key": SECRET_KEY}
        }
        ws.send(json.dumps(auth_data))

        # Get live data from multiple streams (3 currently)
        listen_message = {"action": "listen", "data": {"streams": ["AM.TSLA"]}}
        ws.send(json.dumps(listen_message))

    def on_message(self, ws, message):
        print(f"Received a message: {message}")

    # def on_close(self):
    # Check remaining time till market closes.
    # def time_to_market_close(self):
    #     clock = self.api.get_clock()
    #     return (clock.next_close - clock.timestamp).total_seconds()
    #
    # Put the bot to sleep until the market re-opens.
    # def wait_for_market_open(self):
    #     clock = self.api.get_clock()
    #     if not clock.is_open():
    #         time_to_open = (clock.next_open - clock.timestamp).total_seconds()
    #         time.sleep(round(time_to_open))

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

    # symbol = list of symbols
    def getBars(self, timeframe, symbol):
        symbols = ",".join(symbol)
        r = requests.get(f"{self.BARS_URL}/{timeframe}?symbols={symbols}&limit=1000", headers=self.HEADERS)
        print(json.dumps(r.json(), indent=4))

    # 100 Symbols limit per request!
    def getAllBars(self, timeframe, symbollist):
        symbols = ",".join(symbollist)
        r = requests.get(f"{self.BARS_URL}/{timeframe}?symbols={symbols}&limit=1000", headers=self.HEADERS)
        print(json.dumps(r.json(), indent=4))

    # def analyseSymbol():
    # model = Model()
    # Run model on given symbol

    # Get the top 5 performing symbols and trade them.


# Test Code - Do NOT run this unless you want to execute the order.
bot = Bot()
# bot.stream_websocket()
bot.getBars("1D", bot.getAllSymbols()[:100])
