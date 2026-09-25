import { AbsoluteFill, interpolate, random, useCurrentFrame } from "remotion";
import { CenterLine, clamp, easeOut } from "../../kit/Cinematic";
import { colors, fonts } from "../../kit/theme";
import { FINALE_HIT, sceneFrames } from "../timeline";

const D = sceneFrames("Finale");

// Recap: each era flashes by, faster and faster.
const WORDS = ["GEOMETRY", "LAW", "PRINT", "SCIENCE", "REASON", "STEAM", "SILICON", "STARS"];
const DURATIONS = [36, 32, 28, 24, 20, 16, 12, 10];
const FLASHES = DURATIONS.reduce<{ word: string; from: number; to: number }[]>((acc, d, i) => {
  const from = i === 0 ? 15 : acc[i - 1].to;
  return [...acc, { word: WORDS[i], from, to: from + d }];
}, []);

const Flash: React.FC<{ word: string; from: number; to: number }> = ({ word, from, to }) => {
  const frame = useCurrentFrame();
  if (frame < from || frame >= to) return null;
  const t = (frame - from) / (to - from);
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <div
        style={{
          fontFamily: fonts.serif,
          fontWeight: 700,
          fontSize: 170,
          letterSpacing: "0.12em",
          color: colors.ink,
          scale: 1.08 - 0.08 * t,
          opacity: interpolate(t, [0, 0.15, 0.85, 1], [0, 1, 1, 0.2]),
        }}
      >
        {word}
      </div>
    </AbsoluteFill>
  );
};

// After the hit, stars streak outward like a jump to lightspeed.
const Warp: React.FC = () => {
  const frame = useCurrentFrame();
  const t = frame - FINALE_HIT;
  if (t < 0) return null;
  return (
    <AbsoluteFill>
      <svg width="100%" height="100%">
        {new Array(220).fill(0).map((_, i) => {
          const a = random(`wa${i}`) * Math.PI * 2;
          const d0 = 40 + random(`wd${i}`) * 900;
          const speed = 4 + random(`ws${i}`) * 10;
          const r = (d0 + t * speed * (1 + d0 / 400)) % 1300;
          const len = Math.min(220, 8 + t * speed * 0.6) * (r / 800);
          return (
            <line
              key={i}
              x1={960 + Math.cos(a) * r}
              y1={540 + Math.sin(a) * r}
              x2={960 + Math.cos(a) * (r + len)}
              y2={540 + Math.sin(a) * (r + len)}
              stroke={i % 7 === 0 ? colors.goldBright : colors.ink}
              strokeOpacity={0.55}
              strokeWidth={2}
            />
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};

export const Finale: React.FC = () => {
  const frame = useCurrentFrame();
  const hit = interpolate(frame, [FINALE_HIT, FINALE_HIT + 28], [0, 1], { ...clamp, easing: easeOut });
  const fadeToBlack = interpolate(frame, [D - 45, D], [1, 0], clamp);
  return (
    <AbsoluteFill style={{ background: colors.bg }}>
      <AbsoluteFill style={{ opacity: fadeToBlack }}>
        {FLASHES.map((f) => (
          <Flash key={f.word} {...f} />
        ))}
        <CenterLine text="The next chapter is ours to write." start={FLASHES[FLASHES.length - 1].to + 6} end={FINALE_HIT - 8} size={60} y={540} />
        <Warp />
        {frame >= FINALE_HIT ? (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <div
              style={{
                fontFamily: fonts.serif,
                fontWeight: 700,
                fontSize: 170,
                whiteSpace: "nowrap",
                color: colors.ink,
                letterSpacing: `${0.6 - 0.46 * hit}em`,
                scale: 1.3 - 0.3 * hit,
                textShadow: `0 0 ${60 - 30 * hit}px rgba(243,207,122,0.8)`,
              }}
            >
              ACCELERATE
            </div>
            <div
              style={{
                marginTop: 30,
                width: interpolate(frame, [FINALE_HIT + 20, FINALE_HIT + 70], [0, 900], { ...clamp, easing: easeOut }),
                height: 3,
                background: colors.gold,
                boxShadow: `0 0 16px ${colors.gold}`,
              }}
            />
          </AbsoluteFill>
        ) : null}
      </AbsoluteFill>
      {/* White flash on the hit */}
      <AbsoluteFill
        style={{
          background: "#fff8e6",
          opacity: interpolate(frame, [FINALE_HIT, FINALE_HIT + 14], [0.9, 0], clamp) * (frame >= FINALE_HIT ? 1 : 0),
        }}
      />
    </AbsoluteFill>
  );
};
