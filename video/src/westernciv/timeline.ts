import timeline from "./timeline.json";

export const FPS = timeline.fps;
export const TRANSITION = timeline.transition;
export const FINALE_HIT = timeline.finaleHit;

export type SceneId =
  | "Open"
  | "Greece"
  | "Rome"
  | "Printing"
  | "Science"
  | "Enlightenment"
  | "Machine"
  | "Information"
  | "Kardashev"
  | "Finale";

export const SCENES = timeline.scenes as { id: SceneId; frames: number }[];

export const sceneFrames = (id: SceneId) =>
  SCENES.find((s) => s.id === id)!.frames;

// Transitions overlap neighbouring scenes, so each one shortens the total.
export const TOTAL_FRAMES =
  SCENES.reduce((sum, s) => sum + s.frames, 0) - TRANSITION * (SCENES.length - 1);
