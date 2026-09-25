/**
 * Note: When using the Node.JS APIs, the config file
 * doesn't apply. Instead, pass options directly to the APIs.
 *
 * All configuration options: https://remotion.dev/docs/config
 */

import fs from "node:fs";
import { Config } from "@remotion/cli/config";
import { enableTailwind } from "@remotion/tailwind-v4";

Config.setRspack(true);
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.overrideBundlerConfig(enableTailwind);

// Claude Code cloud sessions can't download Remotion's headless Chrome
// (remotion.media is blocked), but Playwright's Chromium is pre-installed.
// Use it when present; everywhere else Remotion downloads its own browser.
const preinstalledChromium =
  "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell";
const browser = process.env.REMOTION_BROWSER_EXECUTABLE ?? preinstalledChromium;
if (fs.existsSync(browser)) {
  Config.setBrowserExecutable(browser);
}
