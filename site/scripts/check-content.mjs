// Focused source-data and content checks for the research showcase.
// Run after `npm run build`. Exits non-zero on any failure.
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const site = fileURLToPath(new URL("..", import.meta.url));
const repo = join(site, "..");
const findings = JSON.parse(readFileSync(join(repo, "docs/res440/findings.json"), "utf8"));
const failures = [];
const check = (ok, msg) => {
  if (!ok) failures.push(msg);
};
const near = (a, b, tol = 5e-5) => Math.abs(a - b) <= tol;

// 1. Headline figures quoted by the specification are what the public JSON contains.
const cv = findings.history_baseline_comparisons.find(
  (r) => r.baseline === "constant_velocity_1s_v1" && r.representation === "origin_relative_displacement" && r.metric === "ade_m",
);
check(near(cv.baseline_mean_m, 2.2433), `constant velocity ADE ${cv.baseline_mean_m}`);
check(near(cv.learned_mean_m, 1.668), `history-only displacement ADE ${cv.learned_mean_m}`);
check(cv.reduction_percent.toFixed(1) === "25.6", `reduction ${cv.reduction_percent}`);

// 2. Evaluation design counts and denominators reconcile.
check(findings.independent_units === 4, "independent units must be 4");
check(findings.records === 72, "records must be 72");
check(findings.windows === 51713, "windows must be 51,713");
check(findings.classification.includes("NOT_QUALIFIED"), "classification must remain NOT_QUALIFIED");
const sum = (k) => findings.denominators.reduce((a, d) => a + d[k], 0);
check(sum("windows") === findings.windows, "per-match windows must sum to the total");
check(sum("scenes") === 2 * findings.windows, "every window has two directed scenes");
check(sum("scored_points") === 17065290, "scored player-time points");
check(sum("provider_extrapolated") === 6008819, "provider-extrapolated points");
check(findings.denominators.reduce((a, d) => a + d.scene_quality.detected_only, 0) === 1343, "detected-only scenes");
check(findings.summary.length === 6, "six configurations");
check(findings.match_means.length === 24, "six configurations x four matches");

// 3. The built page carries the scientific limitations and labels.
const dist = join(site, "dist");
check(existsSync(join(dist, "index.html")), "run `npm run build` first");
const bundle = existsSync(dist)
  ? readdirSync(join(dist, "assets"))
      .filter((f) => f.endsWith(".js"))
      .map((f) => readFileSync(join(dist, "assets", f), "utf8"))
      .join("\n")
  : "";
for (const phrase of [
  "NOT_QUALIFIED",
  "not a deployable forecast",
  "never an input",
  "not tracking data",
  "234-fit plan",
  "216 training leave-one-match-out fits",
  "independent observations",
  "No significance tests",
  "not a confidence interval",
  "Paper B",
  "SkillCorner Open Data",
  "non-archival",
]) {
  check(bundle.includes(phrase), `built site is missing required text: "${phrase}"`);
}
// Every number on the page is computed from findings.json; the bundle must embed it.
check(bundle.includes("constant_velocity_1s_v1") && bundle.includes("2.2433"), "findings.json is not embedded in the bundle");

// 4. Repository file and naming rules for the committed site tree.
const forbiddenNames = [
  /ALI[-_]?[0-9]+/i,
  /BM[-_]?[0-9]+/i,
  /SB[-_]?R0(?:[-_][A-Z0-9]+)*/i,
  /SC[-_]?R0(?:[-_][A-Z0-9]+)*/i,
  /H[0-9]+F[0-9]+/i,
  new RegExp("R7" + "D", "i"),
  new RegExp("R7" + "E", "i"),
  /RES-[0-9]+/i,
];
const forbiddenSuffix = /\.(csv|tsv|jsonl|parquet|npy|npz|pkl|pt|pth|ckpt|onnx|safetensors|h5|hdf5|feather|arrow|sqlite)$/i;
const skip = new Set(["node_modules", "dist", "qa", ".vercel"]);
function walk(dir) {
  for (const name of readdirSync(dir)) {
    if (skip.has(name)) continue;
    const p = join(dir, name);
    const rel = relative(repo, p);
    if (statSync(p).isDirectory()) {
      walk(p);
      continue;
    }
    check(!forbiddenSuffix.test(name), `forbidden data file: ${rel}`);
    if (/\.(png|jpe?g|webp|ico)$/i.test(name)) continue;
    const text = readFileSync(p, "utf8");
    for (const re of forbiddenNames) {
      const m = text.match(re) ?? name.match(re);
      check(!m, `forbidden identifier "${m?.[0]}" in ${rel}`);
    }
  }
}
walk(site);

if (failures.length) {
  for (const f of failures) console.error("FAIL", f);
  process.exit(1);
}
console.log("content checks passed");
