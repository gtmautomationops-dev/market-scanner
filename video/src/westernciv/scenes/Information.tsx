import { AbsoluteFill, interpolate, random, useCurrentFrame } from "remotion";
import { SceneFrame, TitleBlock, clamp, drawProps, progress } from "../../kit/Cinematic";
import { colors, fonts } from "../../kit/theme";
import { sceneFrames } from "../timeline";

const D = sceneFrames("Information");

const CHIP = { x: 1400, y: 430, size: 240 };

type Pt = [number, number];

// Circuit traces: from a random point on the screen edge to one of the chip's
// pins, routed with right angles like a PCB.
const TRACES: Pt[][] = new Array(34).fill(0).map((_, i) => {
  const side = i % 4;
  const pinT = (Math.floor(i / 4) + 0.5) / 9;
  const half = CHIP.size / 2;
  const edge = random(`e${i}`);
  let start: Pt;
  let pin: Pt;
  let mid: Pt;
  if (side === 0) {
    pin = [CHIP.x - half + pinT * CHIP.size, CHIP.y - half];
    start = [900 + edge * 1000, -20];
    mid = [start[0], pin[1] - 40 - random(`m${i}`) * 120];
    return [start, mid, [pin[0], mid[1]], pin];
  }
  if (side === 1) {
    pin = [CHIP.x + half, CHIP.y - half + pinT * CHIP.size];
    start = [1940, edge * 1080];
    mid = [pin[0] + 40 + random(`m${i}`) * 120, start[1]];
    return [start, mid, [mid[0], pin[1]], pin];
  }
  if (side === 2) {
    pin = [CHIP.x - half + pinT * CHIP.size, CHIP.y + half];
    start = [900 + edge * 1000, 1100];
    mid = [start[0], pin[1] + 40 + random(`m${i}`) * 120];
    return [start, mid, [pin[0], mid[1]], pin];
  }
  pin = [CHIP.x - half, CHIP.y - half + pinT * CHIP.size];
  start = [760, 120 + edge * 640];
  mid = [pin[0] - 40 - random(`m${i}`) * 200, start[1]];
  return [start, mid, [mid[0], pin[1]], pin];
});

const pointAlong = (pts: Pt[], t: number): Pt => {
  const lens = pts.slice(1).map((p, i) => Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]));
  let d = t * lens.reduce((a, b) => a + b, 0);
  for (let i = 0; i < lens.length; i++) {
    if (d <= lens[i]) {
      const k = lens[i] === 0 ? 0 : d / lens[i];
      return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k];
    }
    d -= lens[i];
  }
  return pts[pts.length - 1];
};

const MILESTONES = [
  { year: "1947", text: "The transistor", at: 40 },
  { year: "1969", text: "Apollo 11 lands on the Moon", at: 105 },
  { year: "1991", text: "The World Wide Web", at: 170 },
  { year: "2012", text: "Machines that learn", at: 235 },
];

export const Information: React.FC = () => {
  const frame = useCurrentFrame();
  const chip = progress(frame, 0, 40);
  return (
    <SceneFrame duration={D}>
      <AbsoluteFill>
        <svg width="100%" height="100%">
          {TRACES.map((pts, i) => {
            const d = `M ${pts.map((p) => p.join(",")).join(" L ")}`;
            const draw = progress(frame, 5 + (i % 12) * 5, 70);
            const pulseT = ((frame * 0.012 + random(`p${i}`)) % 1);
            const [px, py] = pointAlong(pts, pulseT);
            return (
              <g key={i}>
                <path d={d} fill="none" stroke={colors.blue} strokeOpacity={0.35} strokeWidth={2} {...drawProps(draw)} />
                <circle cx={px} cy={py} r={4} fill={colors.blue} opacity={draw >= 1 ? 0.9 : 0} style={{ filter: `drop-shadow(0 0 6px ${colors.blue})` }} />
              </g>
            );
          })}
          <g opacity={chip}>
            <rect
              x={CHIP.x - CHIP.size / 2}
              y={CHIP.y - CHIP.size / 2}
              width={CHIP.size}
              height={CHIP.size}
              rx={16}
              fill="#0d1624"
              stroke={colors.blue}
              strokeWidth={3}
              style={{ filter: `drop-shadow(0 0 ${20 + 10 * Math.sin(frame * 0.1)}px rgba(111,179,255,0.6))` }}
            />
            <text x={CHIP.x} y={CHIP.y + 30} fill={colors.blue} fontFamily={fonts.sans} fontWeight={300} fontSize={96} textAnchor="middle">
              Si
            </text>
          </g>
        </svg>
      </AbsoluteFill>

      <div style={{ position: "absolute", left: 140, top: 150 }}>
        {MILESTONES.map((m, i) => {
          const p = progress(frame, m.at, 25);
          const next = MILESTONES[i + 1];
          const dimmed = next ? interpolate(frame, [next.at, next.at + 20], [1, 0.45], clamp) : 1;
          return (
            <div
              key={m.year}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 28,
                height: 92,
                opacity: p * dimmed,
                translate: `${(1 - p) * -30}px 0`,
              }}
            >
              <span style={{ fontFamily: fonts.serif, fontWeight: 700, fontSize: 58, color: colors.gold, width: 190 }}>{m.year}</span>
              <span style={{ fontFamily: fonts.sans, fontWeight: 300, fontSize: 38, color: colors.ink }}>{m.text}</span>
            </div>
          );
        })}
      </div>

      <TitleBlock
        kicker="1947 → TODAY"
        title="THE INFORMATION AGE"
        sub="Computation doubles, and doubles again."
        start={290}
      />
    </SceneFrame>
  );
};
