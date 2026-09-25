# Videos (Remotion + Claude Code)

Cinematic motion-graphics videos, written as React code by Claude Code and
rendered to MP4 by [Remotion](https://www.remotion.dev). This is a separate
Node project; nothing here touches the market scanner.

## Making a video

Open Claude Code in this repo and describe what you want. The
`make-video` skill (`../.claude/skills/make-video/`) walks Claude through
brief → scenes → frame checks → render → a file small enough to send in chat.
Remotion's own skills (`../.claude/skills/remotion-*`) cover the API.

Briefs that work well name the **arc**, **length**, **format**, **style**,
and **ending**:

> Make a 90-second vertical video on the history of money, from barter to
> Bitcoin. House style. One scene per era with a date/place kicker. End on
> "SOVEREIGN".

## Commands

```console
npm i                                      # once
npm run dev                                # Remotion Studio preview
npm run video -- <Id> --frames=0,90,300    # PNG previews in out/<Id>-frames/
npm run video -- <Id>                      # out/<Id>.mp4 (+ out/<Id>-share.mp4 if > 28 MB)
npm run lint                               # eslint + tsc
```

Rendering takes about 3 s per second of video on a 4-core cloud container.

## Layout

| Path | What |
| --- | --- |
| `src/kit/` | Shared look: colours, bundled fonts, `SceneFrame` (slow push-in), `TitleBlock`, `CenterLine`, `Starfield`, `FilmGrain`, `Vignette`, `drawProps()` for self-drawing SVG, timing helpers |
| `src/<video>/` | One folder per video: `timeline.json`, `scenes/*.tsx`, the assembled video |
| `src/westernciv/` | Worked example: 2 min, 10 scenes, Greek geometry → Dyson swarm → "ACCELERATE" |
| `scripts/make-score.mjs` | Synthesizes an original soundtrack for every `src/*/timeline.json` |
| `scripts/video.mjs` | The `npm run video` command |

### timeline.json

Scene order and lengths in frames. The video and the soundtrack both read
it, so changing a scene length keeps the music in sync.

```json
{
  "fps": 30,
  "transition": 15,
  "hit": { "scene": "Finale", "frame": 270, "chord": "A" },
  "scenes": [
    { "id": "Open", "frames": 240, "chord": "Am" },
    { "id": "Machine", "frames": 360, "chord": "Amwide", "bpm": 60 },
    { "id": "Finale", "frames": 435, "chord": "E", "accelerate": true }
  ]
}
```

- `chord` — pad chord for the scene (list in `make-score.mjs`); defaults cycle Am F C G.
- `bpm` — adds a heartbeat pulse during that scene.
- `accelerate` — pulse speeds up with a rising noise sweep into the `hit`.
- `hit` — optional boom and resolution chord at that frame of that scene.

The generated `public/*-score.wav` files and everything in `out/` are
git-ignored; only source is committed.

## Running in a Claude Code cloud session

- Remotion's headless-Chrome download (`remotion.media`) is blocked there, so
  `remotion.config.ts` uses the pre-installed Chromium when present
  (override with `REMOTION_BROWSER_EXECUTABLE`). Locally nothing changes.
- Fonts come from npm (`@fontsource/*`), so renders need no network.
- Image hosts like Wikimedia are blocked, so visuals are drawn in code.

## Licensing

Remotion is free for individuals and companies of up to 3 people; larger
companies need a [company license](https://www.remotion.pro/license).
