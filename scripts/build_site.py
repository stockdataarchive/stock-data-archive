"""Build a static, crawlable page with results embedded for offline interaction."""
import html
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = json.loads((root / "docs/results.json").read_text())
base = data["scenarios"][0]
template = (root / "site/index.html").read_text()
replacements = {
    "@@DATA@@": json.dumps(data).replace("</", "<\\/"),
    "@@BAR_RESULT@@": f'{data["bar_model"]["gross_per_share"]:.3f}',
    "@@QUOTE_RESULT@@": f'{base["gross_per_share"]:.3f}',
    "@@SPREAD_CENTS@@": f'{base["spread_cost_per_share"] * 100:g}',
    "@@BAR_GAP_CENTS@@": f'{base["bar_minus_quote_per_share"] * 100:g}',
    "@@BAR_BUY@@": f'{data["bar_model"]["buy"]:.3f}',
    "@@BAR_SELL@@": f'{data["bar_model"]["sell"]:.2f}',
    "@@QUOTE_BUY@@": f'{base["entry"]["ask"]:.2f}',
    "@@QUOTE_SELL@@": f'{base["exit"]["bid"]:.2f}',
    "@@MID_BUY@@": f'{base["entry"]["mid"]:.3f}',
    "@@MID_SELL@@": f'{base["exit"]["mid"]:.3f}',
    "@@MID_RESULT@@": f'{base["midpoint_per_share"]:.3f}',
    "@@SOURCE_ROWS@@": "\n".join(
        f'<tr><th scope="row"><a href="{html.escape(s["url"])}">{s["dataset"]}</a></th>'
        f'<td>{data["counts"][{"1min":"bars", "trades":"trades", "quotes":"quotes"}[s["dataset"]]]:,}</td>'
        f'<td><code class="hash">{s["sha256"]}</code></td></tr>' for s in data["sources"]
    ),
}
for key, value in replacements.items():
    template = template.replace(key, value)
if "@@" in template:
    raise ValueError("Unresolved template field")
(root / "docs/index.html").write_text(template)
print("Built docs/index.html from pinned backtest results")
