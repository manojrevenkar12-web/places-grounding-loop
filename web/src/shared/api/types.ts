export type HarnessName = "plain" | "guarded" | "plan_fetch";
export type Mode = "invented_argument" | "stale_context" | "silent_partial" | "unbounded_loop" | "guessed_between_matches";

export interface Summary {
  success: number;
  success_lo: number;
  success_hi: number;
  wrong: number;
  no_answer: number;
  by_kind: Record<string, number>;
  modes: Record<Mode, number>;
  trips: Record<string, number>;
  p50_ms: number;
  p95_ms: number;
  cost_eur: number;
  model_calls: number;
  tool_calls: number;
  cache_hit_share: number;
  runs: number;
  turns: number;
  vs_guarded?: [number, number, number];
}

export interface PipelineScore {
  places: number;
  completeness: number;
  duplicates: number;
  wrong_merges: number;
  position_error_median_m: number | null;
  position_error_p90_m: number | null;
  hours_correct: number;
  closed_still_listed_open: number;
  closures_applied: number;
  closed_in_truth: number;
  wrongly_closed: number;
  id_stability: number | null;
}

export interface GateDecision {
  current: string;
  diff: number;
  lo: number;
  hi: number;
  budget: { p50_ms: number; p95_ms: number; cost_eur: number };
  regressions_broken: string[];
  blocked: boolean;
  reasons: string[];
}

export interface Feedback {
  requests: number;
  failed: number;
  reported: number;
  false_reports: number;
  confirmed: number;
  unreported_failures: number;
  cases: number;
  case_modes: Record<string, number>;
  pass: Record<HarnessName, number>;
}

export interface DevSet {
  pipeline: Record<"full" | "naive", { r1: PipelineScore; r2: PipelineScore; checks: Record<string, number>; blocked: boolean }>;
  harnesses: Record<HarnessName, Summary>;
  paired: Record<string, [number, number, number]>;
  ablations: Record<string, Summary>;
  on_naive_data: Partial<Record<HarnessName, Summary>>;
  feedback: Feedback;
  gate: Record<string, GateDecision>;
}

export interface HeldoutSet {
  commit: string;
  pipeline: Record<"full" | "naive", PipelineScore>;
  harnesses: Record<HarnessName, Summary>;
  paired: Record<string, [number, number, number]>;
}

export interface Results {
  dev: DevSet;
  heldout?: HeldoutSet;
  heldout_runs: string[];
  targets: { p95_latency_ms: number; cost_per_request_eur: number };
  config: { repeats: number; tasks_dev: number; tasks_heldout: number; max_steps: number; gate_max_drop: number };
}

/** [lon, lat, flag, sources]: flag 0 one record per place, 1 a duplicate of another place, 2 two places merged. */
export type Point = [number, number, 0 | 1 | 2, number];
export interface MapData {
  full: Point[];
  naive: Point[];
  box: [number, number, number, number];
  lon_max: number;
}
