# Videos (Remotion + Claude Code)

Motion-graphics videos written as React code by Claude Code and rendered to
MP4 by [Remotion](https://www.remotion.dev). Nothing here touches the market
scanner — it's a separate Node project.

The Remotion agent skills live in `../.claude/skills/` (from
[remotion-dev/skills](https://github.com/remotion-dev/skills)), so any Claude
Code session opened in this repo knows Remotion's best practices.

## Commands

```console
npm i              # once
npm run dev        # Remotion Studio preview (generates the score first)
npm run render     # -> out/western-civ.mp4 (1920x1080, 30fps, ~2 min)
npm run lint       # eslint + tsc
```

Rendering the 2-minute video takes ~6 minutes on a 4-core cloud container.

Render a few frames as PNGs to check a change without rendering everything:

```console
npx remotion render WesternCiv out/frames --frames=190,565,890 --image-format=png --scale=0.5
```

## Making a new video

Open Claude Code in this repo and describe the video. Briefs that work well
name the **arc**, the **length**, the **style**, and the **ending**:

> Make a 90-second cinematic video tracing the history of money, from barter
> to Bitcoin. Same style as WesternCiv (dark, gold, Cinzel titles, film
> grain). One scene per era with a date/place kicker. End on the word
> "SOVEREIGN". Reuse src/kit.

Each video gets its own folder under `src/` (like `src/westernciv/`) and its
own `<Composition>` in `src/Root.tsx`.

## What's reusable

`src/kit/` is the shared look:

| File | What it gives you |
| --- | --- |
| `theme.ts` | Colours and bundled fonts (Cinzel titles, Inter body, Cormorant Garamond for maths/lowercase — Cinzel has no lowercase) |
| `Cinematic.tsx` | `SceneFrame` (slow push-in), `TitleBlock` (kicker + headline + subline), `CenterLine`, `Starfield`, `FilmGrain`, `Vignette`, `drawProps()` for self-drawing SVG lines, timing helpers |

## How WesternCiv is put together

- `src/westernciv/timeline.json` — scene order and lengths in frames. **Single
  source of truth**: the video and the soundtrack both read it, so editing a
  scene length keeps the music in sync.
- `src/westernciv/scenes/*.tsx` — one file per scene. Each scene is also
  registered on its own (`WesternCiv-Greece`, …) for previewing in Studio.
- `scripts/make-score.mjs` — synthesizes an original soundtrack (chord pad
  per era, accelerating pulse, riser, final hit on ACCELERATE) to
  `public/westernciv-score.wav`. It's generated, not committed.

All visuals are drawn in code (SVG/CSS) — no stock images or footage — so
there's nothing to license and nothing to download at render time.

## Running in a Claude Code cloud session

- The cloud sandbox can't download Remotion's own headless Chrome
  (`remotion.media` is blocked), so `remotion.config.ts` uses the
  pre-installed Chromium when it exists. Locally, Remotion downloads its own
  browser as usual. Override with `REMOTION_BROWSER_EXECUTABLE`.
- Fonts come from npm (`@fontsource/*`), not Google Fonts, so renders don't
  need network access.
- `out/` is git-ignored; rendered MP4s are not committed.

## Licensing

Remotion is free for individuals and companies of up to 3 people; larger
companies need a [company license](https://www.remotion.pro/license).
