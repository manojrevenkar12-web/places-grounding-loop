import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/app/App";
import type { MapData, Results, Summary } from "../src/shared/api/types";

const modes = { invented_argument: 0.1, stale_context: 0.05, silent_partial: 0.02, unbounded_loop: 0.04, guessed_between_matches: 0.07 };
const none = { invented_argument: 0, stale_context: 0, silent_partial: 0, unbounded_loop: 0, guessed_between_matches: 0 };
const summary = (success: number, wrong: number, p95: number, cost: number, m = none): Summary => ({
  success, success_lo: success - 0.08, success_hi: success + 0.07, wrong, no_answer: 0.08, by_kind: {}, modes: m,
  trips: { provenance: 27, freshness: 35 }, p50_ms: 2000, p95_ms: p95, cost_eur: cost, model_calls: 2.3, tool_calls: 2.6,
  cache_hit_share: 0.14, runs: 159, turns: 180,
});
const set = { plain: summary(0.7, 0.22, 8100, 0.0147, modes), guarded: summary(0.91, 0.02, 6700, 0.0097), plan_fetch: summary(0.91, 0.02, 2900, 0.0057) };
const score = (dup: number, stab: number) => ({
  places: 700, completeness: 0.99, duplicates: dup, wrong_merges: 4, position_error_median_m: 4, position_error_p90_m: 11, hours_correct: 0.94,
  closed_still_listed_open: 6, closures_applied: 11, closed_in_truth: 14, wrongly_closed: 0, id_stability: stab,
});
const results: Results = {
  dev: {
    pipeline: {
      full: { r1: score(5, 1), r2: score(6, 0.997), checks: { id_loss_share: 0.03 }, blocked: false },
      naive: { r1: score(200, 1), r2: score(222, 0.49), checks: { id_loss_share: 0.56 }, blocked: true },
    },
    harnesses: set,
    paired: {},
    ablations: { "guarded without freshness": { ...summary(0.84, 0.08, 6500, 0.0099), vs_guarded: [-0.072, -0.11, -0.04] } },
    on_naive_data: {},
    feedback: { requests: 264, failed: 85, reported: 47, false_reports: 5, confirmed: 42, unreported_failures: 43, cases: 34, case_modes: {}, pass: { plain: 0, guarded: 25, plan_fetch: 25 } },
    gate: {
      "drop the freshness check": { current: "plan_fetch", diff: -0.072, lo: -0.11, hi: -0.04, budget: { p50_ms: 2100, p95_ms: 3000, cost_eur: 0.006 }, regressions_broken: ["REG-002"], blocked: true, reasons: ["task success may drop"] },
      "plan then fetch": { current: "guarded", diff: 0, lo: 0, hi: 0, budget: { p50_ms: 2100, p95_ms: 3000, cost_eur: 0.006 }, regressions_broken: [], blocked: false, reasons: [] },
    },
  },
  heldout: { commit: "ad8a5e5", pipeline: { full: score(3, 0.996), naive: score(126, 0.48) }, harnesses: set, paired: {} },
  heldout_runs: ["2026-11-08T16:20:24Z commit=ad8a5e5"],
  targets: { p95_latency_ms: 4000, cost_per_request_eur: 0.01 },
  config: { repeats: 3, tasks_dev: 88, tasks_heldout: 53, max_steps: 8, gate_max_drop: 0.02 },
};
const mapData: MapData = {
  full: [[13.3, 52.5, 0, 2], [13.31, 52.51, 1, 1]],
  naive: [[13.3, 52.5, 0, 2], [13.31, 52.51, 1, 1], [13.32, 52.52, 1, 1], [13.33, 52.53, 2, 2]],
  box: [13.28, 52.45, 13.43, 52.58],
  lon_max: 13.52,
};

function serve(map: Record<string, unknown>, fail = new Set<string>()) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (fail.has(url)) return new Response("no", { status: 500 });
    if (!(url in map)) return new Response("no", { status: 404 });
    return new Response(JSON.stringify(map[url]), { status: 200 });
  }));
}
afterEach(() => vi.unstubAllGlobals());

describe("dashboard", () => {
  it("loads, then states the held-out result", async () => {
    serve({ "/data/results.json": results, "/data/map.json": mapData });
    render(<App />);
    expect(screen.getByRole("status", { name: "Loading results" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("plan then fetch answered 91% right and was confidently wrong 2% of the time. The plain loop was wrong 22%");
    expect(screen.getByRole("rowheader", { name: "Plan then fetch" })).toBeInTheDocument();
  });

  it("switches the map to the naive merge and shows its blocked release", async () => {
    serve({ "/data/results.json": results, "/data/map.json": mapData });
    render(<App />);
    expect(await screen.findByRole("img", { name: /2 places in the development area, 1 of them/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Name-and-distance merge/ }));
    expect(await screen.findByRole("img", { name: /4 places in the development area, 3 of them/ })).toBeInTheDocument();
    expect(screen.getByText(/Blocked: 56% of ids would change/)).toBeInTheDocument();
  });

  it("marks over-budget latency and blocked changes", async () => {
    serve({ "/data/results.json": results, "/data/map.json": mapData });
    render(<App />);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByText("8.1 s")).toHaveClass("is-bad");
    expect(screen.getByText("2.9 s")).not.toHaveClass("is-bad");
    expect(screen.getByText("Blocked")).toBeInTheDocument();
  });

  it("explains a failed load and loads again", async () => {
    const fail = new Set(["/data/results.json"]);
    serve({ "/data/results.json": results, "/data/map.json": mapData }, fail);
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
    fail.clear();
    await userEvent.click(screen.getByRole("button", { name: "Load again" }));
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("says so when the map has no places", async () => {
    serve({ "/data/results.json": results, "/data/map.json": { ...mapData, full: [] } });
    render(<App />);
    expect(await screen.findByText("No places in this release")).toBeInTheDocument();
  });

  it("says so before the held-out run", async () => {
    serve({ "/data/results.json": { ...results, heldout: undefined, heldout_runs: [] }, "/data/map.json": mapData });
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("The held-out run has not happened yet.");
  });
});
