import re
from pathlib import Path

html_path = Path("frontend/index.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

# 1. Update font link in <head> to local bundled fonts (no CDN)
html = re.sub(
    r'<link rel="preconnect" href="https://fonts\.googleapis\.com">[\s\S]*?<link rel="stylesheet" href="/static/style\.css">',
    '<link rel="stylesheet" href="/static/fonts/fonts.css">\n  <link rel="stylesheet" href="/static/style.css">',
    html
)

# 2. Update head script to initialize lumen_font_scale (default 18)
html = html.replace(
    'const theme = params.get("theme")',
    'const savedScale = localStorage.getItem("lumen_font_scale") || "18"; document.documentElement.style.fontSize = savedScale + "px";\n      const theme = params.get("theme")'
)

# 3. Add backdrop before <aside id="sidebar">
if '<div id="sidebar-backdrop"' not in html:
    html = html.replace(
        '<aside id="sidebar" class="notion-sidebar">',
        '<div id="sidebar-backdrop" class="sidebar-backdrop" onclick="toggleSidebar()"></div>\n    <aside id="sidebar" class="notion-sidebar">'
    )

# 4. Redesign sidebar content
sidebar_pattern = r'<aside id="sidebar" class="notion-sidebar">[\s\S]*?</aside>'
new_sidebar = """<aside id="sidebar" class="notion-sidebar" aria-label="Main Navigation">
      <div class="sidebar-header">
        <div class="sidebar-brand" onclick="navigateToHome()" style="cursor: pointer;" title="Lumen — Finds what is missing">
          <span class="brand-icon">📓</span>
          <div style="display: flex; flex-direction: column;">
            <span class="brand-name" style="font-weight: 700; font-size: 1.15rem; line-height: 1.2;">Lumen</span>
            <span style="font-size: 0.85rem; color: var(--text-secondary); font-weight: normal;">Finds what is missing</span>
          </div>
        </div>
        <button id="btn-sidebar-close" class="sidebar-close-btn" onclick="toggleSidebar()" aria-label="Close navigation sidebar">
          <span aria-hidden="true">✕</span> <span>Close</span>
        </button>
      </div>

      <div class="sidebar-action-wrap" style="padding: 12px 10px 4px 10px;">
        <button id="btn-new-investigation" class="sidebar-action-btn" onclick="openNewInvestigation()" style="width: 100%; font-weight: 600; background: var(--accent-ink); color: #ffffff; border-color: var(--accent-ink);">
          <span class="btn-icon" aria-hidden="true" style="font-size: 1.2rem; font-weight: bold;">+</span> <span>New Investigation</span>
        </button>
      </div>

      <nav class="sidebar-nav" aria-label="Primary navigation">
        <button id="btn-sidebar-home" class="sidebar-link-btn" onclick="window.location.hash='#/'">
          <span class="btn-icon" aria-hidden="true">🏛️</span> <span>Home</span>
        </button>
        <button id="btn-sidebar-domains" class="sidebar-link-btn" onclick="window.location.hash='#/category/education'">
          <span class="btn-icon" aria-hidden="true">📂</span> <span>Explore (domains)</span>
        </button>
        <button id="btn-sidebar-registry" class="sidebar-link-btn" onclick="window.location.hash='#/registry'">
          <span class="btn-icon" aria-hidden="true">📋</span> <span>Source registry</span>
        </button>
        <button id="btn-open-profile" class="sidebar-link-btn" onclick="openProfileModal()">
          <span class="btn-icon" aria-hidden="true">👤</span> <span>Profile</span>
          <span id="profile-indicator" class="profile-status-dot"></span>
        </button>
      </nav>

      <div class="sidebar-section">
        <div class="sidebar-section-title">Past Investigations</div>
        <div id="sidebar-history-list" class="sidebar-history-list">
          <div class="history-empty">No past investigations yet.</div>
        </div>
      </div>

      <div class="sidebar-footer">
        <div class="sidebar-footer-row" style="display: flex; flex-direction: column; gap: 8px;">
          <button id="theme-toggle" class="theme-toggle-btn" onclick="toggleTheme()" title="Switch Light or Dark Theme" style="width: 100%;">
            <span id="theme-icon" aria-hidden="true">🌙</span> <span id="theme-text">Dark Mode</span>
          </button>
          <button id="sidebar-contrast-toggle" class="contrast-toggle-btn" onclick="toggleHighContrast()" title="Switch High-Contrast Mode" style="width: 100%;">
            <span aria-hidden="true">👁️</span> <span>High Contrast</span>
          </button>
        </div>
        <div id="llm-mode-badge" class="badge badge-mock" style="width: 100%; justify-content: center; margin-top: 0.5rem;">
          <span class="dot"></span>
          <span id="llm-mode-text">Checking LLM status...</span>
        </div>
      </div>
    </aside>"""

html = re.sub(sidebar_pattern, new_sidebar, html)

# 5. Redesign Header / Notion-Topbar
topbar_pattern = r'<header class="notion-topbar">[\s\S]*?</header>'
new_topbar = """<header class="notion-topbar">
        <div class="topbar-left">
          <button id="btn-sidebar-open" class="sidebar-open-btn" onclick="toggleSidebar()" aria-label="Open navigation sidebar" style="margin-right: 10px;">
            <span class="hamburger-icon" aria-hidden="true">☰</span> <span>Menu</span>
          </button>
          <div class="breadcrumbs">
            <span class="breadcrumb-item" onclick="navigateToHome()" style="cursor: pointer;">Notebook</span>
            <span class="breadcrumb-sep">/</span>
            <span id="breadcrumb-title" class="breadcrumb-current">Home</span>
          </div>
        </div>
        <div class="topbar-right">
          <div class="topbar-actions" style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <!-- Font size controls: scales 16px to 24px -->
            <div class="font-size-controls" role="group" aria-label="Text size scale controls" style="display: inline-flex; align-items: center; border: 1.5px solid var(--border-hairline); border-radius: var(--radius-md); overflow: hidden;">
              <button id="btn-font-decrease" class="notion-btn-ghost btn-mini" onclick="changeFontSize(-1)" title="Smaller text (A−)" aria-label="Decrease text size" style="padding: 10px 14px !important; min-height: 48px !important; font-size: 1rem !important;">
                <span aria-hidden="true" style="font-weight: bold;">A−</span> <span>Smaller</span>
              </button>
              <span id="font-size-display" class="font-size-val" style="padding: 0 10px; font-weight: 600; font-size: 1rem; color: var(--text-primary);">18px</span>
              <button id="btn-font-increase" class="notion-btn-ghost btn-mini" onclick="changeFontSize(1)" title="Larger text (A+)" aria-label="Increase text size" style="padding: 10px 14px !important; min-height: 48px !important; font-size: 1rem !important;">
                <span aria-hidden="true" style="font-weight: bold;">A+</span> <span>Larger</span>
              </button>
            </div>

            <!-- Topbar Theme Toggle -->
            <button id="topbar-theme-toggle" class="notion-btn-subtle" onclick="toggleTheme()" title="Switch Light or Dark Theme">
              <span id="topbar-theme-icon" aria-hidden="true">🌙</span> <span id="topbar-theme-text">Theme</span>
            </button>

            <!-- High Contrast Toggle -->
            <button id="btn-contrast-toggle" class="notion-btn-subtle" onclick="toggleHighContrast()" title="Toggle High-Contrast Mode">
              <span aria-hidden="true">👁️</span> <span>High Contrast</span>
            </button>

            <!-- Export Buttons -->
            <button id="btn-export-json" class="notion-btn-subtle" onclick="exportAuditTrailJson()" title="Download structured audit trail JSON">
              <span aria-hidden="true">📥</span> <span>Download JSON</span>
            </button>
            <button id="btn-export-html" class="notion-btn-subtle" onclick="exportAuditTrailHtml()" title="Open printable audit trail report">
              <span aria-hidden="true">🖨️</span> <span>Printable Report</span>
            </button>
            <button class="notion-btn-subtle" onclick="openProfileModal()" aria-label="Open personal profile modal">
              <span aria-hidden="true">👤</span> <span>Profile</span>
            </button>
          </div>
        </div>
      </header>"""

html = re.sub(topbar_pattern, new_topbar, html)

# 6. Redesign HOME VIEW to be the Calm ChatGPT-like Investigate Experience
home_pattern = r'<section id="home-view" class="home-screen-view">[\s\S]*?</section>'
new_home = """<section id="home-view" class="home-screen-view">
          <div class="chat-container">
            <div id="chat-thread-scroll" class="chat-thread-scroll">
              
              <!-- Empty State: Friendly Greeting, Composer, Suggestion Chips, 1-Click Demo -->
              <div id="chat-empty-state" class="chat-empty-state">
                <h1 class="chat-greeting">What would you like to check?</h1>
                <p class="chat-greeting-desc">We read multiple sources, find what is missing, and flag where sources disagree.</p>

                <!-- 4 Suggestion Chips -->
                <div class="suggestion-chips-grid" role="group" aria-label="Preset research questions">
                  <button type="button" class="suggestion-chip" onclick="selectSuggestion('scholarship')">
                    <span class="chip-icon" aria-hidden="true">🎓</span>
                    <div class="chip-content">
                      <div class="chip-title">Scholarship Scheme</div>
                      <div class="chip-sub">Check eligibility, deadlines, and benefits for students</div>
                    </div>
                  </button>

                  <button type="button" class="suggestion-chip" onclick="selectSuggestion('college_admission')">
                    <span class="chip-icon" aria-hidden="true">🏛️</span>
                    <div class="chip-content">
                      <div class="chip-title">College Admission</div>
                      <div class="chip-sub">Check cutoffs, fees, and admission criteria</div>
                    </div>
                  </button>

                  <button type="button" class="suggestion-chip" onclick="selectSuggestion('government_scheme')">
                    <span class="chip-icon" aria-hidden="true">📋</span>
                    <div class="chip-content">
                      <div class="chip-title">Government Scheme</div>
                      <div class="chip-sub">Check income ceilings, welfare criteria, and documents</div>
                    </div>
                  </button>

                  <button type="button" class="suggestion-chip" onclick="selectSuggestion('laptop')">
                    <span class="chip-icon" aria-hidden="true">💻</span>
                    <div class="chip-content">
                      <div class="chip-title">Laptop Purchase</div>
                      <div class="chip-sub">Check performance, warranty, and price under $2,500</div>
                    </div>
                  </button>
                </div>

                <!-- 1-Click Demo Action -->
                <div class="demo-action-row">
                  <button id="btn-home-1click-demo" type="button" class="btn-demo-primary" onclick="runOneClickDemo()">
                    <span aria-hidden="true">🚀</span> <span>Try the 1-click demo</span>
                  </button>
                </div>

                <!-- Secondary Area: Snapshot Reliability Banner & Explore Domain Chips -->
                <div class="home-secondary-section" style="width: 100%;">
                  <div id="demo-snapshot-banner" class="demo-snapshot-banner" style="margin-bottom: 16px;">
                    <div class="demo-snapshot-left">
                      <span class="snapshot-pill">OFFLINE RELIABILITY</span>
                      <span id="snapshot-status-text">Demo snapshot taken 31 Oct 2026</span>
                    </div>
                    <button class="notion-btn-subtle btn-mini" onclick="refreshLiveSnapshot()" title="Re-sync data with live official sources">↻ Refresh Live</button>
                  </div>

                  <div class="domain-nav-chips">
                    <a class="domain-chip" href="#/category/education">🎓 Education <span class="chip-count" id="count-chip-edu">10 sources</span></a>
                    <a class="domain-chip" href="#/category/career">💼 Career <span class="chip-count" id="count-chip-car">4 sources</span></a>
                    <a class="domain-chip" href="#/category/public_services">🏛️ Public Services <span class="chip-count" id="count-chip-pub">5 sources</span></a>
                    <a class="domain-chip" href="#/category/research">🔬 Research <span class="chip-count" id="count-chip-res">5 sources</span></a>
                    <a class="domain-chip" href="#/category/business">🏢 Business <span class="chip-count" id="count-chip-biz">5 sources</span></a>
                  </div>
                </div>

              </div>

              <!-- Chat Messages Thread List (populated when question is sent) -->
              <div id="chat-messages-list" class="chat-messages-list" aria-live="polite"></div>

            </div>

            <!-- Fixed Composer at the Bottom -->
            <div class="chat-composer-fixed-wrap" id="chat-composer-container">
              <div class="composer-box-inner">
                <label for="chat-input" class="sr-only" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); border: 0;">What would you like to check?</label>
                <textarea id="chat-input" class="composer-textarea" rows="2" placeholder="Ask what you would like to check... (Enter sends, Shift+Enter makes a new line)" onkeydown="handleComposerKeydown(event)"></textarea>
                
                <!-- Attached Source Chips Container -->
                <div id="chat-source-chips" class="composer-attached-chips" aria-label="Attached sources list"></div>

                <!-- Composer Bottom Controls -->
                <div class="composer-bar-bottom">
                  <div style="display: flex; align-items: center; gap: 10px;">
                    <button id="btn-chat-add-source" type="button" class="btn-composer-secondary" onclick="openAddSourceDrawer()" title="Add web URLs or paste text as evidence sources">
                      <span aria-hidden="true">+</span> <span>Add sources</span>
                    </button>
                    <span id="composer-sources-count" class="composer-sources-note" style="color: var(--text-secondary); font-size: 0.95rem;">0 sources attached</span>
                  </div>
                  <div>
                    <button id="btn-chat-send" type="button" class="btn-composer-send" onclick="handleComposerSubmit()" title="Run investigation on attached sources">
                      <span>Check</span> <span aria-hidden="true">→</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>

          </div>

          <!-- Hidden legacy elements for complete backward compatibility with existing tests/APIs -->
          <div style="display: none !important;">
            <input type="text" id="home-search-input">
            <button id="btn-home-search"></button>
            <div id="home-recent-entities"></div>
            <div id="home-profile-banner"></div>
          </div>
        </section>"""

html = re.sub(home_pattern, new_home, html)

# 7. Add Add-Source Drawer / Modal
if 'id="chat-add-source-modal"' not in html:
    modal_snippet = """
  <!-- Accessible Add Sources Drawer / Modal -->
  <div id="chat-add-source-modal" class="modal-overlay" style="display: none;">
    <div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="chat-add-source-title">
      <div class="modal-header">
        <h3 id="chat-add-source-title">Add Sources to Investigation</h3>
        <button class="notion-btn-ghost btn-small" onclick="closeAddSourceDrawer()" aria-label="Close dialog">✕ Close</button>
      </div>
      <div class="modal-body" style="padding: 16px 0;">
        <div class="tab-buttons" style="display: flex; gap: 8px; margin-bottom: 16px;">
          <button id="tab-btn-url" type="button" class="notion-btn-primary" onclick="switchAddSourceTab('url')">🌐 Web URL</button>
          <button id="tab-btn-paste" type="button" class="notion-btn-secondary" onclick="switchAddSourceTab('paste')">📋 Paste Text</button>
        </div>
        <div id="add-source-tab-url">
          <label for="chat-source-url-input" style="display: block; font-weight: 500; margin-bottom: 6px;">Web page URL:</label>
          <input type="url" id="chat-source-url-input" class="property-input" placeholder="https://example.com/guidelines-or-circular" style="width: 100%; min-height: 48px; font-size: 1rem;">
        </div>
        <div id="add-source-tab-paste" style="display: none;">
          <label for="chat-source-title-input" style="display: block; font-weight: 500; margin-bottom: 6px;">Document Title:</label>
          <input type="text" id="chat-source-title-input" class="property-input" placeholder="Official announcement or press release" style="width: 100%; min-height: 48px; font-size: 1rem; margin-bottom: 12px;">
          <label for="chat-source-paste-input" style="display: block; font-weight: 500; margin-bottom: 6px;">Document Text:</label>
          <textarea id="chat-source-paste-input" class="property-input" rows="5" placeholder="Paste circular or raw text here..." style="width: 100%; font-size: 1rem;"></textarea>
        </div>
      </div>
      <div class="modal-footer" style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px;">
        <button type="button" class="notion-btn-secondary" onclick="closeAddSourceDrawer()">Cancel</button>
        <button id="btn-add-source-confirm" type="button" class="notion-btn-primary" onclick="confirmAddSource()">Attach Source</button>
      </div>
    </div>
  </div>
"""
    html = html.replace('</body>', modal_snippet + '\n</body>')

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

print("Successfully patched frontend/index.html")
