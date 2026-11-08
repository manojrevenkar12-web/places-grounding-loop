import { chart, color, harnessColor } from "../../theme/tokens";
import type { HarnessName, Summary } from "../../shared/api/types";
import { harnessLabel, seconds } from "../../shared/format";

const ORDER: HarnessName[] = ["plain", "guarded", "plan_fetch"];

/** p50 to p95 per turn for each harness, with the p95 budget drawn across. */
export function LatencyStrip({ set, budgetMs }: { set: Record<HarnessName, Summary>; budgetMs: number }) {
  const W = 640;
  const left = chart.label - 90;
  const max = Math.ceil(Math.max(budgetMs, ...ORDER.map((h) => set[h].p95_ms)) / 2000) * 2000;
  const x = (ms: number) => left + ((W - left - 16) * ms) / max;
  const H = ORDER.length * chart.row + chart.axis + 18;
  const ticks = Array.from({ length: max / 2000 + 1 }, (_, i) => i * 2000);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Latency per turn, median to 95th percentile, against the budget">
      <line x1={x(budgetMs)} x2={x(budgetMs)} y1={8} y2={H - chart.axis} stroke={color.road} strokeWidth={2} />
      <text x={x(budgetMs) + 6} y={14} className="chart__note" fill={color.road}>
        p95 budget {seconds(budgetMs)}
      </text>
      {ORDER.map((h, i) => {
        const s = set[h];
        const cy = 24 + i * chart.row;
        return (
          <g key={h}>
            <text x={0} y={cy + 4} className="chart__label">
              {harnessLabel[h]}
            </text>
            <line x1={x(s.p50_ms)} x2={x(s.p95_ms)} y1={cy} y2={cy} stroke={harnessColor[h]} strokeWidth={3} />
            <circle cx={x(s.p50_ms)} cy={cy} r={chart.dot} fill={color.sheet} stroke={harnessColor[h]} strokeWidth={2} />
            <circle cx={x(s.p95_ms)} cy={cy} r={chart.dot} fill={harnessColor[h]} />
          </g>
        );
      })}
      <g transform={`translate(0, ${H - chart.axis + 4})`}>
        {ticks.map((t) => (
          <text key={t} x={x(t)} y={12} textAnchor="middle" className="chart__tick">
            {t / 1000} s
          </text>
        ))}
      </g>
    </svg>
  );
}
