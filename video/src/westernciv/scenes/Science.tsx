import { AbsoluteFill, useCurrentFrame } from "remotion";
import { SceneFrame, TitleBlock, drawProps, fadeWindow, progress } from "../../kit/Cinematic";
import { colors, fonts } from "../../kit/theme";
import { sceneFrames } from "../timeline";

const D = sceneFrames("Science");

const SUN = { x: 1240, y: 420 };
const TILT = 0.4;
// Orbit radii; angular speed follows Kepler's third law (ω ∝ r^-1.5).
const ORBITS = [
  { r: 90, color: colors.dim, size: 7 },
  { r: 140, color: colors.sun, size: 10 },
  { r: 205, color: colors.blue, size: 12, label: "EARTH" },
  { r: 275, color: "#d9694a", size: 9 },
  { r: 390, color: colors.goldBright, size: 18 },
];

export const Science: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <SceneFrame duration={D}>
      <AbsoluteFill>
        <svg width="100%" height="100%">
          <defs>
            <radialGradient id="sunGlow">
              <stop offset="0%" stopColor={colors.goldBright} stopOpacity={0.9} />
              <stop offset="100%" stopColor={colors.sun} stopOpacity={0} />
            </radialGradient>
          </defs>
          <circle cx={SUN.x} cy={SUN.y} r={140} fill="url(#sunGlow)" opacity={progress(frame, 0, 40)} />
          <circle cx={SUN.x} cy={SUN.y} r={32} fill={colors.goldBright} opacity={progress(frame, 0, 30)} />
          {ORBITS.map((o, i) => {
            const draw = progress(frame, 15 + i * 14, 60);
            const omega = 0.045 * Math.pow(90 / o.r, 1.5);
            const a = i * 1.7 + frame * omega;
            const px = SUN.x + Math.cos(a) * o.r;
            const py = SUN.y + Math.sin(a) * o.r * TILT;
            return (
              <g key={i}>
                <ellipse
                  cx={SUN.x}
                  cy={SUN.y}
                  rx={o.r}
                  ry={o.r * TILT}
                  fill="none"
                  stroke={colors.ink}
                  strokeOpacity={0.3}
                  strokeWidth={1.5}
                  {...drawProps(draw)}
                />
                <g opacity={progress(frame, 50 + i * 14, 20)}>
                  <circle cx={px} cy={py} r={o.size} fill={o.color} />
                  {o.label ? (
                    <>
                      <circle
                        cx={px + Math.cos(frame * 0.15) * 24}
                        cy={py + Math.sin(frame * 0.15) * 10}
                        r={4}
                        fill={colors.ink}
                      />
                      <text x={px + 22} y={py - 20} fill={colors.blue} fontFamily={fonts.sans} fontSize={22} letterSpacing="0.2em">
                        {o.label}
                      </text>
                    </>
                  ) : null}
                </g>
              </g>
            );
          })}
        </svg>
      </AbsoluteFill>

      <div
        style={{
          position: "absolute",
          left: 140,
          top: 150,
          fontFamily: fonts.math,
          fontStyle: "italic",
          fontWeight: 500,
          fontSize: 96,
          color: colors.ink,
          opacity: fadeWindow(frame, 170, null, 30),
          filter: `blur(${(1 - progress(frame, 170, 30)) * 8}px)`,
        }}
      >
        F <span style={{ fontStyle: "normal" }}>=</span> G
        <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", verticalAlign: "middle", margin: "0 18px", fontSize: 72, lineHeight: 1.1 }}>
          <span>
            m<sub style={{ fontSize: 36, fontStyle: "normal" }}>1</sub>m<sub style={{ fontSize: 36, fontStyle: "normal" }}>2</sub>
          </span>
          <span style={{ width: "100%", height: 3, background: colors.ink }} />
          <span>
            r<sup style={{ fontSize: 36, fontStyle: "normal" }}>2</sup>
          </span>
        </span>
      </div>
      <div
        style={{
          position: "absolute",
          left: 140,
          top: 330,
          fontFamily: fonts.sans,
          fontSize: 26,
          letterSpacing: "0.3em",
          color: colors.dim,
          opacity: fadeWindow(frame, 200, null, 30),
        }}
      >
        NEWTON · PRINCIPIA · 1687
      </div>

      <TitleBlock
        kicker="1543 – 1687"
        title="THE LAWS OF NATURE"
        sub="Copernicus moves the Earth. Newton writes the equations."
        start={110}
      />
    </SceneFrame>
  );
};
