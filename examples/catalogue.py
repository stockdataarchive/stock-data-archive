"""Read ticker coverage, file schemas and sample URLs from the public MCP server.

python examples/catalogue.py LEH
python examples/catalogue.py AAPL --json

This small client uses the stateless JSON responses provided by Stock Data Archive.
It calls only public read-only tools and sends no account credentials.
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

ENDPOINT = "https://stockdataarchive.com/mcp"
PROTOCOL = "2025-11-25"
IDS = itertools.count(1)


def request(method: str, params: dict, *, notification: bool = False):
    payload = {"jsonrpc": "2.0", "method": method, "params": params}
    if not notification:
        payload["id"] = next(IDS)
    req = Request(ENDPOINT, json.dumps(payload).encode(), headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL,
    })
    with urlopen(req, timeout=30) as response:
        body = response.read()
    if notification:
        return None
    reply = json.loads(body)
    if "error" in reply:
        raise RuntimeError(reply["error"].get("message", "MCP request failed"))
    return reply["result"]


def tool(name: str, arguments: dict):
    result = request("tools/call", {"name": name, "arguments": arguments})
    if result.get("isError"):
        message = " ".join(item.get("text", "") for item in result.get("content", []))
        raise RuntimeError(message or f"{name} failed")
    if "structuredContent" in result:
        return result["structuredContent"]
    return json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", default="LEH")
    parser.add_argument("--json", action="store_true", help="Print full tool results as JSON")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9.\-]{1,16}", args.symbol):
        parser.error("Use a ticker symbol, such as AAPL, LEH or BRK.B.")
    try:
        initialized = request("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "stockdataarchive-example", "version": "1.0"},
        })
        if initialized["protocolVersion"] != PROTOCOL:
            raise RuntimeError("The server negotiated a different protocol version.")
        request("notifications/initialized", {}, notification=True)
        coverage = tool("get_ticker", {"symbol": args.symbol.upper()})
        formats = tool("get_file_format", {})
        samples = tool("get_sample_files", {})
    except (URLError, RuntimeError, json.JSONDecodeError) as error:
        parser.exit(1, f"Request failed: {error}\n")

    if args.json:
        print(json.dumps({"coverage": coverage, "formats": formats, "samples": samples}, indent=2))
        return
    print(f"{coverage['symbol']}: {coverage['name']}")
    print(f"Coverage: {coverage['first_date']} to {coverage['last_date']}")
    if coverage.get("page_url"):
        print(f"Website: {coverage['page_url']}")
    print("Formats: " + ", ".join(formats["formats"]))
    minute = next(dataset for dataset in formats["datasets"] if dataset["id"] == "minute")
    print("Minute-bar columns: " + ", ".join(minute["columns"]))
    print("Public sample files:")
    for file in samples["files"]:
        print(f"  {file['dataset']} ({file['rows']:,} rows): {file['url']}")
    print("Coverage and schemas are metadata; market data is read from the files.")


if __name__ == "__main__":
    main()
