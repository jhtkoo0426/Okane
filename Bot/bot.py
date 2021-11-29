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

    def calcTakeProfit(self, symbol):
        currPrice = float(si.get_live_price(symbol))
        return currPrice * 1.01

    def calcStopLoss(self, symbol):
        currPrice = float(si.get_live_price(symbol))
        return currPrice * 0.99

    def buyOrder(self, symbol, qty):
        takeProfit = dict(limit_price=self.calcTakeProfit(symbol))
        stopLoss = dict(stop_price=self.calcStopLoss(symbol), limit_price=self.calcStopLoss(symbol))
        self.api.submit_order(symbol=symbol, side='buy', type='market', qty=qty, time_in_force='day', take_profit=takeProfit, stop_loss=stopLoss)

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

    def getAccountPositions(self):
        return [i.raw['symbol'] for i in self.api.list_positions()]

    # Function to determine how many shares to buy
    def determineBuyShares(self, sharesPrice):
        current_cash = self.getAccountCash()
        shares_to_buy = math.ceil(float(current_cash) * 0.1 / sharesPrice) # Risking 3% of equity.
        return shares_to_buy

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
                # if floor(remaining_time) % 60 == 0:
                for symbol in watchlist:
                    if self.fetchSymbolBars(symbol) is True:        # Prevent empty dataframe error
                        self.updateBar(symbol)          # Update bar data file

                        self.strategy_macd(symbol)
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
        r = requests.get(f"{self.DATA_BASE_URL}/v1/bars/1Min?symbols={symbol}&limit=200", headers=self.HEADERS)
        data = r.json()
        if not data[symbol]:
            print(f"[SYSTEM]: Data collected from {symbol} is insufficient for analysing.")
            return False
        else:
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
            return True

    # Calls the API to update the bar information.
    def updateBar(self, symbol):
        filepath = f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt"
        filename = f"{symbol}.txt"
        if not os.path.isfile(filepath):
            self.fetchSymbolBars(symbol)

        now = datetime.now(tz=pytz.timezone(self.NY))
        delay = now - timedelta(minutes=15)
        start = pd.Timestamp(delay.strftime("%Y-%m-%d %H:%M"), tz=self.NY).isoformat()

        symbolDF = self.api.get_bars(symbol, TimeFrame(1, TimeFrameUnit.Minute), start=start, end=start, adjustment='raw').df

        if not symbolDF.empty:
            barData = symbolDF.iloc[0]
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

        last_bid_price = si.get_live_price(symbol)

        print(f"[STRATEGY] Recent data for {symbol}:\nLast Bid: {last_bid_price} | MA: {recent_moving_av} | MACD: {macd} | Signal: {signal} | Histogram: {histogram}")

        if recent_moving_av < last_bid_price and macd > 0.1:
        # if recent_moving_av < last_bid_price < 100:
            # if macd > 0:
                # ENTRY: Buy when the MACD crosses over the zero line.
                # NEW: Only buy if no positions for symbol
                if self.getPosition(symbol) is None:
                    quantity = self.determineBuyShares(last_bid_price)
                    if quantity > 0:
                        print(f"[STRATEGY]: Conditions for order for {symbol} are satisfied. Making order...")
                        self.buyOrder(symbol, quantity)
                        print(f"[STRATEGY]: Bought {quantity} shares of {symbol}.")
        try:
            entry = float(self.getPosition(symbol)['avg_entry_price'])
            if macd < 0 or (entry is not None and entry * 1.05 > last_bid_price):
                if self.getPosition(symbol) is not None:
                    self.strategy_macd_sell(symbol, last_bid_price)
                else:
                    pass
        except TypeError:
            pass

    def strategy_macd_sell(self, symbol, last_bid_price):
        # Selling conditions
        positionDetails = self.getPosition(symbol)
        print(positionDetails)
        buyPrice = positionDetails['avg_entry_price']
        takeProfitPrice = float(buyPrice) * 1.01
        stopLossPrice = float(buyPrice) * 0.995

        if last_bid_price > takeProfitPrice:
            print(f"[STRATEGY]: Current price for {symbol} greater than take profit price. Selling for profit :)")
            # EXIT: Sell at a proft or loss when the MACD crosses below the zero line.
            quantity = self.getQty(symbol)
            if quantity is not None:
                self.sellOrder(symbol, quantity)
                print(f"[STRATEGY]: Sold all shares of {symbol}.")
        elif last_bid_price < stopLossPrice:
            print(f"[STRATEGY]: Current price for {symbol} lower than stop loss price. Selling to minimise loss :(")
            # EXIT: Sell at a proft or loss when the MACD crosses below the zero line.
            quantity = self.getQty(symbol)
            if quantity is not None:
                self.sellOrder(symbol, quantity)
                print(f"[STRATEGY]: Sold all shares of {symbol}.")


if __name__ == '__main__':
    bot = Bot()
    bot.start_bot()