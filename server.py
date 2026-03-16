import json
import os
import uvicorn
import yfinance as yf
import pandas as pd
import numpy as np
from mcp.server.fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware

mcp = FastMCP(
    "Stockflow",
    stateless_http=True,
    json_response=True,
)

# Disable DNS rebinding protection (required for Railway external access)
mcp.settings.transport_security = None

# ============================================================
# TECHNICAL INDICATOR HELPERS
# ============================================================

def compute_rsi_wilder(closes: pd.Series, period: int = 14) -> pd.Series:
    """
    Compute RSI using Wilder's smoothing method (same as TradingView).
    Uses exponential moving average with alpha = 1/period.
    Requires full price history for proper warm-up.
    """
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all technical indicators on a DataFrame with 'Close' column.
    Uses Wilder smoothing for RSI and standard EMA for MACD.
    Expects the FULL price history for proper warm-up.
    """
    close = df['Close']

    # SMA
    df['sma_20'] = close.rolling(window=20).mean()
    df['sma_50'] = close.rolling(window=50).mean()
    df['sma_200'] = close.rolling(window=200).mean()

    # RSI - Wilder's smoothing method (matches TradingView)
    df['rsi_14'] = compute_rsi_wilder(close, 14)

    # MACD (12, 26, 9) - standard EMA
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_histogram'] = df['macd'] - df['macd_signal']

    # Bollinger Bands (20, 2)
    df['bb_middle'] = df['sma_20']
    bb_std = close.rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)

    return df


# ============================================================
# MCP TOOLS
# ============================================================

@mcp.tool()
def get_stock_data(
    symbol: str,
    include_financials: bool = False,
    include_analysis: bool = False,
    include_calendar: bool = False
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
        ticker = yf.Ticker(symbol)
        info = ticker.info

        result = {
            "symbol": symbol.upper(),
            "name": info.get("longName", ""),
            "price": {
                "current": info.get("currentPrice") or info.get("regularMarketPrice"),
                "open": info.get("open") or info.get("regularMarketOpen"),
                "high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
                "low": info.get("dayLow") or info.get("regularMarketDayLow"),
                "previous_close": info.get("previousClose") or info.get("regularMarketPreviousClose"),
                "change": info.get("regularMarketChange"),
                "change_percent": info.get("regularMarketChangePercent"),
            },
            "volume": {
                "current": info.get("volume") or info.get("regularMarketVolume"),
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
        }

        if include_financials:
            quarterly = ticker.quarterly_income_stmt
            if quarterly is not None and not quarterly.empty:
                result["financials_summary"] = {
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
                }
                result["quarterly_financials"] = {}
                for col in quarterly.columns:
                    col_data = quarterly[col].to_dict()
                    result["quarterly_financials"][str(col)] = {
                        str(k): (float(v) if pd.notna(v) else None)
                        for k, v in col_data.items()
                    }

        if include_analysis:
            result["target"] = {
                "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "target_mean": info.get("targetMeanPrice"),
                "target_median": info.get("targetMedianPrice"),
                "recommendation": info.get("recommendationKey"),
                "number_of_analysts": info.get("numberOfAnalystOpinions"),
            }
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                recent = recs.tail(4)
                result["recent_recommendations"] = recent.to_dict()

        if include_calendar:
            try:
                cal = ticker.calendar
                if cal is not None:
                    if isinstance(cal, dict):
                        result["calendar"] = {
                            k: (v if not isinstance(v, pd.Timestamp) else str(v))
                            for k, v in cal.items()
                        }
                    elif isinstance(cal, pd.DataFrame):
                        result["calendar"] = cal.to_dict()
            except Exception:
                result["calendar"] = None

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_historical_data(
    symbol: str,
    period: str = "1y",
    interval: str = "1d"
) -> str:
    """Get historical price data with OHLC values and volume, plus technical indicators
    (SMA 20/50/200, RSI 14, MACD, Bollinger Bands).

    RSI uses Wilder's smoothing method (matches TradingView) with full history warm-up.

    Args:
        symbol: Stock ticker symbol (e.g. AAPL, CEG, TLN)
        period: Time period - 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
        interval: Data interval - 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    """
    try:
        ticker = yf.Ticker(symbol)

        # For daily/weekly/monthly intervals, always fetch max history
        # for indicator warm-up, then trim to requested period.
        # For intraday intervals, use the requested period directly
        # (Yahoo limits intraday history anyway).
        warmup_intervals = {'1d', '5d', '1wk', '1mo', '3mo'}
        needs_warmup = interval in warmup_intervals and period != 'max'

        if needs_warmup:
            # Fetch full history for indicator warm-up
            df_full = ticker.history(period='max', interval=interval)
            if df_full.empty:
                return json.dumps({"error": f"No data found for {symbol}"})

            # Fetch requested period to get the start date cutoff
            df_requested = ticker.history(period=period, interval=interval)
            if df_requested.empty:
                return json.dumps({"error": f"No data for period {period}"})

            # Compute indicators on full history (proper warm-up)
            df_full = compute_indicators(df_full)

            # Trim to requested period
            start_date = df_requested.index[0]
            df = df_full[df_full.index >= start_date].copy()
        else:
            # Intraday or max period — fetch and compute directly
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                return json.dumps({"error": f"No data found for {symbol}"})
            df = compute_indicators(df)

        # Format output
        records = []
        for idx, row in df.iterrows():
            records.append({
                "date": str(idx),
                "open": float(row["Open"]) if pd.notna(row.get("Open")) else None,
                "high": float(row["High"]) if pd.notna(row.get("High")) else None,
                "low": float(row["Low"]) if pd.notna(row.get("Low")) else None,
                "close": float(row["Close"]) if pd.notna(row.get("Close")) else None,
                "volume": float(row["Volume"]) if pd.notna(row.get("Volume")) else None,
                "sma_20": float(row["sma_20"]) if pd.notna(row.get("sma_20")) else None,
                "sma_50": float(row["sma_50"]) if pd.notna(row.get("sma_50")) else None,
                "sma_200": float(row["sma_200"]) if pd.notna(row.get("sma_200")) else None,
                "rsi_14": float(row["rsi_14"]) if pd.notna(row.get("rsi_14")) else None,
                "macd": float(row["macd"]) if pd.notna(row.get("macd")) else None,
                "macd_signal": float(row["macd_signal"]) if pd.notna(row.get("macd_signal")) else None,
                "macd_histogram": float(row["macd_histogram"]) if pd.notna(row.get("macd_histogram")) else None,
                "bb_upper": float(row["bb_upper"]) if pd.notna(row.get("bb_upper")) else None,
                "bb_middle": float(row["bb_middle"]) if pd.notna(row.get("bb_middle")) else None,
                "bb_lower": float(row["bb_lower"]) if pd.notna(row.get("bb_lower")) else None,
            })

        latest = records[-1] if records else {}

        return json.dumps({
            "symbol": symbol.upper(),
            "period": period,
            "interval": interval,
            "total_records": len(records),
            "indicator_note": "RSI uses Wilder smoothing with full history warm-up (matches TradingView)",
            "latest": latest,
            "data": records,
        }, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_options_chain(
    symbol: str,
    expiration_date: str = "",
    include_greeks: bool = True
) -> str:
    """Get options chain data including calls and puts with strike prices, bid/ask,
    volume, open interest, implied volatility, and optionally Greeks.

    Args:
        symbol: Stock ticker symbol (e.g. AAPL, CEG)
        expiration_date: Options expiration date in YYYY-MM-DD format. Leave empty for nearest expiration.
        include_greeks: Include delta, gamma, theta, vega if available
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")

        expirations = ticker.options
        if not expirations:
            return json.dumps({"error": f"No options data available for {symbol}"})

        if expiration_date and expiration_date in expirations:
            exp = expiration_date
        elif expiration_date:
            exp = min(expirations, key=lambda x: abs(pd.Timestamp(x) - pd.Timestamp(expiration_date)))
        else:
            exp = expirations[0]

        chain = ticker.option_chain(exp)

        def format_options(df, option_type):
            options = []
            for _, row in df.iterrows():
                opt = {
                    "type": option_type,
                    "strike": float(row["strike"]),
                    "last_price": float(row["lastPrice"]) if pd.notna(row.get("lastPrice")) else None,
                    "bid": float(row["bid"]) if pd.notna(row.get("bid")) else None,
                    "ask": float(row["ask"]) if pd.notna(row.get("ask")) else None,
                    "change": float(row["change"]) if pd.notna(row.get("change")) else None,
                    "percent_change": float(row["percentChange"]) if pd.notna(row.get("percentChange")) else None,
                    "volume": float(row["volume"]) if pd.notna(row.get("volume")) else None,
                    "open_interest": float(row["openInterest"]) if pd.notna(row.get("openInterest")) else None,
                    "implied_volatility": float(row["impliedVolatility"]) if pd.notna(row.get("impliedVolatility")) else None,
                    "in_the_money": bool(row["inTheMoney"]) if pd.notna(row.get("inTheMoney")) else None,
                    "contract_symbol": str(row.get("contractSymbol", "")),
                }
                if include_greeks:
                    opt["greeks"] = {
                        "delta": float(row["delta"]) if pd.notna(row.get("delta")) else None,
                        "gamma": float(row["gamma"]) if pd.notna(row.get("gamma")) else None,
                        "theta": float(row["theta"]) if pd.notna(row.get("theta")) else None,
                        "vega": float(row["vega"]) if pd.notna(row.get("vega")) else None,
                        "rho": float(row["rho"]) if pd.notna(row.get("rho")) else None,
                    }
                options.append(opt)
            return options

        calls = format_options(chain.calls, "call")
        puts = format_options(chain.puts, "put")

        return json.dumps({
            "symbol": symbol.upper(),
            "current_price": current_price,
            "expiration_date": exp,
            "available_expirations": list(expirations),
            "calls_count": len(calls),
            "puts_count": len(puts),
            "calls": calls,
            "puts": puts,
        }, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)})


# ============================================================
# APP SETUP
# ============================================================

# streamable_http_app() returns a complete Starlette app with /mcp route
# and lifespan handler. Do NOT wrap in another Starlette or Mount.
# Settings above enable:
#   stateless_http=True  -> no session required (Claude.ai compatible)
#   json_response=True   -> returns JSON not SSE streams
#   transport_security=None -> allows external hosts (Railway)

app = mcp.streamable_http_app()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
