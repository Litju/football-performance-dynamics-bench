import type { Regime, Representation } from "./data/findings";

export type ViewName = "broadcast" | "tactical" | "focus" | "hero";
export type Hud = "none" | "timeline" | "encoding";

export interface StoryState {
  chapter: number;
  regime: Regime;
  tau: number; // seconds relative to the forecast origin, −5 … 3
  representation: Representation;
  showTarget: boolean;
  viewOverride: "broadcast" | "tactical" | null;
  resetNonce: number;
}

export interface ChapterPreset {
  id: string;
  view: ViewName;
  hud: Hud;
  regime?: Regime;
  tau?: number;
  representation?: Representation;
  showTarget?: boolean;
}

export const CHAPTERS: ChapterPreset[] = [
  { id: "question", view: "hero", hud: "none", regime: "history_only", tau: 0, showTarget: false },
  { id: "origin", view: "broadcast", hud: "timeline", regime: "history_only", tau: 0, showTarget: false },
  { id: "history_only", view: "tactical", hud: "timeline", regime: "history_only", tau: 3, showTarget: false },
  { id: "future_ball", view: "tactical", hud: "timeline", regime: "future_ball", tau: 3, showTarget: false },
  { id: "future_opponent_plus_ball", view: "tactical", hud: "timeline", regime: "future_opponent_plus_ball", tau: 3, showTarget: true },
  { id: "absolute", view: "focus", hud: "encoding", tau: 3, representation: "absolute_xy" },
  { id: "displacement", view: "focus", hud: "encoding", tau: 3, representation: "origin_relative_displacement" },
];

export const initialState: StoryState = {
  chapter: 0,
  regime: "history_only",
  tau: 0,
  representation: "absolute_xy",
  showTarget: false,
  viewOverride: null,
  resetNonce: 0,
};

export function applyChapter(state: StoryState, chapter: number): StoryState {
  const p = CHAPTERS[chapter];
  return {
    ...state,
    chapter,
    regime: p.regime ?? state.regime,
    tau: p.tau ?? state.tau,
    representation: p.representation ?? state.representation,
    showTarget: p.showTarget ?? state.showTarget,
    viewOverride: null,
  };
}

export function effectiveView(state: StoryState): ViewName {
  return state.viewOverride ?? CHAPTERS[state.chapter].view;
}
