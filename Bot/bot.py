import math
import sys
from math import floor
import time
from datetime import datetime, timedelta

import alpaca_trade_api as tradeapi
import btalib
import pandas as pd
from alpaca_trade_api import TimeFrameUnit
from alpaca_trade_api.stream import URL
from alpaca_trade_api.rest import APIError, TimeFrame
import yahoo_fin.stock_info as si

from Bot.config import API_KEY, SECRET_KEY

from termcolor import colored


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
        twoWeekTime = nowTime - timedelta(days=14)
        todayDate = nowTime.strftime("%Y-%m-%d")
        oneWeekDate = twoWeekTime.strftime("%Y-%m-%d")

        start = pd.Timestamp(oneWeekDate, tz=self.NY).isoformat()
        end = pd.Timestamp(todayDate, tz=self.NY).isoformat()
        bars = self.api.get_bars([symbol], TimeFrame(hourFrame, TimeFrameUnit.Hour), adjustment='raw', start=start, end=end).df
        return bars

    def getDailyBars(self, symbol):
        nowTime = datetime.now()
        twoWeekTime = nowTime - timedelta(days=14)
        todayDate = nowTime.strftime("%Y-%m-%d")
        oneWeekDate = twoWeekTime.strftime("%Y-%m-%d")
        start = pd.Timestamp(oneWeekDate, tz=self.NY).isoformat()
        end = pd.Timestamp(todayDate, tz=self.NY).isoformat()
        bars = self.api.get_bars([symbol], TimeFrame(1, TimeFrameUnit.Day), adjustment='raw', start=start,
                                 end=end).df
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

        # Add bar type and trend data to symbol dataframe.
        HADataframe = self.analyseHABars(dataframe)
        return HADataframe

    def analyseHABars(self, dataframe):
        df = dataframe.copy()
        prev_high, prev_low = -1, -1        # Tracker for determining trends
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

    # Function to determine the trend for the higher timeframe
    def HADetermineSymbolTrend(self, dataframe):
        prev_low, prev_high = dataframe.iloc[-2]['low'], dataframe.iloc[-2]['high']
        low, high = dataframe.iloc[-1]['low'], dataframe.iloc[-1]['high']
        # print("low: ", low, "prev low: ", prev_low, "high: ", high, "prev high: ", prev_high)
        if (low > prev_low and high > prev_high) or (low > prev_low and high < prev_high):
            return "UPTREND"
        elif (low < prev_low and high < prev_high) or (low < prev_low and high > prev_high):
            return "DOWNTREND"
        else:
            # TODO: Research on what to do if (low > pl and high < ph) and (low < pl and high > ph).
            return "UNDETERMINED"

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
        stopLoss = dict(stop_price=stopLossPrice, limit_price=stopLossPrice)
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
            ema10 = btalib.ema(dataframe, 10).df['ema']
            combinedDF = pd.concat([dataframe, ema10], axis=1)
            combinedDF.rename(columns={'ema': f'ema10'}, inplace=True)  # Rename column

            ema30 = btalib.ema(dataframe, 30).df['ema']
            combinedDF2 = pd.concat([combinedDF, ema30], axis=1)
            combinedDF2.rename(columns={'ema': f'ema30'}, inplace=True)  # Rename column
            return combinedDF2

    # This function determines if a symbol satisfies all the criteria.
    def strategy_decide_buy(self, symbol):
        one_hour_bars = self.getHourBars(symbol, 1)  # Get 1hr raw dataframe
        four_hour_bars = self.getHourBars(symbol, 4)  # Get 4hr raw dataframe
        daily_bars = self.getDailyBars(symbol)  # Get daily raw dataframe
        one_hour_ha_bars = self.calc_ha(one_hour_bars)  # Generate HA dataframe (1 hr)
        four_hour_ha_bars = self.calc_ha(four_hour_bars)

        # Apply EMA Indicators
        one_hr_DF = self.calc_ema(one_hour_ha_bars)
        four_hr_DF = self.calc_ema(four_hour_ha_bars)

        satisfied_criteria_count = 0
        if one_hr_DF is None or four_hr_DF is None or one_hour_bars is None or four_hour_bars is None:
            sys.stdout.write(colored(f"[HA STRATEGY]: Insufficient data to analyse {symbol}.\n", 'red'))
            return 0, "NaN", 0
        else:
            one_hr_ema10, one_hr_ema30, one_hr_lastBar = one_hr_DF.iloc[-1]['ema10'], one_hr_DF.iloc[-1]['ema30'], one_hr_DF.iloc[-1]['barType']
            four_hr_ema10, four_hr_ema30, four_hr_lastBar = four_hr_DF.iloc[-1]['ema10'], four_hr_DF.iloc[-1]['ema30'], four_hr_DF.iloc[-1]['barType']
            four_hr_trend = self.HADetermineSymbolTrend(four_hour_bars)
            daily_trend = self.HADetermineSymbolTrend(daily_bars)

            # Criteria 1: The higher timeframe must be in an uptrend.
            # if four_hr_trend == "UPTREND" and daily_trend == "UPTREND":
            if four_hr_trend == "UPTREND":
                satisfied_criteria_count += 1

            # Criteria 2: EMA10 > EMA30 for the lower timeframe.
            #if one_hr_ema10 > one_hr_ema30 and four_hr_ema10 > four_hr_ema30:
            if four_hr_ema10 > four_hr_ema30:
                satisfied_criteria_count += 1

            barTypeColumn = four_hr_DF['barType'].tolist()
            if barTypeColumn.count("BULL") > barTypeColumn.count("BEAR"):
                satisfied_criteria_count += 1
            print(four_hr_DF['barType'].tolist())

            stopLoss = self.HADetermineStopLoss(one_hr_DF)
            return satisfied_criteria_count, one_hr_lastBar, stopLoss

    # Strategy
    # The bot trades on the 1 hr timeframe, so it determines the entry point using the 1 hr dataframe.
    def exec(self, symbol):
        satisfied_criteria_count, one_hr_lastBar, stopLossPrice = self.strategy_decide_buy(symbol)
        print(satisfied_criteria_count, one_hr_lastBar)

        # Determine entry point/leaving point
        if satisfied_criteria_count == 2:   # All criteria satisfied.
            sys.stdout.write(colored(f"[HA STRATEGY]: All pre-conditions satisified for {symbol}.\n", 'blue'))

            if one_hr_lastBar == "BULL":
                if self.getPosition(symbol) is not None:
                    sys.stdout.write(colored(f"[HA STRATEGY]: Continuing holding {symbol}.\n", 'green'))
                else:
                    sys.stdout.write(colored(f"[HA STRATEGY]: Conditions satisfied to buy {symbol}.\n", 'blue'))

                    # Buy non-fractional shares with 5% of equity.
                    symbolCurrentPrice = si.get_live_price(symbol)
                    if self.getPosition(symbol) is None:
                        qty = self.determineBuyShares(symbolCurrentPrice)
                        self.HABuyOrder(symbol, stopLossPrice, qty)
                        sys.stdout.write(colored(f"[HA STRATEGY]: Bought {qty} shares of {symbol}.\n", 'yellow'))

            elif one_hr_lastBar == "BEAR":
                if self.getPosition(symbol) is not None:
                    sys.stdout.write(colored(f"[HA STRATEGY]: STOP LOSS: Selling all shares of {symbol}.\n", 'red'))
                    qty = self.getQty(symbol)
                    self.sellOrder(symbol, qty)
                else:
                    sys.stdout.write(colored(f"[HA STRATEGY]: No positions - Do nothing for {symbol}.\n", 'grey'))
            else:
                sys.stdout.write(colored(f"[HA STRATEGY]: Indecisive bar - Do nothing for {symbol}.\n", 'grey'))
        else:
            sys.stdout.write(colored(f"Some criteria is not satisfied for {symbol}.\n", "grey"))

    # Main function to activate bot.
    def start_bot(self):
        print("[SYSTEM]: Bot Started.")
        if self.marketIsOpen() is True:
            remaining_time = self.time_to_market_close()
            while remaining_time > 120:
                # Watch all symbols that are involved:
                symbols = si.get_day_most_active(25)['Symbol'].to_list()
                positions = self.getAccountPositions()  # Get all current positions
                watchlist = list(set(symbols + positions))

                # Get bars every 1 hour.
                if floor(remaining_time) % 60 == 0:
                    sys.stdout.write("\033[H\033[J")
                    sys.stdout.write(colored(f"[SYSTEM]: Current watchlist has {len(watchlist)} symbols.\n", 'yellow'))
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
