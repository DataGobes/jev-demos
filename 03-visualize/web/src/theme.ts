/**
 * Vega-Lite theme for the demo's dark surface.
 *
 * Presentation only: the backend decides *what* chart to emit and Jev ranks it,
 * so nothing here may change either. Keeping the theme on this side also leaves
 * `golden.toml` and the eval fixtures untouched, so a restyle can never perturb
 * a recorded eval result.
 *
 * The token values below mirror `app.css`'s custom properties. Vega renders to
 * canvas and cannot resolve `var(--...)`, so the literals have to live here;
 * change one and change the other.
 */

const SURFACE = "#171a21"; // --panel: the surface charts are drawn on
const LINE = "#262b36"; // --line
const TEXT = "#e6e8ee"; // --text
const MUTED = "#8b93a7"; // --muted

const FONT = "ui-sans-serif, system-ui, -apple-system, sans-serif";

/**
 * Categorical hues, assigned in fixed order and never cycled.
 *
 * Validated for the dark band against SURFACE (lightness band, chroma floor,
 * adjacent-pair CVD separation, normal-vision floor, 3:1 contrast). The demo's
 * rules cap series at 8 (`multi_line` needs `n.distinct <= 8`), which is exactly
 * this list, so no chart ever runs off the end.
 *
 * The app accent (--accent #ff7a3d) is deliberately absent: at OKLCH L 0.726 it
 * sits outside the 0.48-0.67 dark band and fails validation as a series color.
 * It stays a UI accent, so orange in this demo always reads as "Jev's judgment"
 * rather than as a data series.
 */
const CATEGORY = [
  "#3987e5", // blue
  "#d95926", // orange
  "#199e70", // aqua
  "#c98500", // yellow
  "#d55181", // magenta
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
];

/** Sequential ramp for the heatmap rule: one hue, near-zero recedes toward the surface. */
const RAMP = ["#104281", "#184f95", "#256abf", "#3987e5", "#5598e7", "#86b6ef", "#b7d3f6"];

const axisBase = {
  labelFont: FONT,
  titleFont: FONT,
  labelColor: MUTED,
  titleColor: MUTED,
  labelFontSize: 11,
  titleFontSize: 11,
  titleFontWeight: 500 as const,
  domainColor: LINE,
  tickColor: LINE,
  gridColor: LINE,
  gridOpacity: 0.6,
  labelPadding: 6,
  labelOverlap: true,
  // Vega scales tick count to axis length, which on a full-width single panel
  // means ticks every 20 units. A fixed budget also stops a 1-5 rating axis
  // being labelled in meaningless half-steps.
  tickCount: 6,
};

export const vegaTheme = {
  background: "transparent",
  font: FONT,
  padding: 4,
  // Vega-Lite draws a border around the plot area by default; on a panel that
  // already has a border it reads as a box inside a box.
  view: { stroke: null },
  axis: axisBase,
  // A horizontal title above the axis instead of a rotated one beside it: the
  // rotated title costs ~20px of width in a half-width panel and is harder to read.
  axisY: { ...axisBase, grid: true, domain: false, ticks: false, titleAngle: 0, titleAlign: "left", titleAnchor: "start", titleBaseline: "bottom", titleX: 0, titleY: -8 },
  axisX: { ...axisBase, grid: false },
  axisTemporal: { format: "%b %Y", labelAngle: 0, tickCount: 6 },
  // Vega rotates band labels to 90 degrees on its own, which collides with the
  // axis title and is far harder to read. Safe to pin flat: `bar` switches to a
  // horizontal layout above 8 categories, so a band x-axis is never crowded,
  // and `labelOverlap` still drops labels rather than letting them collide.
  axisBand: { labelAngle: 0 },
  legend: {
    // Below the plot, not above: a top legend and the horizontal y-axis title
    // both want the top-left corner, and the title is drawn outside the view
    // without reserving space, so they collide.
    orient: "bottom",
    direction: "horizontal",
    // The backend's `enc()` helper sets an explicit encoding title, which wins
    // over any config default, so the title is styled rather than removed -
    // inline beside the symbols so it costs no extra row.
    titleOrient: "left",
    titleFont: FONT,
    titleColor: MUTED,
    titleFontSize: 11,
    titleFontWeight: 500 as const,
    titlePadding: 6,
    labelFont: FONT,
    labelColor: MUTED,
    labelFontSize: 11,
    symbolType: "circle",
    symbolSize: 70,
    offset: 4,
    padding: 0,
    rowPadding: 2,
  },
  title: { font: FONT, color: TEXT, fontSize: 13, fontWeight: 600 as const, anchor: "start" as const },
  // 4px rounded data-ends, anchored to the baseline.
  bar: { cornerRadiusEnd: 4 },
  line: { strokeWidth: 2 },
  point: { size: 70, filled: true },
  // No stroke on `arc`: the `pie` rule emits an unaggregated `theta`, so a query
  // returning 360 rows draws 360 arcs that merely *group* by colour. Stroking
  // each one turns three slices into a starburst. `rect` is safe because the
  // heatmap's colour encoding carries `aggregate`, so Vega-Lite emits one mark
  // per cell.
  rect: { stroke: SURFACE, strokeWidth: 1 },
  range: { category: CATEGORY, heatmap: RAMP, ramp: RAMP },
  numberFormat: "~s", // 1800000 -> "1.8M"
};
