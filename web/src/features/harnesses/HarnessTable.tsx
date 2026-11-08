import { chart, harnessColor } from "../../theme/tokens";
import type { HarnessName, Summary } from "../../shared/api/types";
import { euro, harnessLabel, pct, seconds } from "../../shared/format";

const ORDER: HarnessName[] = ["plain", "guarded", "plan_fetch"];
const BAR_W = 160;

/** Success with its interval, wrong answers, latency and cost per turn, against the budgets. */
export function HarnessTable({ set, targets }: { set: Record<HarnessName, Summary>; targets: { p95_latency_ms: number; cost_per_request_eur: number } }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Harness</th>
            <th scope="col">Task success</th>
            <th scope="col" className="num">
              Confidently wrong
            </th>
            <th scope="col" className="num">
              p95 per turn
            </th>
            <th scope="col" className="num">
              Cost per turn
            </th>
            <th scope="col" className="num">
              Model calls
            </th>
          </tr>
        </thead>
        <tbody>
          {ORDER.map((h) => {
            const s = set[h];
            const slow = s.p95_ms > targets.p95_latency_ms;
            const dear = s.cost_eur > targets.cost_per_request_eur;
            return (
              <tr key={h}>
                <th scope="row">
                  <span className="swatch" style={{ background: harnessColor[h] }} aria-hidden="true" />
                  {harnessLabel[h]}
                </th>
                <td>
                  <span className="rate">
                    <svg width={BAR_W} height={chart.bar + 6} aria-hidden="true">
                      <rect y={3} width={BAR_W} height={chart.bar} className="rate__track" />
                      <rect y={3} width={BAR_W * s.success} height={chart.bar} fill={harnessColor[h]} />
                      <line x1={BAR_W * s.success_lo} x2={BAR_W * s.success_hi} y1={3 + chart.bar / 2} y2={3 + chart.bar / 2} className="rate__ci" />
                    </svg>
                    <span>
                      {pct(s.success)} <span className="muted">({pct(s.success_lo)}–{pct(s.success_hi)})</span>
                    </span>
                  </span>
                </td>
                <td className={`num ${s.wrong > 0.05 ? "is-bad" : ""}`}>{pct(s.wrong, 1)}</td>
                <td className={`num ${slow ? "is-bad" : ""}`}>{seconds(s.p95_ms)}</td>
                <td className={`num ${dear ? "is-bad" : ""}`}>{euro(s.cost_eur)}</td>
                <td className="num">{s.model_calls.toFixed(1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="note">
        Budgets: p95 {seconds(targets.p95_latency_ms)} per turn, {euro(targets.cost_per_request_eur)} per turn. Red is over budget. The bar's dark line is the 95% interval, resampling tasks.
      </p>
    </div>
  );
}
