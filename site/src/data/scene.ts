// A hand-authored, deterministic SCHEMATIC football scene.
//
// Nothing here is tracking data, a reconstruction of a real sequence, or a model
// prediction. The paths only illustrate the study's time grid: 25 history
// intervals plus the origin (5 s) and 15 future steps (3 s) at 0.2 s.

export type Team = "target" | "opponent" | "ball";
export type Vec2 = [number, number];

export interface Track {
  id: string;
  team: Team;
  role: string;
  points: Vec2[]; // one per TIMES entry, pitch-centred metres (x: length, y: width)
}

export const PITCH = { length: 105, width: 68 };
export const DT = 0.2;
export const HISTORY_S = 5;
export const FUTURE_S = 3;
export const TIMES: number[] = Array.from({ length: 41 }, (_, k) => Math.round((-HISTORY_S + k * DT) * 10) / 10);
export const ORIGIN_INDEX = 25;

const smooth = (a: number, b: number, t: number) => {
  const u = Math.min(1, Math.max(0, (t - a) / (b - a)));
  return u * u * (3 - 2 * u);
};

// Small deterministic pseudo-random generator so every visitor sees the same schematic.
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

// The attack drifts toward the right flank (negative y) as the move develops.
const focusY = (t: number) => -6 - 14 * smooth(-5, 3, t);
const attackShift = (t: number) => 9 * smooth(-5, 3, t);

interface Spec {
  id: string;
  role: string;
  base: Vec2;
  run?: { from: number; to: number; delta: Vec2 };
}

const TARGET: Spec[] = [
  { id: "t-gk", role: "Goalkeeper", base: [-47, 0] },
  { id: "t-rb", role: "Right back", base: [-18, -25], run: { from: -1, to: 3, delta: [14, -3] } },
  { id: "t-rcb", role: "Centre back", base: [-27, -9] },
  { id: "t-lcb", role: "Centre back", base: [-27, 9] },
  { id: "t-lb", role: "Left back", base: [-19, 24] },
  { id: "t-cm", role: "Holding midfielder", base: [-13, -2] },
  { id: "t-rcm", role: "Midfielder", base: [-5, -12], run: { from: -2.5, to: 0.5, delta: [8, -3] } },
  { id: "t-lcm", role: "Midfielder", base: [-4, 11] },
  { id: "t-rw", role: "Right winger", base: [12, -25], run: { from: -0.5, to: 2.6, delta: [10, 2] } },
  { id: "t-st", role: "Striker", base: [17, -2], run: { from: -0.4, to: 3, delta: [11, -7] } },
  { id: "t-lw", role: "Left winger", base: [13, 24], run: { from: 0, to: 3, delta: [6, -9] } },
];

const OPPONENT: Spec[] = [
  { id: "o-gk", role: "Goalkeeper", base: [48, 0] },
  { id: "o-lb", role: "Full back", base: [31, -21], run: { from: 0.3, to: 3, delta: [-2, -5] } },
  { id: "o-lcb", role: "Centre back", base: [33, -7], run: { from: 0, to: 3, delta: [-1, -6] } },
  { id: "o-rcb", role: "Centre back", base: [33, 7] },
  { id: "o-rb", role: "Full back", base: [31, 21] },
  { id: "o-lm", role: "Wide midfielder", base: [19, -22], run: { from: -1, to: 2, delta: [-6, -2] } },
  { id: "o-lcm", role: "Central midfielder", base: [21, -7] },
  { id: "o-rcm", role: "Central midfielder", base: [21, 7] },
  { id: "o-rm", role: "Wide midfielder", base: [19, 22] },
  { id: "o-ls", role: "Forward", base: [5, -6], run: { from: -3, to: 0, delta: [-6, -2] } },
  { id: "o-rs", role: "Forward", base: [5, 7] },
];

function playerTrack(spec: Spec, team: "target" | "opponent", seed: number): Track {
  const r = rng(seed);
  const phase = [r() * 6.28, r() * 6.28, r() * 6.28, r() * 6.28];
  const amp = spec.role === "Goalkeeper" ? 0.4 : 1.3;
  const isGk = spec.role === "Goalkeeper";
  const points = TIMES.map((t): Vec2 => {
    const shift = team === "target" ? attackShift(t) : 0.55 * attackShift(t);
    const lateral = (isGk ? 0.12 : team === "target" ? 0.28 : 0.38) * focusY(t);
    let x = spec.base[0] + (isGk ? shift * 0.2 : shift);
    let y = spec.base[1] + lateral;
    if (spec.run) {
      const s = smooth(spec.run.from, spec.run.to, t);
      x += spec.run.delta[0] * s;
      y += spec.run.delta[1] * s;
    }
    x += amp * Math.sin(0.55 * t + phase[0]) + 0.5 * amp * Math.sin(1.3 * t + phase[1]);
    y += amp * Math.sin(0.45 * t + phase[2]) + 0.5 * amp * Math.sin(1.1 * t + phase[3]);
    return [x, y];
  });
  return { id: spec.id, team, role: spec.role, points };
}

export const PLAYERS: Track[] = [
  ...TARGET.map((s, i) => playerTrack(s, "target", 101 + i * 17)),
  ...OPPONENT.map((s, i) => playerTrack(s, "opponent", 907 + i * 23)),
];

const byId = (id: string) => {
  const t = PLAYERS.find((p) => p.id === id);
  if (!t) throw new Error(id);
  return t;
};

export function positionAt(track: Track, t: number): Vec2 {
  const f = (t - TIMES[0]) / DT;
  const i = Math.max(0, Math.min(TIMES.length - 2, Math.floor(f)));
  const u = Math.max(0, Math.min(1, f - i));
  const a = track.points[i];
  const b = track.points[i + 1];
  return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
}

// Ball: carried by a holder, or travelling between two players during a pass.
type Phase = { kind: "hold"; who: string; from: number; to: number } | { kind: "pass"; a: string; b: string; from: number; to: number };
const BALL_PLAN: Phase[] = [
  { kind: "hold", who: "t-rcb", from: -5, to: -3.8 },
  { kind: "pass", a: "t-rcb", b: "t-cm", from: -3.8, to: -3.0 },
  { kind: "hold", who: "t-cm", from: -3.0, to: -2.2 },
  { kind: "pass", a: "t-cm", b: "t-rcm", from: -2.2, to: -1.4 },
  { kind: "hold", who: "t-rcm", from: -1.4, to: 0.4 },
  { kind: "pass", a: "t-rcm", b: "t-rw", from: 0.4, to: 1.4 },
  { kind: "hold", who: "t-rw", from: 1.4, to: 2.2 },
  { kind: "pass", a: "t-rw", b: "t-st", from: 2.2, to: 3.4 },
];

function ballAt(t: number): Vec2 {
  const phase = BALL_PLAN.find((p) => t >= p.from && t <= p.to) ?? BALL_PLAN[BALL_PLAN.length - 1];
  if (phase.kind === "hold") {
    const [x, y] = positionAt(byId(phase.who), t);
    return [x + 0.9, y - 0.4];
  }
  const start = positionAt(byId(phase.a), phase.from);
  const end = positionAt(byId(phase.b), Math.min(phase.to, 3));
  const u = (t - phase.from) / (phase.to - phase.from);
  return [start[0] + (end[0] - start[0]) * u, start[1] + (end[1] - start[1]) * u];
}

export const BALL: Track = { id: "ball", team: "ball", role: "Ball", points: TIMES.map(ballAt) };

/** The target-team player used to explain absolute vs. displacement targets. */
export const FOCUS_ID = "t-st";
export const FOCUS = byId(FOCUS_ID);

export type Regime = "history_only" | "future_ball" | "future_opponent_plus_ball";

/** Is this track's information available to the model after the origin? */
export function futureVisible(team: Team, regime: Regime): boolean {
  if (team === "target") return false; // never an input
  if (team === "ball") return regime !== "history_only";
  return regime === "future_opponent_plus_ball";
}

export function samplesBetween(track: Track, t0: number, t1: number): Vec2[] {
  if (t1 <= t0) return [];
  const out: Vec2[] = [positionAt(track, t0)];
  for (let k = 0; k < TIMES.length; k++) {
    if (TIMES[k] > t0 + 1e-6 && TIMES[k] < t1 - 1e-6) out.push(track.points[k]);
  }
  out.push(positionAt(track, t1));
  return out;
}
