import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { CenterLine, SceneFrame, clamp, progress } from "../../kit/Cinematic";
import { colors, fonts } from "../../kit/theme";
import { sceneFrames } from "../timeline";

const D = sceneFrames("Enlightenment");
const WORDS = "SAPERE AUDE".split("");

export const Enlightenment: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <SceneFrame duration={D} push={0.07}>
      {/* God rays */}
      <AbsoluteFill
        style={{
          opacity: interpolate(frame, [0, 60], [0, 0.55], clamp),
          background: `repeating-conic-gradient(from ${frame * 0.15}deg at 50% 46%, rgba(243,207,122,0.16) 0deg 4deg, rgba(0,0,0,0) 4deg 14deg)`,
          maskImage: "radial-gradient(circle at 50% 46%, black 0%, transparent 65%)",
        }}
      />
      <AbsoluteFill
        style={{
          background: "radial-gradient(circle at 50% 46%, rgba(243,207,122,0.25), rgba(0,0,0,0) 40%)",
          opacity: progress(frame, 0, 60),
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 390,
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
          fontFamily: fonts.serif,
          fontWeight: 700,
          fontSize: 150,
          color: colors.ink,
          textShadow: `0 0 40px rgba(243,207,122,0.35)`,
        }}
      >
        {WORDS.map((ch, i) => {
          const p = progress(frame, 10 + i * 4, 40);
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                width: ch === " " ? 70 : undefined,
                margin: "0 6px",
                opacity: p,
                translate: `0 ${(1 - p) * 30}px`,
                filter: `blur(${(1 - p) * 12}px)`,
              }}
            >
              {ch}
            </span>
          );
        })}
      </div>
      <CenterLine text="Dare to know." start={80} end={null} size={52} y={660} font={fonts.sans} weight={300} />
      <CenterLine
        text="IMMANUEL KANT · 1784 · THE ENLIGHTENMENT"
        start={110}
        end={null}
        size={26}
        y={740}
        font={fonts.sans}
        color={colors.gold}
        weight={600}
      />
    </SceneFrame>
  );
};
