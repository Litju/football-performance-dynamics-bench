import { useEffect, useRef, useState } from "react";
import Results from "./components/Results";
import Stage from "./components/Stage";
import {
  LINKS,
  baselineComparison,
  classification,
  contrast,
  fmt,
  fmtInt,
  fmtPct,
  headline,
  independentUnits,
  provenance,
  records,
  stratum,
  summary,
  totals,
  windows,
} from "./data/findings";
import { CHAPTERS, applyChapter, initialState } from "./story";
import type { StoryState } from "./story";

const pct = (a: number, b: number) => fmtPct((100 * a) / b);

function Chapter({ index, children, wide = false }: { index: number; children: React.ReactNode; wide?: boolean }) {
  return (
    <section className={`chapter${wide ? " chapter--hero" : ""}`} data-chapter={index} id={`story-${CHAPTERS[index].id}`}>
      <div className="card">{children}</div>
    </section>
  );
}

function Header() {
  return (
    <header className="masthead">
      <a className="wordmark" href="#top">
        <span className="wordmark__mark" aria-hidden="true" />
        FPD Bench
      </a>
      <nav aria-label="Primary">
        <a href="#design">Design</a>
        <a href="#results">Results</a>
        <a href="#limits">Limits</a>
        <a href="#research">Research</a>
      </nav>
    </header>
  );
}

export default function App() {
  const [state, setState] = useState<StoryState>(initialState);
  const chapterRef = useRef(0);

  // Scroll position selects the chapter; it never moves the page itself.
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>("[data-chapter]"));
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          const i = Number((e.target as HTMLElement).dataset.chapter);
          if (i !== chapterRef.current) {
            chapterRef.current = i;
            setState((s) => applyChapter(s, i));
          }
        }
      },
      // Desktop reads mid-screen; on phones the text column sits below the sticky pitch.
      { rootMargin: window.innerWidth >= 1000 ? "-45% 0px -45% 0px" : "-78% 0px -20% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  const cvAbs = baselineComparison("constant_velocity_1s_v1", "absolute_xy", "ade_m");
  const cvDispFde = baselineComparison("constant_velocity_1s_v1", "origin_relative_displacement", "fde_m");
  const c1abs = contrast("C1", "absolute_xy");
  const c1disp = contrast("C1", "origin_relative_displacement");
  const c2abs = contrast("C2", "absolute_xy");
  const c2disp = contrast("C2", "origin_relative_displacement");
  const bestFde = summary("future_opponent_plus_ball", "origin_relative_displacement", "fde_m").mean;
  const earlyFopb = stratum("early", "future_opponent_plus_ball", "absolute_xy", "ade_m");
  const earlyFb = stratum("early", "future_ball", "absolute_xy", "ade_m");

  return (
    <>
      <a className="skip" href="#results">
        Skip to measured results
      </a>
      <Header />
      <main id="top">
        <div className="story">
          <Stage state={state} setState={setState} />
          <div className="story__chapters">
            <Chapter index={0} wide>
              <p className="kicker">Football Performance Dynamics Bench · Paper A companion</p>
              <h1>
                Are we forecasting football movement — <em>or conditioning on information from the future?</em>
              </h1>
              <p className="lede">
                Predicting where players will be in three seconds sounds simple. But if a model is quietly handed where the ball or the opponents actually went next, it is no longer forecasting; it is answering a different, easier question with hindsight. FPD Bench makes that line explicit and measures what crossing it does to the error.
              </p>
              <div className="hero-stat">
                <div>
                  <span className="hero-stat__value">{fmt(headline.dispAde)} m</span>
                  <span className="hero-stat__label">history-only displacement model, average error</span>
                </div>
                <div>
                  <span className="hero-stat__value hero-stat__value--muted">{fmt(headline.cvAde)} m</span>
                  <span className="hero-stat__label">constant-velocity reference</span>
                </div>
                <p className="hero-stat__note">
                  A {fmtPct(headline.percent)} descriptive reduction ({fmt(headline.reduction)} m ADE) on {independentUnits} held-out matches. Research-only; not a significance claim.
                </p>
              </div>
              <div className="actions">
                <a className="btn btn--primary" href={LINKS.paperPdf}>
                  Read Paper A (PDF)
                </a>
                <a className="btn" href={LINKS.results}>
                  Full scientific results
                </a>
              </div>
              <p className="scroll-cue" aria-hidden="true">
                Scroll to step through the study
              </p>
            </Chapter>

            <Chapter index={1}>
              <p className="step">01 · The forecast origin</p>
              <h2>Freeze the match at t = 0</h2>
              <p>
                Each test example is a moment from a real match. At the <strong>forecast origin t = 0</strong>, the model may look back over the previous <strong>5 seconds</strong> (25 intervals, sampled every 0.2 s) for both teams and the ball.
              </p>
              <p>
                Its job: the <strong>target team's</strong> positions at each of the next <strong>15 steps</strong>, out to 3 seconds. Every window is scored twice, once with each team as the target.
              </p>
              <p className="aside">The players on this pitch follow a hand-made schematic play to show the time grid. They are not tracking data, a reconstructed sequence or a model prediction.</p>
            </Chapter>

            <Chapter index={2}>
              <p className="step">02 · What the model sees</p>
              <h2>
                <code>history_only</code>: a genuine forecast
              </h2>
              <p>
                Only what had happened by t = 0. After the origin, the model learns nothing new: opponents and ball stay frozen where they were last seen (faded). This is the only regime that matches a forecast you could make live.
              </p>
              <p className="aside">Use the timeline to scrub from −5 s to +3 s, or press play.</p>
            </Chapter>

            <Chapter index={3}>
              <p className="step">02 · What the model sees</p>
              <h2>
                <code>future_ball</code>: told where the ball goes
              </h2>
              <p>
                The model also receives the ball's <span className="ink-future">realized path over the next 3 seconds</span>. That path only exists after the fact, so this is a <strong>conditional prediction, not a deployable forecast</strong>.
              </p>
            </Chapter>

            <Chapter index={4}>
              <p className="step">02 · What the model sees</p>
              <h2>
                <code>future_opponent_plus_ball</code>: told what everyone else does
              </h2>
              <p>
                Now the opponents' <span className="ink-future">realized future paths</span> are inputs too. Only the target team's future is withheld: it is what gets scored (dashed), and it is <strong>never an input in any regime</strong>.
              </p>
              <p className="aside">Lower error here measures how much easier the task becomes with hindsight. It is not forecasting skill.</p>
            </Chapter>

            <Chapter index={5}>
              <p className="step">03 · How the answer is written</p>
              <h2>Absolute XY: where on the pitch?</h2>
              <p>
                One way to ask for the future is in <span className="ink-abs">absolute pitch coordinates</span>, measured from the centre spot. Targets span the whole field, ±52.5 m by ±34 m.
              </p>
            </Chapter>

            <Chapter index={6}>
              <p className="step">03 · How the answer is written</p>
              <h2>Displacement: how far from here?</h2>
              <p>
                The other asks for <span className="ink-disp">origin-relative displacement</span>: how far each player moves from their own position at t = 0. Same physical trajectory, different target encoding.
              </p>
              <p>
                Both are converted back to pitch coordinates and scored in <strong>metres</strong>, so their errors are directly comparable.
              </p>
            </Chapter>
          </div>
        </div>

        <section className="section" id="design" aria-labelledby="design-title">
          <div className="section__head">
            <p className="step">04 · The experiment</p>
            <h2 id="design-title">Twenty matches, four that count</h2>
            <p className="section__lede">
              Matches, not windows, are the unit of evidence. Every window inherits exactly one role from its match, and the four evaluation matches never touch fitting or checkpoint selection.
            </p>
          </div>
          <div className="design">
            <div className="design__roles" role="list" aria-label="Match roles">
              {[
                { n: 12, label: "Training", sub: "fit the models", cls: "train" },
                { n: 4, label: "Validation", sub: "select checkpoints", cls: "val" },
                { n: 4, label: "Evaluation", sub: "held out, scored once", cls: "eval" },
              ].map((g) => (
                <div className={`role role--${g.cls}`} key={g.cls} role="listitem">
                  <div className="role__tiles" aria-hidden="true">
                    {Array.from({ length: g.n }, (_, i) => (
                      <span key={i} />
                    ))}
                  </div>
                  <p>
                    <strong>
                      {g.n} {g.label.toLowerCase()} matches
                    </strong>
                    <span>{g.sub}</span>
                  </p>
                </div>
              ))}
            </div>
            <ol className="design__flow">
              <li>
                <span className="num">18</span>
                <p>
                  <strong>frozen checkpoints</strong>3 information regimes × 2 target encodings × 3 seeds, one model class (DeepSets), selected on validation ADE. No new fits.
                </p>
              </li>
              <li>
                <span className="num">× 4</span>
                <p>
                  <strong>held-out matches</strong>
                  = {records} match-scoped records, each scoring every eligible window of one match.
                </p>
              </li>
              <li>
                <span className="num">{fmtInt(windows)}</span>
                <p>
                  <strong>overlapping windows ≠ {fmtInt(windows)} independent observations</strong>
                  Windows overlap in time and share players. Seeds are not extra matches either. The independent unit is the match: <b>n = {independentUnits}</b>.
                </p>
              </li>
            </ol>
            <div className="design__agg">
              <h3>How a number is made</h3>
              <ol>
                <li>Score each directed scene (ADE, FDE at 3 s, XY RMSE in metres)</li>
                <li>Average scenes within window, then windows within match</li>
                <li>Average the three seeds within match</li>
                <li>Average the four matches equally</li>
              </ol>
              <p>
                Window counts per match ({fmtInt(totals.windows)} in total) do not set the weights. Canonical schematic:{" "}
                <a href={`${LINKS.repo}/blob/main/docs/paper-a/evaluation-design.svg`}>Paper A evaluation design</a> ·{" "}
                <a href={`${LINKS.repo}/blob/main/docs/paper-a/information-boundary.svg`}>information boundary</a>.
              </p>
            </div>
          </div>
        </section>

        <section className="section" id="results" aria-labelledby="results-title">
          <div className="section__head">
            <p className="step">05 · Measured outcomes</p>
            <h2 id="results-title">What the four held-out matches showed</h2>
            <p className="section__lede">
              Every number below is read directly from the published aggregate results file at build time. Read history-only rows as forecasts; read amber-marked rows as conditional tasks.
            </p>
          </div>
          <div className="findings">
            <article>
              <h3>Displacement beat absolute XY everywhere</h3>
              <p>
                Lower ADE, FDE and XY RMSE in all three regimes, in every match after seed averaging. History-only: {fmt(headline.absAde)} m → {fmt(headline.dispAde)} m ADE.
              </p>
            </article>
            <article>
              <h3>Learned history-only models beat simple physics</h3>
              <p>
                Against 1-second constant velocity ({fmt(headline.cvAde)} m ADE): displacement {fmt(headline.reduction)} m lower ({fmtPct(headline.percent)}), absolute XY {fmt(cvAbs.diff)} m lower ({fmtPct(cvAbs.percent)}). FDE fell {fmt(cvDispFde.diff)} m for displacement. The learned models also see wider context than these target-only baselines: a system comparison, not an isolated architecture effect.
              </p>
            </article>
            <article className="findings__future">
              <h3>Hindsight lowers error, as expected</h3>
              <p>
                Realized future ball: −{fmt(c1abs.mean)} m (absolute) / −{fmt(c1disp.mean)} m (displacement) ADE. Adding realized opponents: a further −{fmt(c2abs.mean)} / −{fmt(c2disp.mean)} m. Positive in all four matches. Conditional, not deployable skill.
              </p>
            </article>
          </div>
          <Results />
        </section>

        <section className="section" id="limits" aria-labelledby="limits-title">
          <div className="section__head">
            <p className="step">06 · Read this before quoting a number</p>
            <h2 id="limits-title">What this does and does not prove</h2>
            <p className="section__lede">
              Status: <code>{classification}</code>. These are descriptive findings about these fitted systems on these four matches.
            </p>
          </div>
          <div className="limits">
            <div>
              <h3>Supported, descriptively</h3>
              <ul>
                <li>On these four matches, displacement targets had lower physical error than absolute XY targets for these fitted models in every regime.</li>
                <li>History-only learned models had lower error than the comparable constant-velocity and persistence references in every match.</li>
                <li>Supplying realized future ball, then opponent, trajectories was associated with lower overall error.</li>
              </ul>
            </div>
            <div>
              <h3>Not established</h3>
              <ul>
                <li>
                  <strong>No inference beyond n = {independentUnits}.</strong> No significance tests, confidence intervals, or generalization to other matches, leagues, seasons, teams or providers.
                </li>
                <li>
                  <strong>No deployable forecast from conditional regimes.</strong> They use information unavailable at t = 0; their gains are not forecasting skill or causal effects.
                </li>
                <li>
                  <strong>No causal mechanism.</strong> The displacement gap describes separately fitted, validation-selected checkpoints, not an intrinsic property of the encoding.
                </li>
                <li>
                  <strong>Not uniform.</strong> Added context did not help every interval: absolute-XY early ADE was {fmt(earlyFopb)} m with opponents plus ball versus {fmt(earlyFb)} m with ball only.
                </li>
                <li>
                  <strong>No tactical understanding or operational readiness.</strong> The lowest-error combination still had {fmt(bestFde)} m FDE at 3 s.
                </li>
                <li>
                  <strong>Targets are not independent ground truth.</strong> {fmtInt(totals.extrapolated)} of {fmtInt(totals.points)} scored player-time points ({pct(totals.extrapolated, totals.points)}) were provider-extrapolated; only {fmtInt(totals.detectedOnly)} of {fmtInt(totals.scenes)} directed scenes were detected-only.
                </li>
                <li>
                  <strong>Incomplete design.</strong> The original 234-fit plan was not completed and the 216 training leave-one-match-out fits were not executed. The study followed a separately authorized post-failure descriptive route after an interrupted first scoring attempt, so it is not an untouched confirmatory evaluation.
                </li>
              </ul>
            </div>
          </div>
        </section>

        <section className="section" id="research" aria-labelledby="research-title">
          <div className="section__head">
            <p className="step">07 · Go deeper</p>
            <h2 id="research-title">Read the full research</h2>
          </div>
          <ul className="links">
            {[
              { href: LINKS.paperPdf, t: "Paper A manuscript", d: "Information-boundary-aware evaluation of multi-agent football motion (PDF)" },
              { href: LINKS.results, t: "Scientific results", d: "Complete four-match report, figures and interpretation" },
              { href: LINKS.findings, t: "Machine-readable findings", d: "The aggregate JSON this site is built from, with provenance hashes" },
              { href: LINKS.evidence, t: "Paper A evidence package", d: "Task matrix, schematics and traceability" },
              { href: LINKS.reproducibility, t: "Reproducibility notes", d: "Deterministic locks, provenance and how to re-run checks" },
              { href: LINKS.rights, t: "Data rights & attribution", d: "SkillCorner Open Data rights audit and publication policy" },
              { href: LINKS.repo, t: "GitHub repository", d: "Benchmark code, contracts and documentation (Apache-2.0)" },
            ].map((l) => (
              <li key={l.href}>
                <a href={l.href}>
                  <strong>{l.t}</strong>
                  <span>{l.d}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      </main>
      <footer className="footer">
        <p>
          A non-archival research communication companion to Paper A of Football Performance Dynamics Bench. It is not a new publication and adds no analysis: measured values come from the public aggregate results; pitch motion is a schematic illustration.
        </p>
        <p>
          Source data: <a href={LINKS.skillcorner}>SkillCorner Open Data</a>, acknowledged with thanks to SkillCorner and PySport. No source rows, player identities, predictions, checkpoints or private receipts are published here. Execution commit <code>{provenance.execution_commit.slice(0, 12)}</code>.
        </p>
      </footer>
    </>
  );
}
