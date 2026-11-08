import type { DevSet } from "../../shared/api/types";
import { pct } from "../../shared/format";

/** What the merge did to release 2 of the development area, for the pipeline shown on the map. */
export function PipelineFigures({ dev, mode }: { dev: DevSet; mode: "full" | "naive" }) {
  const p = dev.pipeline[mode];
  const s = p.r2;
  const lost = p.checks.id_loss_share ?? 0;
  return (
    <dl className="figures">
      <div className="figures__row">
        <dt>Places listed twice</dt>
        <dd className={s.duplicates > 20 ? "is-bad" : ""}>{s.duplicates}</dd>
      </div>
      <div className="figures__row">
        <dt>Different places merged</dt>
        <dd>{s.wrong_merges}</dd>
      </div>
      <div className="figures__row">
        <dt>Place ids kept across the refresh</dt>
        <dd className={(s.id_stability ?? 0) < 0.9 ? "is-bad" : ""}>{s.id_stability === null ? "–" : pct(s.id_stability, 1)}</dd>
      </div>
      <div className="figures__row">
        <dt>Positions off by more than (p90)</dt>
        <dd>{s.position_error_p90_m === null ? "–" : `${Math.round(s.position_error_p90_m)} m`}</dd>
      </div>
      <div className="figures__row">
        <dt>Closures applied</dt>
        <dd>
          {s.closures_applied} of {s.closed_in_truth}
          {s.wrongly_closed > 0 && <span className="is-bad">, {s.wrongly_closed} open places closed</span>}
        </dd>
      </div>
      <div className="figures__row">
        <dt>Release check</dt>
        <dd className={p.blocked ? "is-bad" : "is-good"}>{p.blocked ? `Blocked: ${pct(lost)} of ids would change` : `Passes: ${pct(lost, 1)} of ids change`}</dd>
      </div>
    </dl>
  );
}
