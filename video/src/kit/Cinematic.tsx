import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  random,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { colors, fonts } from "./theme";

export const clamp = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;

// Fast-out, soft-landing ease used for almost every reveal.
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

/** 0→1 progress between two frames, eased. */
export const progress = (
  frame: number,
  start: number,
  duration: number,
  easing = easeOut,
) => interpolate(frame, [start, start + duration], [0, 1], { ...clamp, easing });

/** Opacity that fades in at `start` and (optionally) out at `end`. */
export const fadeWindow = (
  frame: number,
  start: number,
  end: number | null,
  fade = 20,
) =>
  end === null
    ? interpolate(frame, [start, start + fade], [0, 1], clamp)
    : interpolate(frame, [start, start + fade, end - fade, end], [0, 1, 1, 0], clamp);

/** Props for an SVG shape that "draws itself" as p goes 0→1. */
export const drawProps = (p: number) => ({
  pathLength: 1,
  strokeDasharray: "1 1",
  strokeDashoffset: 1 - p,
});

/** Background plus a slow push-in, the cheapest way to feel "cinematic". */
export const SceneFrame: React.FC<{
  duration: number;
  background?: string;
  push?: number;
  children: React.ReactNode;
}> = ({ duration, background = colors.bg, push = 0.05, children }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background }}>
      <AbsoluteFill
        style={{
          scale: interpolate(frame, [0, duration], [1, 1 + push], clamp),
        }}
      >
        {children}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const Starfield: React.FC<{
  count?: number;
  seed?: string;
  opacity?: number;
  drift?: number;
}> = ({ count = 260, seed = "stars", opacity = 1, drift = 0.15 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ opacity }}>
      {new Array(count).fill(0).map((_, i) => {
        const x = random(`${seed}-x-${i}`) * width;
        const y = random(`${seed}-y-${i}`) * height;
        const size = 1 + random(`${seed}-s-${i}`) * 2.2;
        const phase = random(`${seed}-p-${i}`) * Math.PI * 2;
        const twinkle = 0.45 + 0.55 * Math.abs(Math.sin(frame * 0.04 + phase));
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: (x - frame * drift * size + width) % width,
              top: y,
              width: size,
              height: size,
              borderRadius: "50%",
              background: colors.ink,
              opacity: twinkle * (0.25 + size / 4),
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

export const FilmGrain: React.FC<{ opacity?: number }> = ({ opacity = 0.09 }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ opacity, mixBlendMode: "overlay", pointerEvents: "none" }}>
      <svg width="100%" height="100%">
        <filter id="grain">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.85"
            numOctaves="2"
            seed={frame % 60}
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#grain)" />
      </svg>
    </AbsoluteFill>
  );
};

export const Vignette: React.FC<{ strength?: number }> = ({ strength = 0.75 }) => (
  <AbsoluteFill
    style={{
      pointerEvents: "none",
      background: `radial-gradient(ellipse at center, rgba(0,0,0,0) 45%, rgba(0,0,0,${strength}) 100%)`,
    }}
  />
);

/** Centered line of display text that fades/unblurs in and out. */
export const CenterLine: React.FC<{
  text: React.ReactNode;
  start: number;
  end: number | null;
  size?: number;
  y?: number;
  font?: string;
  color?: string;
  weight?: number;
}> = ({
  text,
  start,
  end,
  size = 64,
  y = 540,
  font = fonts.serif,
  color = colors.ink,
  weight = 400,
}) => {
  const frame = useCurrentFrame();
  const p = progress(frame, start, 30);
  return (
    <div
      style={{
        position: "absolute",
        left: 120,
        right: 120,
        top: y,
        translate: `0 ${-size / 2 + (1 - p) * 16}px`,
        textAlign: "center",
        fontFamily: font,
        fontWeight: weight,
        fontSize: size,
        color,
        letterSpacing: "0.04em",
        opacity: fadeWindow(frame, start, end, 24),
        filter: `blur(${(1 - p) * 8}px)`,
      }}
    >
      {text}
    </div>
  );
};

/**
 * Lower-left title card: small gold kicker (date · place), big serif
 * headline, one line of supporting text.
 */
export const TitleBlock: React.FC<{
  kicker: string;
  title: string;
  sub?: string;
  start: number;
  end?: number | null;
  titleSize?: number;
}> = ({ kicker, title, sub, start, end = null, titleSize = 96 }) => {
  const frame = useCurrentFrame();
  const k = progress(frame, start, 30);
  const t = progress(frame, start + 8, 45);
  const s = progress(frame, start + 22, 35);
  const out = end === null ? 1 : interpolate(frame, [end - 20, end], [1, 0], clamp);
  return (
    <>
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(to top, rgba(0,0,0,0.75) 0%, rgba(0,0,0,0) 38%)",
          opacity: k * out,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 140,
          right: 140,
          bottom: 110,
          opacity: out,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 20,
            fontFamily: fonts.sans,
            fontWeight: 600,
            fontSize: 30,
            letterSpacing: "0.32em",
            color: colors.gold,
            opacity: k,
          }}
        >
          <div style={{ width: 70 * k, height: 2, background: colors.gold }} />
          {kicker}
        </div>
        <div
          style={{
            marginTop: 18,
            fontFamily: fonts.serif,
            fontWeight: 700,
            fontSize: titleSize,
            lineHeight: 1.05,
            color: colors.ink,
            letterSpacing: `${0.2 - 0.14 * t}em`,
            opacity: t,
            filter: `blur(${(1 - t) * 10}px)`,
          }}
        >
          {title}
        </div>
        {sub ? (
          <div
            style={{
              marginTop: 20,
              fontFamily: fonts.sans,
              fontWeight: 300,
              fontSize: 44,
              color: colors.ink,
              opacity: s * 0.85,
              translate: `0 ${(1 - s) * 12}px`,
            }}
          >
            {sub}
          </div>
        ) : null}
      </div>
    </>
  );
};
