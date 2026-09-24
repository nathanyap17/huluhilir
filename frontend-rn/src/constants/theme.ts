/**
 * PepperDex design tokens -- "Organic Modernism" (pitch-and-design/MOCK_DESIGN.md
 * §3-§5). Token NAMES are kept from the first build so every screen picks up
 * the new language without re-plumbing; the values follow the brief.
 *
 * Deviations from the brief, both forced by its own §2.3 contrast rule:
 *  - white text on water (#28C4EE) is ~2.3:1, so anything filled with water
 *    uses ink text (`onAccent`, ~8.9:1) instead of white;
 *  - water as TEXT on paper is too faint outdoors, so links use `accentInk`.
 */
export const colors = {
  // Surfaces
  background: "#F3F0E5", // warm paper
  paperDeep: "#E9E3D2", // recessed wells, input fills
  surface: "#FFFFFF", // cards, elevated above paper
  brandDark: "#1B3326", // deep vine green -- headers, the Rain Pulse card
  border: "#E2DCCB",

  // Ink
  text: "#15251B",
  textMuted: "#6B5340", // clay -- captions, metadata (6.9:1 on paper)
  onDark: "#F3F0E5",

  // Interaction -- water
  accent: "#28C4EE",
  accentGlow: "#7FF0FF",
  accentInk: "#0B6680", // links / accent-coloured text on paper
  onAccent: "#15251B",

  // Leaf green: confirmations, selected chips, farmer-positive states that are
  // NOT block state. White text on it is 6.4:1.
  brandGreen: "#2E6B47",
  brandLight: "#8FBF8F",
  berryRed: "#9B2D5F",

  // Errors and cautions deliberately avoid the four state hues (brief §3:
  // a form error must never read as "your plant is dying").
  danger: "#9B2D5F",
  warning: "#8A5A2B",

  // Block state -- load-bearing, reserved for state only (brief §3)
  stateProtected: "#4F8A5B",
  stateAlerted: "#C98A1E",
  stateHarmed: "#B2422A",
  stateOverrun: "#7A2E24",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 20, // brief §5: 20 dp screen padding
  xl: 32,
} as const;

export const radius = {
  sm: 10,
  button: 16, // brief §5
  md: 20, // cards -- the primary "organic" signal
  lg: 24,
  pill: 999,
} as const;

/** Loaded in app/_layout.tsx. On Android a custom family must be named per
 * weight -- never combine these with fontWeight. */
export const fonts = {
  display: "BricolageGrotesque_800ExtraBold", // screen titles, wordmark
  displayBold: "BricolageGrotesque_700Bold", // card headlines
  body: "IBMPlexSans_400Regular",
  bodyMedium: "IBMPlexSans_500Medium",
  bodySemi: "IBMPlexSans_600SemiBold",
  mono: "IBMPlexMono_500Medium", // stats, technical values, small labels
} as const;

/** One soft, single-direction shadow (brief §5) -- not a different one per card. */
export const shadow = {
  card: {
    shadowColor: "#15251B",
    shadowOpacity: 0.08,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
} as const;

export const stateColor: Record<string, string> = {
  protected: colors.stateProtected,
  alerted: colors.stateAlerted,
  harmed: colors.stateHarmed,
  overrun: colors.stateOverrun,
};
