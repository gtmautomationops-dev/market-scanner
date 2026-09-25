import { AbsoluteFill, useCurrentFrame } from "remotion";
import { SceneFrame, TitleBlock, drawProps, progress } from "../../kit/Cinematic";
import { colors, fonts } from "../../kit/theme";
import { sceneFrames } from "../timeline";

const D = sceneFrames("Machine");

const gearPath = (teeth: number, pitch: number) => {
  const outer = pitch + 12;
  const inner = pitch - 12;
  const pts: string[] = [];
  for (let i = 0; i < teeth; i++) {
    const a = (i / teeth) * Math.PI * 2;
    const step = (Math.PI * 2) / teeth;
    const corners: [number, number][] = [
      [inner, a],
      [outer, a + step * 0.2],
      [outer, a + step * 0.5],
      [inner, a + step * 0.7],
    ];
    corners.forEach(([r, t]) => pts.push(`${Math.cos(t) * r},${Math.sin(t) * r}`));
  }
  return `M ${pts.join(" L ")} Z`;
};

// Meshing gears sit exactly (pitch1 + pitch2) apart and turn at speeds
// inversely proportional to their tooth counts.
const meshed = (from: { x: number; y: number; pitch: number }, pitch: number, deg: number) => ({
  x: from.x + Math.cos((deg * Math.PI) / 180) * (from.pitch + pitch),
  y: from.y + Math.sin((deg * Math.PI) / 180) * (from.pitch + pitch),
});
const G1 = { x: 470, y: 400, teeth: 24, pitch: 150, dir: 1 };
const GEARS = [
  G1,
  { ...meshed(G1, 88, 15), teeth: 14, pitch: 88, dir: -1 },
  { ...meshed(G1, 62, -120), teeth: 10, pitch: 62, dir: -1 },
];

// Chart: AD 1 → today on a linear time axis. Output per person is flat for
// ~1,800 years, then bends upward.
const CHART = { x0: 1000, x1: 1760, y0: 620, y1: 190 };
const curve = (() => {
  const pts: string[] = [];
  for (let i = 0; i <= 200; i++) {
    const t = i / 200;
    const year = 1 + t * 2025;
    const v = Math.pow(Math.max(0, (year - 1780) / 246), 2.6);
    const x = CHART.x0 + t * (CHART.x1 - CHART.x0);
    const y = CHART.y0 - 20 - v * (CHART.y0 - CHART.y1 - 20);
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return `M ${pts.join(" L ")}`;
})();
const x1800 = CHART.x0 + ((1800 - 1) / 2025) * (CHART.x1 - CHART.x0);

const Tick: React.FC<{ x: number; label: string; opacity: number }> = ({ x, label, opacity }) => (
  <text x={x} y={CHART.y0 + 44} fill={colors.dim} fontFamily={fonts.sans} fontSize={24} textAnchor="middle" letterSpacing="0.15em" opacity={opacity}>
    {label}
  </text>
);

export const Machine: React.FC = () => {
  const frame = useCurrentFrame();
  const axes = progress(frame, 20, 40);
  const line = progress(frame, 50, 160);
  return (
    <SceneFrame duration={D}>
      <AbsoluteFill>
        <svg width="100%" height="100%">
          {GEARS.map((g, i) => (
            <g
              key={i}
              transform={`translate(${g.x} ${g.y}) rotate(${g.dir * frame * (36 / g.teeth) + (i === 1 ? 180 / g.teeth : 0)})`}
              opacity={progress(frame, i * 10, 40) * 0.9}
            >
              <path d={gearPath(g.teeth, g.pitch)} fill="none" stroke={colors.gold} strokeWidth={3} />
              <circle r={g.pitch * 0.35} fill="none" stroke={colors.gold} strokeWidth={2} strokeOpacity={0.6} />
              <circle r={10} fill={colors.gold} />
            </g>
          ))}

          <g stroke={colors.ink} strokeOpacity={0.45} strokeWidth={2}>
            <line x1={CHART.x0} y1={CHART.y0} x2={CHART.x1} y2={CHART.y0} {...drawProps(axes)} />
            <line x1={CHART.x0} y1={CHART.y0} x2={CHART.x0} y2={CHART.y1} {...drawProps(axes)} />
          </g>
          <text x={CHART.x0} y={CHART.y1 - 26} fill={colors.dim} fontFamily={fonts.sans} fontSize={24} letterSpacing="0.2em" opacity={axes}>
            OUTPUT PER PERSON
          </text>
          <Tick x={CHART.x0} label="AD 1" opacity={axes} />
          <Tick x={x1800} label="1800" opacity={progress(frame, 150, 20)} />
          <line x1={x1800} y1={CHART.y0} x2={x1800} y2={CHART.y1} stroke={colors.gold} strokeOpacity={0.35} strokeDasharray="6 8" opacity={progress(frame, 150, 20)} />
          <path
            d={curve}
            fill="none"
            stroke={colors.goldBright}
            strokeWidth={5}
            style={{ filter: `drop-shadow(0 0 10px ${colors.gold})` }}
            {...drawProps(line)}
          />
        </svg>
      </AbsoluteFill>
      <TitleBlock
        kicker="1769 · JAMES WATT'S STEAM ENGINE"
        title="THE MACHINE AGE"
        sub="For the first time in history, the curve bends upward."
        start={120}
      />
    </SceneFrame>
  );
};
