# UI Design System Rules

## Palette & Surface
- Light mode (warm paper): bg `#FBFAF7`, surface `#FFFFFF`, text `#1F2328`, muted `#6B6F76`, hairline `#E7E4DD`.
- Dark mode (warm charcoal): bg `#1C1B19`, surface `#252421`, text `#ECE9E2`, muted `#A09C94`, hairline `#34322E`.
- Single Ink Accent: Light `#28435F`, Dark `#8FB0D8`.
- Semantic Status Colors (Muted):
  - Verified: Sage `#5B8266`
  - Single-Source: Amber `#B7791F`
  - Conflict / Stale: Brick `#B4443C`
  - Informational: Dusty Blue `#4A6FA5`
  - Dark Spot / Missing: Solid Black `#000000` (reveals on hover/tap)

## Typography & Scale
- Headings: Serif (`Newsreader`, `Fraunces`, or Georgia fallback).
- Body & UI: Sans-serif (`Inter`, `DM Sans`, or system fallback).
- Quotes & Hashes: Monospace (`JetBrains Mono`, `Fira Code`, or monospace).
- Hindi Fallback: `Noto Sans Devanagari`.
- Scale: 12px, 14px, 16px, 18px, 22px, 28px, 36px. Line height 1.5.

## Shape & Elevation
- Radius: Strict 6px - 8px. Never round everything uniformly.
- Borders: 1px hairline border (`#E7E4DD` / `#34322E`).
- Shadows: Minimal soft elevation only for dropdowns, tooltips, and modals.
- Spacing: 4px / 8px grid system (4, 8, 12, 16, 24, 32, 48px).

## "Not AI-Looking" Mandate
- Prohibited: Neon gradients, glow filters, glassmorphism blur, purple/cyan AI schemes.
- Prohibited: Sparkle icons, cards-inside-cards, floating hero cards, emojis in headings.
- Required: Honest document aesthetic, quiet highlighters, footnote evidence tags.
