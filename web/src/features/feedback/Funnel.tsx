import { color } from "../../theme/tokens";
import type { Feedback } from "../../shared/api/types";

/** From production traffic to regression cases, as one bar per stage, widths in proportion to the requests. */
export function Funnel({ f }: { f: Feedback }) {
  const stages = [
    { label: "Production requests on the plain loop", n: f.requests, tone: color.faint },
    { label: "Failed", n: f.failed, tone: color.signal },
    { label: "Reported by a user", n: f.reported, tone: color.signal },
    { label: "Confirmed by a reviewer", n: f.confirmed, tone: color.signal },
    { label: "Kept as regression cases", n: f.cases, tone: color.ink },
    { label: "Pass on plan then fetch", n: f.pass.plan_fetch, tone: color.water },
  ];
  return (
    <figure className="figure">
      <ol className="funnel">
        {stages.map((s) => (
          <li key={s.label} className="funnel__stage">
            <span className="funnel__label">{s.label}</span>
            <span className="funnel__bar" style={{ width: `${(100 * s.n) / f.requests}%`, background: s.tone }} />
            <span className="funnel__n">{s.n}</span>
          </li>
        ))}
      </ol>
      <figcaption className="note">
        {f.unreported_failures} failures were never reported, and {f.false_reports} reports were about answers that were right: user reports find cases, the evaluation measures rates. The{" "}
        {f.cases - f.pass.plan_fetch} cases that still fail are data gaps (phone numbers no source carries, an opening hour the partner feed has wrong), which go to the pipeline, not the
        agent.
      </figcaption>
    </figure>
  );
}
