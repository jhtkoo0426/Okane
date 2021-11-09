import pandas as pd
import btalib


class Indicators:
    def __init__(self):
        pass

    def getSymbolDf(self, symbol):
        df = pd.read_csv(f"D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt", parse_dates=True,
                         index_col="Date")
        return df

    # 1 | Simple moving average (SMA)
    # It calculates the average over a period of time.
    # Current timeframe is 1Day (1D)
    def calc_sma(self, symbol):
        symbol_df = self.getSymbolDf(symbol)
        sma = btalib.sma(symbol_df, period=5)  # Returns sma object, 5-day moving av.

        # Append sma to df.
        symbol_df['sma'] = sma.df.fillna(0)  # Fillna(0) replaces NaN values with 0.

        # Update file
        symbol_df.to_csv(fr'D:/Coding/Projects/Okane/Analysis/SymbolsBarsData/{symbol}.txt', header=True, index=True,
                         sep=",")
        return symbol_df

    # 2 | Relative Strength Index (RSI)
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
    # 3 | MOVING-AVERAGE CONVERGENCE/DIVERGENCE (MACD)
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
