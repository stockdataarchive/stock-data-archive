"""Download a free AAPL minute-bar sample, check its session, and export CSV.

Run from the repository root: python examples/aapl_sample.py
Sample files and documentation: https://stockdataarchive.com/free-intraday-data/
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from urllib.request import urlopen

import duckdb

ROOT = Path(__file__).resolve().parents[1]
FILENAME = "AAPL_2026-11-09_1min.parquet"
URL = f"https://stockdataarchive.com/samples/{FILENAME}"
SHA256 = "4c71b06b49a83c964db738632b9e6c96243e3c1df4f07558ab3618a252fe8c4d"


def main():
    directory = ROOT / ".cache"
    directory.mkdir(exist_ok=True)
    path = directory / FILENAME
    if not path.exists():
        with urlopen(URL, timeout=30) as response:
            contents = response.read()
        if hashlib.sha256(contents).hexdigest() != SHA256:
            raise ValueError("The sample fingerprint changed; review the file before updating its hash.")
        path.write_bytes(contents)
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise ValueError("The cached sample does not match the published fingerprint.")

    con = duckdb.connect()
    con.execute("CREATE TABLE bars AS SELECT * FROM read_parquet(?)", [str(path)])
    con.execute('''CREATE VIEW local_bars AS
        SELECT symbol,
            to_timestamp("timestamp" / 1e9)
                AT TIME ZONE 'America/New_York' AS bar_start_et,
            open, high, low, close, volume, trade_count
        FROM bars''')
    total, pre, regular, after = con.execute('''
        SELECT count(*),
            count(*) FILTER (WHERE CAST(bar_start_et AS TIME) >= TIME '04:00'
                AND CAST(bar_start_et AS TIME) < TIME '09:30'),
            count(*) FILTER (WHERE CAST(bar_start_et AS TIME) >= TIME '09:30'
                AND CAST(bar_start_et AS TIME) < TIME '16:00'),
            count(*) FILTER (WHERE CAST(bar_start_et AS TIME) >= TIME '16:00'
                AND CAST(bar_start_et AS TIME) < TIME '20:00')
        FROM local_bars''').fetchone()
    output = path.with_suffix(".csv")
    query = con.execute("SELECT * FROM local_bars ORDER BY bar_start_et")
    with output.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow([column[0] for column in query.description])
        writer.writerows(query.fetchall())
    print(f"File: {FILENAME}")
    print(f"Bars: {total} | pre-market: {pre} | regular: {regular} | after-hours: {after}")
    print("Bar starts are displayed in America/New_York time.")
    print(f"CSV: {output}")
    print("File documentation: https://stockdataarchive.com/docs/")


if __name__ == "__main__":
    main()
