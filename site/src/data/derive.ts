// Turns (regime, scrub time) into what should be drawn. Shared by the 3D scene
// and the SVG fallback, so both always teach exactly the same boundary.
import { BALL, FUTURE_S, HISTORY_S, PLAYERS, futureVisible, positionAt, samplesBetween } from "./scene";
import type { Regime, Track, Vec2 } from "./scene";

export type TokenState = "live" | "future-input" | "frozen";

export interface DrawnTrack {
  track: Track;
  position: Vec2;
  state: TokenState;
  history: Vec2[];
  future: Vec2[]; // realized future context supplied as an input (accent colour)
  withheld: Vec2[]; // target-team future: scored, never an input
}

export function deriveFrame(regime: Regime, tau: number, showTarget: boolean): DrawnTrack[] {
  return [...PLAYERS, BALL].map((track) => {
    const visible = futureVisible(track.team, regime);
    const history = samplesBetween(track, -HISTORY_S, Math.min(tau, 0));
    let state: TokenState = "live";
    let position = positionAt(track, tau);
    let future: Vec2[] = [];
    if (tau > 0) {
      if (visible) {
        state = "future-input";
        future = samplesBetween(track, 0, tau);
      } else {
        state = "frozen";
        position = positionAt(track, 0);
      }
    }
    const withheld = track.team === "target" && showTarget && tau > 0 ? samplesBetween(track, 0, FUTURE_S) : [];
    return { track, position, state, history, future, withheld };
  });
}

export const REGIME_EXPLAINER: Record<Regime, { badge: string; conditional: boolean; text: string }> = {
  history_only: {
    badge: "Ex-ante forecast",
    conditional: false,
    text: "Only what had happened by t = 0. After the origin the model knows nothing new: opponents and ball stay where they were last seen.",
  },
  future_ball: {
    badge: "Conditional · not a deployable forecast",
    conditional: true,
    text: "History plus the ball's realized path over the next 3 s — information that only exists after the fact.",
  },
  future_opponent_plus_ball: {
    badge: "Conditional · not a deployable forecast",
    conditional: true,
    text: "History plus the realized future paths of the ball and every opponent. Only the target team's future is withheld.",
  },
};

export function clockLabel(tau: number): string {
  if (Math.abs(tau) < 0.05) return "t = 0.0 s";
  return `t ${tau < 0 ? "−" : "+"} ${Math.abs(tau).toFixed(1)} s`;
}

export function phaseLabel(tau: number): string {
  if (tau < -0.05) return "Observed history";
  if (tau <= 0.05) return "Forecast origin";
  return "Forecast horizon";
}
