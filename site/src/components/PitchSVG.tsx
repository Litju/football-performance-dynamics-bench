// Static top-down fallback for devices without WebGL or visitors who prefer
// reduced motion. It renders the same derived frame as the 3D scene.
import { deriveFrame } from "../data/derive";
import { FOCUS, PITCH, positionAt, samplesBetween } from "../data/scene";
import type { Vec2 } from "../data/scene";
import type { StoryState } from "../story";
import { COLORS } from "../three/colors";

const L = PITCH.length / 2;
const W = PITCH.width / 2;
const p = (v: Vec2) => `${v[0].toFixed(2)},${(-v[1]).toFixed(2)}`;
const path = (pts: Vec2[]) => (pts.length < 2 ? "" : `M${pts.map(p).join("L")}`);

export default function PitchSVG({ state }: { state: StoryState }) {
  const encoding = state.chapter >= 5;
  const frame = encoding ? deriveFrame("history_only", 0, false) : deriveFrame(state.regime, state.tau, state.showTarget);
  const o = positionAt(FOCUS, 0);
  const f = positionAt(FOCUS, 3);
  const isAbs = state.representation === "absolute_xy";
  const arc = Math.acos((16.5 - 11) / 9.15);
  return (
    <svg className="pitch-svg" viewBox={`${-L - 4} ${-W - 4} ${PITCH.length + 8} ${PITCH.width + 8}`} role="img" aria-label="Schematic top-down pitch; see the text panel for a description">
      <defs>
        <pattern id="stripes" width={PITCH.length / 7} height="10" patternUnits="userSpaceOnUse" x={-L}>
          <rect width={PITCH.length / 14} height="10" fill={COLORS.grassA} />
          <rect x={PITCH.length / 14} width={PITCH.length / 14} height="10" fill={COLORS.grassB} />
        </pattern>
        <marker id="arrow-abs" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
          <path d="M0,0L10,5L0,10z" fill={COLORS.absolute} />
        </marker>
        <marker id="arrow-disp" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
          <path d="M0,0L10,5L0,10z" fill={COLORS.displacement} />
        </marker>
      </defs>
      <rect x={-L - 4} y={-W - 4} width={PITCH.length + 8} height={PITCH.width + 8} fill={COLORS.runoff} />
      <rect x={-L} y={-W} width={PITCH.length} height={PITCH.width} fill="url(#stripes)" />
      <g fill="none" stroke={COLORS.line} strokeWidth="0.18" opacity="0.85">
        <rect x={-L} y={-W} width={PITCH.length} height={PITCH.width} />
        <line x1="0" y1={-W} x2="0" y2={W} />
        <circle r="9.15" />
        {[-1, 1].map((s) => (
          <g key={s}>
            <rect x={s > 0 ? L - 16.5 : -L} y={-20.16} width="16.5" height="40.32" />
            <rect x={s > 0 ? L - 5.5 : -L} y={-9.16} width="5.5" height="18.32" />
            <path
              d={`M${s * (L - 16.5)},${-9.15 * Math.sin(arc)} A9.15,9.15 0 0 ${s > 0 ? 0 : 1} ${s * (L - 16.5)},${9.15 * Math.sin(arc)}`}
            />
          </g>
        ))}
      </g>
      {frame.map((d) => (
        <g key={d.track.id}>
          <path
            d={path(d.history)}
            fill="none"
            stroke={d.track.team === "opponent" ? COLORS.historyOpp : COLORS.history}
            strokeWidth={d.track.team === "ball" ? 0.4 : 0.3}
            opacity={encoding ? 0.25 : 0.65}
          />
          <path d={path(d.future)} fill="none" stroke={COLORS.future} strokeWidth="0.55" />
          <path d={path(d.withheld)} fill="none" stroke={COLORS.target} strokeWidth="0.3" strokeDasharray="0.9 0.7" opacity="0.75" />
        </g>
      ))}
      {frame.map((d) => {
        const [x, y] = d.position;
        const op = d.state === "frozen" ? 0.32 : 1;
        if (d.track.team === "ball")
          return (
            <g key={d.track.id} opacity={op}>
              {d.state === "future-input" && <circle cx={x} cy={-y} r="1.45" fill="none" stroke={COLORS.future} strokeWidth="0.3" />}
              <circle cx={x} cy={-y} r="0.75" fill="#fff" />
            </g>
          );
        const target = d.track.team === "target";
        return (
          <g key={d.track.id} opacity={op}>
            {d.state === "future-input" && <circle cx={x} cy={-y} r="1.6" fill="none" stroke={COLORS.future} strokeWidth="0.3" />}
            <circle cx={x} cy={-y} r="1.05" fill={target ? COLORS.target : COLORS.opponent} stroke={target ? "none" : COLORS.opponentRim} strokeWidth="0.3" />
            {encoding && d.track.id === FOCUS.id && <circle cx={x} cy={-y} r="2" fill="none" stroke={COLORS.target} strokeWidth="0.25" />}
          </g>
        );
      })}
      {encoding && (
        <g>
          <path d="M-6,0H6M0,-6V6" stroke={COLORS.line} strokeWidth="0.2" />
          <path d={path(samplesBetween(FOCUS, 0, 3))} fill="none" stroke={COLORS.target} strokeWidth="0.3" strokeDasharray="0.9 0.7" />
          <line x1="0" y1="0" x2={f[0]} y2={-f[1]} stroke={COLORS.absolute} strokeWidth={isAbs ? 0.6 : 0.3} opacity={isAbs ? 1 : 0.3} markerEnd="url(#arrow-abs)" />
          <line x1={o[0]} y1={-o[1]} x2={f[0]} y2={-f[1]} stroke={COLORS.displacement} strokeWidth={isAbs ? 0.3 : 0.6} opacity={isAbs ? 0.3 : 1} markerEnd="url(#arrow-disp)" />
          <circle cx={f[0]} cy={-f[1]} r="1.1" fill="none" stroke={COLORS.target} strokeWidth="0.25" />
        </g>
      )}
    </svg>
  );
}
