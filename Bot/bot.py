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

from config import API_KEY, SECRET_KEY


class Bot:
    def __init__(self):
        self.NY = 'America/New_York'
        self.BASE_URL = URL("https://paper-api.alpaca.markets")
        self.DATA_BASE_URL = "https://data.alpaca.markets"
        self.HEADERS = {'APCA-API-KEY-ID': API_KEY,
                        'APCA-API-SECRET-KEY': SECRET_KEY}

        self.api = tradeapi.REST(API_KEY, SECRET_KEY, self.BASE_URL, api_version='v2')

    def fetchSymbolBars(self, symbol):
        print("getbars")
        r = requests.get(f"{self.DATA_BASE_URL}/v1/bars/1Min?symbols={symbol}&limit=1000", headers=self.HEADERS)
        data = r.json()

        # Check if data file for the symbol exists, if not create file.
        filename = f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt"
        f = open(filename, 'w+')
        f.write('Date,Open,High,Low,Close,Volume,MACD\n')

        # Get bars of symbol
        bars = data[symbol]

        # Format each line
        for bar in bars:
            t = datetime.fromtimestamp(bar['t'])
            day = t.strftime('%Y-%m-%d')
            line = f"{day},{bar['o']},{bar['h']},{bar['l']},{bar['c']},{bar['v']},0.0\n"
            f.write(line)

        print(f"[SYSTEM]: Added/Updated {symbol}.txt.")

    def updateBar(self, symbol):
        filepath = f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt"
        filename = f"{symbol}.txt"
        if not os.path.isfile(filepath):
            self.fetchSymbolBars(symbol)

        now = datetime.now(tz=pytz.timezone(self.NY))
        delay = now - timedelta(minutes=15)
        start = pd.Timestamp(delay.strftime("%Y-%m-%d %H:%M"), tz=self.NY).isoformat()

        data = self.api.get_bars(symbol, TimeFrame(1, TimeFrameUnit.Minute), start=start, end=start, adjustment='raw').df.iloc[0]
        op, high, low, close, volume = str(data['open']), str(data['high']), str(data['low']), str(data['close']), str(data['trade_count'])
        date = delay.strftime("%Y-%m-%d")
        writeData = ','.join([date, op, high, low, close, volume, "0.0"])

        with open(filepath, 'a') as f:
            f.write(writeData)
            f.write("\n")
            print(f"[SYSTEM]: Updated bar file for {symbol}.txt.")

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
                # print(timeformat)
                sys.stdout.write(f"\r{timeformat}")
                sys.stdout.flush()
                time_to_open -= 1
                time.sleep(1)
        self.start_bot()

    # Read csv into dataframe
    def extractCSV(self, symbol):
        return pd.read_csv(f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt", parse_dates=True, index_col="Date")

    # Main function to trigger any action when market opens.
    def start_bot(self):
        self.fetchSymbolBars("AAPL")
        remaining_time = self.time_to_market_close()
        while remaining_time > 120:
            # Get bars every 1 minute (with current 15 minute delay).
            if floor(remaining_time) % 60 == 0:
                self.updateBar("AAPL")
                macd, signal, histogram = self.calc_macd("AAPL")
            remaining_time -= 1
            time.sleep(1)

    # Implement MACD Strategy
    def calc_macd(self, symbol):
        dataf = self.extractCSV(symbol)
        res = btalib.macd(dataf).df         # Resulting dataframe after calculating MACD.
        recent = res.iloc[-1]               # Retrieve the most recent (with 15 min delay) MACD data.
        macd, signal, histogram = recent['macd'], recent['signal'], recent['histogram']
        return macd, signal, histogram


if __name__ == '__main__':
    bot = Bot()
    if bot.time_to_market_close() < 120:
        print("[SYSTEM]: Market is closing in 2 minutes.")
    elif bot.time_to_market_close() == 0:
        print("[SYSTEM]: Market has closed. Bot will now sleep. Goodnight!")
    data = bot.api.get_clock().raw
    bot.wait_for_market_open()