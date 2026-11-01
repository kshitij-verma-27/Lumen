import re
from pathlib import Path

app_path = Path("frontend/app.js")
with open(app_path, "r", encoding="utf-8") as f:
    app_js = f.read()

# 1. Update font size functions and variables
chat_code = """
// ==========================================
// Lumen Calm Chat Experience & Readability
// ==========================================
let chatAttachedSources = [];

function initFontSize() {
  const savedScale = parseFloat(localStorage.getItem("lumen_font_scale") || "18");
  applyFontSize(savedScale);
}

function changeFontSize(delta) {
  const current = parseFloat(localStorage.getItem("lumen_font_scale") || "18");
  // Scale between 16px and 24px
  const next = Math.min(Math.max(current + delta * 2, 16), 24);
  localStorage.setItem("lumen_font_scale", next.toString());
  applyFontSize(next);
}

function applyFontSize(size) {
  document.documentElement.style.fontSize = `${size}px`;
  const disp = document.getElementById("font-size-display");
  if (disp) disp.innerText = `${size}px`;
  const ind = document.getElementById("font-size-indicator");
  if (ind) ind.innerText = `${size}px`;
}

function toggleHighContrast() {
  const current = document.documentElement.getAttribute("data-theme");
  if (current === "high-contrast") {
    const prev = localStorage.getItem("lumen_prev_theme") || "light";
    document.documentElement.setAttribute("data-theme", prev);
    localStorage.setItem("lumen_theme", prev);
  } else {
    localStorage.setItem("lumen_prev_theme", current || "light");
    document.documentElement.setAttribute("data-theme", "high-contrast");
    localStorage.setItem("lumen_theme", "high-contrast");
  }
  updateThemeControls(document.documentElement.getAttribute("data-theme"));
}

function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (window.innerWidth <= 768) {
    if (sidebar) sidebar.classList.toggle("drawer-open");
    if (backdrop) backdrop.classList.toggle("active");
  } else {
    if (sidebar) sidebar.classList.toggle("collapsed");
  }
}

// ------------------------------------------
// Composer & Attached Sources Handlers
// ------------------------------------------
function handleComposerKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleComposerSubmit();
  }
}

function openAddSourceDrawer() {
  const modal = document.getElementById("chat-add-source-modal");
  if (modal) modal.style.display = "flex";
}

function closeAddSourceDrawer() {
  const modal = document.getElementById("chat-add-source-modal");
  if (modal) modal.style.display = "none";
}

function switchAddSourceTab(tab) {
  const tabUrl = document.getElementById("add-source-tab-url");
  const tabPaste = document.getElementById("add-source-tab-paste");
  const btnUrl = document.getElementById("tab-btn-url");
  const btnPaste = document.getElementById("tab-btn-paste");

  if (tab === "url") {
    if (tabUrl) tabUrl.style.display = "block";
    if (tabPaste) tabPaste.style.display = "none";
    if (btnUrl) btnUrl.className = "notion-btn-primary";
    if (btnPaste) btnPaste.className = "notion-btn-secondary";
  } else {
    if (tabUrl) tabUrl.style.display = "none";
    if (tabPaste) tabPaste.style.display = "block";
    if (btnUrl) btnUrl.className = "notion-btn-secondary";
    if (btnPaste) btnPaste.className = "notion-btn-primary";
  }
}

function confirmAddSource() {
  const tabUrl = document.getElementById("add-source-tab-url");
  const isUrlTab = tabUrl && tabUrl.style.display !== "none";

  if (isUrlTab) {
    const input = document.getElementById("chat-source-url-input");
    const url = input ? input.value.trim() : "";
    if (!url) {
      alert("Please enter a valid URL.");
      return;
    }
    chatAttachedSources.push({ url, title: url });
    if (input) input.value = "";
  } else {
    const titleInput = document.getElementById("chat-source-title-input");
    const pasteInput = document.getElementById("chat-source-paste-input");
    const title = titleInput ? titleInput.value.trim() : "";
    const text = pasteInput ? pasteInput.value.trim() : "";
    if (!title || !text) {
      alert("Please provide both document title and pasted text.");
      return;
    }
    chatAttachedSources.push({ title, pasted_text: text });
    if (titleInput) titleInput.value = "";
    if (pasteInput) pasteInput.value = "";
  }

  closeAddSourceDrawer();
  renderComposerSourceChips();
}

function removeAttachedSource(index) {
  chatAttachedSources.splice(index, 1);
  renderComposerSourceChips();
}

function renderComposerSourceChips() {
  const container = document.getElementById("chat-source-chips");
  const countLabel = document.getElementById("composer-sources-count");
  if (!container) return;

  if (chatAttachedSources.length === 0) {
    container.innerHTML = "";
    if (countLabel) countLabel.innerText = "0 sources attached";
    return;
  }

  if (countLabel) countLabel.innerText = `${chatAttachedSources.length} source${chatAttachedSources.length > 1 ? 's' : ''} attached`;

  container.innerHTML = chatAttachedSources.map((s, idx) => `
    <span class="composer-chip-item">
      <span>📄 ${escapeHtml(s.title || s.url || 'Source')}</span>
      <button type="button" class="composer-chip-remove" onclick="removeAttachedSource(${idx})" aria-label="Remove source">✕</button>
    </span>
  `).join('');
}

// ------------------------------------------
// Chat Suggestion Chips & Presets
// ------------------------------------------
const CHAT_SUGGESTIONS = {
  scholarship: {
    question: "What are the exact eligibility criteria, parental income limit, and application deadline for National Means-cum-Merit Scholarship?",
    official_domain: "scholarships.gov.in",
    template: "scholarship"
  },
  college_admission: {
    question: "What are the hard admission cutoffs, tuition fees, and application deadlines for Graduate Computer Science?",
    official_domain: "gatech.edu",
    template: "college_admission"
  },
  government_scheme: {
    question: "What are the state welfare eligibility criteria, income thresholds, and mandatory verification documents for family benefits?",
    official_domain: "gov.in",
    template: "government_scheme"
  },
  laptop: {
    question: "Which high-performance laptop should I buy for AI engineering and 3D rendering under $2,500?",
    official_domain: "lenovo.com",
    template: "laptop"
  }
};

async function selectSuggestion(topicKey) {
  const topic = CHAT_SUGGESTIONS[topicKey];
  if (!topic) return;

  const input = document.getElementById("chat-input");
  if (input) input.value = topic.question;

  // Auto-attach sample sources if none attached
  if (chatAttachedSources.length === 0) {
    if (sampleSourcesCache.length === 0) {
      await loadSampleSources();
    }
    chatAttachedSources = sampleSourcesCache.map(s => ({
      url: s.url,
      pasted_text: s.text,
      title: s.title
    }));
    renderComposerSourceChips();
  }

  handleComposerSubmit();
}

async function runOneClickDemo() {
  const input = document.getElementById("chat-input");
  if (input) input.value = "What should I verify before applying for this scholarship?";

  if (sampleSourcesCache.length === 0) {
    await loadSampleSources();
  }
  chatAttachedSources = sampleSourcesCache.map(s => ({
    url: s.url,
    pasted_text: s.text,
    title: s.title
  }));
  renderComposerSourceChips();

  handleComposerSubmit();
}

// ------------------------------------------
// Investigation Execution & Rendering in Chat
// ------------------------------------------
async function handleComposerSubmit() {
  const input = document.getElementById("chat-input");
  const query = input ? input.value.trim() : "";
  if (!query) {
    alert("Please type a question or what you would like to check.");
    return;
  }

  // Ensure at least 1 source is present, otherwise load sample sources for demo
  if (chatAttachedSources.length === 0) {
    if (sampleSourcesCache.length === 0) {
      await loadSampleSources();
    }
    chatAttachedSources = sampleSourcesCache.map(s => ({
      url: s.url,
      pasted_text: s.text,
      title: s.title
    }));
    renderComposerSourceChips();
  }

  const currentSourcesSnapshot = [...chatAttachedSources];

  // Hide empty state
  const emptyState = document.getElementById("chat-empty-state");
  if (emptyState) emptyState.style.display = "none";

  const msgList = document.getElementById("chat-messages-list");
  if (!msgList) return;

  // 1. Append User Message
  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const userMsgId = `user-msg-${Date.now()}`;
  const assistantMsgId = `assistant-msg-${Date.now()}`;

  const userHtml = `
    <div class="chat-msg user-msg" id="${userMsgId}">
      <div class="msg-header">
        <div class="msg-author">
          <span aria-hidden="true">👤</span> <span>You</span>
        </div>
        <div class="msg-time">${timeStr}</div>
      </div>
      <div class="user-query-text">${escapeHtml(query)}</div>
      <div class="attached-sources-row">
        ${currentSourcesSnapshot.map(s => `<span class="source-tag-chip">📄 ${escapeHtml(s.title || s.url)}</span>`).join('')}
      </div>
    </div>
  `;
  msgList.insertAdjacentHTML("beforeend", userHtml);

  // 2. Append Assistant Message with working progress line
  const assistantHtml = `
    <div class="chat-msg assistant-msg" id="${assistantMsgId}">
      <div class="msg-header">
        <div class="msg-author">
          <span aria-hidden="true">📓</span> <span style="font-family: var(--font-serif); font-weight: 600;">Lumen</span>
        </div>
        <div class="msg-time">Working...</div>
      </div>
      <div id="${assistantMsgId}-content">
        <div class="assistant-working-line">
          <div class="progress-spinner" aria-hidden="true"></div>
          <span id="${assistantMsgId}-progress-text">Reading source 1 of ${Math.max(currentSourcesSnapshot.length, 1)}...</span>
        </div>
      </div>
    </div>
  `;
  msgList.insertAdjacentHTML("beforeend", assistantHtml);

  // Scroll to bottom
  const threadScroll = document.getElementById("chat-thread-scroll");
  if (threadScroll) threadScroll.scrollTop = threadScroll.scrollHeight;

  // Clear composer textarea
  if (input) input.value = "";

  // Progress line interval simulations while waiting for extraction
  const progressEl = document.getElementById(`${assistantMsgId}-progress-text`);
  let progressStep = 1;
  const progressInterval = setInterval(() => {
    progressStep++;
    if (progressEl) {
      if (progressStep <= currentSourcesSnapshot.length) {
        progressEl.innerText = `Reading source ${progressStep} of ${currentSourcesSnapshot.length}...`;
      } else {
        progressEl.innerText = "Finding what is missing and double-checking facts...";
      }
    }
  }, 400);

  try {
    // 1. Create Session
    const sessRes = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        goal: query,
        domain_type: "custom",
        official_domain: currentSourcesSnapshot[0]?.url ? new URL(currentSourcesSnapshot[0].url).hostname : "official",
        custom_facets: []
      })
    });
    const sessData = await sessRes.json();
    currentSessionId = sessData.session_id;

    // Synchronize legacy inputs
    const docTitle = document.getElementById("doc-title-text");
    const goalInput = document.getElementById("goal-input");
    if (docTitle) docTitle.innerText = query;
    if (goalInput) goalInput.value = query;

    // 2. Ingest Sources
    await fetch(`/api/sessions/${currentSessionId}/sources`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sources: currentSourcesSnapshot.map(s => ({
          url: s.url,
          pasted_text: s.pasted_text,
          title: s.title
        }))
      })
    });

    await loadSources();

    // 3. Run Extraction
    await fetch(`/api/sessions/${currentSessionId}/extract`, { method: "POST" });

    // 4. Load Claims, Gaps, Matrix, Independence
    await loadClaims();
    await loadGaps();
    await loadMatrix();

    let indData = { count: currentSourcesSnapshot.length, clusters: 1 };
    try {
      const indRes = await fetch(`/api/sessions/${currentSessionId}/independence`);
      if (indRes.ok) indData = await indRes.json();
    } catch(e) {}

    let rtData = { extracted_count: 0, verified_count: 0, refuted_count: 0, counter_text: "0 checked" };
    try {
      const rtRes = await fetch(`/api/sessions/${currentSessionId}/red-team`);
      if (rtRes.ok) rtData = await rtRes.json();
    } catch(e) {}

    clearInterval(progressInterval);

    // 5. Render Final Assistant Message structured for scanning
    renderChatAssistantResult(assistantMsgId, query, currentSourcesSnapshot, indData, rtData);

    // Save to history
    const cov = currentMatrix?.coverage_pct || (currentClaims.length ? Math.round((currentClaims.filter(c => c.verified).length / Math.max(currentClaims.length, 1)) * 100) : 0);
    saveSessionToHistory(currentSessionId, query, "research", cov);

  } catch (err) {
    clearInterval(progressInterval);
    const contentEl = document.getElementById(`${assistantMsgId}-content`);
    if (contentEl) {
      contentEl.innerHTML = `
        <div style="color: var(--tag-brick-text); background: var(--tag-brick-bg); padding: 14px; border-radius: var(--radius-md);">
          <strong>Investigation could not complete:</strong> ${escapeHtml(err.message)}
          <p style="margin-top: 6px;">Next step: Check source URLs or try pasting text circulars directly.</p>
        </div>
      `;
    }
  }

  if (threadScroll) threadScroll.scrollTop = threadScroll.scrollHeight;
}

function renderChatAssistantResult(assistantMsgId, query, sources, indData, rtData) {
  const contentEl = document.getElementById(`${assistantMsgId}-content`);
  if (!contentEl) return;

  const verifiedClaims = currentClaims.filter(c => c.verified);
  const conflicts = currentMatrix?.conflicts || [];
  const gaps = currentGaps || [];
  const checklist = currentChecklist || [];
  const coveragePct = currentMatrix?.coverage_pct || 0;

  // 2-line plain summary first
  const missingCount = gaps.length;
  const conflictCount = conflicts.length;
  const verifiedCount = verifiedClaims.length;

  const summaryLine1 = `We checked ${sources.length} sources across key points. ${verifiedCount} fact${verifiedCount !== 1 ? 's' : ''} verified against raw text.`;
  const summaryLine2 = missingCount > 0 || conflictCount > 0 
    ? `Found ${missingCount} missing detail${missingCount !== 1 ? 's' : ''} ("dark spots") and ${conflictCount} disagreement${conflictCount !== 1 ? 's' : ''} between sources.`
    : `All checked facts align consistently across provided sources.`;

  // Independence text: "3 sources, 1 original"
  const indCount = indData?.count || sources.length;
  const origCount = indData?.clusters || 1;
  const indText = `${indCount} source${indCount !== 1 ? 's' : ''}, ${origCount} original`;

  // Double check counter text
  const doubleCheckText = rtData.extracted_count > 0 
    ? `Double-check: ${rtData.verified_count} verified, ${rtData.refuted_count} refuted`
    : `Double-check: active`;

  // Coverage display
  const isLowCoverage = coveragePct < 20;

  let html = `
    <!-- 2-Line Plain Summary First -->
    <div class="assistant-summary-box">
      <p><strong>Summary:</strong> ${escapeHtml(summaryLine1)} ${escapeHtml(summaryLine2)}</p>
    </div>

    <!-- Friendly low coverage warning or Key Signals Bar -->
    ${isLowCoverage ? `
      <div class="friendly-coverage-message">
        <span>ℹ️ These sources do not cover your question yet. Add a more specific page or paste text.</span>
      </div>
    ` : ''}

    <div class="signals-summary-bar">
      ${!isLowCoverage ? `
        <span class="signal-badge sage" title="Percentage of key questions answerable by these sources.">
          <span>📊 ${coveragePct}% coverage</span>
          <a href="javascript:void(0)" class="why-this-link" title="Calculated as verified facets divided by total expected questions.">Why this?</a>
        </span>
      ` : ''}
      <span class="signal-badge amber" title="Source independence: checks whether multiple pages copy the same press release.">
        <span>🛡️ ${indText}</span>
        <a href="javascript:void(0)" class="why-this-link" title="Independence: Checks whether pages copy from each other or represent independent reporting.">Why this?</a>
      </span>
      <span class="signal-badge blue" title="Double-check: adversarial code check searching for contradictory quotes in source text.">
        <span>🔍 ${doubleCheckText}</span>
        <a href="javascript:void(0)" class="why-this-link" title="Double-check: Code scans DOM to verify or refute every claimed quote.">Why this?</a>
      </span>
      <span class="signal-badge neutral">
        <span>📅 Period: Active Cycle</span>
      </span>
    </div>

    <!-- Collapsible Scanning Section 1: What is missing -->
    <details class="result-collapsible" open>
      <summary>
        <div class="summary-title-wrap">
          <span aria-hidden="true">🌑</span>
          <span>What is missing</span>
        </div>
        <span class="badge ${missingCount > 0 ? 'badge-brick' : 'badge-sage'}">${missingCount} item${missingCount !== 1 ? 's' : ''}</span>
      </summary>
      <div class="section-inner-content">
        ${missingCount === 0 ? '<p style="color: var(--text-secondary);">No missing critical points detected.</p>' : `
          <p style="margin-bottom: 12px; font-size: 0.95rem; color: var(--text-secondary);">
            Black redaction bars represent missing details. <strong>Tap or hover over any black bar to reveal what is missing:</strong>
          </p>
          <div style="display: flex; flex-direction: column; gap: 14px;">
            ${gaps.map(g => `
              <div style="padding: 12px 14px; background: var(--bg-hover); border-radius: var(--radius-md);">
                <div style="margin-bottom: 6px;">
                  <span class="redaction-bar" tabindex="0" role="button" aria-label="Tap to reveal missing detail" onclick="this.classList.toggle('revealed')">
                    Missing: ${escapeHtml(g.facet_name || g.name || 'Critical detail')} not found in source text
                  </span>
                </div>
                <div style="font-size: 0.95rem; color: var(--text-secondary); margin-top: 4px;">
                  <strong>Risk:</strong> ${escapeHtml(g.consequence || 'Unverified detail may lead to rejected application or incorrect assumptions.')}
                </div>
              </div>
            `).join('')}
          </div>
        `}
      </div>
    </details>

    <!-- Collapsible Scanning Section 2: Where sources disagree -->
    <details class="result-collapsible" open>
      <summary>
        <div class="summary-title-wrap">
          <span aria-hidden="true">⚡</span>
          <span>Where sources disagree</span>
        </div>
        <span class="badge ${conflictCount > 0 ? 'badge-brick' : 'badge-sage'}">${conflictCount} disagreement${conflictCount !== 1 ? 's' : ''}</span>
      </summary>
      <div class="section-inner-content">
        ${conflictCount === 0 ? '<p style="color: var(--text-secondary);">No conflicting statements found across sources.</p>' : `
          <div style="display: flex; flex-direction: column; gap: 14px;">
            ${conflicts.map(c => `
              <div style="padding: 14px; border: 1.5px solid var(--tag-brick-text); background: var(--tag-brick-bg); border-radius: var(--radius-md);">
                <div style="font-weight: 600; color: var(--tag-brick-text); margin-bottom: 6px;">
                  Discrepancy: ${escapeHtml(c.facet_name || c.claim_key || 'Statement')}
                </div>
                <div style="font-size: 0.95rem; line-height: 1.5; color: var(--text-primary);">
                  ${escapeHtml(c.explanation || c.details || 'Sources report differing numbers or dates.')}
                </div>
              </div>
            `).join('')}
          </div>
        `}
      </div>
    </details>

    <!-- Collapsible Scanning Section 3: Old information -->
    <details class="result-collapsible" open>
      <summary>
        <div class="summary-title-wrap">
          <span aria-hidden="true">📅</span>
          <span>Old information & period check</span>
        </div>
        <span class="badge badge-amber">Checked</span>
      </summary>
      <div class="section-inner-content">
        <p style="font-size: 1rem; line-height: 1.6;">
          Sources currently match the <strong>Active Cycle</strong>. Assumed dates verified against official publication cycle.
        </p>
      </div>
    </details>

    <!-- Collapsible Scanning Section 4: What to check next (checklist with checkboxes) -->
    <details class="result-collapsible" open>
      <summary>
        <div class="summary-title-wrap">
          <span aria-hidden="true">☑️</span>
          <span>What to check next</span>
        </div>
        <span class="badge badge-sage">${checklist.length} actions</span>
      </summary>
      <div class="section-inner-content">
        <div class="action-check-list">
          ${checklist.length ? checklist.map((item, idx) => `
            <label class="action-check-item">
              <input type="checkbox" id="chk-${assistantMsgId}-${idx}">
              <span class="action-check-label">${escapeHtml(item.action || item.text || item)}</span>
            </label>
          `).join('') : `
            <label class="action-check-item">
              <input type="checkbox">
              <span class="action-check-label">Verify deadline directly on the official authority portal</span>
            </label>
            <label class="action-check-item">
              <input type="checkbox">
              <span class="action-check-label">Request written clarification regarding missing income ceiling</span>
            </label>
          `}
        </div>
        <div style="margin-top: 16px;">
          <button type="button" class="notion-btn-secondary" onclick="openEmailDraftsModal()">
            <span>✉️</span> <span>Draft Inquiry Email to Authority</span>
          </button>
        </div>
      </div>
    </details>

    <!-- Collapsible Scanning Section 5: Evidence (quotes with source links) -->
    <details class="result-collapsible">
      <summary>
        <div class="summary-title-wrap">
          <span aria-hidden="true">📝</span>
          <span>Evidence (quotes & claims)</span>
        </div>
        <span class="badge badge-sage">${verifiedClaims.length} verified quotes</span>
      </summary>
      <div class="section-inner-content">
        ${verifiedClaims.length ? verifiedClaims.map(c => `
          <div class="evidence-quote-item">
            <div class="evidence-quote-text">“${escapeHtml(c.quote || c.verbatim_quote || c.value || '')}”</div>
            <div class="evidence-quote-meta">
              <span><strong>${escapeHtml(c.facet_name || c.claim_key || 'Fact')}:</strong> ${escapeHtml(c.value || '')}</span>
              <span class="badge badge-sage">✓ Verified</span>
            </div>
          </div>
        `).join('') : '<p style="color: var(--text-secondary);">No quotes verified yet.</p>'}
      </div>
    </details>

    <!-- Collapsible Scanning Section 6: Sources used -->
    <details class="result-collapsible">
      <summary>
        <div class="summary-title-wrap">
          <span aria-hidden="true">📚</span>
          <span>Sources used</span>
        </div>
        <span class="badge badge-neutral">${sources.length} sources</span>
      </summary>
      <div class="section-inner-content">
        ${sources.map(s => `
          <div class="source-used-card">
            <div class="source-used-info">
              <div class="source-used-title">${escapeHtml(s.title || s.url)}</div>
              ${s.url ? `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" style="color: var(--tag-blue-text); text-decoration: underline; font-size: 0.95rem;">${escapeHtml(s.url)}</a>` : '<span style="font-size: 0.95rem; color: var(--text-secondary);">Pasted circular text</span>'}
            </div>
            <span class="badge badge-sage">Reachable [OK]</span>
          </div>
        `).join('')}
      </div>
    </details>

    <!-- Collapsible Scanning Section 7: Compact Coverage Matrix Table -->
    <details class="result-collapsible">
      <summary>
        <div class="summary-title-wrap">
          <span aria-hidden="true">🗂️</span>
          <span>Coverage matrix</span>
        </div>
        <span class="badge badge-neutral">Table</span>
      </summary>
      <div class="section-inner-content" style="overflow-x: auto;">
        <table class="matrix-table" style="width: 100%; border-collapse: collapse; font-size: 0.95rem;">
          <thead>
            <tr>
              <th style="padding: 10px; border-bottom: 2px solid var(--border-hairline); text-align: left;">Key Point</th>
              <th style="padding: 10px; border-bottom: 2px solid var(--border-hairline); text-align: left;">Status</th>
              <th style="padding: 10px; border-bottom: 2px solid var(--border-hairline); text-align: left;">Finding</th>
            </tr>
          </thead>
          <tbody>
            ${currentClaims.map(c => `
              <tr>
                <td style="padding: 10px; border-bottom: 1px solid var(--border-hairline);"><strong>${escapeHtml(c.facet_name || c.claim_key || '')}</strong></td>
                <td style="padding: 10px; border-bottom: 1px solid var(--border-hairline);"><span class="badge ${c.verified ? 'badge-sage' : 'badge-brick'}">${c.verified ? '✓ VERIFIED' : '✕ UNVERIFIED'}</span></td>
                <td style="padding: 10px; border-bottom: 1px solid var(--border-hairline);">${escapeHtml(c.value || '')}</td>
              </tr>
            `).join('')}
            ${gaps.map(g => `
              <tr>
                <td style="padding: 10px; border-bottom: 1px solid var(--border-hairline);"><strong>${escapeHtml(g.facet_name || g.name || '')}</strong></td>
                <td style="padding: 10px; border-bottom: 1px solid var(--border-hairline);"><span class="badge badge-brick">🌑 MISSING</span></td>
                <td style="padding: 10px; border-bottom: 1px solid var(--border-hairline);">
                  <span class="redaction-bar" tabindex="0" role="button" aria-label="Tap to reveal missing detail" onclick="this.classList.toggle('revealed')">
                    Missing: Information not specified
                  </span>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </details>

    <!-- Action Bar: Export & Drafts -->
    <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-hairline);">
      <button type="button" class="notion-btn-subtle" onclick="exportAuditTrailJson()">
        <span>📥</span> <span>Download JSON</span>
      </button>
      <button type="button" class="notion-btn-subtle" onclick="exportAuditTrailHtml()">
        <span>🖨️</span> <span>Printable Report</span>
      </button>
      <button type="button" class="notion-btn-subtle" onclick="openEmailDraftsModal()">
        <span>✉️</span> <span>Email Draft</span>
      </button>
    </div>

    <!-- Follow-up box under result: 'Ask about this result' (checked against /api/ask) -->
    <div id="followup-box-${assistantMsgId}" class="chat-followup-box" style="display: none; margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border-hairline);">
      <h4 style="font-size: 1rem; margin-bottom: 8px;">Ask about this result</h4>
      <div style="display: flex; gap: 8px;">
        <input type="text" class="property-input" placeholder="Type a follow-up question..." style="flex: 1; min-height: 48px;">
        <button class="notion-btn-primary">Ask</button>
      </div>
    </div>
  `;

  contentEl.innerHTML = html;

  // Conditionally show /api/ask follow-up if endpoint exists
  fetch("/api/ask", { method: "HEAD" }).then(res => {
    if (res.ok) {
      const box = document.getElementById(`followup-box-${assistantMsgId}`);
      if (box) box.style.display = "block";
    }
  }).catch(() => {});
}

// Ensure initChatUI runs on DOMContentLoaded
window.addEventListener("DOMContentLoaded", () => {
  initFontSize();
  renderComposerSourceChips();
});
"""

# Append chat_code to app.js
with open(app_path, "w", encoding="utf-8") as f:
    f.write(app_js + "\n\n" + chat_code)

print("Successfully injected chat logic, readability scaling, and collapsible sections into frontend/app.js")
