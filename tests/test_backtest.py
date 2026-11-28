"""Regression checks for timing and quote withdrawal, using synthetic inputs."""
import sys
import unittest
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backtest import MINUTE, choose_signal, clock_ns, quote_at


class TimingTests(unittest.TestCase):
    def opening(self):
        return [{"timestamp": clock_ns("09:30") + i * MINUTE, "high": 100} for i in range(30)]

    def test_signal_waits_until_bar_completes(self):
        high, signal = choose_signal(self.opening() + [{"timestamp": clock_ns("10:03"), "high": 101}], clock_ns("10:00"), clock_ns("15:55"))
        self.assertEqual(high, 100)
        self.assertEqual(signal["known_at_ns"], clock_ns("10:04"))

    def test_equal_high_is_not_breakout(self):
        _, signal = choose_signal(self.opening() + [{"timestamp": clock_ns("10:00"), "high": 100}], clock_ns("10:00"), clock_ns("15:55"))
        self.assertIsNone(signal)

    def test_entry_at_exit_is_rejected(self):
        _, signal = choose_signal(self.opening() + [{"timestamp": clock_ns("15:54"), "high": 101}], clock_ns("10:00"), clock_ns("15:55"))
        self.assertIsNone(signal)

    def test_incomplete_opening_range_fails(self):
        with self.assertRaises(ValueError):
            choose_signal(self.opening()[:-1], clock_ns("10:00"), clock_ns("15:55"))


class QuoteTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.con.execute("CREATE TABLE quotes(ts_sip BIGINT, sequence_number BIGINT, bid_price DOUBLE, ask_price DOUBLE, bid_size DOUBLE, ask_size DOUBLE)")

    def tearDown(self):
        self.con.close()

    def test_future_and_equal_timestamp_quotes_are_excluded(self):
        self.con.execute("INSERT INTO quotes VALUES (100,1,99,101,1,1),(200,2,199,201,1,1),(300,3,299,301,1,1)")
        self.assertEqual(quote_at(self.con, 200)["ask"], 101)

    def test_sequence_breaks_ties(self):
        self.con.execute("INSERT INTO quotes VALUES (100,1,99,101,1,1),(100,2,100,102,1,1)")
        self.assertEqual(quote_at(self.con, 200)["ask"], 102)

    def test_withdrawal_does_not_resurrect_previous_quote(self):
        self.con.execute("INSERT INTO quotes VALUES (100,1,99,101,1,1),(200,2,0,0,0,0)")
        with self.assertRaises(ValueError):
            quote_at(self.con, 300)

    def test_stale_quote_fails(self):
        self.con.execute("INSERT INTO quotes VALUES (100,1,99,101,1,1)")
        with self.assertRaises(ValueError):
            quote_at(self.con, 2_000_000_000)


if __name__ == "__main__":
    unittest.main()
