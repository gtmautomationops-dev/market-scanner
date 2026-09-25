// Synthesizes an original, royalty-free soundtrack for the WesternCiv video
// straight to public/westernciv-score.wav. No samples, no network: just sine
// waves and filtered noise, timed from src/westernciv/timeline.json so the
// chord changes land on the scene cuts and the final hit lands on ACCELERATE.
import fs from "node:fs";

const T = JSON.parse(fs.readFileSync(new URL("../src/westernciv/timeline.json", import.meta.url)));
const OUT = new URL("../public/westernciv-score.wav", import.meta.url);
const SR = 44100;

// Scene start times (seconds) on the final, transition-overlapped timeline.
const starts = {};
let f = 0;
for (const s of T.scenes) {
  starts[s.id] = f / T.fps;
  f += s.frames - T.transition;
}
const TOTAL = (f + T.transition) / T.fps;
const HIT = starts.Finale + T.finaleHit / T.fps;
const N = Math.ceil(TOTAL * SR);

const CHORDS = {
  Open: [110, 164.81, 220, 261.63],
  Greece: [87.31, 174.61, 220, 261.63, 349.23],
  Rome: [130.81, 196, 261.63, 329.63],
  Printing: [110, 164.81, 220, 261.63],
  Science: [98, 196, 246.94, 293.66],
  Enlightenment: [130.81, 261.63, 329.63, 392, 523.25],
  Machine: [110, 220, 261.63, 329.63],
  Information: [87.31, 174.61, 261.63, 349.23, 440],
  Kardashev: [73.42, 146.83, 220, 293.66, 329.63],
  Finale: [82.41, 164.81, 246.94, 329.63, 415.3],
  Resolve: [110, 220, 277.18, 329.63, 440, 554.37],
};

// Chord timeline: one entry per scene, plus the resolution on the hit.
const sections = T.scenes.map((s) => ({ t: starts[s.id], chord: CHORDS[s.id] }));
sections.push({ t: HIT, chord: CHORDS.Resolve });

let seed = 1234567;
const rand = () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const lerp = (a, b, t) => a + (b - a) * t;
const TAU = Math.PI * 2;

const L = new Float32Array(N);
const R = new Float32Array(N);

// ---- Pad + sub drone ----
const padLevel = (t) => {
  let v = lerp(0.12, 0.26, smooth(t / starts.Finale)); // slow build across history
  v *= smooth(t / 4); // fade in
  if (t > starts.Finale) v *= lerp(1, 1.35, smooth((t - starts.Finale) / (HIT - starts.Finale)));
  v *= 1 - smooth((t - (HIT - 0.7)) / 0.4) * (t < HIT ? 1 : 0); // a breath of silence before the hit
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
  const subLvl = t < HIT ? lerp(0.08, 0.22, smooth(t / HIT)) * smooth(t / 6) * (t > HIT - 0.7 ? 0 : 1) : 0;
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

// ---- Pulse: a heartbeat that starts with the machines and accelerates ----
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
const beats = [];
for (let t = starts.Machine; t < starts.Information; t += 1.0) beats.push([t, 0.35]);
for (let t = starts.Information; t < starts.Kardashev; t += 0.667) beats.push([t, 0.4]);
for (let t = starts.Kardashev; t < starts.Finale; t += 0.5) beats.push([t, 0.45]);
{
  let t = starts.Finale;
  const end = HIT - 0.75;
  while (t < end) {
    const k = (t - starts.Finale) / (end - starts.Finale);
    beats.push([t, lerp(0.45, 0.6, k)]);
    t += lerp(0.45, 0.1, Math.pow(k, 0.7));
  }
}
beats.forEach(([t, a]) => kick(t, a));

// ---- Riser into the hit ----
{
  const s = Math.floor(starts.Finale * SR);
  const e = Math.floor((HIT - 0.7) * SR);
  let y = 0;
  for (let i = s; i < e; i++) {
    const k = (i - s) / (e - s);
    const fc = 200 * Math.pow(30, k);
    const a = 1 - Math.exp((-TAU * fc) / SR);
    y += a * (rand() * 2 - 1 - y);
    const v = y * 0.35 * k * k;
    L[i] += v;
    R[i] += v;
  }
}

// ---- The hit ----
{
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
fs.mkdirSync(new URL("../public/", import.meta.url), { recursive: true });
fs.writeFileSync(OUT, buf);
console.log(`Wrote ${OUT.pathname} (${TOTAL.toFixed(2)}s, hit at ${HIT.toFixed(2)}s)`);
