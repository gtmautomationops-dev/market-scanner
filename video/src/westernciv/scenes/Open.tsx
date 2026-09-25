import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { CenterLine, SceneFrame, Starfield, clamp, drawProps, progress } from "../../kit/Cinematic";
import { colors } from "../../kit/theme";
import { sceneFrames } from "../timeline";

const D = sceneFrames("Open");

export const Open: React.FC = () => {
  const frame = useCurrentFrame();
  const line = progress(frame, 150, 60);
  return (
    <SceneFrame duration={D} push={0.04}>
      <Starfield opacity={interpolate(frame, [0, 50], [0, 0.8], clamp)} />
      <CenterLine text="For most of history, the world was a mystery." start={15} end={125} />
      <CenterLine text="Then someone drew a line." start={130} end={null} size={72} y={470} />
      <AbsoluteFill>
        <svg width="100%" height="100%">
          <line
            x1={560}
            y1={600}
            x2={1360}
            y2={600}
            stroke={colors.goldBright}
            strokeWidth={3}
            style={{ filter: `drop-shadow(0 0 12px ${colors.gold})` }}
            {...drawProps(line)}
          />
        </svg>
      </AbsoluteFill>
    </SceneFrame>
  );
};
