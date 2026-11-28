"""Reproduce the public AAPL bar/quote execution lab. Python 3.10+, DuckDB 1.4.1.

The signal is known only when a minute finishes. Both models enter at the NEXT
minute boundary. Quote prices are strictly before the requested execution time.
No credentials or paid data are used. Downloads are checked against pinned hashes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-09"
SYMBOL = "AAPL"
NY = ZoneInfo("America/New_York")
MINUTE = 60_000_000_000
MAX_QUOTE_AGE_NS = 1_000_000_000
SOURCES = {
    "1min": ("AAPL_2026-11-09_1min.parquet", "4c71b06b49a83c964db738632b9e6c96243e3c1df4f07558ab3618a252fe8c4d"),
    "trades": ("AAPL_2026-11-09_trades.parquet", "b035526a7613132fb084dcd9ab918e77ef1621dbc477157a10f294d620da4ac4"),
    "quotes": ("AAPL_2026-11-09_quotes.parquet", "3b83642ee152bbe408da169c080df8d808d0c97ba18ee8bb6325b61177d8e54b"),
}


def clock_ns(hhmm: str) -> int:
    local = datetime.fromisoformat(f"{DAY}T{hhmm}:00").replace(tzinfo=NY)
    return int(local.timestamp()) * 1_000_000_000


def clock_text(ns: int) -> str:
    seconds, nanos = divmod(ns, 1_000_000_000)
    local = datetime.fromtimestamp(seconds, timezone.utc).astimezone(NY)
    return local.strftime("%H:%M:%S") + f".{nanos // 1_000_000:03d}"


def load_sources(directory: Path) -> tuple[dict, list]:
    directory.mkdir(parents=True, exist_ok=True)
    paths, provenance = {}, []
    for kind, (filename, expected) in SOURCES.items():
        path = directory / filename
        url = f"https://stockdataarchive.com/samples/{filename}"
        if not path.exists():
            with urlopen(url, timeout=60) as response:
                contents = response.read()
            if hashlib.sha256(contents).hexdigest() != expected:
                raise ValueError(f"Unexpected source hash: {filename}; review before updating pins")
            path.write_bytes(contents)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Source hash mismatch: {filename}")
        paths[kind] = str(path)
        provenance.append({"dataset": kind, "url": url, "sha256": actual, "bytes": path.stat().st_size})
    return paths, provenance


def choose_signal(bars: list[dict], range_end: int, exit_time: int) -> tuple[float, dict | None]:
    opening = [b for b in bars if clock_ns("09:30") <= b["timestamp"] < range_end]
    if len(opening) != 30:
        raise ValueError("The opening range requires all 30 regular-session minutes")
    high = max(float(b["high"]) for b in opening)
    # Sorting and waiting for bar completion prevents using future OHLC data.
    for bar in sorted(bars, key=lambda b: b["timestamp"]):
        entry_time = bar["timestamp"] + MINUTE
        if range_end <= bar["timestamp"] and entry_time < exit_time and float(bar["high"]) > high:
            return high, {"bar_start_ns": bar["timestamp"], "known_at_ns": entry_time, "high": float(bar["high"])}
    return high, None


def quote_at(con, request_ns: int) -> dict:
    # Select first, validate second. Filtering invalid quotes BEFORE selection
    # would incorrectly resurrect an older quote after the latest one withdrew.
    row = con.execute("""
        SELECT ts_sip, sequence_number, bid_price, ask_price, bid_size, ask_size
        FROM quotes WHERE ts_sip < ?
        ORDER BY ts_sip DESC, sequence_number DESC LIMIT 1
    """, [request_ns]).fetchone()
    if row is None:
        raise ValueError("No quote before requested execution")
    timestamp, sequence, bid, ask, bid_size, ask_size = row
    if not all(math.isfinite(float(x)) for x in (bid, ask, bid_size, ask_size)):
        raise ValueError("Non-finite quote")
    if bid <= 0 or ask < bid or bid_size <= 0 or ask_size <= 0:
        raise ValueError("Latest quote is invalid or withdrawn")
    age = request_ns - timestamp
    if age > MAX_QUOTE_AGE_NS:
        raise ValueError("Latest quote is older than one second")
    return {"request_ns": request_ns, "request_time": clock_text(request_ns),
            "quote_ns": timestamp, "sequence_number": sequence, "age_ms": round(age / 1e6, 6),
            "bid": float(bid), "ask": float(ask), "mid": float((bid + ask) / 2),
            "bid_size_raw": float(bid_size), "ask_size_raw": float(ask_size)}


def run(directory: Path) -> dict:
    paths, provenance = load_sources(directory)
    con = duckdb.connect()
    for kind, name in [("1min", "bars"), ("trades", "trades"), ("quotes", "quotes")]:
        # A parameterized reader avoids treating filenames as SQL.
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet(?)", [paths[kind]])
    for name in ("bars", "trades", "quotes"):
        symbols = con.execute(f"SELECT DISTINCT symbol FROM {name}").fetchall()
        if symbols != [(SYMBOL,)]:
            raise ValueError(f"Unexpected symbols in {name}: {symbols}")
    if con.execute('SELECT count(*) - count(DISTINCT "timestamp") FROM bars').fetchone()[0]:
        raise ValueError("Duplicate bar timestamps")
    if con.execute('SELECT count(*) FROM bars WHERE "timestamp" % ? != 0', [MINUTE]).fetchone()[0]:
        raise ValueError("Bars are not aligned to minute starts")
    session_start, session_end = clock_ns("09:30"), clock_ns("16:00")
    columns = ['timestamp', 'open', 'high', 'low', 'close']
    rows = con.execute('SELECT "timestamp", open, high, low, close FROM bars WHERE "timestamp" >= ? AND "timestamp" < ? ORDER BY "timestamp"', [session_start, session_end]).fetchall()
    bars = [dict(zip(columns, row)) for row in rows]
    if len(bars) != 390 or any(b["timestamp"] != session_start + i * MINUTE for i, b in enumerate(bars)):
        raise ValueError("This sample requires a complete 390-minute regular session")
    if any(not (b['low'] <= b['open'] <= b['high'] and b['low'] <= b['close'] <= b['high']) for b in bars):
        raise ValueError("Inconsistent OHLC prices")
    exit_time = clock_ns("15:55")
    high, signal = choose_signal(bars, clock_ns("10:00"), exit_time)
    counts = {name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in ("bars", "trades", "quotes")}
    audit = {"regular_session_bars": len(bars), "opening_range_bars": 30,
             "duplicate_bar_timestamps": 0, "quote_age_limit_ms": MAX_QUOTE_AGE_NS // 1_000_000,
             "invalid_quote_rows": con.execute("SELECT count(*) FROM quotes WHERE bid_price <= 0 OR ask_price < bid_price OR bid_size <= 0 OR ask_size <= 0").fetchone()[0]}
    result = {"symbol": SYMBOL, "date": DAY, "timezone": "America/New_York", "duckdb_version": duckdb.__version__,
              "sources": provenance, "counts": counts, "audit": audit, "range_high": high,
              "traded": signal is not None, "scenarios": []}
    # Five-minute closes for a small chart; raw source files are not republished.
    result["chart"] = [{"time": clock_text(b["timestamp"]), "minute": (b["timestamp"] - session_start) // MINUTE,
                        "close": float(b["close"])} for i, b in enumerate(bars) if i % 5 == 4]
    if signal is None:
        return result
    entry_time = signal["known_at_ns"]
    by_time = {b["timestamp"]: b for b in bars}
    bar_buy, bar_sell = (float(by_time[t]["open"]) for t in (entry_time, exit_time))
    result["signal"] = {**signal, "bar_start": clock_text(signal["bar_start_ns"]),
                        "known_at": clock_text(entry_time), "exit_at": clock_text(exit_time)}
    result["bar_model"] = {"buy": bar_buy, "sell": bar_sell, "gross_per_share": round(bar_sell - bar_buy, 8)}
    for latency_ms in (0, 100, 250, 1000):
        entry = quote_at(con, entry_time + latency_ms * 1_000_000)
        exit_quote = quote_at(con, exit_time + latency_ms * 1_000_000)
        gross = exit_quote["bid"] - entry["ask"]
        mid_gross = exit_quote["mid"] - entry["mid"]
        result["scenarios"].append({"latency_ms": latency_ms, "entry": entry, "exit": exit_quote,
            "gross_per_share": round(gross, 8), "midpoint_per_share": round(mid_gross, 8),
            "spread_cost_per_share": round(mid_gross - gross, 8),
            "bar_minus_quote_per_share": round(bar_sell - bar_buy - gross, 8)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".cache")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "results.json")
    args = parser.parse_args()
    result = run(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    with args.output.with_suffix(".csv").open("w", newline="") as out:
        fields = ["latency_ms", "gross_per_share", "midpoint_per_share", "spread_cost_per_share", "bar_minus_quote_per_share"]
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["scenarios"])
    print(json.dumps({k: v for k, v in result.items() if k not in ("sources", "chart")}, indent=2))


if __name__ == "__main__":
    main()
