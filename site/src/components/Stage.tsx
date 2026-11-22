import { Suspense, lazy, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { REGIMES, REGIME_SHORT, REPRESENTATION_LABEL } from "../data/findings";
import type { Regime, Representation } from "../data/findings";
import { REGIME_EXPLAINER, clockLabel, phaseLabel } from "../data/derive";
import { FUTURE_S, HISTORY_S } from "../data/scene";
import { CHAPTERS, effectiveView } from "../story";
import type { StoryState } from "../story";
import type { CameraOffsets } from "../three/PitchScene";
import PitchSVG from "./PitchSVG";

const PitchScene = lazy(() => import("../three/PitchScene"));

function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return reduced;
}

function useViewport() {
  const [vp, setVp] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }));
  useEffect(() => {
    const on = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return vp;
}

function useHeight(el: HTMLElement | null) {
  const [h, setH] = useState(0);
  useEffect(() => {
    if (!el) return setH(0);
    const ro = new ResizeObserver(([e]) => setH(Math.round(e.borderBoxSize?.[0]?.blockSize ?? e.contentRect.height)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return h;
}

interface Props {
  state: StoryState;
  setState: Dispatch<SetStateAction<StoryState>>;
}

export default function Stage({ state, setState }: Props) {
  const reduced = usePrefersReducedMotion();
  const [hasGL] = useState(webglAvailable);
  const [mode, setMode] = useState<"3d" | "2d">(() => (webglAvailable() && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "3d" : "2d"));
  const offsets = useRef<CameraOffsets>({ az: 0, pol: 0 });
  const invalidate = useRef<() => void>(() => {});
  const drag = useRef<{ x: number; y: number; id: number } | null>(null);
  const vp = useViewport();
  const [hudEl, setHudEl] = useState<HTMLDivElement | null>(null);
  const hudH = useHeight(hudEl);
  const [playing, setPlaying] = useState(false);
  const hud = CHAPTERS[state.chapter].hud;
  const view = effectiveView(state);
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  const wide = vp.w >= 1000;
  const insets = {
    left: wide ? Math.min(520, vp.w * 0.36) : 0,
    top: wide ? 96 : 92,
    bottom: hud === "none" ? (wide ? 40 : 12) : hudH + (wide ? 24 : 10),
  };

  // A chapter change or "Reset view" eases any manual orbit back to the directed shot.
  useEffect(() => {
    offsets.current = { az: 0, pol: 0 };
    invalidate.current();
  }, [state.chapter, state.resetNonce]);

  useEffect(() => setPlaying(false), [state.chapter]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      let done = false;
      setState((s) => {
        const next = Math.min(FUTURE_S, s.tau + dt);
        if (next >= FUTURE_S) done = true;
        return { ...s, tau: next };
      });
      if (done) setPlaying(false);
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, setState]);

  const nudge = (az: number, pol: number) => {
    const o = offsets.current;
    o.az = Math.max(-0.95, Math.min(0.95, o.az + az));
    o.pol = Math.max(-0.6, Math.min(0.4, o.pol + pol));
    invalidate.current();
  };

  const onKey = (e: React.KeyboardEvent) => {
    const step = 0.08;
    if (e.key === "ArrowLeft") nudge(-step, 0);
    else if (e.key === "ArrowRight") nudge(step, 0);
    else if (e.key === "ArrowUp") nudge(0, -step);
    else if (e.key === "ArrowDown") nudge(0, step);
    else if (e.key === "r" || e.key === "R") setState((s) => ({ ...s, resetNonce: s.resetNonce + 1 }));
    else return;
    e.preventDefault();
  };

  const setRegime = (regime: Regime) => setState((s) => ({ ...s, regime, tau: s.tau <= 0 ? FUTURE_S : s.tau }));
  const setRep = (representation: Representation) => setState((s) => ({ ...s, representation }));
  const setTau = (tau: number) => {
    setPlaying(false);
    setState((s) => ({ ...s, tau }));
  };
  const explainer = REGIME_EXPLAINER[state.regime];

  return (
    <>
      <div className="overlay" data-hud={hud}>
        <div className="overlay__inner">
      <div className="stage__badge" aria-hidden="true">
        <span className="long">Schematic illustration · not tracking data or model output</span>
        <span className="short">Schematic · not tracking data</span>
      </div>

      <div className="stage__tools" role="toolbar" aria-label="Pitch view">
        {mode === "3d" && (
          <>
            <div className="seg seg--small" role="radiogroup" aria-label="Camera">
              {(["broadcast", "tactical"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  role="radio"
                  aria-checked={view === v}
                  className={view === v ? "is-on" : ""}
                  onClick={() => setState((s) => ({ ...s, viewOverride: v }))}
                >
                  {v === "broadcast" ? "Broadcast" : "Tactical"}
                </button>
              ))}
            </div>
            <button type="button" className="tool" onClick={() => setState((s) => ({ ...s, resetNonce: s.resetNonce + 1, viewOverride: null }))}>
              Reset view
            </button>
          </>
        )}
        {hasGL && (
          <button type="button" className="tool" onClick={() => setMode((m) => (m === "3d" ? "2d" : "3d"))} aria-pressed={mode === "2d"}>
            {mode === "3d" ? "2D view" : "3D view"}
          </button>
        )}
      </div>

      {mode === "3d" && state.chapter === 0 && (
        <p className="stage__hint" aria-hidden="true">
          <span className="hint-icon" /> {coarse ? "Swipe sideways to orbit" : "Drag to look around"}
        </p>
      )}

      {hud === "timeline" && (
        <div className="hud" aria-label="Information boundary controls" role="region" ref={setHudEl}>
          <div className="hud__row hud__row--top">
            <div className="seg" role="radiogroup" aria-label="Information available to the model">
              {REGIMES.map((r) => (
                <button
                  key={r}
                  type="button"
                  role="radio"
                  aria-checked={state.regime === r}
                  className={state.regime === r ? "is-on" : ""}
                  onClick={() => setRegime(r)}
                >
                  <code>{r}</code>
                  <span>{REGIME_SHORT[r]}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="hud__row hud__explain" aria-live="polite">
            <span className={`pill ${explainer.conditional ? "pill--future" : "pill--forecast"}`}>{explainer.badge}</span>
            <span className="hud__text">{explainer.text}</span>
          </div>
          <div className="hud__row hud__timeline">
            <button
              type="button"
              className="play"
              onClick={() => {
                if (playing) return setPlaying(false);
                if (state.tau >= FUTURE_S - 0.01) setState((s) => ({ ...s, tau: -HISTORY_S }));
                setPlaying(true);
              }}
              aria-label={playing ? "Pause timeline" : "Play timeline from −5 s to +3 s"}
            >
              {playing ? "❚❚" : "▶"}
            </button>
            <div className="scrub">
              <div className="scrub__track" aria-hidden="true">
                <span className="scrub__hist" />
                <span className="scrub__fut" data-future={state.regime !== "history_only"} />
                <span className="scrub__origin" />
              </div>
              <input
                type="range"
                min={-HISTORY_S}
                max={FUTURE_S}
                step={0.2}
                value={state.tau}
                onChange={(e) => setTau(Number(e.target.value))}
                aria-label="Time relative to the forecast origin"
                aria-valuetext={`${clockLabel(state.tau)}, ${phaseLabel(state.tau)}`}
              />
              <div className="scrub__ticks" aria-hidden="true">
                <span>−5 s</span>
                <span className="o">t = 0</span>
                <span>+3 s</span>
              </div>
            </div>
            <div className="clock" aria-hidden="true">
              <strong>{clockLabel(state.tau)}</strong>
              <span>{phaseLabel(state.tau)}</span>
            </div>
          </div>
          <div className="hud__row hud__legend">
            <Legend />
            <label className="check">
              <input type="checkbox" checked={state.showTarget} onChange={(e) => setState((s) => ({ ...s, showTarget: e.target.checked, tau: e.target.checked && s.tau <= 0 ? FUTURE_S : s.tau }))} />
              Show scored target path
            </label>
          </div>
        </div>
      )}

      {hud === "encoding" && (
        <div className="hud hud--compact" role="region" aria-label="Target encoding" ref={setHudEl}>
          <div className="seg" role="radiogroup" aria-label="Target encoding">
            {(["absolute_xy", "origin_relative_displacement"] as const).map((r) => (
              <button key={r} type="button" role="radio" aria-checked={state.representation === r} className={state.representation === r ? "is-on" : ""} onClick={() => setRep(r)}>
                <i className={`swatch swatch--${r === "absolute_xy" ? "abs" : "disp"}`} />
                <span>{REPRESENTATION_LABEL[r]}</span>
              </button>
            ))}
          </div>
          <p className="hud__text">
            {state.representation === "absolute_xy"
              ? "Target = where the player is, measured from the centre spot."
              : "Target = how far the player moved from their own t = 0 position."}
          </p>
        </div>
      )}
        </div>
      </div>
      <div className="story__stage" data-mode={mode}>
      <div
        className="stage__viewport"
        tabIndex={mode === "3d" ? 0 : -1}
        role={mode === "3d" ? "group" : undefined}
        aria-label={mode === "3d" ? "3D pitch. Use arrow keys to orbit, R to reset the view." : undefined}
        onKeyDown={mode === "3d" ? onKey : undefined}
        onPointerDown={(e) => {
          if (mode !== "3d" || e.button !== 0) return;
          drag.current = { x: e.clientX, y: e.clientY, id: e.pointerId };
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d || d.id !== e.pointerId) return;
          const dx = e.clientX - d.x;
          const dy = e.clientY - d.y;
          drag.current = { ...d, x: e.clientX, y: e.clientY };
          nudge(dx * 0.0045, e.pointerType === "touch" ? 0 : -dy * 0.0035);
        }}
        onPointerUp={() => (drag.current = null)}
        onPointerCancel={() => (drag.current = null)}
        onPointerLeave={() => (drag.current = null)}
      >
        {mode === "3d" ? (
          <Suspense fallback={<div className="stage__loading">Preparing pitch…</div>}>
            <PitchScene state={state} offsets={offsets} reducedMotion={reduced} insets={insets} invalidateRef={invalidate} />
          </Suspense>
        ) : (
          <div className="stage__svg" style={{ paddingTop: insets.top, paddingBottom: insets.bottom, paddingLeft: insets.left + (wide ? 32 : 8), paddingRight: wide ? 32 : 8 }}>
            <PitchSVG state={state} />
          </div>
        )}
      </div>

      </div>
    </>
  );
}

export function Legend() {
  return (
    <ul className="legend" aria-label="Legend">
      <li>
        <i className="key key--target" /> Target team
      </li>
      <li>
        <i className="key key--opp" /> Opponents
      </li>
      <li>
        <i className="key key--ball" /> Ball
      </li>
      <li>
        <i className="key key--hist" /> Observed history
      </li>
      <li>
        <i className="key key--future" /> Realized future input
      </li>
      <li>
        <i className="key key--withheld" /> Withheld target (scored, never input)
      </li>
    </ul>
  );
}
