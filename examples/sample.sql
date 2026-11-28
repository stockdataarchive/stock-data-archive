-- Run in DuckDB. These queries use the public AAPL sample for November 9, 2026.
-- Dataset documentation: https://stockdataarchive.com/docs/

CREATE OR REPLACE VIEW aapl_sample AS
SELECT * FROM read_parquet(
  'https://stockdataarchive.com/samples/AAPL_2026-11-09_1min.parquet'
);

-- Every minute with trades, including extended hours: 846 bars.
SELECT symbol, count(*) AS minute_bars
FROM aapl_sample
GROUP BY symbol;

-- Convert the stored nanoseconds since the Unix epoch to New York time.
SELECT
  to_timestamp("timestamp" / 1e9)
    AT TIME ZONE 'America/New_York' AS bar_start,
  open, high, low, close, volume, trade_count
FROM aapl_sample
ORDER BY "timestamp"
LIMIT 5;

-- Keep regular-session bar starts from 09:30 through 15:59 Eastern.
WITH local_bars AS (
  SELECT *,
    to_timestamp("timestamp" / 1e9)
      AT TIME ZONE 'America/New_York' AS bar_start
  FROM aapl_sample
)
SELECT count(*) AS regular_session_bars
FROM local_bars
WHERE CAST(bar_start AS TIME) >= TIME '09:30:00'
  AND CAST(bar_start AS TIME) < TIME '16:00:00';
