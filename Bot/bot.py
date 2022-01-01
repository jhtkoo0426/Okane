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

    def getSymbolCurrentPrice(self, symbol):
        return si.get_live_price(symbol)

    # Function to determine how many shares to buy
    def determineBuyShares(self, sharesPrice):
        current_cash = self.getAccountCash()
        shares_to_buy = math.ceil(float(current_cash) * 0.1 / sharesPrice)  # Risking 3% of equity.
        return shares_to_buy

    # def buyOrder(self, symbol, qty):
    #     takeProfit = dict(limit_price=self.calcTakeProfit(symbol))
    #     stopLoss = dict(stop_price=self.HA_Strategy_Stop_Loss(symbol), limit_price=self.HA_Strategy_Stop_Loss(symbol))
    #     self.api.submit_order(symbol=symbol, side='buy', type='market', qty=qty, time_in_force='day',
    #                           take_profit=takeProfit, stop_loss=stopLoss)

    def sellOrder(self, symbol, qty):
        self.api.submit_order(symbol=symbol, side='sell', type='market', qty=qty, time_in_force='day')

    # Data-related functions
    # Get bars for a symbol.
    # symbol = list of symbols / single symbol
    # hourFrame = 1 hour / 4 hours depending on heiken-ashi strategy
    def getHourBars(self, symbol, hourFrame):
        nowTime = datetime.now()
        twoWeekTime = nowTime - timedelta(days=7)
        todayDate = nowTime.strftime("%Y-%m-%d")
        oneWeekDate = twoWeekTime.strftime("%Y-%m-%d")

        start = pd.Timestamp(oneWeekDate, tz=self.NY).isoformat()
        end = pd.Timestamp(todayDate, tz=self.NY).isoformat()
        bars = self.api.get_bars([symbol], TimeFrame(hourFrame, TimeFrameUnit.Hour), adjustment='raw', start=start, end=end).df
        return bars

    # Technical Indicators
    # Heiken Ashi Candlesticks
    # https://stackoverflow.com/questions/40613480/heiken-ashi-using-pandas-python
    def calc_ha(self, df):
        dataframe = df.copy()

        # Calculating close bar for HA = 0.25(open + high + low + close)
        dataframe['HA_close'] = (dataframe['open'] + dataframe['high'] + dataframe['low'] + dataframe['close']) / 4
        idx = dataframe.index.name
        dataframe.reset_index(inplace=True)

        # Calculating open bar for HA = 0.5(ytd open + ytd close)
        for i in range(0, len(dataframe)):
            # Determine open bar for HA
            if i == 0:
                dataframe._set_value(i, 'HA_open', ((dataframe._get_value(i, 'open') + dataframe._get_value(i, 'close')) / 2))
            else:
                dataframe._set_value(i, 'HA_open', ((dataframe._get_value(i - 1, 'HA_open') + dataframe._get_value(i - 1, 'HA_close')) / 2))

        if idx:
            dataframe.set_index(idx, inplace=True)

        dataframe['HA_high'] = dataframe[['HA_open', 'HA_close', 'high']].max(axis=1)
        dataframe['HA_low'] = dataframe[['HA_open', 'HA_close', 'low']].min(axis=1)

        # Determining bar type for each timeframe
        HADataframe = self.createHABars(dataframe)
        return HADataframe

    def createHABars(self, dataframe):
        df = dataframe.copy()
        for index, row in df.iterrows():
            # Determining bar type for each timeframe
            high, low, open, close = row['HA_high'], row['HA_low'], row['HA_open'], row['HA_close']
            barType = self.HADetermineBarType(high, low, open, close)
            df._set_value(index, 'barType', barType)
        return df

    def HADetermineTrend(self, dataframe):
        df = dataframe.copy()
        ph, pl = -1, -1
        for index, row in df.iterrows():
            high, low = row['HA_high'], row['HA_low']
            if index != 0:
                if low > pl and high > ph:
                    # Uptrend
                    df._set_value(index, 'trend', 'UPTREND')
                elif low < pl and high < ph:
                    # Downtrend
                    df._set_value(index, 'trend', 'DOWNTREND')
                else:
                    # TODO: Research on what to do if (low > pl and high < ph) and (low < pl and high > ph).
                    df._set_value(index, 'trend', 'UNDETERMINED')
            else:
                df._set_value(index, 'trend', 'NaN')
            ph, pl = high, low
        return df

    # Auxiliary function to determine the type of bar for the Heiken-Ashi strategy
    def HADetermineBarType(self, high, low, open, close):
        if low == open and high > close:
            # Bullish trend: Price increasing
            return "BULL"
        elif high == open and low < close:
            # Bearish trend: Price decreasing
            return "BEAR"
        else:
            # Indecisive bar
            return "INDECISIVE"

    def HADetermineStopLoss(self, dataframe):
        # Determining bar type for each timeframe
        lastBear = -1  # Variable to determine the final bear bar in the dataframe
        for index, row in dataframe.iterrows():
            # Determine bar type
            high, low, open, close = row['HA_high'], row['HA_low'], row['HA_open'], row['HA_close']
            res = self.HADetermineBarType(high, low, open, close)
            dataframe._set_value(index, 'barType', res)
            if res == "BEAR":
                lastBear = index
        return lastBear

    def HA_buy_order(self, symbol, stopLossPrice, qty):
        takeProfit = dict(limit_price=self.calcTakeProfit(symbol))
        stopLoss = dict(stop_price=stopLossPrice, limit_price=stopLossPrice)
        self.api.submit_order(symbol=symbol, side='buy', type='market', qty=qty, time_in_force='day',
                              take_profit=takeProfit, stop_loss=stopLoss)

    def calc_ema(self, df, period):
        dataframe = df.copy()
        ema = btalib.ema(dataframe, period).df
        combinedDF = pd.concat([dataframe, ema], axis=1)

        # Renaming ema column
        combinedDF.rename(columns={'ema': f'ema{period}'}, inplace=True)
        return combinedDF

    # Strategy
    def exec(self, symbol):
        one_hour_bars = self.getHourBars(symbol, 1)         # Get 1hr raw dataframe
        one_hour_ha_bars = self.calc_ha(one_hour_bars)      # Generate HA dataframe (1 hr)

        # Apply EMA Indicators
        one_hour_ha_ema10 = self.calc_ema(one_hour_ha_bars, 10)
        one_hour_ha_ema30 = self.calc_ema(one_hour_ha_ema10, 30)

        # Determine share price trend
        finalDF = self.HADetermineTrend(one_hour_ha_ema30)

        ema10, ema30 = finalDF.iloc[-1]['ema10'], finalDF.iloc[-1]['ema30']
        lastBar = finalDF.iloc[-1]['barType']
        trend = finalDF.iloc[-1]['trend']

        # Determine entry point
        print(f"[HA STRATEGY INFO]: lastBar: {lastBar} | ema10: {ema10} | ema30: {ema30} | trend: {trend}")
        if lastBar == "BULL" and ema10 > ema30 and trend == "UPTREND":
            print(f"[HA STRATEGY]: Conditions satisfied to buy {symbol}.")
            stopLossPrice = self.HADetermineStopLoss(finalDF)

            # TODO: Find way to determine how many shares to buy
            symbolCurrentPrice = self.getSymbolCurrentPrice(symbol)
            qty = math.floor(self.getAccountEquity() * 0.05 / self.determineBuyShares(symbolCurrentPrice))
            self.HA_buy_order(symbol, stopLossPrice, qty)
            print(f"[HA STRATEGY]: Bought {qty} shares of {symbol}.")
        elif lastBar == "BEAR" and ema10 < ema30 and trend == "DOWNTREND":
            print(f"[HA STRATEGY]: STOP LOSS: Selling all shares of {symbol}.")
            qty = self.getPosition(symbol)
            self.sellOrder(symbol, qty)
        else:
            print(f"[HA STRATEGY]: Continuing holding {symbol}.")

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

    # Main Function alternative for testing
    def mainTesting(self):
        print("[SYSTEM]: Starting Testing Bot")
        # Watch all symbols that are involved:
        symbols = si.get_day_most_active(25)['Symbol'].to_list()
        positions = self.getAccountPositions()  # Get all current positions
        watchlist = list(set(symbols + positions))
        for symbol in watchlist:
            self.exec(symbol)


if __name__ == '__main__':
    bot = Bot()
    bot.start_bot()
    # bot.mainTesting()
