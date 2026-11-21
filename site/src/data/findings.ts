// Typed, read-only view of the published aggregate results.
// Source of truth: docs/res440/findings.json (imported at build time, never copied).
import raw from "@evidence/res440/findings.json";

export type Regime = "history_only" | "future_ball" | "future_opponent_plus_ball";
export type Representation = "absolute_xy" | "origin_relative_displacement";
export type Metric = "ade_m" | "fde_m" | "xy_rmse_m";

export const REGIMES: readonly Regime[] = ["history_only", "future_ball", "future_opponent_plus_ball"];
export const REPRESENTATIONS: readonly Representation[] = ["absolute_xy", "origin_relative_displacement"];
export const METRICS: readonly Metric[] = ["ade_m", "fde_m", "xy_rmse_m"];

export const REGIME_LABEL: Record<Regime, string> = {
  history_only: "History only",
  future_ball: "History + realized future ball",
  future_opponent_plus_ball: "History + realized future opponents and ball",
};

export const REGIME_SHORT: Record<Regime, string> = {
  history_only: "History only",
  future_ball: "+ future ball",
  future_opponent_plus_ball: "+ future opponents & ball",
};

export const REPRESENTATION_LABEL: Record<Representation, string> = {
  absolute_xy: "Absolute XY",
  origin_relative_displacement: "Displacement",
};

export const METRIC_LABEL: Record<Metric, { short: string; long: string }> = {
  ade_m: { short: "ADE", long: "Average displacement error over the 3 s horizon" },
  fde_m: { short: "FDE", long: "Final displacement error at 3 s" },
  xy_rmse_m: { short: "XY RMSE", long: "Scene coordinate RMSE, √[Σ(dx²+dy²)/(2N)]" },
};

interface SummaryRow {
  regime: Regime;
  representation: Representation;
  [key: string]: string | number;
}
interface MatchRow {
  match: string;
  regime: Regime;
  representation: Representation;
  ade_m: number;
  fde_m: number;
  xy_rmse_m: number;
}
interface ContrastRow {
  contrast: "C1" | "C2";
  representation: Representation;
  mean_m: number;
  sd_m: number;
  min_m: number;
  max_m: number;
  delete_one_min_m: number;
  delete_one_max_m: number;
  [match: string]: string | number;
}
interface BaselineRow {
  baseline: string;
  representation: Representation;
  metric: Metric;
  baseline_mean_m: number;
  learned_mean_m: number;
  baseline_minus_learned_m: number;
  reduction_percent: number;
}
interface DenominatorRow {
  match: string;
  windows: number;
  scenes: number;
  scored_points: number;
  provider_extrapolated: number;
  scene_quality: { detected_only: number; with_provider_extrapolation: number; unclassified: number };
}

const data = raw as unknown as {
  classification: string;
  independent_units: number;
  records: number;
  windows: number;
  attempts: number;
  provenance: Record<string, string>;
  summary: SummaryRow[];
  match_means: MatchRow[];
  contrasts: ContrastRow[];
  history_baseline_comparisons: BaselineRow[];
  denominators: DenominatorRow[];
  strata: (MatchRow & { stratum: string })[];
};

export const classification = data.classification;
export const independentUnits = data.independent_units;
export const records = data.records;
export const windows = data.windows;
export const provenance = data.provenance;

export const matches: string[] = data.denominators.map((d) => d.match);

export function summary(regime: Regime, representation: Representation, metric: Metric) {
  const row = data.summary.find((r) => r.regime === regime && r.representation === representation);
  if (!row) throw new Error(`missing summary ${regime}/${representation}`);
  return {
    mean: row[metric] as number,
    sd: row[`${metric}_sd`] as number,
    min: row[`${metric}_min`] as number,
    max: row[`${metric}_max`] as number,
  };
}

export function matchValues(regime: Regime, representation: Representation, metric: Metric) {
  return data.match_means
    .filter((r) => r.regime === regime && r.representation === representation)
    .map((r) => ({ match: r.match, value: r[metric] }));
}

export function baseline(name: "constant_velocity_1s_v1" | "origin_persistence_v1", metric: Metric) {
  // Deterministic baselines yield identical physical predictions under either encoding.
  const row = data.history_baseline_comparisons.find(
    (r) => r.baseline === name && r.metric === metric && r.representation === "absolute_xy",
  );
  if (!row) throw new Error(`missing baseline ${name}/${metric}`);
  return row.baseline_mean_m;
}

export function baselineComparison(
  name: "constant_velocity_1s_v1" | "origin_persistence_v1",
  representation: Representation,
  metric: Metric,
) {
  const row = data.history_baseline_comparisons.find(
    (r) => r.baseline === name && r.metric === metric && r.representation === representation,
  );
  if (!row) throw new Error(`missing comparison ${name}/${representation}/${metric}`);
  return { diff: row.baseline_minus_learned_m, percent: row.reduction_percent, baseline: row.baseline_mean_m };
}

export function contrast(name: "C1" | "C2", representation: Representation) {
  const row = data.contrasts.find((r) => r.contrast === name && r.representation === representation);
  if (!row) throw new Error(`missing contrast ${name}/${representation}`);
  return {
    mean: row.mean_m,
    sd: row.sd_m,
    min: row.min_m,
    max: row.max_m,
    perMatch: matches.map((m) => ({ match: m, value: row[m] as number })),
  };
}

export function stratum(name: string, regime: Regime, representation: Representation, metric: Metric) {
  const row = data.strata.find((r) => r.stratum === name && r.regime === regime && r.representation === representation);
  if (!row) throw new Error(`missing stratum ${name}/${regime}/${representation}`);
  return row[metric];
}

export const denominators = data.denominators;
export const totals = data.denominators.reduce(
  (acc, d) => ({
    windows: acc.windows + d.windows,
    scenes: acc.scenes + d.scenes,
    points: acc.points + d.scored_points,
    extrapolated: acc.extrapolated + d.provider_extrapolated,
    detectedOnly: acc.detectedOnly + d.scene_quality.detected_only,
  }),
  { windows: 0, scenes: 0, points: 0, extrapolated: 0, detectedOnly: 0 },
);

export const fmt = (v: number, digits = 4) => v.toFixed(digits);
export const fmtInt = (v: number) => v.toLocaleString("en-US");
export const fmtPct = (v: number, digits = 1) => `${v.toFixed(digits)}%`;

/** The headline comparison, computed rather than typed. */
export const headline = (() => {
  const cv = baselineComparison("constant_velocity_1s_v1", "origin_relative_displacement", "ade_m");
  return {
    cvAde: cv.baseline,
    dispAde: summary("history_only", "origin_relative_displacement", "ade_m").mean,
    absAde: summary("history_only", "absolute_xy", "ade_m").mean,
    reduction: cv.diff,
    percent: cv.percent,
  };
})();

const repo = "https://github.com/Litju/football-performance-dynamics-bench";
export const LINKS = {
  repo,
  paperPdf: `${repo}/blob/main/docs/paper-a/manuscript.pdf`,
  results: `${repo}/blob/main/docs/res440/results.md`,
  tables: `${repo}/blob/main/docs/res440/tables.md`,
  findings: `${repo}/blob/main/docs/res440/findings.json`,
  evidence: `${repo}/blob/main/docs/paper-a-evidence.md`,
  reproducibility: `${repo}/blob/main/docs/reproducibility.md`,
  rights: `${repo}/blob/main/docs/data-rights.md`,
  supplement: `${repo}/blob/main/docs/paper-a/supplement.md`,
  skillcorner: "https://github.com/SkillCorner/opendata",
};
