-- ============================================================
-- SQL STOCK MARKET ANALYSIS - SQLITE 3
-- Advanced analytical layer for the Streamlit dashboard
-- Six NSE stocks | 2015-01-01 to 2018-07-31
--
-- Source tables expected:
-- bajaj_auto, eicher_motors, hero_motocorp, infosys, tcs, tvs_motors
-- Dates: YYYY-MM-DD text
--
-- This file is SQLite-only. No MySQL DELIMITER, YEAR(), stored
-- functions, or other MySQL-only syntax is used.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. DATA COVERAGE
-- ============================================================
SELECT 'Bajaj Auto' AS stock, COUNT(*) trading_days, MIN(date) first_day, MAX(date) last_day FROM bajaj_auto
UNION ALL SELECT 'Eicher Motors', COUNT(*), MIN(date), MAX(date) FROM eicher_motors
UNION ALL SELECT 'Hero Motocorp', COUNT(*), MIN(date), MAX(date) FROM hero_motocorp
UNION ALL SELECT 'Infosys', COUNT(*), MIN(date), MAX(date) FROM infosys
UNION ALL SELECT 'TCS', COUNT(*), MIN(date), MAX(date) FROM tcs
UNION ALL SELECT 'TVS Motors', COUNT(*), MIN(date), MAX(date) FROM tvs_motors;

-- ============================================================
-- 2. EICHER TOP 5 CLOSING PRICES
-- ============================================================
SELECT date, close_price
FROM eicher_motors
ORDER BY close_price DESC
LIMIT 5;

-- ============================================================
-- 3. TCS YEARLY AVERAGE CLOSE
-- ============================================================
SELECT
    CAST(strftime('%Y', date) AS INTEGER) AS year,
    ROUND(AVG(close_price), 2) AS avg_close
FROM tcs
GROUP BY strftime('%Y', date)
ORDER BY year;

-- ============================================================
-- 4. MISSING DELIVERABLE QUANTITIES
-- ============================================================
SELECT 'Bajaj Auto' stock, date FROM bajaj_auto WHERE deliverable_qty IS NULL
UNION ALL SELECT 'Eicher Motors', date FROM eicher_motors WHERE deliverable_qty IS NULL
UNION ALL SELECT 'Hero Motocorp', date FROM hero_motocorp WHERE deliverable_qty IS NULL
UNION ALL SELECT 'Infosys', date FROM infosys WHERE deliverable_qty IS NULL
UNION ALL SELECT 'TCS', date FROM tcs WHERE deliverable_qty IS NULL
UNION ALL SELECT 'TVS Motors', date FROM tvs_motors WHERE deliverable_qty IS NULL
ORDER BY date, stock;

-- ============================================================
-- 5. BAJAJ MA20 / MA50
-- ============================================================
DROP TABLE IF EXISTS bajaj_ma;
CREATE TABLE bajaj_ma AS
WITH numbered AS (
    SELECT date, close_price,
           ROW_NUMBER() OVER (ORDER BY date) AS rn
    FROM bajaj_auto
)
SELECT date, close_price,
       CASE WHEN rn >= 20 THEN ROUND(
           AVG(close_price) OVER (
               ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
           ), 2) END AS ma20,
       CASE WHEN rn >= 50 THEN ROUND(
           AVG(close_price) OVER (
               ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
           ), 2) END AS ma50
FROM numbered;

SELECT * FROM bajaj_ma ORDER BY date;

-- ============================================================
-- 6. MASTER CLOSE-PRICE TABLE
-- ============================================================
DROP TABLE IF EXISTS master_prices;
CREATE TABLE master_prices AS
SELECT b.date,
       b.close_price AS bajaj_auto,
       e.close_price AS eicher_motors,
       h.close_price AS hero_motocorp,
       i.close_price AS infosys,
       t.close_price AS tcs,
       v.close_price AS tvs_motors
FROM bajaj_auto b
JOIN eicher_motors e ON e.date = b.date
JOIN hero_motocorp h ON h.date = b.date
JOIN infosys i ON i.date = b.date
JOIN tcs t ON t.date = b.date
JOIN tvs_motors v ON v.date = b.date;

SELECT * FROM master_prices ORDER BY date;

-- ============================================================
-- 7. BAJAJ CROSSOVER SIGNALS
-- ============================================================
DROP TABLE IF EXISTS bajaj_signals;
CREATE TABLE bajaj_signals AS
WITH lagged AS (
    SELECT date, close_price, ma20, ma50,
           LAG(ma20) OVER (ORDER BY date) AS prev_ma20,
           LAG(ma50) OVER (ORDER BY date) AS prev_ma50
    FROM bajaj_ma
)
SELECT date, close_price, ma20, ma50,
       CASE
           WHEN ma20 > ma50 AND prev_ma20 <= prev_ma50 THEN 'Buy'
           WHEN ma20 < ma50 AND prev_ma20 >= prev_ma50 THEN 'Sell'
           ELSE 'Hold'
       END AS signal
FROM lagged;

SELECT * FROM bajaj_signals ORDER BY date;

-- ============================================================
-- 8. BAJAJ SIGNAL COUNTS
-- ============================================================
SELECT signal, COUNT(*) AS signal_count
FROM bajaj_signals
GROUP BY signal
ORDER BY CASE signal WHEN 'Buy' THEN 1 WHEN 'Sell' THEN 2 ELSE 3 END;

-- ============================================================
-- 9. DATE-SPECIFIC BAJAJ SIGNAL
-- Use a parameter in the application:
-- SELECT * FROM bajaj_signals WHERE date = ?;
-- ============================================================

-- ============================================================
-- 10. ALL-STOCK SIGNAL ENGINE
-- ============================================================
DROP TABLE IF EXISTS all_stock_signals;
CREATE TABLE all_stock_signals AS
WITH prices AS (
    SELECT 'Bajaj Auto' stock, date, close_price FROM bajaj_auto
    UNION ALL SELECT 'Eicher Motors', date, close_price FROM eicher_motors
    UNION ALL SELECT 'Hero Motocorp', date, close_price FROM hero_motocorp
    UNION ALL SELECT 'Infosys', date, close_price FROM infosys
    UNION ALL SELECT 'TCS', date, close_price FROM tcs
    UNION ALL SELECT 'TVS Motors', date, close_price FROM tvs_motors
),
ma AS (
    SELECT stock, date, close_price,
           CASE WHEN ROW_NUMBER() OVER (PARTITION BY stock ORDER BY date) >= 20 THEN
               AVG(close_price) OVER (
                   PARTITION BY stock ORDER BY date
                   ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
               ) END AS ma20,
           CASE WHEN ROW_NUMBER() OVER (PARTITION BY stock ORDER BY date) >= 50 THEN
               AVG(close_price) OVER (
                   PARTITION BY stock ORDER BY date
                   ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
               ) END AS ma50
    FROM prices
),
lagged AS (
    SELECT *,
           LAG(ma20) OVER (PARTITION BY stock ORDER BY date) prev_ma20,
           LAG(ma50) OVER (PARTITION BY stock ORDER BY date) prev_ma50
    FROM ma
)
SELECT stock, date, close_price,
       ROUND(ma20, 2) ma20, ROUND(ma50, 2) ma50,
       CASE
           WHEN ma20 > ma50 AND prev_ma20 <= prev_ma50 THEN 'Buy'
           WHEN ma20 < ma50 AND prev_ma20 >= prev_ma50 THEN 'Sell'
           ELSE 'Hold'
       END signal
FROM lagged;

SELECT stock, signal, COUNT(*) signal_count
FROM all_stock_signals
GROUP BY stock, signal
ORDER BY stock, CASE signal WHEN 'Buy' THEN 1 WHEN 'Sell' THEN 2 ELSE 3 END;

-- ============================================================
-- 11. RAW FULL-PERIOD RETURNS
-- ============================================================
WITH prices AS (
    SELECT 'Bajaj Auto' stock,date,close_price FROM bajaj_auto
    UNION ALL SELECT 'Eicher Motors',date,close_price FROM eicher_motors
    UNION ALL SELECT 'Hero Motocorp',date,close_price FROM hero_motocorp
    UNION ALL SELECT 'Infosys',date,close_price FROM infosys
    UNION ALL SELECT 'TCS',date,close_price FROM tcs
    UNION ALL SELECT 'TVS Motors',date,close_price FROM tvs_motors
),
ends AS (
    SELECT stock, MIN(date) first_date, MAX(date) last_date
    FROM prices GROUP BY stock
)
SELECT e.stock,
       p1.close_price first_close,
       p2.close_price last_close,
       ROUND(100.0 * (p2.close_price / p1.close_price - 1), 1) pct_change
FROM ends e
JOIN prices p1 ON p1.stock=e.stock AND p1.date=e.first_date
JOIN prices p2 ON p2.stock=e.stock AND p2.date=e.last_date
ORDER BY pct_change DESC;

-- ============================================================
-- 12. WORST DAILY MOVE
-- ============================================================
WITH prices AS (
    SELECT 'Bajaj Auto' stock,date,close_price FROM bajaj_auto
    UNION ALL SELECT 'Eicher Motors',date,close_price FROM eicher_motors
    UNION ALL SELECT 'Hero Motocorp',date,close_price FROM hero_motocorp
    UNION ALL SELECT 'Infosys',date,close_price FROM infosys
    UNION ALL SELECT 'TCS',date,close_price FROM tcs
    UNION ALL SELECT 'TVS Motors',date,close_price FROM tvs_motors
),
moves AS (
    SELECT stock,date,close_price,
           100.0 * (close_price / LAG(close_price) OVER (
               PARTITION BY stock ORDER BY date
           ) - 1) pct_move
    FROM prices
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY stock ORDER BY pct_move
    ) rn
    FROM moves
    WHERE pct_move IS NOT NULL
)
SELECT stock,date,close_price,ROUND(pct_move,1) pct_move
FROM ranked WHERE rn=1
ORDER BY pct_move;

-- ============================================================
-- 13. CORPORATE-ACTION-ADJUSTED RETURNS
-- TCS: 1:1 bonus, ex-date 2018-05-31
-- Infosys: 1:1 bonus, ex-date 2015-06-15
-- ============================================================
WITH adjusted AS (
    SELECT 'TCS' stock,date,
           CASE WHEN date < '2018-05-31' THEN close_price/2.0 ELSE close_price END adj_close
    FROM tcs
    UNION ALL
    SELECT 'Infosys',date,
           CASE WHEN date < '2015-06-15' THEN close_price/2.0 ELSE close_price END
    FROM infosys
),
ends AS (
    SELECT stock, MIN(date) first_date, MAX(date) last_date
    FROM adjusted GROUP BY stock
)
SELECT e.stock,
       ROUND(100.0 * (
           MAX(CASE WHEN a.date=e.last_date THEN a.adj_close END) /
           MAX(CASE WHEN a.date=e.first_date THEN a.adj_close END) - 1
       ), 1) adjusted_pct_change
FROM ends e
JOIN adjusted a ON a.stock=e.stock
GROUP BY e.stock
ORDER BY e.stock;

-- ============================================================
-- 14. ADVANCED: DAILY RETURNS + RISK METRICS
-- ============================================================
DROP VIEW IF EXISTS stock_daily_returns;
CREATE VIEW stock_daily_returns AS
WITH prices AS (
    SELECT 'Bajaj Auto' stock,date,close_price FROM bajaj_auto
    UNION ALL SELECT 'Eicher Motors',date,close_price FROM eicher_motors
    UNION ALL SELECT 'Hero Motocorp',date,close_price FROM hero_motocorp
    UNION ALL SELECT 'Infosys',date,close_price FROM infosys
    UNION ALL SELECT 'TCS',date,close_price FROM tcs
    UNION ALL SELECT 'TVS Motors',date,close_price FROM tvs_motors
),
x AS (
    SELECT stock,date,close_price,
           LAG(close_price) OVER (PARTITION BY stock ORDER BY date) prev_close
    FROM prices
)
SELECT stock,date,close_price,prev_close,
       (close_price / prev_close - 1.0) daily_return
FROM x
WHERE prev_close IS NOT NULL;

-- SQLite has no built-in STDDEV aggregate. Calculate population
-- standard deviation from E[x] and E[x^2].
SELECT
    stock,
    COUNT(*) AS return_days,
    ROUND(100.0 * AVG(daily_return), 4) AS avg_daily_return_pct,
    ROUND(100.0 * SQRT(
        AVG(daily_return * daily_return) -
        AVG(daily_return) * AVG(daily_return)
    ), 2) AS daily_volatility_pct,
    ROUND(100.0 * MIN(daily_return), 2) AS worst_day_pct,
    ROUND(100.0 * MAX(daily_return), 2) AS best_day_pct,
    SUM(CASE WHEN daily_return > 0 THEN 1 ELSE 0 END) AS up_days,
    SUM(CASE WHEN daily_return < 0 THEN 1 ELSE 0 END) AS down_days
FROM stock_daily_returns
GROUP BY stock
ORDER BY stock;

-- ============================================================
-- 15. MAXIMUM DRAWDOWN
-- ============================================================
WITH prices AS (
    SELECT 'Bajaj Auto' stock,date,close_price FROM bajaj_auto
    UNION ALL SELECT 'Eicher Motors',date,close_price FROM eicher_motors
    UNION ALL SELECT 'Hero Motocorp',date,close_price FROM hero_motocorp
    UNION ALL SELECT 'Infosys',date,close_price FROM infosys
    UNION ALL SELECT 'TCS',date,close_price FROM tcs
    UNION ALL SELECT 'TVS Motors',date,close_price FROM tvs_motors
),
running AS (
    SELECT *,
           MAX(close_price) OVER (
               PARTITION BY stock ORDER BY date
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) running_peak
    FROM prices
),
dd AS (
    SELECT stock,date,close_price,running_peak,
           close_price / running_peak - 1.0 drawdown
    FROM running
)
SELECT stock,
       ROUND(100.0 * MIN(drawdown), 2) AS max_drawdown_pct,
       MIN(date) FILTER (WHERE drawdown = (SELECT MIN(d2.drawdown) FROM dd d2 WHERE d2.stock=dd.stock)) AS trough_date
FROM dd
GROUP BY stock
ORDER BY stock;

-- ============================================================
-- 16. SIGNAL-TO-FORWARD-RETURN ANALYSIS
-- Measures the next 1, 5 and 20 trading-day return after a
-- non-Hold crossover signal. This is descriptive backtest
-- analysis, not an investment recommendation.
-- ============================================================
WITH signals AS (
    SELECT stock,date,close_price,signal
    FROM all_stock_signals
    WHERE signal IN ('Buy','Sell')
),
future AS (
    SELECT stock,date,close_price,signal,
           LEAD(close_price,1) OVER (PARTITION BY stock ORDER BY date) p1,
           LEAD(close_price,5) OVER (PARTITION BY stock ORDER BY date) p5,
           LEAD(close_price,20) OVER (PARTITION BY stock ORDER BY date) p20
    FROM signals
)
SELECT stock,signal,
       COUNT(*) AS signal_count,
       ROUND(100.0 * AVG(p1 / close_price - 1), 2) AS avg_next_1d_return_pct,
       ROUND(100.0 * AVG(p5 / close_price - 1), 2) AS avg_next_5d_return_pct,
       ROUND(100.0 * AVG(p20 / close_price - 1), 2) AS avg_next_20d_return_pct
FROM future
GROUP BY stock,signal
ORDER BY stock,signal;

-- ============================================================
-- 17. WHIPSAW DIAGNOSTIC
-- Counts opposite non-Hold signals within 30 calendar days.
-- ============================================================
WITH signals AS (
    SELECT stock,date,signal
    FROM all_stock_signals
    WHERE signal IN ('Buy','Sell')
),
pairs AS (
    SELECT a.stock,a.date signal_date,a.signal,
           b.date opposite_date,b.signal opposite_signal,
           julianday(b.date)-julianday(a.date) days_between
    FROM signals a
    JOIN signals b
      ON b.stock=a.stock
     AND b.date>a.date
     AND b.signal<>a.signal
)
SELECT stock,
       COUNT(*) AS opposite_signals_within_30d
FROM pairs
WHERE days_between <= 30
GROUP BY stock
ORDER BY stock;

-- ============================================================
-- 18. PORTFOLIO-READY NORMALIZED SERIES
-- Growth of 100 using raw prices. The dashboard uses adjusted
-- prices for TCS/Infosys when the adjusted view is selected.
-- ============================================================
WITH prices AS (
    SELECT 'Bajaj Auto' stock,date,close_price FROM bajaj_auto
    UNION ALL SELECT 'Eicher Motors',date,close_price FROM eicher_motors
    UNION ALL SELECT 'Hero Motocorp',date,close_price FROM hero_motocorp
    UNION ALL SELECT 'Infosys',date,close_price FROM infosys
    UNION ALL SELECT 'TCS',date,close_price FROM tcs
    UNION ALL SELECT 'TVS Motors',date,close_price FROM tvs_motors
),
firsts AS (
    SELECT stock, MIN(date) first_date FROM prices GROUP BY stock
)
SELECT p.stock,p.date,p.close_price,
       ROUND(100.0 * p.close_price / f.close_price, 2) growth_of_100
FROM prices p
JOIN firsts x ON x.stock=p.stock AND p.date>=x.first_date
JOIN prices f ON f.stock=p.stock AND f.date=x.first_date
ORDER BY p.stock,p.date;

-- ============================================================
-- END
-- ============================================================
