import { MotionConfig } from "framer-motion";
import { useState } from "react";
import { base, fetchJSON } from "../shared/api/client";
import type { HarnessName, MapData, Results, Summary } from "../shared/api/types";
import { useResource } from "../shared/hooks/useResource";
import { Empty, ErrorState, Section, Skeleton } from "../shared/ui/States";
import { Segmented } from "../shared/ui/Segmented";
import { pct } from "../shared/format";
import { ConflationMap, MapKey } from "../features/map/ConflationMap";
import { PipelineFigures } from "../features/map/PipelineFigures";
import { HarnessTable } from "../features/harnesses/HarnessTable";
import { LatencyStrip } from "../features/harnesses/LatencyStrip";
import { FailureMatrix } from "../features/failures/FailureMatrix";
import { AblationChart } from "../features/ablations/AblationChart";
import { Funnel } from "../features/feedback/Funnel";
import { GateList } from "../features/gate/GateList";

const RESULTS = `${base}/results.json`;
const MAP = `${base}/map.json`;

export function App() {
  const res = useResource((s) => fetchJSON<Results>(RESULTS, s), RESULTS);
  return (
    <MotionConfig reducedMotion="user">
      <main className="page">
        <p className="masthead">places-grounding-loop</p>
        {res.state === "loading" && <Skeleton />}
        {res.state === "error" && <ErrorState error={res.error} onRetry={res.retry} />}
        {res.state === "ready" && <Report r={res.data} />}
      </main>
    </MotionConfig>
  );
}

function Headline({ r }: { r: Results }) {
  const ho = r.heldout;
  if (!ho) {
    const d = r.dev.harnesses;
    return <h1>On the development tasks, plan then fetch answered {pct(d.plan_fetch.success)} right; the plain loop {pct(d.plain.success)}. The held-out run has not happened yet.</h1>;
  }
  const h = ho.harnesses;
  return (
    <h1>
      On {r.config.tasks_heldout} requests from an area nobody looked at while building, plan then fetch answered {pct(h.plan_fetch.success)} right and was confidently wrong{" "}
      {pct(h.plan_fetch.wrong)} of the time. The plain loop was wrong {pct(h.plain.wrong)} of the time.
    </h1>
  );
}

function Report({ r }: { r: Results }) {
  const [mode, setMode] = useState<"full" | "naive">("full");
  const [set, setSet] = useState<"heldout" | "dev">(r.heldout ? "heldout" : "dev");
  const harnesses: Record<HarnessName, Summary> = set === "heldout" && r.heldout ? r.heldout.harnesses : r.dev.harnesses;
  const n = set === "heldout" ? r.config.tasks_heldout : r.config.tasks_dev;
  return (
    <>
      <header className="hero">
        <Headline r={r} />
        <p className="hero__lead">
          One pipeline merges a community source, a partner feed and user reports into one record per place with ids that survive a refresh. Agents answer place questions
          through an MCP server over that data. The model and the tools are the same in every column; the harness around them is what changes.
        </p>
      </header>

      <Section id="pipeline" title="One record per place" lead="Release 2 of the development area, after a refresh of every source. Switch to a name-and-distance merge to see what a first version leaves behind.">
        <Segmented
          label="Pipeline"
          value={mode}
          onChange={(v) => setMode(v as "full" | "naive")}
          options={[
            { id: "full", label: "This pipeline", note: "learned matcher, id inheritance" },
            { id: "naive", label: "Name-and-distance merge", note: "what a first version does" },
          ]}
        />
        <MapPanel r={r} mode={mode} />
      </Section>

      <div className="set-switch">
        <Segmented
          label="Task set"
          value={set}
          onChange={(v) => setSet(v as "heldout" | "dev")}
          options={[
            ...(r.heldout ? [{ id: "heldout", label: "Held-out tasks", note: `${r.config.tasks_heldout} tasks, run once` }] : []),
            { id: "dev", label: "Development tasks", note: `${r.config.tasks_dev} tasks, used while building` },
          ]}
        />
      </div>

      <Section id="harnesses" title="Three harnesses, one model" lead={`${n} tasks × ${r.config.repeats} repeats with different model draws and tool failures. A turn is one user message.`}>
        <HarnessTable set={harnesses} targets={r.targets} />
        <LatencyStrip set={harnesses} budgetMs={r.targets.p95_latency_ms} />
      </Section>

      <Section id="failures" title="Where each mistake is stopped" lead="The simulated model makes these mistakes at fixed rates. The guards have to catch them from what the model proposes, the way they would with a real one.">
        <FailureMatrix set={harnesses} />
      </Section>

      <Section id="ablations" title="What each guard is worth" lead="Development tasks only.">
        <AblationChart rows={r.dev.ablations} />
      </Section>

      <Section id="feedback" title="From a production failure to a regression case" lead="Three days of development traffic served by the plain loop, with users reporting what they saw.">
        <Funnel f={r.dev.feedback} />
      </Section>

      <Section id="gate" title="The gate a change has to pass" lead="Six changes, each against the harness it would replace. CI runs the same check on every pull request.">
        <GateList gate={r.dev.gate} maxDrop={r.config.gate_max_drop} />
      </Section>

      <footer className="footer">
        {r.heldout_runs.length ? (
          <p>
            Held-out run log: <code>{r.heldout_runs[0]}</code>
          </p>
        ) : (
          <p>The held-out tasks have not been run.</p>
        )}
      </footer>
    </>
  );
}

function MapPanel({ r, mode }: { r: Results; mode: "full" | "naive" }) {
  const m = useResource((s) => fetchJSON<MapData>(MAP, s), MAP);
  return (
    <div className="map-panel">
      <div className="map-panel__map">
        {m.state === "loading" && <div className="skeleton__map" role="status" aria-label="Loading the map" />}
        {m.state === "error" && <ErrorState error={m.error} onRetry={m.retry} />}
        {m.state === "ready" && (m.data[mode].length ? <ConflationMap data={m.data} mode={mode} /> : <Empty title="No places in this release">Run make report to export the map.</Empty>)}
        <MapKey />
      </div>
      <PipelineFigures dev={r.dev} mode={mode} />
    </div>
  );
}
