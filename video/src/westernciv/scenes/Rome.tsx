import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { SceneFrame, TitleBlock, clamp, drawProps, progress } from "../../kit/Cinematic";
import { colors } from "../../kit/theme";
import { sceneFrames } from "../timeline";

const D = sceneFrames("Rome");

const LEFT = 160;
const RIGHT = 1760;
const GROUND = 660;
const DECK_LOW = 430;
const DECK_TOP = 300;

// One arch opening: two piers joined by a semicircle.
const arch = (a: number, b: number, bottom: number, spring: number) => {
  const r = (b - a) / 2;
  return `M ${a} ${bottom} V ${spring} A ${r} ${r} 0 0 1 ${b} ${spring} V ${bottom}`;
};

const lowerArches = new Array(9).fill(0).map((_, i) => {
  const w = (RIGHT - LEFT) / 9;
  return arch(LEFT + i * w + 20, LEFT + (i + 1) * w - 20, GROUND, 520);
});

const upperArches = new Array(18).fill(0).map((_, i) => {
  const w = (RIGHT - LEFT) / 18;
  return arch(LEFT + i * w + 10, LEFT + (i + 1) * w - 10, DECK_LOW, 360);
});

export const Rome: React.FC = () => {
  const frame = useCurrentFrame();
  const deck = progress(frame, 0, 70);
  return (
    <SceneFrame duration={D}>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse 70% 45% at 50% 72%, rgba(255,179,71,0.22), rgba(0,0,0,0) 70%)",
          opacity: interpolate(frame, [0, 60], [0, 1], clamp),
        }}
      />
      <AbsoluteFill style={{ translate: `${interpolate(frame, [0, D], [20, -20])}px 0` }}>
        <svg width="100%" height="100%">
          <g fill="none" stroke={colors.ink} strokeOpacity={0.8} strokeWidth={3}>
            <line x1={LEFT - 60} y1={GROUND} x2={RIGHT + 60} y2={GROUND} {...drawProps(deck)} />
            <line x1={LEFT} y1={DECK_LOW} x2={RIGHT} y2={DECK_LOW} {...drawProps(deck)} />
            <line x1={LEFT} y1={DECK_TOP} x2={RIGHT} y2={DECK_TOP} {...drawProps(progress(frame, 40, 70))} />
            {lowerArches.map((d, i) => (
              <path key={`l${i}`} d={d} {...drawProps(progress(frame, 20 + i * 7, 45))} />
            ))}
            {upperArches.map((d, i) => (
              <path key={`u${i}`} d={d} strokeWidth={2} {...drawProps(progress(frame, 60 + i * 4, 35))} />
            ))}
          </g>
        </svg>
      </AbsoluteFill>
      <TitleBlock
        kicker="509 BC – AD 476 · ROME"
        title="ORDER"
        sub="Law. Roads. Aqueducts. Order at the scale of an empire."
        start={120}
      />
    </SceneFrame>
  );
};
