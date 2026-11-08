import type { HarnessName, Mode, Summary } from "../../shared/api/types";
import { harnessLabel, modeLabel, pct } from "../../shared/format";

const ORDER: HarnessName[] = ["plain", "guarded", "plan_fetch"];
const MODES = Object.keys(modeLabel) as Mode[];
const TRIP: Record<Mode, string[]> = {
  invented_argument: ["provenance"],
  stale_context: ["freshness"],
  silent_partial: ["partial_retry"],
  unbounded_loop: ["loop_guard", "plan_widen"],
  guessed_between_matches: ["ambiguity"],
};

/** For each production failure mode: how often it reached the user, and what stops it. */
export function FailureMatrix({ set }: { set: Record<HarnessName, Summary> }) {
  const top = Math.max(0.01, ...MODES.flatMap((m) => ORDER.map((h) => set[h].modes[m])));
  return (
    <div className="table-wrap">
      <table className="table matrix">
        <thead>
          <tr>
            <th scope="col">Failure mode</th>
            {ORDER.map((h) => (
              <th key={h} scope="col" className="num">
                {harnessLabel[h]}
              </th>
            ))}
            <th scope="col">What stops it</th>
          </tr>
        </thead>
        <tbody>
          {MODES.map((m) => {
            const fired = TRIP[m].reduce((n, t) => n + (set.plan_fetch.trips[t] ?? 0), 0);
            return (
              <tr key={m}>
                <th scope="row">{modeLabel[m]!.name}</th>
                {ORDER.map((h) => {
                  const v = set[h].modes[m];
                  return (
                    <td key={h} className="num matrix__cell" style={{ ["--heat" as string]: String(v / top) }}>
                      {v === 0 ? <span className="muted">none</span> : pct(v, 1)}
                    </td>
                  );
                })}
                <td className="matrix__why">
                  {modeLabel[m]!.stoppedBy}
                  <span className="matrix__count">Caught {fired} times in plan then fetch</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="note">Share of runs in which the mistake got past the harness into an answer or an executed call, read from the trace.</p>
    </div>
  );
}
