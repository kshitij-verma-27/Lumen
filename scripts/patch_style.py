import re
from pathlib import Path

css_path = Path("frontend/style.css")
with open(css_path, "r", encoding="utf-8") as f:
    orig_css = f.read()

# New Design System Tokens, Atkinson Hyperlegible, High-Contrast, 48px buttons, and Chat Thread Layout
new_header = """/* ==========================================================================
   LUMEN — Calm Research Notebook & Information-Gap Engine
   Aesthetic: Warm Paper (#FBFAF7) / Charcoal (#1C1B19) / High-Contrast
   Body Font: Atkinson Hyperlegible (with Noto Sans / Devanagari fallbacks)
   Title Font: Newsreader (serif only for page titles)
   Base Font Size: 18px (scalable 16-24px)
   Buttons: Min 48px height, strong focus rings, high contrast >= 7:1
   ========================================================================== */

@import url('fonts/fonts.css');

:root,
[data-theme="light"] {
  --bg-page: #FBFAF7;
  --bg-surface: #FFFFFF;
  --bg-sidebar: #F4F1EA;
  --bg-hover: #ECE8E0;
  --bg-active: #E2DDD3;
  --bg-callout: #F2EEE5;

  /* Contrast ratio >= 7:1 on #FBFAF7 and #FFFFFF */
  --text-primary: #1A1D20;
  --text-secondary: #3D424A;
  --text-tertiary: #4A5059;
  --text-muted: #4A5059;
  --text-inverse: #FFFFFF;

  --border-hairline: #D0CDC7;
  --border-strong: #A8A49C;
  --border-dashed: #B5B1A8;

  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;

  /* Muted Tag Palette with high contrast text */
  --tag-sage-bg: #E7EFEA;
  --tag-sage-text: #1B4430;
  --tag-amber-bg: #FEF3C7;
  --tag-amber-text: #78350F;
  --tag-brick-bg: #FEE2E2;
  --tag-brick-text: #7F1D1D;
  --tag-blue-bg: #E0F2FE;
  --tag-blue-text: #075985;
  --tag-neutral-bg: #ECE8E0;
  --tag-neutral-text: #2D3136;

  /* Ink Accent */
  --accent-ink: #1B3F68;
  --accent: #1B3F68;

  /* Redaction */
  --highlight-yellow: #FEF08A;
  --highlight-yellow-text: #1A1D20;
  --redaction-bg: #000000;
  --redaction-text-reveal: #FFFFFF;

  --font-serif: 'Newsreader', Georgia, Cambria, 'Times New Roman', serif;
  --font-sans: 'Atkinson Hyperlegible', 'Noto Sans', 'Noto Sans Devanagari', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', SFMono-Regular, Menlo, Monaco, Consolas, monospace;

  --shadow-notion: 0 1px 3px rgba(0, 0, 0, 0.06);
  --shadow-popover: 0 4px 16px rgba(0, 0, 0, 0.10);
}

[data-theme="dark"] {
  --bg-page: #1A1917;
  --bg-surface: #242320;
  --bg-sidebar: #151412;
  --bg-hover: #2E2D29;
  --bg-active: #393833;
  --bg-callout: #292825;

  /* Contrast ratio >= 7:1 on #1A1917 and #242320 */
  --text-primary: #F7F5F0;
  --text-secondary: #CCC7BD;
  --text-tertiary: #B8B3A8;
  --text-muted: #B8B3A8;
  --text-inverse: #1A1917;

  --border-hairline: #423E37;
  --border-strong: #69655D;
  --border-dashed: #555149;

  /* Tag Palette Dark */
  --tag-sage-bg: #1B3328;
  --tag-sage-text: #C6F6D5;
  --tag-amber-bg: #3B2606;
  --tag-amber-text: #FEEBC8;
  --tag-brick-bg: #3E1618;
  --tag-brick-text: #FED7D7;
  --tag-blue-bg: #0C2E47;
  --tag-blue-text: #BAE6FD;
  --tag-neutral-bg: #2E2D29;
  --tag-neutral-text: #EDEAE4;

  /* Ink Accent Dark */
  --accent-ink: #8AB4F8;
  --accent: #8AB4F8;

  --highlight-yellow: #543A14;
  --highlight-yellow-text: #FEF9C3;
  --redaction-bg: #000000;
  --redaction-text-reveal: #F7F5F0;

  --shadow-notion: 0 1px 3px rgba(0, 0, 0, 0.35);
  --shadow-popover: 0 6px 20px rgba(0, 0, 0, 0.55);
}

[data-theme="high-contrast"] {
  --bg-page: #000000;
  --bg-surface: #121212;
  --bg-sidebar: #0A0A0A;
  --bg-hover: #222222;
  --bg-active: #333333;
  --bg-callout: #181818;

  --text-primary: #FFFFFF;
  --text-secondary: #FFFFFF;
  --text-tertiary: #EEEEEE;
  --text-muted: #EEEEEE;
  --text-inverse: #000000;

  --border-hairline: #FFFFFF;
  --border-strong: #FFFFFF;
  --border-dashed: #FFFFFF;

  --tag-sage-bg: #003300;
  --tag-sage-text: #FFFFFF;
  --tag-amber-bg: #443300;
  --tag-amber-text: #FFFF00;
  --tag-brick-bg: #550000;
  --tag-brick-text: #FFFFFF;
  --tag-blue-bg: #002255;
  --tag-blue-text: #FFFFFF;
  --tag-neutral-bg: #222222;
  --tag-neutral-text: #FFFFFF;

  --accent-ink: #FFFF00;
  --accent: #FFFF00;

  --highlight-yellow: #FFFF00;
  --highlight-yellow-text: #000000;
  --redaction-bg: #000000;
  --redaction-text-reveal: #FFFFFF;

  --shadow-notion: none;
  --shadow-popover: 0 0 0 2px #FFFFFF;
}

html {
  font-size: 18px;
}

body.notion-body {
  background-color: var(--bg-page);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 1rem;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Page titles strictly serif */
h1, .chat-greeting, .document-title, .serif-heading {
  font-family: var(--font-serif);
  font-weight: 500;
  color: var(--text-primary);
  letter-spacing: -0.015em;
}

h2, h3, h4, h5, h6 {
  font-family: var(--font-sans);
  font-weight: 600;
  color: var(--text-primary);
}

p, li, .chat-message-text {
  max-width: 72ch;
  line-height: 1.6;
}

/* No body text below 16px */
small, .badge, .chip-sub, .footnote-ref, .stat-pill, .signal-pill, .composer-sources-note, .property-hint, .history-meta, .breadcrumb-item, .breadcrumb-current {
  font-size: max(0.888rem, 16px) !important;
}

/* Universal Button Sizing Mandate: Min 48px height, visible text beside icon */
button,
.notion-btn-primary,
.notion-btn-secondary,
.notion-btn-subtle,
.notion-btn-ghost,
.sidebar-link-btn,
.sidebar-action-btn,
.theme-toggle-btn,
.contrast-toggle-btn,
.btn-composer-send,
.btn-composer-secondary,
.btn-control,
.btn-demo-primary,
.sidebar-open-btn,
.sidebar-close-btn {
  min-height: 48px !important;
  font-size: 1rem !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 8px !important;
  padding: 10px 18px !important;
  border-radius: var(--radius-md) !important;
  font-family: inherit !important;
  font-weight: 500 !important;
  cursor: pointer !important;
  text-decoration: none !important;
}

/* Clear visible focus ring on all interactive elements */
button:focus-visible,
a:focus-visible,
input:focus-visible,
textarea:focus-visible,
select:focus-visible,
summary:focus-visible,
[tabindex="0"]:focus-visible {
  outline: 3px solid var(--accent-ink) !important;
  outline-offset: 2px !important;
}

/* Redaction Bars: Solid black until interacted with (tap/hover) */
.redaction-bar {
  background: #000000 !important;
  color: #000000 !important;
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  display: inline-block;
  cursor: pointer;
  user-select: none;
  font-weight: 600;
  transition: background 0.2s ease, color 0.2s ease;
  line-height: 1.4;
  border: 1px solid transparent;
}

.redaction-bar:hover,
.redaction-bar:focus,
.redaction-bar.revealed {
  background: #2D2D2D !important;
  color: #FFFFFF !important;
  user-select: text;
  border-color: var(--border-hairline);
}

[data-theme="dark"] .redaction-bar:hover,
[data-theme="dark"] .redaction-bar:focus,
[data-theme="dark"] .redaction-bar.revealed {
  background: #3A3833 !important;
  color: #F7F5F0 !important;
}

[data-theme="high-contrast"] .redaction-bar {
  border: 2px solid #FFFFFF !important;
}

[data-theme="high-contrast"] .redaction-bar:hover,
[data-theme="high-contrast"] .redaction-bar:focus,
[data-theme="high-contrast"] .redaction-bar.revealed {
  background: #FFFFFF !important;
  color: #000000 !important;
}

/* ==========================================================================
   CHAT CONVERSATION THREAD LAYOUT (ChatGPT-like)
   ========================================================================== */
.chat-container {
  max-width: 760px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 60px);
  position: relative;
}

.chat-thread-scroll {
  flex: 1;
  padding: 24px 16px 32px 16px;
  overflow-y: auto;
}

/* Empty State */
.chat-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 36px 8px 24px 8px;
}

.chat-greeting {
  font-size: 2.3rem;
  margin-bottom: 12px;
  line-height: 1.25;
}

.chat-greeting-desc {
  font-size: 1.15rem;
  color: var(--text-secondary);
  margin-bottom: 32px;
  max-width: 65ch;
}

.suggestion-chips-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  width: 100%;
  margin-bottom: 24px;
}

.suggestion-chip {
  background: var(--bg-surface);
  border: 1px solid var(--border-hairline);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  text-align: left;
  cursor: pointer;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  transition: border-color 0.15s, background 0.15s, transform 0.1s;
  min-height: 72px;
}

.suggestion-chip:hover {
  border-color: var(--accent-ink);
  background: var(--bg-hover);
  transform: translateY(-1px);
}

.chip-icon {
  font-size: 1.5rem;
  line-height: 1;
}

.chip-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chip-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-primary);
}

.chip-sub {
  font-size: 0.95rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

.demo-action-row {
  display: flex;
  justify-content: center;
  width: 100%;
  margin: 12px 0 28px 0;
}

.btn-demo-primary {
  background: var(--tag-sage-bg) !important;
  color: var(--tag-sage-text) !important;
  border: 1.5px solid var(--tag-sage-text) !important;
  font-weight: 600 !important;
  font-size: 1.1rem !important;
  padding: 14px 28px !important;
  border-radius: var(--radius-md) !important;
  box-shadow: var(--shadow-notion) !important;
}

.btn-demo-primary:hover {
  filter: brightness(0.97);
}

/* Chat Messages */
.chat-messages-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
}

.chat-msg {
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  border: 1px solid var(--border-hairline);
  background: var(--bg-surface);
}

.user-msg {
  background: var(--bg-surface);
  border-left: 4px solid var(--accent-ink);
}

.msg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
}

.msg-author {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 1.05rem;
}

.msg-time {
  font-size: 0.95rem;
  color: var(--text-secondary);
  font-weight: normal;
}

.user-query-text {
  font-size: 1.15rem;
  font-weight: 500;
  line-height: 1.5;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.attached-sources-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.source-tag-chip {
  background: var(--tag-neutral-bg);
  color: var(--tag-neutral-text);
  border: 1px solid var(--border-hairline);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 0.9rem;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* Assistant Message Working State */
.assistant-working-line {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  font-size: 1.1rem;
  color: var(--accent-ink);
  font-weight: 500;
}

.progress-spinner {
  width: 22px;
  height: 22px;
  border: 3px solid var(--border-hairline);
  border-top-color: var(--accent-ink);
  border-radius: 50%;
  animation: lumenSpin 0.75s linear infinite;
}

@keyframes lumenSpin {
  to { transform: rotate(360deg); }
}

/* Assistant Finished Message */
.assistant-summary-box {
  background: var(--bg-hover);
  border-left: 4px solid var(--accent-ink);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  padding: 14px 18px;
  margin-bottom: 20px;
  font-size: 1.1rem;
  line-height: 1.6;
}

.assistant-summary-box strong {
  color: var(--text-primary);
}

.signals-summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-hairline);
}

.signal-badge {
  min-height: 42px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  font-size: 0.95rem;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid transparent;
}

.signal-badge.sage { background: var(--tag-sage-bg); color: var(--tag-sage-text); border-color: var(--tag-sage-text); }
.signal-badge.amber { background: var(--tag-amber-bg); color: var(--tag-amber-text); border-color: var(--tag-amber-text); }
.signal-badge.brick { background: var(--tag-brick-bg); color: var(--tag-brick-text); border-color: var(--tag-brick-text); }
.signal-badge.blue { background: var(--tag-blue-bg); color: var(--tag-blue-text); border-color: var(--tag-blue-text); }
.signal-badge.neutral { background: var(--tag-neutral-bg); color: var(--tag-neutral-text); border-color: var(--border-hairline); }

.why-this-link {
  color: inherit;
  text-decoration: underline;
  font-size: 0.9rem;
  opacity: 0.85;
  margin-left: 4px;
  cursor: pointer;
}

.why-this-link:hover {
  opacity: 1;
}

.friendly-coverage-message {
  background: var(--tag-amber-bg);
  color: var(--tag-amber-text);
  border: 1.5px solid var(--tag-amber-text);
  border-radius: var(--radius-md);
  padding: 14px 18px;
  font-size: 1.05rem;
  font-weight: 500;
  margin-bottom: 18px;
  width: 100%;
}

/* Collapsible Result Sections */
.result-collapsible {
  border: 1px solid var(--border-hairline);
  border-radius: var(--radius-md);
  margin-bottom: 14px;
  background: var(--bg-surface);
  overflow: hidden;
}

.result-collapsible summary {
  padding: 16px 20px;
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  background: var(--bg-page);
  user-select: none;
  list-style: none;
  border-bottom: 1px solid transparent;
  transition: background 0.15s;
}

.result-collapsible summary::-webkit-details-marker {
  display: none;
}

.result-collapsible summary:hover {
  background: var(--bg-hover);
}

.result-collapsible[open] summary {
  border-bottom-color: var(--border-hairline);
}

.summary-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-inner-content {
  padding: 20px;
}

/* Checklist Items */
.action-check-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-check-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-hover);
  border-radius: var(--radius-md);
}

.action-check-item input[type="checkbox"] {
  width: 22px;
  height: 22px;
  margin-top: 2px;
  accent-color: var(--accent-ink);
  cursor: pointer;
}

.action-check-label {
  font-size: 1.05rem;
  color: var(--text-primary);
  line-height: 1.5;
  cursor: pointer;
}

/* Evidence Quotes */
.evidence-quote-item {
  padding: 12px 16px;
  border-left: 3px solid var(--tag-sage-text);
  background: var(--bg-hover);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  margin-bottom: 12px;
}

.evidence-quote-text {
  font-style: italic;
  font-size: 1.05rem;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.evidence-quote-meta {
  font-size: 0.95rem;
  color: var(--text-secondary);
  display: flex;
  gap: 12px;
  align-items: center;
}

/* Sources List */
.source-used-card {
  padding: 12px 16px;
  border: 1px solid var(--border-hairline);
  border-radius: var(--radius-md);
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-surface);
}

.source-used-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.source-used-title {
  font-weight: 600;
  font-size: 1.05rem;
  color: var(--text-primary);
}

.source-used-hash {
  font-family: var(--font-mono);
  font-size: 0.9rem;
  color: var(--text-secondary);
}

/* Fixed Composer at bottom */
.chat-composer-fixed-wrap {
  position: sticky;
  bottom: 0;
  background: var(--bg-surface);
  border-top: 1px solid var(--border-hairline);
  padding: 14px 16px 16px 16px;
  z-index: 100;
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.05);
}

.composer-box-inner {
  border: 1.5px solid var(--border-strong);
  border-radius: var(--radius-lg);
  padding: 12px 16px;
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.composer-box-inner:focus-within {
  border-color: var(--accent-ink);
  box-shadow: 0 0 0 3px rgba(27, 63, 104, 0.15);
}

.composer-textarea {
  width: 100%;
  border: none;
  background: transparent;
  resize: none;
  min-height: 52px;
  max-height: 180px;
  font-family: inherit;
  font-size: 1.1rem;
  line-height: 1.5;
  color: var(--text-primary);
  outline: none;
}

.composer-attached-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 0;
}

.composer-chip-item {
  background: var(--tag-blue-bg);
  color: var(--tag-blue-text);
  border: 1px solid var(--tag-blue-text);
  border-radius: var(--radius-sm);
  padding: 4px 12px;
  font-size: 0.95rem;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.composer-chip-remove {
  background: none;
  border: none;
  color: inherit;
  font-weight: bold;
  cursor: pointer;
  padding: 0 2px;
  font-size: 1rem;
}

.composer-bar-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 4px;
}

.btn-composer-secondary {
  background: var(--bg-hover) !important;
  color: var(--text-primary) !important;
  border: 1px solid var(--border-hairline) !important;
}

.btn-composer-send {
  background: var(--accent-ink) !important;
  color: #FFFFFF !important;
  border: 1.5px solid var(--accent-ink) !important;
  font-weight: 600 !important;
  padding: 10px 24px !important;
}

/* Sidebar Drawer on Mobile & Backdrop */
.sidebar-backdrop {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 998;
}

.sidebar-backdrop.active {
  display: block;
}

.sidebar-close-btn {
  display: none;
  background: transparent !important;
  border: 1px solid var(--border-hairline) !important;
  color: var(--text-primary) !important;
  padding: 8px 12px !important;
}

.sidebar-open-btn {
  display: none;
}

/* Mobile & Responsive Rules */
@media (max-width: 768px) {
  .notion-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: 290px;
    max-width: 85vw;
    z-index: 1000;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.3);
  }

  .notion-sidebar.drawer-open {
    transform: translateX(0);
  }

  .sidebar-close-btn {
    display: inline-flex !important;
  }

  .sidebar-open-btn {
    display: inline-flex !important;
  }

  .suggestion-chips-grid {
    grid-template-columns: 1fr;
  }

  .app-layout, body, .notion-main-wrap, .notion-document-column {
    overflow-x: hidden !important;
    max-width: 100vw;
  }

  .chat-composer-fixed-wrap {
    position: sticky;
    bottom: 0;
    padding: 10px;
  }
}

@media (max-width: 360px) {
  html {
    font-size: 16px;
  }
  .composer-bar-bottom {
    flex-direction: column;
    align-items: stretch;
  }
  .btn-composer-send, .btn-composer-secondary {
    width: 100%;
    justify-content: center;
  }
}
"""

with open(css_path, "w", encoding="utf-8") as f:
    f.write(new_header + "\n\n" + orig_css)

print("Successfully injected new design system and chat layout into frontend/style.css")
