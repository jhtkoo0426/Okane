import btalib
import json
import logging
import math
import os
import time
from datetime import datetime

import alpaca_trade_api as tradeapi
import pandas as pd
import requests
import websocket

from Analysis.indicators import Indicators
from config import *

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
        self.BASE_URL = "https://paper-api.alpaca.markets"          # For authentication when connecting to the API.
        self.HEADERS = {
            'APCA-API-KEY-ID': API_KEY,
            'APCA-API-SECRET-KEY': SECRET_KEY
        }

        self.DATA_BASE_URL = "https://data.alpaca.markets"          # For accessing historical data.
        self.STREAM_URL = "wss://data.alpaca.markets/stream"        # For accessing live data.
        self.ORDER_URL = f"{self.BASE_URL}/v2/orders"               # For executing orders.

        # Instantiate REST API
        self.api = tradeapi.REST(API_KEY, SECRET_KEY, self.BASE_URL, api_version='v2')

        # Implementing Strategies
        self.indicatorAPI = Indicators()
        self.positionSizing = 0.25

        # Websocket
        self.ws = websocket.WebSocketApp(self.STREAM_URL, on_open=self.on_open, on_message=self.on_message)
        self.ws.run_forever()

    # 1 | Websocket functions
    # THIS FUNCTION WILL KEEP THE BOT RUNNING. RUN ANY FUNCTIONS THAT REQUIRE
    # LIVE DATA STREAM HERE.
    def on_open(self, ws):
        print("Websocket opened.")

        # Authenticate
        auth_data = {
            "action": "authenticate",
            "data": {"key_id": API_KEY, "secret_key": SECRET_KEY}
        }
        self.ws.send(json.dumps(auth_data))

        # symbols = self.getAllSymbols()
        # symbols = [f"Q.{a}" for a in symbols]
        # print(symbols[0:10])
        symbols = ['Q.TSLA', 'Q.AAPL', 'Q.MSFT', 'Q.NFLX', 'Q.AMZN']
        listen_message = {"action": "listen", "data": {"streams": symbols}}
        ws.send(json.dumps(listen_message))

    def on_close(self, ws):
        self.ws.close()

    def on_message(self, ws, message):
        print(f"Received a message: {message}")

        # Get message data
        test = json.loads(message)
        symbol, data = test['stream'][2:], test['data']
        bid, ask = data['p'], data['P']
        print(symbol, bid, ask)

        # Implement strategy
        self.strategy(symbol, bid)

    # 2 | Core bot functions
    # Check remaining time till market closes.
    def time_to_market_close(self):
        clock = self.api.get_clock()
        return (clock.next_close - clock.timestamp).total_seconds()

    # Put the bot to sleep until the market re-opens.
    def wait_for_market_open(self):
        clock = self.api.get_clock()
        if not clock.is_open():
            time_to_open = (clock.next_open - clock.timestamp).total_seconds()
            time.sleep(round(time_to_open))

    # 3 | Get account details
    # Get positions of a symbol on the account.
    def get_positions(self, symbol):
        # Gets all positions on the account.
        r = requests.get(f"{self.BASE_URL}/v2/positions", headers=self.HEADERS)
        data = r.json()

        # Get target symbol position
        for position in data:
            if position.get('symbol') == symbol:
                return position.get('qty')
        return 0

    # Get account cash balance
    def get_cash_balance(self):
        return self.api.get_account().cash

    # 4 | Get most recent data
    # Get most recent quote of a symbol
    def getSymbolLastQuote(self, symbol):
        return self.api.get_last_quote(symbol).raw

    def getSymbolLastBid(self, symbol):
        quote = self.getSymbolLastQuote(symbol)
        return quote['bidprice']

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


    # "Analysis" Methods #
    # Get all symbols on the NASDAQ.
    def getAllSymbols(self):
        active_assets = self.api.list_assets(status='active')
        nasdaq_symbols = [a.symbol for a in active_assets if a.exchange == 'NASDAQ']
        return nasdaq_symbols

    def getSymbolDf(self, symbol):
        # Check if file for symbol exists. If not, create file.
        filepath = f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}"
        if os.path.isfile(filepath) is False:
            self.getBar(symbol)
        df = pd.read_csv(f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt", parse_dates=True,
                         index_col="Date")
        return df

    # symbol = list of symbols
    # 100 symbols limit per request!
    # This function gets bars and exports the data to a new .txt file (for every symbol queried).
    # This function is used to generate the bar charts for bta-lib.
    def getBar(self, symbol):
        r = requests.get(f"{self.DATA_BASE_URL}/v1/bars/1D?symbols={symbol}&limit=1000", headers=self.HEADERS)
        data = r.json()

        # Check if data file for the symbol exists, if not create file.
        filename = f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt"
        f = open(filename, 'w+')
        f.write('Date,Open,High,Low,Close,Volume,OpenInterest\n')

        # Get bars of symbol
        bars = data[symbol]
        # Format each line

        for bar in bars:
            t = datetime.fromtimestamp(bar['t'])
            day = t.strftime('%Y-%m-%d')
            line = f"{day},{bar['o']},{bar['h']},{bar['l']},{bar['c']},{bar['v']},0.00\n"
            f.write(line)

    # 5 | Analysis Indicators
    # A | Simple moving average (SMA)
    # It calculates the average over a period of time.
    # Current timeframe is 1Day (1D)
    def calc_sma(self, symbol, period):
        symbol_df = self.getSymbolDf(symbol)
        sma = btalib.sma(symbol_df, period=period)  # Returns sma object, 5-day moving av.

        symbol_df['sma'] = sma.df.fillna(0)  # Fillna(0) replaces NaN values with 0.

        # Update file
        symbol_df.to_csv(fr'D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt', header=True, index=True,
                         sep=",")
        return symbol_df

    # B | Relative Strength Index (RSI)
    # It measures momentum by calculating the ration of higher closes and
    # lower closes after having been smoothed by an average, normalizing
    # the result between 0 and 100
    def calc_rsi(self, symbol):
        symbol_df = self.getSymbolDf(symbol)
        rsi = btalib.rsi(symbol_df)

        # Append rsi to df.
        symbol_df['rsi'] = rsi.df.fillna(0)

        # Update file
        symbol_df.to_csv(fr'D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt', header=True, index=True,
                         sep=",")

        oversold_days = symbol_df[symbol_df['rsi'] < 30]
        # print(oversold_days)

        return symbol_df

    # C | MOVING-AVERAGE CONVERGENCE/DIVERGENCE (MACD)
    # It measures the distance of a fast and a slow moving average to try to
    # identify the trend.
    def calc_macd(self, symbol):
        symbol_df = self.getSymbolDf(symbol)
        macd = btalib.macd(symbol_df)

        # 3 columns are generated in macd.df, so we need to separately append all
        # of these columns to symbol_df.

        # Append macd to df.
        symbol_df['macd'] = macd.df['macd'].fillna(0)
        symbol_df['signal'] = macd.df['signal'].fillna(0)
        symbol_df['histogram'] = macd.df['histogram'].fillna(0)

        # Update file
        symbol_df.to_csv(fr'D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt', header=True, index=True,
                         sep=",")

        return symbol_df

    # 6 | Executing Strategy
    def strategy(self, symbol, bid):
        print("Strategy Implemented")
        # https://alpaca.markets/learn/stock-trading-bot-instruction/
        # Get the most current moving average and make comparison.
        SMA20 = self.calc_sma(symbol, 20)['sma'][-1]  # Gets today's/yesterday's SMA20 from dataframe
        SMA50 = self.calc_sma(symbol, 50)['sma'][-1]  # Gets today's/yesterday's SMA50 from dataframe

        if SMA20 > SMA50:
            # Buy
            open_pos = self.get_positions(symbol)

            if open_pos == 0:
                cash = float(self.get_cash_balance())

                # target_position_size = cash_balance / (current_price / self.positionSizing)
                target_position_size = math.floor(cash*0.1/bid)

                # Authorize order
                data = {
                    "symbol": symbol,
                    "qty": target_position_size,
                    "side": "buy",
                    "type": "market",
                    "time_in_order": "gtc"
                }
                r = requests.post(self.ORDER_URL, json=data, headers=self.HEADERS)
                json.loads(r.content)
                self.simple_order(symbol, target_position_size, "buy", "market", "gtc")
                print(f"Placed order:\nSymbol: {symbol} | Action: Buy | Target Position Size: {target_position_size}")
        else:
            # Sell
            open_pos = self.get_positions(symbol)
            self.simple_order(symbol, open_pos, "sell", "market", "gtc")
            print(f"Placed Order:\nSymbol: {symbol} | Action: Sell | Sold All")

    def moving_av(self, symbol):
        # https://alpaca.markets/learn/stock-trading-bot-instruction/
        # Get the most current moving average and make comparison.
        SMA20 = self.calc_sma(symbol, 20)['sma'][-1]    # Gets today's/yesterday's SMA20 from dataframe
        SMA50 = self.calc_sma(symbol, 50)['sma'][-1]    # Gets today's/yesterday's SMA50 from dataframe

        print(f"Calculated SMA:\nSMA20: {SMA20} | SMA50: {SMA50}")
        # Get owned position for symbol
        # quantity_owned = self.get_positions(symbol)

        # Execute Strategy
        if SMA20 > SMA50:
            # Buy
            open_pos = self.get_positions(symbol)

            if open_pos == 0:
                cash_balance = float(self.get_cash_balance())

                # Get last quote of stock (bid price)
                current_price = float(self.getSymbolLastQuote(symbol)['bidprice'])

                # target_position_size = cash_balance / (current_price / self.positionSizing)
                target_position_size = math.floor(cash_balance*0.1/current_price)
                # Authorize order
                data = {
                    "symbol": symbol,
                    "qty": target_position_size,
                    "side": "buy",
                    "type": "market",
                    "time_in_order": "gtc"
                }
                r = requests.post(self.ORDER_URL, json=data, headers=self.HEADERS)
                json.loads(r.content)
                self.simple_order(symbol, target_position_size, "buy", "market", "gtc")
                print(f"Placed order:\nSymbol: {symbol} | Action: Buy | Target Position Size: {target_position_size}")
        else:
            # Sell
            open_pos = self.get_positions(symbol)
            self.simple_order(symbol, open_pos, "sell", "market", "gtc")
            print(f"Placed Order:\nSymbol: {symbol} | Action: Sell | Sold All")


# Test Code - Do NOT run this unless you want to execute the order.
bot = Bot()
