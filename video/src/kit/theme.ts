// Fonts are bundled from npm (@fontsource) so renders never depend on
// reaching Google Fonts at render time.
import "@fontsource/cinzel/400.css";
import "@fontsource/cinzel/700.css";
import "@fontsource/cormorant-garamond/500-italic.css";
import "@fontsource/cormorant-garamond/500.css";
import "@fontsource/inter/300.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/600.css";
import { continueRender, delayRender } from "remotion";

export const fonts = {
  serif: "Cinzel, serif",
  sans: "Inter, sans-serif",
  // Cinzel has no lowercase, so maths and mixed-case text use this instead.
  math: "\"Cormorant Garamond\", serif",
};

export const colors = {
  bg: "#07070a",
  ink: "#efe6d2",
  dim: "#8a8170",
  gold: "#d4a64a",
  goldBright: "#f3cf7a",
  blue: "#6fb3ff",
  sun: "#ffb347",
};

// Block rendering until the bundled fonts are actually loaded, otherwise the
// first frames can be captured with a fallback font.
const fontHandle = delayRender("Loading fonts");
Promise.all(
  [
    `400 64px Cinzel`,
    `700 64px Cinzel`,
    `italic 500 64px "Cormorant Garamond"`,
    `500 64px "Cormorant Garamond"`,
    `300 32px Inter`,
    `400 32px Inter`,
    `600 32px Inter`,
  ].map((f) => document.fonts.load(f)),
)
  .then(() => continueRender(fontHandle))
  .catch(() => continueRender(fontHandle));
