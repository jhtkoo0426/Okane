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
from alpaca_trade_api.rest import APIError

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

    def buyOrder(self, symbol, qty):
        self.api.submit_order(symbol=symbol, side='buy', type='market', qty=qty, time_in_force='day')

    def sellOrder(self, symbol, qty):
        self.api.submit_order(symbol=symbol, side='sell', type='market', qty=qty, time_in_force='day')

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

    # Function to determine how many shares to buy
    def determineBuyShares(self, sharesPrice):
        current_cash = self.getAccountCash()
        shares_to_buy = math.ceil(float(current_cash) * 0.05 / sharesPrice) # Risking 3% of equity.
        return shares_to_buy

    # Main function to activate bot.
    def start_bot(self):
        print("[SYSTEM]: Starting Bot")
        if self.marketIsOpen() is True:
            remaining_time = self.time_to_market_close()
            while remaining_time > 120:
                # Get bars every 1 minute (with current 15 minute delay).
                if floor(remaining_time) % 60 == 0:
                    symbols = ["AAPL", "MSFT", "NVDA", "RIVN", "TSLA", "LCID", "PYPL", "BABA", "PROG", "PLTR"]
                    for symbol in symbols:
                        self.fetchSymbolBars(symbol)
                        self.updateBar(symbol)          # Update bar data file
                        self.strategy_macd(symbol)      # Calculate the newest MACD from the updated file.
                remaining_time -= 1
                time.sleep(1)
            if 0 < remaining_time < 120:
                print("[SYSTEM]: Market is closing in 2 minutes.")
            elif remaining_time == 0:
                print("[SYSTEM]: Market has closed. Bot will now sleep. Goodnight!")
        self.wait_for_market_open()

    # Data-related functions
    # Get bars for a symbol. Create a file for the symbol if it doesn't exist. Update the file otherwise.
    def fetchSymbolBars(self, symbol):
        print(f"[SYSTEM]: Fetching most recent bars for {symbol}.")
        r = requests.get(f"{self.DATA_BASE_URL}/v1/bars/1Min?symbols={symbol}&limit=1000", headers=self.HEADERS)
        data = r.json()

        # Check if data file for the symbol exists, if not create file.
        filename = f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt"
        f = open(filename, 'w+')
        f.write('Date,Open,High,Low,Close,Volume\n')

        # Get bars of symbol
        bars = data[symbol]

        # Format each line
        for bar in bars:
            t = datetime.fromtimestamp(bar['t'])
            day = t.strftime('%Y-%m-%d')
            line = f"{day},{bar['o']},{bar['h']},{bar['l']},{bar['c']},{bar['v']}\n"
            f.write(line)
        print(f"[SYSTEM]: Added/Updated {symbol}.txt.")

    # Calls the API to update the bar information.
    def updateBar(self, symbol):
        filepath = f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt"
        filename = f"{symbol}.txt"
        if not os.path.isfile(filepath):
            self.fetchSymbolBars(symbol)

        now = datetime.now(tz=pytz.timezone(self.NY))
        delay = now - timedelta(minutes=15)
        start = pd.Timestamp(delay.strftime("%Y-%m-%d %H:%M"), tz=self.NY).isoformat()

        barData = self.api.get_bars(symbol, TimeFrame(1, TimeFrameUnit.Minute), start=start, end=start, adjustment='raw').df.iloc[0]
        op, high, low, close, volume = str(barData['open']), str(barData['high']), str(barData['low']), str(barData['close']), str(barData['trade_count'])
        date = delay.strftime("%Y-%m-%d")
        writeData = ','.join([date, op, high, low, close, volume])

        with open(filepath, 'a') as f:
            f.write(writeData)
            f.write("\n")
            print(f"[SYSTEM]: Updated bar file for {symbol}.txt.")

    # Read csv into dataframe
    def CSVtoDF(self, symbol):
        return pd.read_csv(f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt", parse_dates=True, index_col="Date")

    # Save changes back to csv
    def DFtoCSV(self, df, symbol):
        df.to_csv(f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt")
        print(f"[SYSTEM]: Updated bar data for {symbol} and saved to {symbol}.txt.")

    # Technical Indicators
    def calc_macd(self, symbol):
        dataframe = self.CSVtoDF(symbol)
        res = btalib.macd(dataframe).df         # Resulting dataframe after calculating MACD.
        recent = res.iloc[-1]               # Retrieve the most recent (with 15 min delay) MACD data.
        macd, signal, histogram = recent['macd'], recent['signal'], recent['histogram']
        return macd, signal, histogram

    def calc_ma(self, symbol, period):
        dataframe = self.CSVtoDF(symbol)
        result = btalib.sma(dataframe, period=period).df

        # Return the most recent calculation.
        recent = result.iloc[-1]['sma']
        return recent

    # Strategy
    def strategy_macd(self, symbol):
        # https://www.flowbank.com/en/research/what-is-macd-a-macd-trading-strategy-example
        # LONG/SHORT: Take long MACD signals when price is above the 200 period-moving average.
        macd, signal, histogram = self.calc_macd(symbol)
        recent_moving_av = self.calc_ma(symbol, 200)        # Calculate 200-period moving average.

        last_bid = self.api.get_last_quote(symbol).raw
        last_bid_price = last_bid["bidprice"]

        print(f"[STRATEGY] Recent data for {symbol}:\nLast Bid: {last_bid_price} | MA: {recent_moving_av} | MACD: {macd} | Signal: {signal} | Histogram: {histogram}")

        if last_bid_price > recent_moving_av:
            print(f"[STRATEGY]: Conditions for order for {symbol} are satisfied. Making order...")
            if macd > 0:
                # ENTRY: Buy when the MACD crosses over the zero line.
                quantity = self.determineBuyShares(last_bid_price)
                self.buyOrder(symbol, quantity)
                print(f"[STRATEGY]: Bought {quantity} shares of {symbol}.")
        if macd < 0:
            # EXIT: Sell at a proft or loss when the MACD crosses below the zero line.
            quantity = self.getQty(symbol)
            if quantity is not None:
                self.sellOrder(symbol, quantity)
            print(f"[STRATEGY]: Sold all shares of {symbol}.")


bot = Bot()
bot.start_bot()