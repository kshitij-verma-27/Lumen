---
name: ux-and-accessibility
description: WCAG 2.2 AA accessibility, keyboard navigation, plain language, multi-generational usability.
---

# UX and Accessibility Rules

## WCAG 2.2 Level AA Mandates
- Contrast ratio: Minimum 4.5:1 for body text, 3:1 for large text and UI components.
- Interactive targets: Minimum 44px x 44px touch area for all buttons, chips, and links.
- Focus rings: High-visibility 2px solid `#28435F` / `#8FB0D8` outline with 2px offset.
- Motion: Wrap all CSS transitions in `@media (prefers-reduced-motion: no-preference)`.

## Keyboard & Screen Reader Experience
- Complete keyboard accessibility: Tab, Shift+Tab, Enter, Space, Escape, and `/` for search.
- Semantic HTML landmarks: `<header>`, `<nav>`, `<main>`, `<aside>`, `<footer>`.
- ARIA: Dynamic updates use `aria-live="polite"`. Expandable areas use `aria-expanded`.
- Skip link: Visible on focus `#skip-to-content` jump link at page top.

## Multi-Generational Usability
- Font size control: User-accessible `A-` / `A+` scale buttons stored in preferences.
- High-contrast toggle mode for visually impaired users.
- Visible text labels: No cryptic icon-only buttons without text or `aria-label`.
- Redaction reveal: Touch/tap toggles missing item details on mobile; hover on desktop.

## Plain Language & Tone
- Plain language at Grade 8 reading level. Zero corporate or "AI magic" jargon.
- Clear error states explaining concrete next steps ("Source took too long; paste text").
- All suggestions explicitly marked as "potential signal", never as definitive advice.
