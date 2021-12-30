import json
import math
import os.path
import sys
from math import floor
import time
from datetime import datetime, timedelta

import alpaca_trade_api as tradeapi
import btalib
import pandas as pd
import pytz
import requests
from alpaca_trade_api import TimeFrame, TimeFrameUnit
from alpaca_trade_api.stream import URL
from alpaca_trade_api.rest import APIError, REST, TimeFrame
import yahoo_fin.stock_info as si

from Bot.config import API_KEY, SECRET_KEY


class Bot:
    def __init__(self):
        self.NY = 'America/New_York'
        self.BASE_URL = URL("https://paper-api.alpaca.markets")
        self.DATA_BASE_URL = "https://data.alpaca.markets"
        self.HEADERS = {'APCA-API-KEY-ID': API_KEY,
                        'APCA-API-SECRET-KEY': SECRET_KEY}

        self.api = tradeapi.REST(API_KEY, SECRET_KEY, self.BASE_URL, api_version='v2')

    # Bot essential functions
    def marketIsOpen(self):
        return self.api.get_clock().raw['is_open']

    def time_to_market_close(self):
        clock = self.api.get_clock()
        return (clock.next_close - clock.timestamp).total_seconds()

    # Put the bot to sleep until the market re-opens.
    def wait_for_market_open(self):
        clock = self.api.get_clock()
        if self.marketIsOpen() is False:
            print("[SYSTEM]: Market currently closed.")
            time_to_open = round((clock.next_open - clock.timestamp).total_seconds())
            while time_to_open > 0:
                days, secs = divmod(time_to_open, 86400)
                hours, secs = divmod(secs, 3600)
                mins, secs = divmod(secs, 60)
                timeformat = '{:02d}D | {:02d}H | {:02d}M | {:02d}s'.format(days, hours, mins, secs)
                sys.stdout.write(f"\r{timeformat}")
                sys.stdout.flush()
                time_to_open -= 1
                time.sleep(1)
        self.start_bot()

    def getPosition(self, symbol):
        try:
            return self.api.get_position(symbol).raw
        except APIError:
            return None

    def getQty(self, symbol):
        position = self.getPosition(symbol)
        if position is None:
            return None
        else:
            return position['qty']

    def getAccountDetails(self):
        return self.api.get_account().raw

    def getAccountStatus(self):
        return self.getAccountDetails()['status']

    def getAccountCash(self):
        return self.getAccountDetails()['cash']

    def getAccountEquity(self):
        return self.getAccountDetails()['equity']

    def getAccountPositions(self):
        return [i.raw['symbol'] for i in self.api.list_positions()]

    def calcTakeProfit(self, symbol):
        currPrice = float(si.get_live_price(symbol))
        return currPrice * 1.01

    def calcStopLoss(self, symbol):
        currPrice = float(si.get_live_price(symbol))
        return currPrice * 0.99

    def buyOrder(self, symbol, qty):
        takeProfit = dict(limit_price=self.calcTakeProfit(symbol))
        stopLoss = dict(stop_price=self.calcStopLoss(symbol), limit_price=self.calcStopLoss(symbol))
        self.api.submit_order(symbol=symbol, side='buy', type='market', qty=qty, time_in_force='day',
                              take_profit=takeProfit, stop_loss=stopLoss)

    def sellOrder(self, symbol, qty):
        self.api.submit_order(symbol=symbol, side='sell', type='market', qty=qty, time_in_force='day')

    # Function to determine how many shares to buy
    def determineBuyShares(self, sharesPrice):
        current_cash = self.getAccountCash()
        shares_to_buy = math.ceil(float(current_cash) * 0.05 / sharesPrice) # Risking 5% of equity.
        return shares_to_buy

    # Data-related functions
    # Get bars for a symbol. Create a file for the symbol if it doesn't exist. Update the file otherwise.
    def getHourBars(self, symbol):
        todayDate = datetime.now().strftime("%Y-%m-%d")
        start = pd.Timestamp(todayDate, tz=self.NY).isoformat()
        bars = self.api.get_bars([symbol], TimeFrame(1, TimeFrameUnit.Hour), adjustment='raw', start=start).df
        return bars

    # Technical Indicators
    # Heiken Ashi Candlesticks
    # https://stackoverflow.com/questions/40613480/heiken-ashi-using-pandas-python
    def calc_ha(self, df, symbol):
        dataframe = df.copy()
        dataframe['HA_close'] = (dataframe['open'] + dataframe['high'] + dataframe['low'] + dataframe['close']) / 4
        idx = dataframe.index.name
        dataframe.reset_index(inplace=True)
        for i in range(0, len(dataframe)):
            if i == 0:
                dataframe._set_value(i, 'HA_open', ((dataframe._get_value(i, 'open') + dataframe._get_value(i, 'close')) / 2))
            else:
                dataframe._set_value(i, 'HA_open', ((dataframe._get_value(i - 1, 'HA_open') + dataframe._get_value(i - 1, 'HA_close')) / 2))

        if idx:
            dataframe.set_index(idx, inplace=True)

        dataframe['HA_high'] = dataframe[['HA_open', 'HA_close', 'high']].max(axis=1)
        dataframe['HA_low'] = dataframe[['HA_open', 'HA_close', 'low']].min(axis=1)
        print(f"[INDICATOR]: Geneated Heiken Ashi Candlesticks for {symbol}.")
        return dataframe

    # Strategy
    def exec(self, symbol):
        bars = self.getHourBars(symbol)         # Get Raw dataframe
        heikenAshiBars = self.calc_ha(bars, symbol)     # Generate HA dataframe
        print(heikenAshiBars)

    # Main function to activate bot.
    def start_bot(self):
        print("[SYSTEM]: Starting Bot")
        if self.marketIsOpen() is True:
            remaining_time = self.time_to_market_close()
            while remaining_time > 120:
                # Watch all symbols that are involved:
                symbols = si.get_day_most_active(25)['Symbol'].to_list()
                positions = self.getAccountPositions()  # Get all current positions
                watchlist = list(set(symbols + positions))

                # Get bars every 1 minute (with current 15 minute delay).
                if floor(remaining_time) % 60 == 0:
                    for symbol in watchlist:
                        self.exec(symbol)
                remaining_time -= 1
                time.sleep(1)
            if 0 < remaining_time < 120:
                print("[SYSTEM]: Market is closing in 2 minutes.")
            elif remaining_time == 0:
                print("[SYSTEM]: Market has closed. Bot will now sleep. Goodnight!")
        self.wait_for_market_open()


if __name__ == '__main__':
    bot = Bot()
    bot.start_bot()
