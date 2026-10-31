---
name: frontend-architecture
description: Component structure, state handling, routing by hash, performance budget.
---

# Frontend Architecture Rules

## Component Structure & Vanilla Discipline
- Use Vanilla JS + CSS with cleanly isolated view modules.
- Never introduce React, Vue, or heavy build steps unless explicitly requested.
- Maintain DOM templates with explicit semantic IDs and data attributes.
- Keep event delegation centralized at page boundaries.

## Routing by Hash
- Client-side navigation powered strictly by window hash (`#/`, `#/category/:id`, `#/entity/:id`, `#/source/:id`, `#/registry`, `#/investigate`).
- Listen to `hashchange` and `load` events to render matching views.
- Deep-linking supported for all entities, categories, and audit reports.
- Back and forward browser history must preserve state.

## State Management
- Global reactive state kept minimal in a single immutable-like Store object.
- State slices: `activeSession`, `currentEntity`, `userProfile`, `registry`, `filterState`.
- Profile state persists solely in browser `localStorage`.
- Never store API keys or remote tokens in client-side state.

## Performance Budget
- Total initial HTML + CSS + JS payload under 150KB uncompressed.
- Zero external runtime script dependencies (Google Fonts loaded with `display=swap`).
- First Contentful Paint (FCP) under 800ms on 3G connections.
- Offline-friendly demo mode with mock fallback when API is unreachable.
