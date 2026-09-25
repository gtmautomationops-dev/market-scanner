import { AbsoluteFill, interpolate, random, useCurrentFrame } from "remotion";
import { SceneFrame, TitleBlock, clamp } from "../../kit/Cinematic";
import { colors, fonts } from "../../kit/theme";
import { sceneFrames } from "../timeline";

const D = sceneFrames("Printing");
const PRESS = 150; // frame where the "long night" gives way to print

const LETTERS = "ABCDEFGHILMNOPQRSTVX";
const CELL = 64;
const COLS = Math.ceil(1920 / CELL);
const ROWS = Math.ceil(1080 / CELL);

const Embers: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ opacity: interpolate(frame, [0, 30, PRESS - 10, PRESS + 20], [0, 1, 1, 0], clamp) }}>
      {new Array(40).fill(0).map((_, i) => {
        const x = 300 + random(`ex${i}`) * 1320;
        const y0 = 700 + random(`ey${i}`) * 300;
        const speed = 0.4 + random(`es${i}`) * 0.8;
        const flicker = 0.4 + 0.6 * Math.abs(Math.sin(frame * (0.1 + random(`ef${i}`) * 0.2) + i));
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x + Math.sin(frame * 0.03 + i) * 12,
              top: y0 - frame * speed,
              width: 4,
              height: 4,
              borderRadius: "50%",
              background: colors.sun,
              boxShadow: `0 0 10px ${colors.sun}`,
              opacity: flicker * 0.7,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

// Movable type: letters stamp in, rippling outward from the centre.
const TypeGrid: React.FC = () => {
  const frame = useCurrentFrame();
  const cells = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const cx = c * CELL + CELL / 2;
      const cy = r * CELL + CELL / 2;
      const dist = Math.hypot(cx - 960, cy - 540);
      const t0 = PRESS + dist * 0.09 + random(`t${r}-${c}`) * 6;
      const p = interpolate(frame, [t0, t0 + 8], [0, 1], clamp);
      const settle = interpolate(frame, [t0 + 8, t0 + 30], [1, 0], clamp);
      const hot = random(`h${r}-${c}`) > 0.93;
      const i = Math.floor(random(`l${r}-${c}`) * LETTERS.length);
      cells.push(
        <div
          key={`${r}-${c}`}
          style={{
            position: "absolute",
            left: c * CELL,
            top: r * CELL,
            width: CELL,
            height: CELL,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: fonts.serif,
            fontSize: 40,
            color: hot ? colors.goldBright : colors.ink,
            opacity: p * ((hot ? 0.55 : 0.16) + settle * 0.5),
            scale: 1.6 - 0.6 * p,
          }}
        >
          {LETTERS[i]}
        </div>,
      );
    }
  }
  return <AbsoluteFill>{cells}</AbsoluteFill>;
};

export const Printing: React.FC = () => (
  <SceneFrame duration={D}>
    <Embers />
    <TypeGrid />
    <TitleBlock kicker="AD 476 · THE FALL OF ROME" title="THE LONG NIGHT" start={15} end={PRESS} />
    <TitleBlock
      kicker="1440 · MAINZ"
      title="THE PRINTING PRESS"
      sub="Knowledge escapes the monastery."
      start={PRESS + 40}
    />
  </SceneFrame>
);
