import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { SceneFrame, TitleBlock, clamp, drawProps, fadeWindow, progress } from "../../kit/Cinematic";
import { colors, fonts } from "../../kit/theme";
import { sceneFrames } from "../timeline";

const D = sceneFrames("Greece");

// Euclid, Elements Book I, Proposition 1: build an equilateral triangle on a
// given segment AB using two circles.
const R = 260;
const A = { x: 830, y: 470 };
const B = { x: A.x + R, y: A.y };
const C = { x: (A.x + B.x) / 2, y: A.y - (R * Math.sqrt(3)) / 2 };
const CENTER = { x: (A.x + B.x) / 2, y: A.y };

const Point: React.FC<{ x: number; y: number; label: string; show: number; dx?: number; dy?: number }> = ({
  x,
  y,
  label,
  show,
  dx = -34,
  dy = 40,
}) => (
  <g opacity={show}>
    <circle cx={x} cy={y} r={7} fill={colors.goldBright} />
    <text x={x + dx} y={y + dy} fill={colors.ink} fontFamily={fonts.serif} fontSize={38}>
      {label}
    </text>
  </g>
);

export const Greece: React.FC = () => {
  const frame = useCurrentFrame();
  const ab = progress(frame, 5, 40);
  const circleA = progress(frame, 45, 80);
  const circleB = progress(frame, 100, 80);
  const tri = progress(frame, 190, 50);
  const fill = interpolate(frame, [240, 290], [0, 0.18], clamp);
  const ring = frame * 0.08;

  return (
    <SceneFrame duration={D}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${CENTER.x}px ${CENTER.y - 60}px, rgba(212,166,74,0.10), rgba(0,0,0,0) 55%)`,
        }}
      />
      <AbsoluteFill>
        <svg width="100%" height="100%">
          {/* Slowly turning measurement ring */}
          <g transform={`rotate(${ring} ${CENTER.x} ${CENTER.y})`} opacity={fadeWindow(frame, 20, null, 60) * 0.22}>
            <circle cx={CENTER.x} cy={CENTER.y} r={430} fill="none" stroke={colors.gold} strokeWidth={1.5} />
            {new Array(72).fill(0).map((_, i) => {
              const a = (i / 72) * Math.PI * 2;
              const r2 = i % 6 === 0 ? 404 : 418;
              return (
                <line
                  key={i}
                  x1={CENTER.x + Math.cos(a) * 430}
                  y1={CENTER.y + Math.sin(a) * 430}
                  x2={CENTER.x + Math.cos(a) * r2}
                  y2={CENTER.y + Math.sin(a) * r2}
                  stroke={colors.gold}
                  strokeWidth={1.5}
                />
              );
            })}
          </g>

          <polygon
            points={`${A.x},${A.y} ${B.x},${B.y} ${C.x},${C.y}`}
            fill={colors.gold}
            opacity={fill}
          />
          <circle cx={A.x} cy={A.y} r={R} fill="none" stroke={colors.ink} strokeOpacity={0.55} strokeWidth={2.5} {...drawProps(circleA)} />
          <circle
            cx={B.x}
            cy={B.y}
            r={R}
            fill="none"
            stroke={colors.ink}
            strokeOpacity={0.55}
            strokeWidth={2.5}
            transform={`rotate(180 ${B.x} ${B.y})`}
            {...drawProps(circleB)}
          />
          <line x1={A.x} y1={A.y} x2={B.x} y2={B.y} stroke={colors.goldBright} strokeWidth={4} {...drawProps(ab)} />
          <line x1={A.x} y1={A.y} x2={C.x} y2={C.y} stroke={colors.goldBright} strokeWidth={4} {...drawProps(tri)} />
          <line x1={B.x} y1={B.y} x2={C.x} y2={C.y} stroke={colors.goldBright} strokeWidth={4} {...drawProps(tri)} />

          <Point {...A} label="A" show={progress(frame, 5, 20)} />
          <Point {...B} label="B" show={progress(frame, 30, 20)} dx={14} />
          <Point {...C} label="C" show={progress(frame, 180, 20)} dx={-12} dy={-24} />
        </svg>
      </AbsoluteFill>

      <div
        style={{
          position: "absolute",
          top: 90,
          right: 140,
          textAlign: "right",
          fontFamily: fonts.sans,
          fontSize: 26,
          letterSpacing: "0.3em",
          color: colors.dim,
          opacity: fadeWindow(frame, 60, null, 30),
        }}
      >
        ELEMENTS · BOOK I · PROPOSITION 1
      </div>

      <TitleBlock
        kicker="c. 300 BC · ALEXANDRIA"
        title="GEOMETRY"
        sub="Truth, derived from first principles."
        start={200}
      />
    </SceneFrame>
  );
};
