import type { GateDecision } from "../../shared/api/types";
import { euro, harnessLabel, seconds, signed } from "../../shared/format";

/** Every change put through the gate, with the decision and the reason. */
export function GateList({ gate, maxDrop }: { gate: Record<string, GateDecision>; maxDrop: number }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Change</th>
            <th scope="col">Decision</th>
            <th scope="col" className="num">
              Success change
            </th>
            <th scope="col" className="num">
              p95
            </th>
            <th scope="col" className="num">
              Cost
            </th>
            <th scope="col">Why</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(gate).map(([change, d]) => (
            <tr key={change}>
              <th scope="row">
                {change}
                <span className="cell-sub">against {harnessLabel[d.current] ?? d.current}</span>
              </th>
              <td>
                <span className={`chip ${d.blocked ? "chip--blocked" : "chip--pass"}`}>{d.blocked ? "Blocked" : "Passes"}</span>
              </td>
              <td className="num">
                {signed(d.diff)}
                <span className="cell-sub">lower bound {signed(d.lo)}</span>
              </td>
              <td className="num">{seconds(d.budget.p95_ms)}</td>
              <td className="num">{euro(d.budget.cost_eur)}</td>
              <td className="gate__why">{d.reasons.length ? d.reasons.map((x) => x.charAt(0).toUpperCase() + x.slice(1)).join(". ") + "." : "Nothing got worse."}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">
        Blocked when the lower bound of the paired difference in task success is below −{(100 * maxDrop).toFixed(0)} pts, when a regression case the current harness passes fails,
        or when a change is over the latency or cost budget and worse than the current harness there.
      </p>
    </div>
  );
}
