"use strict";
const data = JSON.parse(document.getElementById("lab-data").textContent);
const $ = (id) => document.getElementById(id);
const number = (id, min, max) => {
  const input = $(id);
  const parsed = Number(input.value);
  return Math.min(max, Math.max(min, Number.isFinite(parsed) ? parsed : min));
};
const money = (n, places = 2) => `${n < 0 ? "−" : "+"}$${Math.abs(n).toLocaleString("en-US", {minimumFractionDigits: places, maximumFractionDigits: places})}`;
function update() {
  const shares = Math.round(number("shares", 1, 100000));
  const bps = number("bps", 0, 20);
  const commission = number("commission", 0, 1);
  const scenario = data.scenarios.find((s) => s.latency_ms === Number($("latency").value));
  const costs = (scenario.entry.ask + scenario.exit.bid) * bps / 10000 + commission * 2;
  const net = scenario.gross_per_share - costs;
  $("bps-label").textContent = `${bps.toFixed(1)} bps`;
  $("net-result").textContent = money(net * shares);
  $("net-per-share").textContent = `${money(net, 4)} per share · ${shares.toLocaleString()} shares`;
  $("net-cost").textContent = `$${(costs * shares).toFixed(2)} in extra modeled costs`;
  $("result-panel").classList.toggle("negative", net < 0);
  $("fills").replaceChildren(...[["Buy at ask", scenario.entry, scenario.entry.ask], ["Sell at bid", scenario.exit, scenario.exit.bid]].map(([label, quote, price]) => {
    const row = document.createElement("tr");
    [label, quote.request_time, `$${price.toFixed(2)}`, `${quote.age_ms.toFixed(3)} ms`].forEach((value, i) => {
      const cell = document.createElement(i === 0 ? "th" : "td");
      if (i === 0) cell.scope = "row";
      cell.textContent = value;
      row.append(cell);
    });
    return row;
  }));
}
$("cost-form").addEventListener("submit", (e) => e.preventDefault());
$("cost-form").addEventListener("input", update);
update();

const svg = $("price-chart");
const NS = "http://www.w3.org/2000/svg";
function draw(name, attrs, text) {
  const element = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
  if (text !== undefined) element.textContent = text;
  svg.append(element);
  return element;
}
const points = data.chart;
const low = Math.floor(Math.min(...points.map((p) => p.close)) - 1);
const high = Math.ceil(Math.max(...points.map((p) => p.close)) + 1);
const x = (minute) => 54 + minute / 390 * 716;
const y = (price) => 250 - (price - low) / (high - low) * 205;
draw("rect", {x: x(0), y: 30, width: x(30) - x(0), height: 220, fill: "#e7f5ec"});
for (let price = low; price <= high; price += 2) {
  draw("line", {x1: 54, y1: y(price), x2: 770, y2: y(price), stroke: "#dce5eb"});
  draw("text", {x: 44, y: y(price) + 4, "text-anchor": "end", fill: "#526d7c", "font-size": 12}, `$${price}`);
}
draw("line", {x1: 54, y1: y(data.range_high), x2: 770, y2: y(data.range_high), stroke: "#417b5c", "stroke-dasharray": "5 5"});
draw("text", {x: 65, y: y(data.range_high) - 10, fill: "#285d40", "font-size": 12}, `Range high $${data.range_high}`);
draw("path", {d: points.map((p, i) => `${i ? "L" : "M"}${x(p.minute).toFixed(2)},${y(p.close).toFixed(2)}`).join(" "), stroke: "#126b91", "stroke-width": 2.5, fill: "none", "stroke-linejoin": "round"});
[[55, "Decision 10:25"], [385, "Exit 15:55"]].forEach(([minute, label]) => {
  draw("line", {x1: x(minute), x2: x(minute), y1: 30, y2: 250, stroke: "#93a7b3", "stroke-dasharray": "3 4"});
  draw("text", {x: x(minute) + (minute > 300 ? -8 : 8), y: 20, "text-anchor": minute > 300 ? "end" : "start", fill: "#344e5e", "font-size": 12}, label);
});
[[0, "09:30"], [90, "11:00"], [210, "13:00"], [330, "15:00"], [390, "16:00"]].forEach(([minute, label]) => draw("text", {x: x(minute), y: 278, "text-anchor": "middle", fill: "#526d7c", "font-size": 12}, label));
