# Okane
Version 1 of my personal trading bot. Created with Python using the Alpaca Market API, Polygon.io and bta-lib.

# Bot Functions (bot.py)
## Basic
These are the fundamental operations of the bot.

### stream_websocket
- Initiates websocket connection to the Alpaca Market data API.
- Carries out different operations depending on `on_open`, `on_message` and `on_close`.

### simple_order
- Makes an order to Alpaca (without `stop_loss` & `take_profit`).

### advanced_order
- Makes an order to Alpaca (with `stop_loss` & `take_profit`).

### getAllSymbols
- Returns all symbols on the [NASDAQ](https://www.nasdaq.com) from all active assets at Alpaca.

### getBars
- Returns a text file consisting of market data for each symbol listed in its `symbol` parameter.

### getSymbolDf
- Returns the dataframe for a symbol.

## Indicators
All indicators in this bot are calculated using the `bta-lib` library.

### calc_sma
- Calculates the Simple Moving Average for a symbol and updates its dataframe.

### calc_rsi
- Calculates the Relative Strength Index for a symbol and updates its dataframe.


## Notes
- Re-generate API key and secret key every 2 days. This is due to the free account subscription.
### calc_macd
- Calculates the Moving Average Convergence Divergence for a symbol and updates its dataframe.
