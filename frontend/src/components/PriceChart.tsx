import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Candle, fetchCandles } from "../api";
import { axisLabel, coinName, price, usd } from "../format";
import { usePolling } from "../hooks";
import { Change, Section } from "./ui";

export const RANGES = [
  { minutes: 60, label: "1 hour", words: "hour" },
  { minutes: 360, label: "6 hours", words: "6 hours" },
  { minutes: 1440, label: "24 hours", words: "24 hours" },
] as const;

function span(minutes: number): string {
  if (minutes < 60) return `${minutes} minutes`;
  const hours = minutes / 60;
  return hours % 1 === 0 ? `${hours} hour${hours === 1 ? "" : "s"}` : `${hours.toFixed(1)} hours`;
}

/** One plain sentence about the period shown, worked out from the candles. */
export function takeaway(name: string, data: Candle[], bucketMin: number): string {
  const first = data[0];
  const last = data[data.length - 1];
  const start = first.open;
  const end = last.close;
  const change = start ? ((end - start) / start) * 100 : 0;
  const busiest = data.reduce((a, b) => (b.notional > a.notional ? b : a));
  const covered = span(data.length * bucketMin);
  const direction = Math.abs(change) < 0.005 ? "is about where it started" : `is ${change > 0 ? "up" : "down"} ${Math.abs(change).toFixed(2)}%`;
  const busiestWhen = new Date(busiest.ws).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `Over the last ${covered}, ${name} ${direction} (from $${price(start)} to $${price(end)}). The busiest ${bucketMin === 1 ? "minute" : `${bucketMin}-minute stretch`} was at ${busiestWhen}, when ${usd(busiest.notional)} was traded.`;
}

export function PriceChart({ symbol, change5m }: { symbol: string; change5m?: number | null }) {
  const [minutes, setMinutes] = useState<number>(60);
  const { data, failed } = usePolling(() => fetchCandles(symbol, minutes), `${symbol}:${minutes}`, minutes === 60 ? 3000 : 15000);

  const name = coinName(symbol);
  const candles = data?.candles ?? [];
  const bucketMin = data?.bucketMin ?? 1;
  const rows = candles.map((c) => ({ ...c, time: axisLabel(c.ws, minutes), average: c.vwap ?? c.close }));
  const lo = rows.length ? Math.min(...rows.map((d) => d.low)) : 0;
  const hi = rows.length ? Math.max(...rows.map((d) => d.high)) : 1;
  // Never zoom in tighter than 0.3% of the price, so a tiny wiggle is not drawn as a dramatic swing.
  const mid = (hi + lo) / 2;
  const half = Math.max((hi - lo) * 0.6, mid * 0.0015);

  return (
    <Section
      title={`${name}: price history`}
      subtitle="The line is the price. The bars underneath show how much money was traded in each period."
      className="chart-card"
      actions={
        <div className="segmented" role="group" aria-label="Time range">
          {RANGES.map((r) => (
            <button key={r.minutes} className={minutes === r.minutes ? "active" : ""} aria-pressed={minutes === r.minutes} onClick={() => setMinutes(r.minutes)}>
              {r.label}
            </button>
          ))}
        </div>
      }
      learn={
        <ul>
          <li>If the line climbs, the price went up over that time; if it falls, the price went down.</li>
          <li>Tall bars mean lots of people were trading. Short bars mean it was quiet.</li>
          <li>The line is each period's <b>average price</b>, weighted so that bigger trades count for more.</li>
          <li>On the 6-hour and 24-hour views each point covers several minutes, so the chart stays easy to read.</li>
        </ul>
      }
    >
      {change5m !== undefined && (
        <div className="chart-head">
          <Change value={change5m} suffix=" in the last 5 minutes" />
        </div>
      )}

      {failed && <div className="notice">The chart could not be loaded just now. It will try again automatically.</div>}
      {rows.length < 2 && !failed && <div className="empty">Collecting data. This chart fills in as time passes.</div>}
      {rows.length >= 2 && (
        <>
          <div className="legend" aria-hidden="true">
            <span><i className="swatch line" /> Price</span>
            <span><i className="swatch bar" /> Money traded {bucketMin === 1 ? "per minute" : `per ${bucketMin} minutes`}</span>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="time" stroke="var(--muted)" tick={{ fontSize: 12 }} minTickGap={40} />
              <YAxis yAxisId="p" orientation="left" domain={[mid - half, mid + half]} stroke="var(--muted)" tick={{ fontSize: 12 }}
                tickFormatter={(v: number) => `$${price(v)}`} width={92} />
              <YAxis yAxisId="v" hide domain={[0, (max: number) => max * 4]} />
              <Tooltip
                contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 10, color: "var(--text)" }}
                labelFormatter={(label) => `At ${label}`}
                formatter={(value: number, key: string) => (key === "notional" ? [usd(value), "Money traded"] : [`$${price(value)}`, "Price"])}
              />
              <Bar yAxisId="v" dataKey="notional" fill="var(--bar)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <Line yAxisId="p" dataKey="average" stroke="var(--line-strong)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="takeaway"><b>In short:</b> {takeaway(name, candles, bucketMin)}</p>
        </>
      )}
    </Section>
  );
}

export default PriceChart;
