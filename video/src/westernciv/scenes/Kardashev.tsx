import { AbsoluteFill, interpolate, random, useCurrentFrame } from "remotion";
import { SceneFrame, Starfield, TitleBlock, clamp, drawProps, easeInOut, progress } from "../../kit/Cinematic";
import { colors, fonts } from "../../kit/theme";
import { sceneFrames } from "../timeline";

const D = sceneFrames("Kardashev");
const SWARM_AT = 200; // frame where the ladder hands over to the Dyson swarm

// ---------- Part A: the scale ----------
const AXIS_X = 760;
const Y0 = 880; // Type 0
const RUNGS = [
  { y: 660, name: "TYPE I", desc: "Planetary", power: "16" },
  { y: 420, name: "TYPE II", desc: "Stellar", power: "26" },
  { y: 180, name: "TYPE III", desc: "Galactic", power: "36" },
];
// Carl Sagan's interpolation puts humanity at roughly 0.7.
const HERE = 0.7;
const hereY = Y0 - HERE * (Y0 - RUNGS[0].y);

const Ladder: React.FC = () => {
  const frame = useCurrentFrame();
  const axis = progress(frame, 5, 50);
  const marker = progress(frame, 70, 60, easeInOut);
  return (
    <AbsoluteFill
      style={{
        transformOrigin: `${AXIS_X + 200}px ${RUNGS[1].y}px`,
        scale: interpolate(frame, [SWARM_AT - 40, SWARM_AT + 20], [1, 2.2], { ...clamp, easing: easeInOut }),
        opacity: interpolate(frame, [SWARM_AT - 10, SWARM_AT + 20], [1, 0], clamp),
      }}
    >
      <svg width="100%" height="100%">
        <line x1={AXIS_X} y1={Y0} x2={AXIS_X} y2={RUNGS[2].y - 40} stroke={colors.ink} strokeOpacity={0.5} strokeWidth={2} {...drawProps(axis)} />
        {RUNGS.map((r, i) => (
          <line key={r.name} x1={AXIS_X - 24} y1={r.y} x2={AXIS_X + 24} y2={r.y} stroke={colors.gold} strokeWidth={3} opacity={progress(frame, 20 + i * 12, 20)} />
        ))}
        <circle cx={AXIS_X} cy={Y0 - marker * (Y0 - hereY)} r={10 + 3 * Math.sin(frame * 0.2)} fill={colors.blue} opacity={progress(frame, 60, 15)} style={{ filter: `drop-shadow(0 0 12px ${colors.blue})` }} />
      </svg>
      {RUNGS.map((r, i) => (
        <div
          key={r.name}
          style={{
            position: "absolute",
            left: AXIS_X + 60,
            top: r.y - 44,
            display: "flex",
            alignItems: "baseline",
            gap: 30,
            opacity: progress(frame, 20 + i * 12, 30),
          }}
        >
          <span style={{ fontFamily: fonts.serif, fontWeight: 700, fontSize: 64, color: colors.ink }}>{r.name}</span>
          <span style={{ fontFamily: fonts.sans, fontWeight: 300, fontSize: 36, color: colors.dim }}>
            {r.desc} · 10<sup style={{ fontSize: 22 }}>{r.power}</sup> W
          </span>
        </div>
      ))}
      <div
        style={{
          position: "absolute",
          right: 1920 - AXIS_X + 40,
          top: hereY - 22,
          fontFamily: fonts.sans,
          fontWeight: 600,
          fontSize: 30,
          letterSpacing: "0.2em",
          color: colors.blue,
          whiteSpace: "nowrap",
          opacity: progress(frame, 120, 25),
        }}
      >
        WE ARE HERE · ~0.7
      </div>
      <div style={{ position: "absolute", left: 140, top: 110, opacity: progress(frame, 0, 30) }}>
        <div style={{ fontFamily: fonts.sans, fontWeight: 600, fontSize: 30, letterSpacing: "0.32em", color: colors.gold }}>
          THE KARDASHEV SCALE
        </div>
        <div style={{ marginTop: 14, fontFamily: fonts.sans, fontWeight: 300, fontSize: 36, color: colors.ink, opacity: 0.8, maxWidth: 520 }}>
          A civilization, measured by the energy it commands.
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------- Part B: a Dyson swarm assembles ----------
const STAR = { x: 960, y: 430 };
const RINGS = [0, 30, 60, 90, 120, 150].map((tilt, k) => ({
  tilt: (tilt * Math.PI) / 180,
  rx: 230 + k * 16,
  squash: 0.26,
  speed: 0.008 * (1 + k * 0.18) * (k % 2 ? -1 : 1),
}));
const PANELS_PER_RING = 44;

type Panel = { x: number; y: number; front: boolean; angle: number; key: string; show: number };

const Swarm: React.FC = () => {
  const frame = useCurrentFrame();
  const local = frame - SWARM_AT;
  const built = interpolate(local, [30, 230], [0, 1], clamp);
  const panels: Panel[] = [];
  RINGS.forEach((ring, k) => {
    for (let j = 0; j < PANELS_PER_RING; j++) {
      const a = (j / PANELS_PER_RING) * Math.PI * 2 + local * ring.speed;
      const lx = Math.cos(a) * ring.rx;
      const ly = Math.sin(a) * ring.rx * ring.squash;
      const x = STAR.x + lx * Math.cos(ring.tilt) - ly * Math.sin(ring.tilt);
      const y = STAR.y + lx * Math.sin(ring.tilt) + ly * Math.cos(ring.tilt);
      const order = random(`panel-${k}-${j}`);
      const show = interpolate(built, [order * 0.9, order * 0.9 + 0.1], [0, 1], clamp);
      panels.push({ x, y, front: Math.sin(a) > 0, angle: (ring.tilt * 180) / Math.PI + (a * 180) / Math.PI + 90, key: `${k}-${j}`, show });
    }
  });
  const renderPanels = (front: boolean) =>
    panels
      .filter((p) => p.front === front && p.show > 0)
      .map((p) => (
        <rect
          key={p.key}
          x={-9}
          y={-4}
          width={18}
          height={8}
          fill={front ? colors.goldBright : colors.gold}
          opacity={p.show * (front ? 0.95 : 0.4)}
          transform={`translate(${p.x} ${p.y}) rotate(${p.angle}) scale(${0.4 + 0.6 * p.show})`}
        />
      ));
  const starGlow = 1 - 0.45 * built;
  return (
    <AbsoluteFill style={{ opacity: interpolate(local, [0, 40], [0, 1], clamp) }}>
      <Starfield seed="deep" opacity={0.6} drift={0.05} />
      <svg width="100%" height="100%">
        <defs>
          <radialGradient id="corona">
            <stop offset="0%" stopColor="#fff6dc" stopOpacity={1} />
            <stop offset="18%" stopColor={colors.goldBright} stopOpacity={0.9} />
            <stop offset="45%" stopColor={colors.sun} stopOpacity={0.25} />
            <stop offset="100%" stopColor={colors.sun} stopOpacity={0} />
          </radialGradient>
        </defs>
        {renderPanels(false)}
        <circle cx={STAR.x} cy={STAR.y} r={330 + 10 * Math.sin(local * 0.08)} fill="url(#corona)" opacity={starGlow} />
        <circle cx={STAR.x} cy={STAR.y} r={62} fill="#fff6dc" style={{ filter: `drop-shadow(0 0 30px ${colors.sun})` }} />
        {renderPanels(true)}
      </svg>
    </AbsoluteFill>
  );
};

export const Kardashev: React.FC = () => (
  <SceneFrame duration={D} push={0.03}>
    <Ladder />
    <Swarm />
    <TitleBlock
      kicker="THE FUTURE"
      title="TYPE II"
      sub="A civilization that harnesses the full power of its star."
      start={SWARM_AT + 110}
    />
  </SceneFrame>
);
