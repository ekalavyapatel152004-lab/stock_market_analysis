# MarketLens — SQL Stock Market Analytics

A SQLite-first stock-market analytics project with an interactive Streamlit dashboard across six Indian stocks (2015-01-01 to 2018-07-31).

## Dashboard pages

1. **Overview** — headline metrics, adjusted growth of ₹100, stock-return comparison and interactive chart.
2. **Signal Explorer** — closing price, MA20/MA50, crossover markers and signal history.
3. **Data Trap** — extreme daily movements, missing-value records and TCS/Infosys bonus-adjustment comparison. The missing-deliverables KPI has been removed as requested.
4. **Risk & Performance** — six-stock table with total return, annualized return (CAGR), annualized volatility, maximum drawdown and return/risk ratio, plus risk/return visuals.
5. **Strategy vs Buy & Hold** — growth of ₹100, drawdown comparison, daily-return distribution and performance scorecard for the MA20/MA50 crossover strategy versus buy-and-hold.
6. **Live SQL Playground** — edit and run SQLite queries, inspect result tables, create charts and download CSV results.

## Run locally on Windows

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app\app.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`).

## Folder structure

```text
SQL_Stock_Market_Analysis/
├── README.md
├── requirements.txt
├── app/app.py
├── assets/marketlens_logo.svg
├── data/                         # six source CSVs
├── database/stock_market.db      # SQLite tables
├── sql/stock_market_analysis_sqlite_advanced.sql
├── reports/stock_market_insights.pdf
└── reference/                    # project brief and student guide
```

## Method notes

- SQLite performs the core SQL analysis: CTEs, window functions, `LAG()`, moving averages, crossover signals, returns and risk calculations.
- Annual return is CAGR over the observed period. Annualized volatility is the population standard deviation of daily returns multiplied by √252. Return/risk is annual return divided by annualized volatility; it is not a Sharpe ratio.
- TCS pre-2018-05-31 closes and Infosys pre-2015-06-15 closes are divided by two for the illustrative 1:1 bonus-adjusted view.
- The strategy backtest shifts the moving-average position by one trading day to reduce look-ahead bias. It excludes transaction costs, taxes, slippage, dividends and execution constraints. Historical results are illustrative, not investment advice.
