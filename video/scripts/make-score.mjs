// Synthesizes an original, royalty-free soundtrack for every video that has a
// src/<video>/timeline.json, writing public/<video>-score.wav. No samples, no
// network: sine waves and filtered noise, timed from the timeline so chord
// changes land on scene cuts and the optional "hit" lands on its frame.
//
//   node scripts/make-score.mjs            # all videos
//   node scripts/make-score.mjs westernciv # one video (folder name)
//
// timeline.json fields used here (all but fps/transition/scenes optional):
//   fps, transition               frames per second, crossfade length
//   scenes[]: { id, frames,
//     chord?      one of CHORDS below (default: cycles Am F C G)
//     bpm?        heartbeat pulse during this scene
//     accelerate? pulse speeds up and a riser builds until the hit }
//   hit?: { scene, frame, chord? }  a boom + resolution chord at that frame
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const SR = 44100;
const TAU = Math.PI * 2;

export const CHORDS = {
  Am: [110, 164.81, 220, 261.63],
  F: [87.31, 174.61, 220, 261.63, 349.23],
  C: [130.81, 196, 261.63, 329.63],
  G: [98, 196, 246.94, 293.66],
  Cbright: [130.81, 261.63, 329.63, 392, 523.25],
  Amwide: [110, 220, 261.63, 329.63],
  Fmaj7: [87.31, 174.61, 261.63, 349.23, 440],
  Dsus2: [73.42, 146.83, 220, 293.66, 329.63],
  E: [82.41, 164.81, 246.94, 329.63, 415.3],
  A: [110, 220, 277.18, 329.63, 440, 554.37],
  Dm: [73.42, 146.83, 220, 293.66, 349.23],
  Em: [82.41, 164.81, 246.94, 329.63, 392],
};
const DEFAULT_CYCLE = ["Am", "F", "C", "G"];

const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const lerp = (a, b, t) => a + (b - a) * t;

const chordFor = (name, where) => {
  const c = CHORDS[name];
  if (!c) throw new Error(`${where}: unknown chord "${name}". Use one of: ${Object.keys(CHORDS).join(", ")}`);
  return c;
};

const makeScore = (video) => {
  const T = JSON.parse(fs.readFileSync(path.join(ROOT, "src", video, "timeline.json"), "utf8"));
  const out = path.join(ROOT, "public", `${video}-score.wav`);

  let seed = 1234567;
  const rand = () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  // Scene start/end times (seconds) on the final, transition-overlapped timeline.
  const scenes = [];
  let f = 0;
  T.scenes.forEach((s, i) => {
    scenes.push({ ...s, start: f / T.fps, end: (f + s.frames) / T.fps, index: i });
    f += s.frames - T.transition;
  });
  const TOTAL = (f + T.transition) / T.fps;
  const N = Math.ceil(TOTAL * SR);
  const byId = Object.fromEntries(scenes.map((s) => [s.id, s]));

  let HIT = null;
  if (T.hit) {
    const s = byId[T.hit.scene];
    if (!s) throw new Error(`${video}: hit.scene "${T.hit.scene}" is not a scene id`);
    HIT = s.start + T.hit.frame / T.fps;
  }
  // The "climax" section: from the start of the hit scene to the hit.
  const climaxStart = HIT === null ? TOTAL : byId[T.hit.scene].start;
  const buildEnd = HIT ?? TOTAL;

  const sections = scenes.map((s, i) => ({
    t: s.start,
    chord: chordFor(s.chord ?? DEFAULT_CYCLE[i % DEFAULT_CYCLE.length], `${video} scene ${s.id}`),
  }));
  if (HIT !== null) sections.push({ t: HIT, chord: chordFor(T.hit.chord ?? "A", `${video} hit`) });

  const L = new Float32Array(N);
  const R = new Float32Array(N);

  // ---- Pad + sub drone ----
  const padLevel = (t) => {
    let v = lerp(0.12, 0.26, smooth(t / climaxStart)); // slow build across the video
    v *= smooth(t / 4); // fade in
    if (HIT === null) return v;
    if (t > climaxStart) v *= lerp(1, 1.35, smooth((t - climaxStart) / (HIT - climaxStart)));
    v *= 1 - smooth((t - (HIT - 0.7)) / 0.4) * (t < HIT ? 1 : 0); // a breath before the hit
    if (t >= HIT) v = 0.34 * Math.exp(-(t - HIT) * 0.12);
    return v;
  };

  let sec = 0;
  for (let i = 0; i < N; i++) {
    const t = i / SR;
    while (sec < sections.length - 1 && t >= sections[sec + 1].t) sec++;
    const xf = sec === 0 ? 1 : smooth((t - sections[sec].t) / (sections[sec].t === HIT ? 0.05 : 1.6));
    const mix = (chord, w) => {
      if (w <= 0) return [0, 0];
      let l = 0;
      let r = 0;
      chord.forEach((hz, n) => {
        const trem = 1 + 0.18 * Math.sin(TAU * 0.13 * t + n * 1.3);
        const pan = n % 2 ? 0.35 : -0.35;
        const vl = Math.sin(TAU * hz * t) + 0.25 * Math.sin(TAU * hz * 2 * t);
        const vr = Math.sin(TAU * (hz + 0.35) * t) + 0.25 * Math.sin(TAU * (hz + 0.35) * 2 * t);
        l += vl * trem * (1 - pan);
        r += vr * trem * (1 + pan);
      });
      return [(l * w) / chord.length, (r * w) / chord.length];
    };
    const [cl, cr] = mix(sections[sec].chord, xf);
    const [pl, pr] = sec > 0 ? mix(sections[sec - 1].chord, 1 - xf) : [0, 0];
    const lvl = padLevel(t);
    const silent = HIT !== null && t > HIT - 0.7;
    const subLvl = silent ? 0 : lerp(0.08, 0.22, smooth(t / buildEnd)) * smooth(t / 6);
    const sub = Math.sin(TAU * 55 * t) * subLvl;
    L[i] += (cl + pl) * lvl + sub;
    R[i] += (cr + pr) * lvl + sub;
  }

  // ---- Air: very quiet low-passed noise for texture ----
  {
    let yl = 0;
    let yr = 0;
    const a = 1 - Math.exp((-TAU * 900) / SR);
    for (let i = 0; i < N; i++) {
      yl += a * (rand() * 2 - 1 - yl);
      yr += a * (rand() * 2 - 1 - yr);
      const env = Math.min(1, i / SR / 3) * Math.min(1, (TOTAL - i / SR) / 2);
      L[i] += yl * 0.05 * env;
      R[i] += yr * 0.05 * env;
    }
  }

  // ---- Pulse: heartbeat kicks for scenes with a bpm, accelerating into the hit ----
  const kick = (at, amp) => {
    const start = Math.floor(at * SR);
    const len = Math.floor(0.45 * SR);
    for (let j = 0; j < len && start + j < N; j++) {
      const tau = j / SR;
      const phase = TAU * (45 * tau + (45 / 20) * (1 - Math.exp(-20 * tau)));
      const v = Math.sin(phase) * Math.exp(-tau * 8) * amp;
      L[start + j] += v;
      R[start + j] += v;
    }
  };
  const pulseScenes = scenes.filter((s) => s.bpm || s.accelerate);
  pulseScenes.forEach((s, k) => {
    const next = scenes[s.index + 1];
    const until = next ? next.start : TOTAL;
    const amp = Math.min(0.45, 0.35 + 0.05 * k);
    if (s.accelerate) {
      const end = (HIT ?? until) - 0.75;
      let t = s.start;
      while (t < end) {
        const p = (t - s.start) / (end - s.start);
        kick(t, lerp(0.45, 0.6, p));
        t += lerp(0.45, 0.1, Math.pow(p, 0.7));
      }
      // Riser: noise whose filter opens up towards the hit.
      const rs = Math.floor(s.start * SR);
      const re = Math.floor((end + 0.05) * SR);
      let y = 0;
      for (let i = rs; i < re && i < N; i++) {
        const p = (i - rs) / (re - rs);
        const a = 1 - Math.exp((-TAU * 200 * Math.pow(30, p)) / SR);
        y += a * (rand() * 2 - 1 - y);
        L[i] += y * 0.35 * p * p;
        R[i] += y * 0.35 * p * p;
      }
    } else {
      for (let t = s.start; t < until; t += 60 / s.bpm) kick(t, amp);
    }
  });

  // ---- The hit ----
  if (HIT !== null) {
    const s = Math.floor(HIT * SR);
    let y = 0;
    const a = 1 - Math.exp((-TAU * 2500) / SR);
    for (let j = 0; s + j < N; j++) {
      const tau = j / SR;
      const boom = Math.sin(TAU * (32 * tau + (40 / 6) * (1 - Math.exp(-6 * tau)))) * Math.exp(-tau * 1.1) * 0.9;
      y += a * (rand() * 2 - 1 - y);
      const noise = y * Math.exp(-tau * 5) * 0.6;
      L[s + j] += boom + noise;
      R[s + j] += boom + noise;
    }
  }

  // ---- Master: soft clip, final fade, normalize, write 16-bit WAV ----
  let peak = 0;
  for (let i = 0; i < N; i++) {
    const fadeOut = Math.min(1, (TOTAL - i / SR) / 1.5);
    L[i] = Math.tanh(L[i] * 1.1) * fadeOut;
    R[i] = Math.tanh(R[i] * 1.1) * fadeOut;
    peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
  }
  const gain = 0.9 / peak;
  const buf = Buffer.alloc(44 + N * 4);
  buf.write("RIFF", 0);
  buf.writeUInt32LE(36 + N * 4, 4);
  buf.write("WAVE", 8);
  buf.write("fmt ", 12);
  buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20);
  buf.writeUInt16LE(2, 22);
  buf.writeUInt32LE(SR, 24);
  buf.writeUInt32LE(SR * 4, 28);
  buf.writeUInt16LE(4, 32);
  buf.writeUInt16LE(16, 34);
  buf.write("data", 36);
  buf.writeUInt32LE(N * 4, 40);
  for (let i = 0; i < N; i++) {
    buf.writeInt16LE(Math.round(L[i] * gain * 32767), 44 + i * 4);
    buf.writeInt16LE(Math.round(R[i] * gain * 32767), 46 + i * 4);
  }
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, buf);
  const hitMsg = HIT === null ? "no hit" : `hit at ${HIT.toFixed(2)}s`;
  console.log(`Wrote public/${video}-score.wav (${TOTAL.toFixed(2)}s, ${hitMsg})`);
};

const requested = process.argv[2];
const videos = requested
  ? [requested]
  : fs
      .readdirSync(path.join(ROOT, "src"), { withFileTypes: true })
      .filter((d) => d.isDirectory() && fs.existsSync(path.join(ROOT, "src", d.name, "timeline.json")))
      .map((d) => d.name);
videos.forEach(makeScore);
