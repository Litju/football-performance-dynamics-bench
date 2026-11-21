import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  METRICS,
  METRIC_LABEL,
  REGIMES,
  REGIME_LABEL,
  REGIME_SHORT,
  REPRESENTATIONS,
  REPRESENTATION_LABEL,
  baseline,
  contrast,
  fmt,
  matchValues,
  matches,
  summary,
} from "../data/findings";
import type { Metric, Regime, Representation } from "../data/findings";
import { COLORS } from "../three/colors";

const SERIES: Record<Representation, { color: string; shape: "circle" | "square" }> = {
  absolute_xy: { color: COLORS.absolute, shape: "circle" },
  origin_relative_displacement: { color: COLORS.displacement, shape: "square" },
};

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(720);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

function Mark({ shape, x, y, r, fill, stroke }: { shape: "circle" | "square"; x: number; y: number; r: number; fill: string; stroke: string }) {
  return shape === "circle" ? (
    <circle cx={x} cy={y} r={r} fill={fill} stroke={stroke} strokeWidth={2} />
  ) : (
    <rect x={x - r} y={y - r} width={2 * r} height={2 * r} rx={1.5} fill={fill} stroke={stroke} strokeWidth={2} />
  );
}

const niceMax = (v: number) => Math.ceil(v * 2) / 2;

interface Tip {
  x: number;
  y: number;
  regime: Regime;
  rep: Representation;
}

function MetricChart({ metric }: { metric: Metric }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const narrow = width < 560;
  const labelW = narrow ? 104 : 150;
  const right = narrow ? 62 : 84;
  const rowH = 34;
  const headH = 34;
  const gap = 18;
  const cv = baseline("constant_velocity_1s_v1", metric);
  const persistence = baseline("origin_persistence_v1", metric);
  const all = REGIMES.flatMap((r) => REPRESENTATIONS.flatMap((p) => matchValues(r, p, metric).map((m) => m.value)));
  // A dot plot needs no zero baseline: the domain hugs the data and both references.
  const minV = Math.floor(Math.min(...all) * 2) / 2;
  const maxV = niceMax(Math.max(persistence, ...all));
  const plotW = Math.max(120, width - labelW - right);
  const x = (v: number) => labelW + ((v - minV) / (maxV - minV)) * plotW;
  const groupH = headH + rowH * 2;
  const top = 8;
  const height = top + REGIMES.length * (groupH + gap) + 34;
  const ticks: number[] = [];
  const step = maxV - minV > 3 || narrow ? 1 : 0.5;
  for (let t = minV; t <= maxV + 1e-9; t += step) ticks.push(Math.round(t * 10) / 10);

  useEffect(() => setTip(null), [metric]);

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={height} role="group" aria-label={`${METRIC_LABEL[metric].short} in metres for six configurations; axis starts at ${minV} m; full values in the table below`}>
        <g className="chart__grid">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={top} y2={height - 28} />
              <text x={x(t)} y={height - 10} textAnchor="middle">
                {t.toFixed(step < 1 ? 1 : 0)}
              </text>
            </g>
          ))}
          <text x={width - 4} y={height - 10} textAnchor="end" className="chart__unit">
            m
          </text>
        </g>
        {REGIMES.map((regime, gi) => {
          const gy = top + gi * (groupH + gap);
          const conditional = regime !== "history_only";
          return (
            <g key={regime}>
              {conditional && <rect x={0} y={gy} width={3} height={groupH} fill={COLORS.future} />}
              {gi === 0 && !narrow && (
                <text x={width - 2} y={gy + 20} textAnchor="end" className="chart__unit">
                  mean, m
                </text>
              )}
              <text x={conditional ? 12 : 0} y={gy + 20} className="chart__group">
                {narrow ? REGIME_SHORT[regime] : regime === "history_only" ? "History only" : REGIME_LABEL[regime].replace("History + realized ", "+ realized ")}
                {!narrow && regime !== "history_only" && (
                  <tspan className={conditional ? "chart__flag chart__flag--future" : "chart__flag"} dx={10}>
                    {conditional ? "conditional · not a forecast" : "ex-ante forecast"}
                  </tspan>
                )}
              </text>
              {regime === "history_only" &&
                [
                  { v: cv, name: "Constant velocity" },
                  { v: persistence, name: "Persistence" },
                ].map((b) => (
                  <g key={b.name} className="chart__ref">
                    <line x1={x(b.v)} x2={x(b.v)} y1={gy + 26} y2={gy + groupH} />
                    {!narrow && (
                      <text x={x(b.v) + (b.name === "Persistence" ? 5 : -5)} y={gy + 20} textAnchor={b.name === "Persistence" ? "start" : "end"}>
                        {b.name} {fmt(b.v)}
                      </text>
                    )}
                  </g>
                ))}
              {REPRESENTATIONS.map((rep, ri) => {
                const y = gy + headH + ri * rowH + rowH / 2;
                const s = summary(regime, rep, metric);
                const vals = matchValues(regime, rep, metric);
                const series = SERIES[rep];
                const active = tip && tip.regime === regime && tip.rep === rep;
                const open = () => setTip({ x: x(s.mean), y, regime, rep });
                return (
                  <g
                    key={rep}
                    tabIndex={0}
                    role="button"
                    className={`chart__row${active ? " is-active" : ""}`}
                    aria-label={`${REPRESENTATION_LABEL[rep]} ${fmt(s.mean)} m ${METRIC_LABEL[metric].short}, ${REGIME_LABEL[regime]}; matches ${vals.map((v) => fmt(v.value)).join(", ")} m`}
                    onMouseEnter={open}
                    onMouseLeave={() => setTip(null)}
                    onFocus={open}
                    onBlur={() => setTip(null)}
                    onClick={open}
                  >
                    <rect x={0} y={y - rowH / 2} width={width} height={rowH} className="chart__hit" />

                    <line x1={x(s.min)} x2={x(s.max)} y1={y} y2={y} stroke={series.color} strokeWidth={2} strokeLinecap="round" opacity={0.55} />
                    {vals.map((v) => (
                      <Mark key={v.match} shape={series.shape} x={x(v.value)} y={y} r={4} fill={COLORS.bg} stroke={series.color} />
                    ))}
                    <Mark shape={series.shape} x={x(s.mean)} y={y} r={6.5} fill={series.color} stroke={COLORS.bg} />
                    <text y={y + 4}>
                      <tspan x={conditional ? 12 : 0} className="chart__label">
                        {REPRESENTATION_LABEL[rep]}
                      </tspan>
                      <tspan x={width - 2} textAnchor="end" className="chart__value">
                        {` ${fmt(s.mean)}`}
                      </tspan>
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      {narrow && (
        <p className="chart__refs">
          Dashed lines, left to right: constant velocity {fmt(cv)} m · persistence {fmt(persistence)} m (history-only references)
        </p>
      )}
      {tip && <Tooltip tip={tip} metric={metric} width={width} />}
    </div>
  );
}

function Tooltip({ tip, metric, width }: { tip: Tip; metric: Metric; width: number }) {
  const s = summary(tip.regime, tip.rep, metric);
  const vals = matchValues(tip.regime, tip.rep, metric);
  const left = Math.min(Math.max(8, tip.x - 130), width - 268);
  return (
    <div className="tooltip" style={{ left, top: tip.y + 22 }} role="status">
      <div className="tooltip__title">
        {REGIME_LABEL[tip.regime]} · {REPRESENTATION_LABEL[tip.rep]}
      </div>
      <div className="tooltip__big">
        {fmt(s.mean)} m <span>{METRIC_LABEL[metric].short}, equal-match mean</span>
      </div>
      <dl>
        {vals.map((v) => (
          <div key={v.match}>
            <dt>Match {v.match}</dt>
            <dd>{fmt(v.value)} m</dd>
          </div>
        ))}
        <div>
          <dt>Descriptive SD across matches</dt>
          <dd>{fmt(s.sd)} m</dd>
        </div>
      </dl>
      {tip.regime !== "history_only" && <p className="tooltip__warn">Uses realized future context: conditional, not a forecast.</p>}
    </div>
  );
}

function ContrastChart() {
  const [ref, width] = useWidth<HTMLDivElement>();
  const narrow = width < 560;
  const labelW = narrow ? 120 : 210;
  const right = narrow ? 62 : 84;
  const rows = (["C1", "C2"] as const).flatMap((c) => REPRESENTATIONS.map((rep) => ({ c, rep, d: contrast(c, rep) })));
  const maxV = 0.35;
  const plotW = Math.max(120, width - labelW - right);
  const x = (v: number) => labelW + (v / maxV) * plotW;
  const rowH = 36;
  const height = rows.length * rowH + 40;
  return (
    <div className="chart chart--small" ref={ref}>
      <svg width={width} height={height} role="img" aria-label="Paired within-match ADE differences for contrasts C1 and C2; values in the table below">
        <g className="chart__grid">
          {[0, 0.1, 0.2, 0.3].map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={4} y2={height - 28} />
              <text x={x(t)} y={height - 10} textAnchor="middle">
                {t.toFixed(1)}
              </text>
            </g>
          ))}
          <text x={width - 4} y={height - 10} textAnchor="end" className="chart__unit">
            m lower ADE
          </text>
        </g>
        {rows.map(({ c, rep, d }, i) => {
          const y = 8 + i * rowH + rowH / 2;
          const series = SERIES[rep];
          return (
            <g key={`${c}${rep}`} aria-label={`${c} ${REPRESENTATION_LABEL[rep]}: mean ${fmt(d.mean)} m`}>
              <text x={0} y={y + 4} className="chart__label">
                <tspan className="chart__strong">{c}</tspan> {narrow ? (rep === "absolute_xy" ? "Abs. XY" : "Displ.") : REPRESENTATION_LABEL[rep]}
              </text>
              {d.perMatch.map((m) => (
                <Mark key={m.match} shape={series.shape} x={x(m.value)} y={y} r={4} fill={COLORS.bg} stroke={series.color} />
              ))}
              <line x1={x(d.mean)} x2={x(d.mean)} y1={y - 10} y2={y + 10} stroke="#f2efe7" strokeWidth={2} />
              <text x={width - 2} y={y + 4} textAnchor="end" className="chart__value">
                {fmt(d.mean)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function Results() {
  const [metric, setMetric] = useState<Metric>("ade_m");
  const [table, setTable] = useState(false);
  return (
    <div className="results">
      <div className="results__controls">
        <div className="seg" role="radiogroup" aria-label="Metric">
          {METRICS.map((m) => (
            <button key={m} type="button" role="radio" aria-checked={metric === m} className={metric === m ? "is-on" : ""} onClick={() => setMetric(m)}>
              {METRIC_LABEL[m].short}
            </button>
          ))}
        </div>
        <ul className="legend legend--chart" aria-label="Chart legend">
          <li>
            <svg width="14" height="14" aria-hidden="true">
              <circle cx="7" cy="7" r="5" fill={COLORS.absolute} />
            </svg>
            Absolute XY target
          </li>
          <li>
            <svg width="14" height="14" aria-hidden="true">
              <rect x="2" y="2" width="10" height="10" rx="1.5" fill={COLORS.displacement} />
            </svg>
            Displacement target
          </li>
          <li>
            <svg width="14" height="14" aria-hidden="true">
              <circle cx="7" cy="7" r="4" fill="none" stroke="#a7b0ba" strokeWidth="2" />
            </svg>
            One match (seed-averaged)
          </li>
        </ul>
      </div>
      <p className="results__metric">
        <strong>{METRIC_LABEL[metric].short}</strong> — {METRIC_LABEL[metric].long}. Lower is better. Filled marks: equal-match means of 4 matches; hollow marks: individual matches; the line spans the observed match range (descriptive, not a confidence interval). Dashed lines: deterministic history-only references. The axis does not start at zero. Hover, tap or tab to a row for values.
      </p>
      <MetricChart metric={metric} />
      <button type="button" className="linkish" aria-expanded={table} onClick={() => setTable((t) => !t)}>
        {table ? "Hide" : "Show"} all values as a table
      </button>
      {table && (
        <div className="table-wrap">
          <table>
            <caption>Equal-match means over four evaluation matches (metres). Source: findings.json.</caption>
            <thead>
              <tr>
                <th scope="col">Information available</th>
                <th scope="col">Target</th>
                <th scope="col">ADE</th>
                <th scope="col">FDE at 3 s</th>
                <th scope="col">XY RMSE</th>
              </tr>
            </thead>
            <tbody>
              {REGIMES.flatMap((r) =>
                REPRESENTATIONS.map((p) => (
                  <tr key={`${r}${p}`}>
                    <td>{REGIME_LABEL[r]}</td>
                    <td>{REPRESENTATION_LABEL[p]}</td>
                    {METRICS.map((m) => (
                      <td key={m}>{fmt(summary(r, p, m).mean)}</td>
                    ))}
                  </tr>
                )),
              )}
              <tr>
                <td>History only (deterministic)</td>
                <td>Constant velocity, 1 s</td>
                {METRICS.map((m) => (
                  <td key={m}>{fmt(baseline("constant_velocity_1s_v1", m))}</td>
                ))}
              </tr>
              <tr>
                <td>History only (deterministic)</td>
                <td>Origin persistence</td>
                {METRICS.map((m) => (
                  <td key={m}>{fmt(baseline("origin_persistence_v1", m))}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <div className="contrast">
        <h3>Adding realized context: paired differences per match</h3>
        <p>
          <strong>C1</strong> = history-only ADE − future-ball ADE. <strong>C2</strong> = future-ball ADE − future-opponents-plus-ball ADE. Paired within each of the {matches.length} matches after averaging seeds; positive means lower error once more realized future context is supplied. Hollow marks are matches, the bar is the mean.
        </p>
        <ContrastChart />
        <p className="note note--future">
          These contrasts measure apparent predictability when the model is handed realized future trajectories. They are conditional, not deployable forecasting gains or causal effects, and they do not estimate what an upstream ball or opponent forecaster would deliver. The conditional analysis is the empirical question Paper B is intended to pursue; values here are reproduced from the published results, not new analysis.
        </p>
      </div>
    </div>
  );
}
