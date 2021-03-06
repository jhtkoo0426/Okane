import math
import sys
from math import floor
import time
from datetime import datetime, timedelta
from threading import Thread

import alpaca_trade_api as tradeapi
import btalib
import pandas as pd
from alpaca_trade_api import TimeFrameUnit
from alpaca_trade_api.stream import URL
from alpaca_trade_api.rest import APIError, TimeFrame
import yahoo_fin.stock_info as si
import yfinance as yf
from requests.exceptions import HTTPError

from Bot.config import API_KEY, SECRET_KEY

from termcolor import colored
import timeit


class Bot:
    def __init__(self):
        self.NY = 'America/New_York'
        self.BASE_URL = URL("https://paper-api.alpaca.markets")
        self.DATA_BASE_URL = "https://data.alpaca.markets"
        self.HEADERS = {'APCA-API-KEY-ID': API_KEY,
                        'APCA-API-SECRET-KEY': SECRET_KEY}
        self.api = tradeapi.REST(API_KEY, SECRET_KEY, self.BASE_URL, api_version='v2')
        self.account = self.api.get_account().raw

    # Market status functions
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

    # Account functions
    def getAccountStatus(self):
        return self.account['status']

    def getAccountCash(self):
        return self.account['cash']

    def getAccountEquity(self):
        return self.account['equity']

    def getAccountPositions(self):
        return [i.raw['symbol'] for i in self.api.list_positions()]

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

    def determineSell(self, symbol, currentPrice):
        position = self.getPosition(symbol)
        if position is None:
            return None
        else:
            entry = position['avg_entry_price']
            if currentPrice > float(entry) * 1.03:
                # SELL IMMEDIATELY FOR PROFIT
                return "PROFIT"
            elif currentPrice < float(entry) * 0.98:
                return "LOSS"
            else:
                return None

    # Get live (as much as possible) price of symbol
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

    # System-related functions
    def writeSystemMsg(self, msg, color):
        sys.stdout.write(colored(msg, color))

    # Data-related functions
    # Get bars for a symbol.
        # symbol = list of symbols / single symbol
        # hourFrame = 1 hour / 4 hours depending on heiken-ashi strategy
    def getHourBars(self, symbol, hourFrame):
        try:
            nowTime = datetime.now()
            twoWeekTime = nowTime - timedelta(days=14)
            todayDate = nowTime.strftime("%Y-%m-%d")
            oneWeekDate = twoWeekTime.strftime("%Y-%m-%d")

            start = pd.Timestamp(oneWeekDate, tz=self.NY).isoformat()
            end = pd.Timestamp(todayDate, tz=self.NY).isoformat()
            bars = self.api.get_bars([symbol], TimeFrame(hourFrame, TimeFrameUnit.Hour), adjustment='raw', start=start,
                                     end=end).df
            return bars
        except HTTPError:
            self.writeSystemMsg(f"[ALPACA SERVER ERROR]: Cannot get data for {symbol}.\n", 'red')
            return None

    # Technical Indicators
    # Heiken Ashi Candlesticks
    # https://stackoverflow.com/questions/40613480/heiken-ashi-using-pandas-python
    def calc_ha(self, df):
        dataframe = df.copy()

        if len(dataframe) != 0:
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

            # Add bar type and trend data to symbol dataframe.
            HADataframe = self.analyseHABars(dataframe)
            return HADataframe
        return None

    def analyseHABars(self, dataframe):
        df = dataframe.copy()
        for index, row in df.iterrows():
            high, low, opn, close = row['HA_high'], row['HA_low'], row['HA_open'], row['HA_close']
            barType = self.HADetermineBarType(high, low, opn, close)
            df._set_value(index, 'barType', barType)
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
            barType = row['barType']
            if barType == "BEAR":
                lastBear = row['low']
        return lastBear

    def HABuyOrder(self, symbol, stopLossPrice, qty):
        stopLoss = dict(stop_price=stopLossPrice)
        try:
            self.api.submit_order(symbol=symbol, side='buy', type='market', qty=qty, time_in_force='day',
                                  stop_loss=stopLoss)
        except APIError:
            print(f"{symbol} is not tradable.")

    # Calculate ema10 and ema30.
    def calc_ema(self, df):
        dataframe = df.copy()

        # Insufficient data to generate ema30
        if len(dataframe) < 40:
            return None
        else:
            ema20 = btalib.ema(dataframe, 20).df['ema']
            combinedDF = pd.concat([dataframe, ema20], axis=1)
            combinedDF.rename(columns={'ema': f'ema20'}, inplace=True)  # Rename column
            return combinedDF

    # This function counts the number of different bar types to determine the symbol's trend direction.
    def determineTrend(self, dataframe):
        df = dataframe.copy()
        barTypeList = df['barType'].tolist()
        bull, bear, indecisive = barTypeList.count("BULL"), barTypeList.count("BEAR"), barTypeList.count("INDECISIVE")

        # We define a pullback = 60% or more non-indecisive bars are BEAR before the price rises.
        # We define a downtrend = 60% or more non-indecisive bars are BULL before the price drops.
        if bear >= (len(barTypeList) - indecisive) * 0.5:
            return "PULLBACK"
        elif bull > (len(barTypeList) - indecisive) * 0.5:
            return "DROP"
        else:
            return "NO TREND"

    def strategy_buy(self, symbol, currentBar, trendType, currentSymbolPrice, one_hr_DF):
        if self.getPosition(symbol) is not None:
            if currentBar == "BULL" and trendType == "PULLBACK":
                qty = self.determineBuyShares(currentSymbolPrice)
                stopLoss = self.HADetermineStopLoss(one_hr_DF)
                self.HABuyOrder(symbol, stopLoss, qty)
                self.writeSystemMsg(f"[STRATEGY - {symbol} (BUY)]: Pullback detected - buying {qty} share(s).\n", 'blue')
            else:
                self.writeSystemMsg(f"[STRATEGY - {symbol} (BUY)]: Continue holding.\n", 'green')
        else:
            self.writeSystemMsg(f"[STRATEGY - {symbol} (SELL)]: No shares, do nothing.\n", 'grey')

    def strategy_sell(self, symbol, currentBar, prevBar, trendType):
        # Check if we hold shares for the symbol.
        if self.getPosition(symbol) is not None:
            if currentBar == "BEAR" and prevBar == "BEAR" and trendType == "DROP":
                qty = self.getQty(symbol)
                self.sellOrder(symbol, qty)
                self.writeSystemMsg(f"[STRATEGY - {symbol} (SELL)]: Downtrend detected - selling all share(s)\n.", 'yellow')
            else:
                self.writeSystemMsg(f"[STRATEGY - {symbol} (BUY)]: Continue holding.\n", 'green')
        else:
            self.writeSystemMsg(f"[STRATEGY - {symbol} (SELL)]: No shares, do nothing.\n", 'grey')

    # This function determines if a symbol satisfies all the criteria.
    def strategy(self, symbol):
        one_hour_bars = self.getHourBars(symbol, 1)     # Get 1hr raw dataframe

        if one_hour_bars is None:
            self.writeSystemMsg(f"[STRATEGY - {symbol}]: Insufficient data.\n", 'red')
        else:
            one_hour_ha_bars = self.calc_ha(one_hour_bars)  # Generate HA dataframe (1 hr)
            if one_hour_ha_bars is None:
                self.writeSystemMsg(f"[STRATEGY - {symbol}]: Insufficient data.\n", 'red')
            else:
                one_hr_DF = self.calc_ema(one_hour_ha_bars)  # Calculate EMA20 for the dataframe.
                if one_hr_DF is None or one_hr_DF.empty:
                    self.writeSystemMsg(f"[STRATEGY - {symbol}]: Insufficient data.\n", 'red')
                else:
                    currentEMA20 = one_hr_DF.iloc[-1]['ema20']
                    # currentSymbolPrice = si.get_live_price(symbol)
                    currentSymbolPrice = self.getSymbolCurrentPrice(symbol)

                    trendType = self.determineTrend(one_hr_DF)
                    currentBar, prevBar = one_hr_DF.iloc[-1]['barType'], one_hr_DF.iloc[-2]['barType']

                    sell_bool = self.determineSell(symbol, currentSymbolPrice)
                    # Emergency sell
                    if sell_bool == "PROFIT":
                        qty = self.getQty(symbol)
                        self.sellOrder(symbol, qty)
                        self.writeSystemMsg(f"[STRATEGY - {symbol} (EMERGENCY SELL)]: Selling all share(s) for profit.\n", 'yellow')
                    elif sell_bool == "LOSS":
                        qty = self.getQty(symbol)
                        self.sellOrder(symbol, qty)
                        self.writeSystemMsg(f"[STRATEGY - {symbol} (EMERGENCY SELL)]: Selling all share(s) to stop loss.\n", 'yellow')
                    else:
                        if currentSymbolPrice > currentEMA20:
                            # Buy the symbol - Check for bar conditions (last 2 are BULL, trend is in pullback)
                            self.strategy_buy(symbol, currentBar, trendType, currentSymbolPrice, one_hr_DF)
                        else:
                            # Sell the symbol - Check for bar conditions
                            self.strategy_sell(symbol, currentBar, prevBar, trendType)

    def exec(self, watchlist):
        now = datetime.now()
        if now.minute == 0:
            self.writeSystemMsg("\nRunning Strategy...\n", 'yellow')
            sys.stdout.write("\033[H\033[J")
            self.writeSystemMsg(f"[SYSTEM]: Current watchlist has {len(watchlist)} symbols.\n", 'yellow')
            for index, symbol in enumerate(watchlist):
                self.strategy(symbol)
        else:
            delta = timedelta(hours=1)
            next_hour = (now + delta).replace(microsecond=0, second=0, minute=1)

            wait_seconds = (next_hour - now).seconds
            self.writeSystemMsg(f"\rTime to run strategy: {wait_seconds}", 'white')
            sys.stdout.flush()

    # Main function to activate bot.
    def start_bot(self):
        print("[SYSTEM]: Bot Started.")
        if self.marketIsOpen() is True:
            remaining_time = self.time_to_market_close()
            while remaining_time > 120:
                # Watch all symbols that are involved:
                try:
                    symbols = si.tickers_sp500(False)
                    positions = self.getAccountPositions()  # Get all current positions
                    watchlist = list(set(symbols + positions))
                    watchlist = sorted(watchlist)

                    # Get bars every 1 hour.
                    self.exec(watchlist)
                except:
                    self.writeSystemMsg("Yahoo Finance Connection Error...", 'red')
                    continue

            if 0 < remaining_time < 120:
                print("[SYSTEM]: Market is closing in 2 minutes.")
            elif remaining_time == 0:
                print("[SYSTEM]: Market has closed. Bot will now sleep. Goodnight!")
        self.wait_for_market_open()


if __name__ == '__main__':
    bot = Bot()
    bot.start_bot()
