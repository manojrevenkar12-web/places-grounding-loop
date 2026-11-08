import { chart, color } from "../../theme/tokens";
import type { Summary } from "../../shared/api/types";
import { euro, seconds, signed } from "../../shared/format";

/** Each row takes one thing away from the guarded loop: the change in task success, with its paired interval. */
export function AblationChart({ rows }: { rows: Record<string, Summary> }) {
  const items = Object.entries(rows).filter(([, s]) => s.vs_guarded);
  const W = 640;
  const left = chart.label;
  const lo = Math.min(-0.05, ...items.map(([, s]) => s.vs_guarded![1]));
  const hi = Math.max(0.05, ...items.map(([, s]) => s.vs_guarded![2]));
  const x = (v: number) => left + ((W - left - 70) * (v - lo)) / (hi - lo);
  const H = items.length * chart.row + chart.axis + 6;
  return (
    <figure className="figure">
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Change in task success when each guard is removed">
        <line x1={x(0)} x2={x(0)} y1={0} y2={H - chart.axis} stroke={color.ink} />
        {items.map(([name, s], i) => {
          const [d, a, b] = s.vs_guarded!;
          const cy = 14 + i * chart.row;
          const bad = b < 0;
          return (
            <g key={name}>
              <text x={0} y={cy + 4} className="chart__label">
                {name.replace(/^guarded,? /, "")}
              </text>
              <rect x={Math.min(x(0), x(d))} y={cy - chart.bar / 2} width={Math.max(1.5, Math.abs(x(d) - x(0)))} height={chart.bar} fill={bad ? color.signal : color.faint} />
              <line x1={x(a)} x2={x(b)} y1={cy} y2={cy} stroke={color.ink} strokeWidth={1.4} />
              <line x1={x(a)} x2={x(a)} y1={cy - chart.whisker / 2} y2={cy + chart.whisker / 2} stroke={color.ink} strokeWidth={1.4} />
              <line x1={x(b)} x2={x(b)} y1={cy - chart.whisker / 2} y2={cy + chart.whisker / 2} stroke={color.ink} strokeWidth={1.4} />
              <text x={W - 64} y={cy + 4} className={`chart__value ${bad ? "is-bad" : ""}`}>
                {signed(d)}
              </text>
            </g>
          );
        })}
        <text x={x(0)} y={H - 6} textAnchor="middle" className="chart__tick">
          no change
        </text>
      </svg>
      <figcaption className="note">
        Removing a guard is measured on the same tasks and draws as the full guarded loop. Red bars are drops whose whole interval is below zero.
      </figcaption>
      <table className="table table--compact">
        <thead>
          <tr>
            <th scope="col">Variant</th>
            <th scope="col" className="num">
              p95 per turn
            </th>
            <th scope="col" className="num">
              Cost per turn
            </th>
            <th scope="col" className="num">
              Cache hits
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map(([name, s]) => (
            <tr key={name}>
              <th scope="row">{name}</th>
              <td className="num">{seconds(s.p95_ms)}</td>
              <td className="num">{euro(s.cost_eur)}</td>
              <td className="num">{Math.round(100 * s.cache_hit_share)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
