// One command to go from code to a shareable MP4 (or preview frames).
//
//   npm run video -- <CompositionId>                     render out/<Id>.mp4
//   npm run video -- <CompositionId> --frames=0,90,300   render PNG previews
//
// Always regenerates soundtracks first. If the MP4 is too big to send in a
// Claude chat (30 MB limit), also writes a smaller out/<Id>-share.mp4.
import { spawnSync } from "node:child_process";
import fs from "node:fs";

const SHARE_LIMIT = 28 * 1024 * 1024;

const [id, ...rest] = process.argv.slice(2);
if (!id) {
  console.error("Usage: npm run video -- <CompositionId> [--frames=0,90,300]");
  process.exit(1);
}
const frames = rest.find((a) => a.startsWith("--frames="));

const run = (cmd, args) => {
  const r = spawnSync(cmd, args, { stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status ?? 1);
};

run("node", ["scripts/make-score.mjs"]);

if (frames) {
  const dir = `out/${id}-frames`;
  fs.rmSync(dir, { recursive: true, force: true });
  run("npx", ["remotion", "render", id, dir, frames, "--image-format=png", "--scale=0.5"]);
  console.log(`Preview frames in ${dir}/`);
  process.exit(0);
}

const mp4 = `out/${id}.mp4`;
run("npx", ["remotion", "render", id, mp4]);
const size = fs.statSync(mp4).size;
console.log(`${mp4}: ${(size / 1048576).toFixed(1)} MB`);

if (size > SHARE_LIMIT) {
  for (const crf of [25, 29, 33]) {
    const share = `out/${id}-share.mp4`;
    run("npx", [
      "remotion", "ffmpeg", "-v", "error", "-y", "-i", mp4,
      "-c:v", "libx264", "-crf", String(crf), "-preset", "slow", "-pix_fmt", "yuv420p",
      "-c:a", "copy", "-movflags", "+faststart", share,
    ]);
    const s = fs.statSync(share).size;
    console.log(`${share}: ${(s / 1048576).toFixed(1)} MB (crf ${crf})`);
    if (s <= SHARE_LIMIT) break;
  }
}
