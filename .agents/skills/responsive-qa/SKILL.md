---
name: responsive-qa
description: Breakpoints 360/768/1024/1440 checklist for all screens in light and dark themes.
---

# Responsive QA Checklist

## Target Viewport Breakpoints
- **Mobile (360px - 767px)**: Single column, sticky top search, bottom category navigation, touch redaction tap-to-reveal.
- **Tablet (768px - 1023px)**: Collapsed icon rail, 2-column card grid, inline drawer for verify details.
- **Desktop (1024px - 1439px)**: Full left category rail, 3-column card grid, dedicated right-rail inspector.
- **Wide Desktop (1440px+)**: Centered content container (max 1280px), side margins, expanded evidence matrix.

## Screen Verification Matrix
Each screen must be verified across 360px and 1440px in both Light and Dark themes:
1. **Home / Discovery**: Wide search bar, category chips, topic gallery, recently verified cards.
2. **Category Page**: Hierarchical breadcrumb, subcategory filter chips, sorted entity grid.
3. **Entity Page**: Properties strip, tab bar (Overview, Evidence, Gaps, Checklist, Sources), redaction bars, footnote popups.
4. **Source Page**: Trust badge, reason pills, reachability timestamp, change-watch diff view.
5. **Registry Manager**: Filterable source table, add-source form, validation status badge.
6. **Profile Popup**: Modal overlay, accessible inputs, clear-profile action.
7. **Investigation View**: Sourced claim highlighter, margin conflict cards, draft query generator.

## Visual & Layout Check Rules
- Zero horizontal scrolling on body at 360px width.
- Text never clips or overflows containers without ellipsis.
- Redaction bars remain solid black until explicitly interacted with.
- Touch tap targets stay >= 44px across all breakpoints.
