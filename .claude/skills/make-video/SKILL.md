---
name: make-video
description: Make a cinematic motion-graphics video (explainer, history, promo, "story of X", data story, social clip) in this repo's video/ Remotion project and deliver a rendered MP4. Use whenever the user asks to make, create, render, or edit a video or animation.
---

# Making a video in this repo

The Remotion project is `video/` (separate from the Python scanner — never
touch `scripts/`, `.github/`, or `docs/` for video work). Read
`video/README.md` first. For Remotion API details use the `remotion-*`
skills (start with `remotion-best-practices`).

`video/src/westernciv/` is a finished 2-minute example. Copy its patterns;
do not rebuild it.

## 1. Get the brief (ask only what's missing)

- **Topic and arc** — the beginning → middle → end, one idea per scene.
- **Length** — default 60–120 s.
- **Format** — 1920×1080 (default, YouTube/X landscape) or 1080×1920
  (vertical, Reels/TikTok/Shorts) or 1080×1080.
- **Style** — default is the house look in `src/kit` (black, gold, Cinzel
  titles, film grain). Other palettes/fonts are fine; add them to the kit.
- **Ending** — a final word/line to land on (e.g. "ACCELERATE").
- **Audio** — default synthesized score (below). Voiceover needs an
  ElevenLabs key (see `remotion-markup/voiceover.md`); a licensed music file
  can go in `video/public/`.

Write the scene list back to the user as a short outline before building
a long video.

## 2. Build

1. Create `video/src/<slug>/` with:
   - `timeline.json` — `fps`, `transition`, `scenes[{id, frames, chord?, bpm?, accelerate?}]`,
     optional `hit {scene, frame, chord?}`. This drives both the video and
     the soundtrack. Chords: see `CHORDS` in `video/scripts/make-score.mjs`.
   - `timeline.ts` — typed accessors (copy from westernciv).
   - `scenes/<Scene>.tsx` — one file per scene.
   - `<Video>.tsx` — `TransitionSeries` of the scenes + `Vignette`,
     `FilmGrain`, and `<Audio src={staticFile("<slug>-score.wav")} />`.
2. Register the video and its scenes in `video/src/Root.tsx` (same pattern
   as `WesternCiv`). Use the brief's width/height.
3. Reuse `src/kit` (`SceneFrame`, `TitleBlock`, `CenterLine`, `Starfield`,
   `drawProps`, `progress`, `fadeWindow`). Put anything reusable you invent
   into the kit, not the video folder.

Patterns already in westernciv worth copying:

| Want | Look at |
| --- | --- |
| Line art drawing itself | `Greece.tsx` (construction), `Rome.tsx` (aqueduct) |
| Wall of text / type stamping in | `Printing.tsx` |
| Orbits / physics diagram + equation | `Science.tsx` |
| Big quote with light rays | `Enlightenment.tsx` |
| Animated chart (hockey stick), gears | `Machine.tsx` |
| Circuit traces with pulses, timeline list | `Information.tsx` |
| Labelled scale + zoom into next shot, particle swarm | `Kardashev.tsx` |
| Accelerating word flashes, warp, final slam + flash | `Finale.tsx` |

Style rules that made it read as "cinematic":
- One focal element per scene; a date/place kicker + big title + one line.
- Everything eases (`easeOut`); nothing pops in. Slow push-in on every scene.
- Draw lines on (`drawProps`) instead of fading them.
- Build pace towards the end: shorter shots, faster pulse, then one hit.
- Text at least 84 px headlines / 44 px body at 1080p, 100+ px from edges.

## 3. Check before rendering the whole thing

```console
cd video
npx tsc && npx eslint src
npm run video -- <Id> --frames=<one or two frames per scene>
```

Then **look at every PNG** in `out/<Id>-frames/` with the Read tool. Fix
overlaps, cut-off text, wrong glyphs, empty frames. Global frame of a scene
= sum of `(frames - transition)` of the scenes before it.

## 4. Render and deliver

```console
npm run video -- <Id>
```

~3 s of render per second of video on a 4-core cloud container, so a
2-minute video takes ~6 min. Writes `out/<Id>.mp4` and, if over 28 MB,
`out/<Id>-share.mp4`. Send the one under 30 MB with SendUserFile (the chat
upload limit). `out/` and `public/*-score.wav` are git-ignored: commit
source only. Tell the user it has only been checked at sampled frames
unless you have watched more.

## Known pitfalls (already hit once)

- **Cinzel has no lowercase** — lowercase renders as small caps (`m₁` → `M₁`,
  `Si` → `SI`, `2020s` → `2020S`). Use `fonts.math` (Cormorant Garamond) or
  `fonts.sans` for mixed case and maths.
- **Cloud sandbox network**: `remotion.media` (Remotion's Chrome download),
  `x.com`, `upload.wikimedia.org` are blocked. The config falls back to the
  pre-installed Chromium automatically. npm and GitHub work. Fonts come from
  `@fontsource/*` npm packages — add new ones the same way, not from Google
  Fonts. Draw visuals in code rather than depending on downloaded images.
- **Remotion's bundled ffmpeg is minimal** — no `tile`, `astats`, or raw
  `s16le` output. To inspect audio, decode to `.wav` with `-c:a pcm_s16le`
  and read samples in Node.
- **CSS animations/transitions don't render** — drive everything from
  `useCurrentFrame()`.
- `interpolate()` input ranges must be strictly increasing — check
  `start + fade < end - fade` when a window is short.
