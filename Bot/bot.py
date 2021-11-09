import json
import requests

from config import *
import alpaca_trade_api as tradeapi
import logging
from datetime import datetime
import websocket
import pandas as pd
import btalib

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
    # 100 symbols limit per request!
    # This function gets bars and exports the data to a new .txt file (for every symbol queried).
    # This function is used to generate the bar charts for bta-lib.
    def getBars(self, timeframe, symbol):
        if len(symbol) == 1:
            symbols = symbol[0]
        else:
            symbols = ",".join(symbol)
        r = requests.get(f"{self.BARS_URL}/{timeframe}?symbols={symbols}&limit=1000", headers=self.HEADERS)
        data = r.json()
        for sym in data:
            # Create file to store data.
            filename = f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{sym}.txt"
            f = open(filename, 'w+')
            f.write('Date,Open,High,Low,Close,Volume,OpenInterest\n')

            # Format each line
            for bar in data[sym]:
                t = datetime.fromtimestamp(bar['t'])
                day = t.strftime('%Y-%m-%d')
                line = f"{day},{bar['o']},{bar['h']},{bar['l']},{bar['c']},{bar['v']},0.00\n"
                f.write(line)

    # Indicators
    def getSymbolDf(self, symbol):
        df = pd.read_csv(f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt", parse_dates=True,
                         index_col="Date")
        return df

    # Simple moving average (timeframe = 1 day, for now only)
    def calc_sma(self, symbol):
        symbol_df = self.getSymbolDf(symbol)
        sma = btalib.sma(symbol_df, period=5)  # Returns sma object, 5-day moving av.

        # Append sma to df.
        symbol_df['sma'] = sma.df.fillna(0)    # Fillna(0) replaces NaN values with 0.

        # Update file
        symbol_df.to_csv(fr'D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt', header=True, index=True,
                         sep=",")

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

        print(symbol_df)
    # def analyseSymbol():
    # model = Model()
    # Run model on given symbol

    # Get the top 5 performing symbols and trade them.


# Test Code - Do NOT run this unless you want to execute the order.
bot = Bot()
# bot.stream_websocket()
bot.getBars("1D", bot.getAllSymbols()[0:2])
bot.calc_sma("AACG")
bot.calc_rsi("AACG")
bot.calc_macd("AACG")
# bot.getBars("1D", bot.getAllSymbols()[0])
