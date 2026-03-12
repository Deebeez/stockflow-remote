"""
StockFlow Remote MCP Server
----------------------------
A remote MCP server that provides real-time stock data via Yahoo Finance.
Designed to connect to claude.ai web via Custom Connectors.

Based on twolven/mcp-stockflow (MIT License).
Converted from stdio to Streamable HTTP transport for cloud deployment.
"""

import os
import json
import datetime
import traceback

import yfinance as yf
import pandas as pd
import numpy as np
from mcp.server.fastmcp import FastMCP

# --- JSON Encoder for financial data types ---
class StockflowJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (pd.Timestamp, datetime.date, datetime.datetime)):
            return obj.isoformat()
        if isinstance(obj, pd.Period):
            return str(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if pd.isna(obj):
            return None
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


def safe_json(data: dict) -> str:
    return json.dumps(data, cls=StockflowJSONEncoder, indent=2)


def clean_value(val):
    if val is None:
        return None
    if isinstance(val, (pd.Timestamp, datetime.date, datetime.datetime)):
        return val.isoformat()
    if isinstance(val, pd.Period):
        return str(val)
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return None if np.isnan(val) else float(val)
    if isinstance(val, float):
        return None if (val != val) else val
    return val


def clean_dict(d: dict) -> dict:
    cleaned = {}
    for k, v in d.items():
        key = k.isoformat() if isinstance(k, (pd.Timestamp, datetime.date)) else str(k)
        if isinstance(v, dict):
            cleaned[key] = clean_dict(v)
        elif isinstance(v, list):
            cleaned[key] = [clean_value(item) for item in v]
        else:
            cleaned[key] = clean_value(v)
    return cleaned


# --- Create MCP Server ---
mcp = FastMCP(
    "StockFlow",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def get_stock_data(
    symbol: str,
    include_financials: bool = False,
    include_analysis: bool = False,
    include_calendar: bool = False,
) -> str:
    """Get comprehensive stock data including price, volume, market cap, P/E ratio,
    52-week high/low, and optionally financials, analyst ratings, and calendar events.

    Args:
        symbol: Stock ticker symbol (e.g. AAPL, MSFT, CEG)
        include_financials: Include quarterly financial statements
        include_analysis: Include analyst recommendations and price targets
        include_calendar: Include upcoming earnings and dividend dates
    """
    try:
        ticker = yf.Ticker(symbol.upper())
        info = ticker.info

        result = {
            "symbol": symbol.upper(),
            "name": info.get("longName") or info.get("shortName", "N/A"),
            "price": {
                "current": info.get("currentPrice") or info.get("regularMarketPrice"),
                "open": info.get("regularMarketOpen"),
                "high": info.get("regularMarketDayHigh"),
                "low": info.get("regularMarketDayLow"),
                "previous_close": info.get("regularMarketPreviousClose"),
                "change": info.get("regularMarketChange"),
                "change_percent": info.get("regularMarketChangePercent"),
            },
            "volume": {
                "current": info.get("regularMarketVolume"),
                "average": info.get("averageVolume"),
                "average_10d": info.get("averageDailyVolume10Day"),
            },
            "market_data": {
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "shares_outstanding": info.get("sharesOutstanding"),
                "float_shares": info.get("floatShares"),
                "short_ratio": info.get("shortRatio"),
                "short_percent_of_float": info.get("shortPercentOfFloat"),
            },
            "valuation": {
                "pe_trailing": info.get("trailingPE"),
                "pe_forward": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "price_to_book": info.get("priceToBook"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "ev_to_revenue": info.get("enterpriseToRevenue"),
                "ev_to_ebitda": info.get("enterpriseToEbitda"),
            },
            "range": {
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "fifty_day_average": info.get("fiftyDayAverage"),
                "two_hundred_day_average": info.get("twoHundredDayAverage"),
            },
            "dividends": {
                "dividend_rate": info.get("dividendRate"),
                "dividend_yield": info.get("dividendYield"),
                "ex_dividend_date": info.get("exDividendDate"),
                "payout_ratio": info.get("payoutRatio"),
            },
            "financials_summary": {
                "revenue": info.get("totalRevenue"),
                "revenue_per_share": info.get("revenuePerShare"),
                "profit_margins": info.get("profitMargins"),
                "operating_margins": info.get("operatingMargins"),
                "return_on_equity": info.get("returnOnEquity"),
                "return_on_assets": info.get("returnOnAssets"),
                "earnings_per_share": info.get("trailingEps"),
                "forward_eps": info.get("forwardEps"),
                "total_cash": info.get("totalCash"),
                "total_debt": info.get("totalDebt"),
                "debt_to_equity": info.get("debtToEquity"),
                "free_cash_flow": info.get("freeCashflow"),
                "operating_cash_flow": info.get("operatingCashflow"),
            },
            "target": {
                "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "target_mean": info.get("targetMeanPrice"),
                "target_median": info.get("targetMedianPrice"),
                "recommendation": info.get("recommendationKey"),
                "number_of_analysts": info.get("numberOfAnalystOpinions"),
            },
        }

        if include_financials:
            try:
                quarterly = ticker.quarterly_financials
                if quarterly is not None and not quarterly.empty:
                    result["quarterly_financials"] = clean_dict(quarterly.to_dict())
            except Exception:
                result["quarterly_financials"] = "unavailable"

        if include_analysis:
            try:
                recs = ticker.recommendations
                if recs is not None and not recs.empty:
                    recent = recs.tail(10)
                    result["recent_recommendations"] = clean_dict(recent.to_dict())
            except Exception:
                result["recent_recommendations"] = "unavailable"

        if include_calendar:
            try:
                cal = ticker.calendar
                if cal is not None:
                    if isinstance(cal, pd.DataFrame):
                        result["calendar"] = clean_dict(cal.to_dict())
                    elif isinstance(cal, dict):
                        result["calendar"] = clean_dict(cal)
            except Exception:
                result["calendar"] = "unavailable"

        return safe_json(clean_dict(result))

    except Exception as e:
        return safe_json({"error": str(e), "traceback": traceback.format_exc()})


@mcp.tool()
def get_historical_data(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> str:
    """Get historical price data with OHLC values and volume, plus technical indicators
    (SMA 20/50/200, RSI 14, MACD, Bollinger Bands).

    Args:
        symbol: Stock ticker symbol (e.g. AAPL, CEG, TLN)
        period: Time period - 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
        interval: Data interval - 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    """
    try:
        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            return safe_json({"error": f"No historical data found for {symbol}"})

        close = hist["Close"]

        hist["SMA_20"] = close.rolling(window=20).mean()
        hist["SMA_50"] = close.rolling(window=50).mean()
        hist["SMA_200"] = close.rolling(window=200).mean()

        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
        rs = gain / loss
        hist["RSI_14"] = 100 - (100 / (1 + rs))

        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        hist["MACD"] = ema_12 - ema_26
        hist["MACD_Signal"] = hist["MACD"].ewm(span=9, adjust=False).mean()
        hist["MACD_Histogram"] = hist["MACD"] - hist["MACD_Signal"]

        hist["BB_Middle"] = hist["SMA_20"]
        bb_std = close.rolling(window=20).std()
        hist["BB_Upper"] = hist["BB_Middle"] + (bb_std * 2)
        hist["BB_Lower"] = hist["BB_Middle"] - (bb_std * 2)

        records = []
        for idx, row in hist.iterrows():
            record = {
                "date": idx.isoformat() if isinstance(idx, pd.Timestamp) else str(idx),
                "open": clean_value(row.get("Open")),
                "high": clean_value(row.get("High")),
                "low": clean_value(row.get("Low")),
                "close": clean_value(row.get("Close")),
                "volume": clean_value(row.get("Volume")),
                "sma_20": clean_value(row.get("SMA_20")),
                "sma_50": clean_value(row.get("SMA_50")),
                "sma_200": clean_value(row.get("SMA_200")),
                "rsi_14": clean_value(row.get("RSI_14")),
                "macd": clean_value(row.get("MACD")),
                "macd_signal": clean_value(row.get("MACD_Signal")),
                "macd_histogram": clean_value(row.get("MACD_Histogram")),
                "bb_upper": clean_value(row.get("BB_Upper")),
                "bb_middle": clean_value(row.get("BB_Middle")),
                "bb_lower": clean_value(row.get("BB_Lower")),
            }
            records.append(record)

        latest = records[-1] if records else {}

        result = {
            "symbol": symbol.upper(),
            "period": period,
            "interval": interval,
            "total_records": len(records),
            "latest": latest,
            "data": records,
        }

        return safe_json(result)

    except Exception as e:
        return safe_json({"error": str(e), "traceback": traceback.format_exc()})


@mcp.tool()
def get_options_chain(
    symbol: str,
    expiration_date: str = "",
    include_greeks: bool = True,
) -> str:
    """Get options chain data including calls and puts with strike prices, bid/ask,
    volume, open interest, implied volatility, and optionally Greeks.

    Args:
        symbol: Stock ticker symbol (e.g. AAPL, CEG)
        expiration_date: Options expiration date in YYYY-MM-DD format. Leave empty for nearest expiration.
        include_greeks: Include delta, gamma, theta, vega if available
    """
    try:
        ticker = yf.Ticker(symbol.upper())

        expirations = ticker.options
        if not expirations:
            return safe_json({"error": f"No options data available for {symbol}"})

        if expiration_date and expiration_date in expirations:
            exp = expiration_date
        else:
            exp = expirations[0]

        chain = ticker.option_chain(exp)

        def process_options(df, option_type):
            options = []
            for _, row in df.iterrows():
                opt = {
                    "type": option_type,
                    "strike": clean_value(row.get("strike")),
                    "last_price": clean_value(row.get("lastPrice")),
                    "bid": clean_value(row.get("bid")),
                    "ask": clean_value(row.get("ask")),
                    "change": clean_value(row.get("change")),
                    "percent_change": clean_value(row.get("percentChange")),
                    "volume": clean_value(row.get("volume")),
                    "open_interest": clean_value(row.get("openInterest")),
                    "implied_volatility": clean_value(row.get("impliedVolatility")),
                    "in_the_money": bool(row.get("inTheMoney", False)),
                    "contract_symbol": str(row.get("contractSymbol", "")),
                }
                if include_greeks:
                    opt["greeks"] = {
                        "delta": clean_value(row.get("delta")),
                        "gamma": clean_value(row.get("gamma")),
                        "theta": clean_value(row.get("theta")),
                        "vega": clean_value(row.get("vega")),
                        "rho": clean_value(row.get("rho")),
                    }
                options.append(opt)
            return options

        calls = process_options(chain.calls, "call")
        puts = process_options(chain.puts, "put")

        info = ticker.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")

        result = {
            "symbol": symbol.upper(),
            "current_price": current_price,
            "expiration_date": exp,
            "available_expirations": list(expirations),
            "calls_count": len(calls),
            "puts_count": len(puts),
            "calls": calls,
            "puts": puts,
        }

        return safe_json(clean_dict(result))

    except Exception as e:
        return safe_json({"error": str(e), "traceback": traceback.format_exc()})


# --- Run the server with CORS support for claude.ai ---
if __name__ == "__main__":
    import uvicorn
    from starlette.middleware.cors import CORSMiddleware
    from starlette.applications import Starlette

    port = int(os.environ.get("PORT", 8000))

    # Get the MCP ASGI app
    mcp_app = mcp.streamable_http_app()

    # Wrap with CORS middleware so claude.ai can connect
    mcp_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    uvicorn.run(mcp_app, host="0.0.0.0", port=port)
