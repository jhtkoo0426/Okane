import requests
import json
from config import *

# This class communicates between the Alpaca Market API and Okane.
class Bot:
    def __init__(self):
        # URLs
        self.ORDERS_BASE_URL = "https://paper-api.alpaca.markets"
        self.ORDERS_URL = f"{self.ORDERS_BASE_URL}/v2/orders"
        self.DATA_BASE_URL = "https://data.alpaca.markets"
        self.ACCOUNT_URL = f"{self.ORDERS_BASE_URL}/v2/account"

        # Headers to authorize access.
        self.HEADERS = {'APCA-API-KEY-ID': API_KEY, 'APCA-API-SECRET-KEY': SECRET_KEY}

    ### "Making Order" Methods ###
    # Make request to retrieve account.
    def get_account(self):
        r = requests.get(self.ACCOUNT_URL, headers=self.HEADERS)
        return json.loads(r.content)

    # Make Order
    def create_order(self, symbol, qty, side, type, time_in_force):
        # Send JSON object
        data = {
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "type": type,
            "time_in_force": time_in_force
        }

        r = requests.post(self.ORDERS_URL, json=data, headers=self.HEADERS)
        return json.loads(r.content)

        ### "Analysis" Methods ###

    # Get all symbols on the market.
    def getAllSymbols(self):
        self.ASSETS_URL = f"{self.DATA_BASE_URL}/v2/assets"

    # start, end (str) is required.
    # limit = no. of data points to return, default 1000, range 1 - 10000.
    def getHistoricalQuotes(self, symbol, start, end, limit):
        self.DATA_URL = f"{self.DATA_BASE_URL}/v2/stocks/{symbol}/quotes"

        # Send JSON object
        data = {
            "symbol": symbol,
            "start": start,
            "end": end,
            "limit": limit
        }
        r = requests.get(self.DATA_URL, json=data, headers=self.HEADERS)
        return json.loads(r.content)

    # def analyseSymbol():
    # model = Model()
    # Run model on given symbol

    # Get the top 5 performing symbols and trade them.


# Test Code - Do NOT run this unless you want to execute the order.
bot = Bot()
# response = bot.create_order("AAPL", 100, "buy", "market", "gtc")
# print(response)
response = bot.getHistoricalQuotes("AAPL", "2010-10-12T07:20:50Z", "2021-11-08T16:49:00Z", 1000)
print(response)