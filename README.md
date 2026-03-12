# StockFlow Remote — Live Stock Data for Claude.ai Web

A remote MCP server that gives Claude.ai web access to **real-time stock data** via Yahoo Finance.

**What you get:** Live prices, technicals (SMA, RSI, MACD, Bollinger Bands), financials, analyst targets, and full options chains — all accessible from any Claude.ai conversation in your browser.

Based on [twolven/mcp-stockflow](https://github.com/twolven/mcp-stockflow) (MIT License), converted from local stdio to remote Streamable HTTP transport.

---

## Tools Available

| Tool | What it does |
|------|-------------|
| `get_stock_data` | Current price, volume, market cap, P/E, 52-week range, dividends, analyst targets. Optionally: quarterly financials, analyst recommendations, calendar events. |
| `get_historical_data` | Historical OHLC + volume with calculated technicals: SMA 20/50/200, RSI 14, MACD, Bollinger Bands. Configurable period and interval. |
| `get_options_chain` | Full options chain with calls/puts, strike prices, bid/ask, volume, open interest, implied volatility, and Greeks (delta, gamma, theta, vega). |

---

## Deployment Guide (Beginner-Friendly)

### Step 1: Create a GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Name it `stockflow-remote`
3. Set it to **Public**
4. Check **"Add a README file"**
5. Click **Create repository**

### Step 2: Upload These Files

1. In your new repo, click **"Add file"** → **"Upload files"**
2. Drag and drop ALL of these files into the upload area:
   - `server.py`
   - `requirements.txt`
   - `Procfile`
   - `runtime.txt`
   - `.gitignore`
3. Click **"Commit changes"**

### Step 3: Deploy to Railway

1. Go to [railway.com](https://railway.com) and sign up with your GitHub account
2. Click **"New Project"**
3. Select **"Deploy from GitHub Repo"**
4. Choose your `stockflow-remote` repository
5. Railway will auto-detect Python and start building
6. Once deployed, click on your service → **Settings** → scroll to **"Networking"**
7. Click **"Generate Domain"** — you'll get a URL like `stockflow-remote-production-xxxx.up.railway.app`
8. **Copy this URL** — you'll need it for the next step

### Step 4: Connect to Claude.ai Web

1. Go to [claude.ai](https://claude.ai)
2. Click your **profile icon** → **Settings**
3. Click **"Connectors"** in the sidebar
4. Scroll down and click **"Add custom connector"**
5. Paste your Railway URL with `/mcp` at the end:
   ```
   https://stockflow-remote-production-xxxx.up.railway.app/mcp
   ```
6. Click **"Add"**

### Step 5: Use It!

Start a new conversation on claude.ai and try:

> "Use the stockflow tools to get me the current data for CEG including analyst targets"

> "Pull historical data for TLN with 6 month period and show me where the 50 and 200 SMA are"

> "Get the options chain for VST for the nearest expiration"

---

## Troubleshooting

- **Railway build fails:** Make sure all files are uploaded correctly, especially `requirements.txt`
- **Connector won't connect:** Make sure your URL ends with `/mcp`
- **No data returned:** Yahoo Finance has rate limits; wait a moment and retry
- **Railway free tier limits:** You get 500 hours/month free, which is plenty for market-hours usage

---

## License

MIT — same as the original mcp-stockflow.
