export const pct = (x: number, digits = 0) => `${(100 * x).toFixed(digits)}%`;
export const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`;
export const euro = (x: number) => `€${x.toFixed(4)}`;
export const signed = (x: number, digits = 1) => `${x >= 0 ? "+" : "−"}${Math.abs(100 * x).toFixed(digits)} pts`;

export const harnessLabel: Record<string, string> = {
  plain: "Plain loop",
  guarded: "Guarded loop",
  plan_fetch: "Plan then fetch",
};

export const modeLabel: Record<string, { name: string; stoppedBy: string }> = {
  invented_argument: { name: "Invented argument", stoppedBy: "Arguments must come from the request or a tool result" },
  stale_context: { name: "Stale context", stoppedBy: "Each turn checks the data version and drops older facts" },
  silent_partial: { name: "Silent partial result", stoppedBy: "Partial results are retried, then disclosed" },
  unbounded_loop: { name: "Unbounded loop", stoppedBy: "A call that came back empty is not run again; a step budget" },
  guessed_between_matches: { name: "Guessed between twins", stoppedBy: "Two equally good matches mean asking which one" },
};
