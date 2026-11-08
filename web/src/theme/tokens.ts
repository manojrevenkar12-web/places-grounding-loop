// The visual system: a survey sheet. Land tint for the page, water, park and contour colours for the three
// harnesses, signal red for what went wrong, road amber for budgets. CSS reads these as custom properties.

export const color = {
  land: "#EBEEE6",
  sheet: "#F8F9F5",
  ink: "#1E2A28",
  muted: "#5C6A65",
  faint: "#8C9893",
  rule: "#CBD2C8",
  water: "#2B6A99",
  park: "#4A8156",
  contour: "#9A6A3D",
  signal: "#B5372B",
  signalWash: "#F2DCD8",
  road: "#C98B1E",
  hatch: "#D6DBD2",
} as const;

export const harnessColor: Record<string, string> = {
  plain: color.contour,
  guarded: color.park,
  plan_fetch: color.water,
};

export const font = { ui: '"Overpass", "Segoe UI", system-ui, sans-serif' } as const;
export const size = { tick: 11, small: 13, body: 15, lead: 18, title: 24, display: 38 } as const;
export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 24, 6: 32, 7: 48, 8: 72 } as const;
export const radius = { control: 3, panel: 2 } as const;
export const layout = { contentMax: 1120, measure: 70, breakpoint: 860 } as const;

/** The map: point and marker sizes in screen pixels, the scale bar length in metres. */
export const map = { width: 640, point: 1.8, ring: 4.6, cross: 3.4, scaleM: 1000, ringIn: 0.35, ringStagger: 0.0015 } as const;
/** Charts: row heights, bar thickness, label column. */
export const chart = { row: 30, bar: 10, label: 230, axis: 22, whisker: 8, dot: 5 } as const;

export function applyTokens(root: HTMLElement = document.documentElement): void {
  const set = (k: string, v: string | number) => root.style.setProperty(k, typeof v === "number" ? `${v}px` : v);
  Object.entries(color).forEach(([k, v]) => set(`--c-${k}`, v));
  Object.entries(size).forEach(([k, v]) => set(`--fs-${k}`, v));
  Object.entries(space).forEach(([k, v]) => set(`--sp-${k}`, v));
  Object.entries(radius).forEach(([k, v]) => set(`--r-${k}`, v));
  set("--font-ui", font.ui);
  set("--content-max", layout.contentMax);
  set("--measure", `${layout.measure}ch`);
  set("--chart-label", chart.label);
}
