/**
 * Farben und Tokens.
 *
 * Zwei Quellen, bewusst getrennt:
 *
 *  - **Chrome** (Flächen, Text, Linien) kommt aus Home Assistants
 *    Theme-Variablen. Das Panel soll aussehen wie der Rest der Installation,
 *    nicht wie ein Fremdkörper.
 *
 *  - **Seriendaten** kommen aus einer festen, geprüften Palette. HA-Themes
 *    sind beliebig; eine Kurvenfarbe, die mal gegen Weiß und mal gegen
 *    Dunkelgrau anläuft, wäre nicht mehr lesbar. Deshalb wird die Helligkeit
 *    der Kartenfläche gemessen und die für diesen Grund geprüfte Variante
 *    gewählt.
 *
 * Die Paletten wurden gegen Lightness-Band, Chroma, Normalsicht-Abstand und
 * Farbsinnstörungen geprüft (OKLab ΔE); Orange und Rot fielen als Paar durch
 * und werden deshalb nie als zwei Serien nebeneinander gezeigt — Rot tritt
 * nur im divergierenden Formband auf, wo zusätzlich die Richtung trägt.
 */

const PALETTE = {
  light: {
    fitness: "#2a78d6",
    fatigue: "#eb6834",
    formPos: "#2a78d6",
    formNeg: "#e34948",
    planGhost: "#86b6ef",
    planActual: "#2a78d6",
    zones: ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"],
    grid: "rgba(16,22,26,0.10)",
    baseline: "rgba(16,22,26,0.22)",
  },
  dark: {
    fitness: "#3987e5",
    fatigue: "#d95926",
    formPos: "#3987e5",
    formNeg: "#e66767",
    planGhost: "#184f95",
    planActual: "#3987e5",
    zones: ["#b7d3f6", "#86b6ef", "#5598e7", "#2a78d6", "#1c5cab"],
    grid: "rgba(242,246,248,0.11)",
    baseline: "rgba(242,246,248,0.24)",
  },
};

const STATUS = { good: "#0ca30c", warning: "#fab219", critical: "#d03b3b" };

/** Relative Helligkeit nach WCAG. */
function luminance(r, g, b) {
  const f = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

/**
 * Hell oder dunkel? Gemessen, nicht geraten: der aufgelöste Hintergrund des
 * Elements wird ausgelesen. Damit stimmt es auch bei eigenen HA-Themes, die
 * weder `prefers-color-scheme` noch eine Theme-Klasse setzen.
 */
export function detectMode(el) {
  try {
    const bg = getComputedStyle(el).getPropertyValue("--card-background-color")
      || getComputedStyle(el).backgroundColor;
    const m = String(bg).match(/(\d+(?:\.\d+)?)/g);
    if (m && m.length >= 3) {
      return luminance(+m[0], +m[1], +m[2]) < 0.4 ? "dark" : "light";
    }
  } catch {
    /* unten Rückfall */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function palette(mode) {
  return { ...PALETTE[mode] || PALETTE.light, status: STATUS };
}

/** Chrome über HA-Variablen, mit eigenen Werten als Rückfall. */
/** Phasenfarben — aus der geprüften Zonenrampe, nicht frei gewählt. */
export function phaseColor(phase, p) {
  const i = { Wiederaufbau: 0, Entwicklung: 2, "Schärfung": 3, Taper: 4 };
  return p.zones[i[phase] ?? 1];
}

export const CSS_TOKENS = `
  --ink:        var(--primary-text-color, #10161a);
  --ink-2:      var(--secondary-text-color, #4a565e);
  --ink-3:      var(--disabled-text-color, #7e8b93);
  --surface:    var(--card-background-color, #fbfcfd);
  --plane:      var(--primary-background-color, #eef1f3);
  --rule:       var(--divider-color, rgba(16,22,26,0.10));
  --accent:     var(--primary-color, #2a78d6);
  --radius:     var(--ha-card-border-radius, 14px);
  --radius-sm:  8px;
  --gap:        16px;
  --pad:        20px;
  --sans:       var(--paper-font-body1_-_font-family, system-ui, -apple-system, sans-serif);
  --mono:       ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
`;
