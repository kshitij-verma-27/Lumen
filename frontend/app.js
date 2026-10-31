// Digital Dark Spot - Universal Information-Gap & Blindspot Detection Engine
// Evidence-First Decision Support across ALL topics

let currentSessionId = null;
let currentSources = [];
let currentClaims = [];
let currentGaps = [];
let currentChecklist = [];
let currentMatrix = null;
let currentActiveTab = 'sourced'; // 'sourced' | 'matrix' | 'gaps' | 'checklist' | 'rejected' | 'all'
let currentMatrixFilter = 'all'; // 'all' | 'darkspots' | 'conflicts' | 'covered'
let sampleSourcesCache = [];
let templatesCache = {};
let activeFacets = [];

// Init on load
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  setupEventListeners();
  loadSampleSources();
  loadTemplatesAndInit();
});

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const badge = document.getElementById("llm-mode-badge");
    const badgeText = document.getElementById("llm-mode-text");

    if (data.mode === "live") {
      badge.className = "badge badge-live";
      badgeText.innerHTML = `✨ Live Gemini Active (${data.model})`;
      badge.title = `Model: ${data.model}`;
    } else {
      badge.className = "badge badge-mock";
      const reason = data.fallback_reason ? `: ${data.fallback_reason.slice(0, 45)}...` : "";
      badgeText.innerHTML = `⚠️ Mock Mode${reason}`;
      badge.title = data.fallback_reason || "Running with offline mock extractor";
    }
  } catch (err) {
    console.error("Health check failed:", err);
  }
}

async function loadSampleSources() {
  try {
    const res = await fetch("/api/sample-sources");
    const data = await res.json();
    sampleSourcesCache = data.samples || [];
  } catch (err) {
    console.error("Failed to fetch sample sources:", err);
  }
}

async function loadTemplatesAndInit() {
  try {
    const res = await fetch("/api/templates");
    const data = await res.json();
    (data.templates || []).forEach(t => {
      templatesCache[t.id] = t;
    });

    // Default to laptop template facets initially for rich demonstration
    const defaultTemplate = templatesCache["laptop"] || templatesCache["scholarship"];
    if (defaultTemplate) {
      activeFacets = JSON.parse(JSON.stringify(defaultTemplate.facets));
      renderFacetsList();
    }
  } catch (err) {
    console.error("Failed to load templates:", err);
  }
}

function setupEventListeners() {
  document.getElementById("btn-init-session").addEventListener("click", initializeSession);
  document.getElementById("btn-load-sample-all").addEventListener("click", runOneClickDemo);
  document.getElementById("btn-open-add-source").addEventListener("click", toggleAddSourceBox);
  document.getElementById("btn-cancel-source").addEventListener("click", toggleAddSourceBox);
  document.getElementById("btn-submit-source").addEventListener("click", submitCustomSource);
  document.getElementById("btn-run-extraction").addEventListener("click", runExtraction);

  // AI Facet Generation & Management
  const btnGen = document.getElementById("btn-generate-facets");
  if (btnGen) btnGen.addEventListener("click", generateFacetsWithAI);

  const templateSelect = document.getElementById("domain-select");
  if (templateSelect) templateSelect.addEventListener("change", handleTemplateChange);

  const btnToggleAdd = document.getElementById("btn-toggle-add-facet");
  if (btnToggleAdd) btnToggleAdd.addEventListener("click", toggleNewFacetPanel);

  const btnCancelNew = document.getElementById("btn-cancel-new-facet");
  if (btnCancelNew) btnCancelNew.addEventListener("click", toggleNewFacetPanel);

  const btnSaveNew = document.getElementById("btn-save-new-facet");
  if (btnSaveNew) btnSaveNew.addEventListener("click", saveCustomFacet);

  // Tab switching inside Add Source box
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.tab).classList.add("active");
    });
  });
}

function handleTemplateChange(e) {
  const tid = e.target.value;
  const goalInput = document.getElementById("goal-input");
  const officialDomainInput = document.getElementById("official-domain-input");

  if (tid === "laptop") {
    goalInput.value = "Which high-performance laptop should I buy for AI engineering and 3D rendering under $2,500?";
    officialDomainInput.value = "lenovo.com";
  } else if (tid === "college_admission") {
    goalInput.value = "What are the exact admission requirements, tuition, and deadlines for Georgia Tech MS CS Fall 2025?";
    officialDomainInput.value = "gatech.edu";
  } else if (tid === "government_scheme") {
    goalInput.value = "What are the eligibility criteria, rooftop solar subsidy amount, and application procedure for PM Surya Ghar Muft Bijli Yojana?";
    officialDomainInput.value = "pmsuryaghar.gov.in";
  } else if (tid === "scholarship") {
    goalInput.value = "What should I verify before applying for this scholarship?";
    officialDomainInput.value = "scholarships.gov.in";
  }

  if (templatesCache[tid]) {
    activeFacets = JSON.parse(JSON.stringify(templatesCache[tid].facets));
    renderFacetsList();
  }
}

async function generateFacetsWithAI() {
  const goal = document.getElementById("goal-input").value.trim();
  if (!goal) {
    alert("Please enter a research goal or question first.");
    return;
  }

  const btn = document.getElementById("btn-generate-facets");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> Generating Facets...`;

  try {
    const res = await fetch("/api/facets/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, domain_type: "custom" })
    });
    const data = await res.json();

    if (data.facets && data.facets.length > 0) {
      activeFacets = data.facets;
      renderFacetsList();

      if (data.suggested_official_domain) {
        const offInput = document.getElementById("official-domain-input");
        if (offInput) offInput.value = data.suggested_official_domain;
      }
    }
    btn.innerHTML = `<span>✓</span> Facets Generated!`;
    setTimeout(() => { btn.innerHTML = originalText; btn.disabled = false; }, 2000);
  } catch (err) {
    alert("Error generating facets: " + err.message);
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}

function toggleNewFacetPanel() {
  const panel = document.getElementById("add-facet-panel");
  if (panel) {
    panel.style.display = panel.style.display === "none" ? "block" : "none";
  }
}

function saveCustomFacet() {
  const id = document.getElementById("new-facet-id").value.trim();
  const name = document.getElementById("new-facet-name").value.trim();
  const type = document.getElementById("new-facet-type").value;
  const importance = document.getElementById("new-facet-importance").value;
  const consequence = document.getElementById("new-facet-consequence").value.trim();
  const is_deadline = document.getElementById("new-facet-deadline").checked;

  if (!id || !name) {
    alert("Please provide both facet id and name.");
    return;
  }

  activeFacets.push({
    id: id.toLowerCase().replace(/\s+/g, '_'),
    name: name,
    description: `User-defined facet for ${name}`,
    expected_type: type,
    importance: importance,
    consequence: consequence || `Unverified ${name} may cause unexpected errors or blindspots.`,
    is_deadline: is_deadline
  });

  // Clear inputs
  document.getElementById("new-facet-id").value = "";
  document.getElementById("new-facet-name").value = "";
  document.getElementById("new-facet-consequence").value = "";
  document.getElementById("new-facet-deadline").checked = false;

  toggleNewFacetPanel();
  renderFacetsList();
}

function deleteFacet(facetId) {
  activeFacets = activeFacets.filter(f => f.id !== facetId);
  renderFacetsList();
}

function renderFacetsList() {
  const container = document.getElementById("facets-list");
  const countBadge = document.getElementById("facets-count");
  if (countBadge) countBadge.innerText = activeFacets.length;
  if (!container) return;

  container.innerHTML = "";

  if (activeFacets.length === 0) {
    container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim); padding: 1.5rem;">No target facets defined. Click "✨ Generate Facets with AI" or "+ Add Custom Facet".</div>`;
    return;
  }

  activeFacets.forEach(f => {
    const card = document.createElement("div");
    card.className = "facet-card";

    const importanceClass = `importance-${f.importance || 'high'}`;

    card.innerHTML = `
      <div class="facet-card-top">
        <div class="facet-card-title">${escapeHtml(f.name)}</div>
        <div style="display: flex; gap: 0.4rem; align-items: center;">
          <span class="importance-pill ${importanceClass}">${(f.importance || 'high').toUpperCase()}</span>
          <button class="facet-btn-delete" title="Remove facet" onclick="deleteFacet('${f.id}')">✕</button>
        </div>
      </div>
      <div class="facet-card-badges">
        <span class="type-pill">${escapeHtml(f.expected_type || 'text')}</span>
        ${f.is_deadline ? '<span class="deadline-pill">📅 Deadline / Expiry</span>' : ''}
        <span style="font-size: 0.72rem; color: var(--text-dim); font-family: var(--font-mono);">id: ${escapeHtml(f.id)}</span>
      </div>
      <p class="facet-card-desc">${escapeHtml(f.description || '')}</p>
      ${f.consequence ? `<div class="facet-card-consequence">⚠️ <strong>Risk if ignored:</strong> ${escapeHtml(f.consequence)}</div>` : ''}
    `;

    container.appendChild(card);
  });
}

async function initializeSession() {
  const goal = document.getElementById("goal-input").value.trim();
  const domain_type = document.getElementById("domain-select").value;
  const official_domain = document.getElementById("official-domain-input").value.trim();
  const targetCycleInput = document.getElementById("target-cycle-input");
  const target_version_period = targetCycleInput && targetCycleInput.value.trim() ? targetCycleInput.value.trim() : null;

  if (!goal) {
    alert("Please enter a research goal.");
    return;
  }

  if (activeFacets.length === 0) {
    alert("Please define at least one target facet before initializing.");
    return;
  }

  const btn = document.getElementById("btn-init-session");
  btn.disabled = true;
  btn.innerText = "Initializing...";

  try {
    const res = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        goal,
        domain_type,
        official_domain,
        target_version_period,
        custom_facets: activeFacets
      })
    });
    const data = await res.json();
    currentSessionId = data.session_id;

    // Show Sources section
    document.getElementById("sources-section").style.display = "block";
    document.getElementById("sources-section").scrollIntoView({ behavior: "smooth" });
    btn.innerText = "Session Active ✓";
  } catch (err) {
    alert("Error initializing session: " + err.message);
    btn.disabled = false;
    btn.innerText = "Initialize Research Session";
  }
}

async function runOneClickDemo() {
  const demoBtn = document.getElementById("btn-load-sample-all");
  demoBtn.disabled = true;
  demoBtn.innerText = "⏳ Loading Demo Sources & Running Extraction...";

  try {
    // 1. Initialize session if not active
    if (!currentSessionId) {
      const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: "What should I verify before applying for this scholarship?",
          domain_type: "scholarship",
          official_domain: "scholarships.gov.in",
          custom_facets: templatesCache["scholarship"] ? templatesCache["scholarship"].facets : activeFacets
        })
      });
      const data = await res.json();
      currentSessionId = data.session_id;
    }

    // 2. Add all bundled sample sources
    if (sampleSourcesCache.length === 0) {
      await loadSampleSources();
    }

    const sourcesPayload = {
      sources: sampleSourcesCache.map(s => ({
        url: s.url,
        pasted_text: s.text,
        title: s.title
      }))
    };

    const addRes = await fetch(`/api/sessions/${currentSessionId}/sources`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sourcesPayload)
    });
    await addRes.json();

    // 3. Refresh sources
    await loadSources();
    document.getElementById("sources-section").style.display = "block";

    // 4. Trigger Extraction
    await runExtraction();

    demoBtn.disabled = false;
    demoBtn.innerText = "🚀 1-Click Demo (Scholarship Quick-Start)";
  } catch (err) {
    alert("Demo failed: " + err.message);
    demoBtn.disabled = false;
    demoBtn.innerText = "🚀 1-Click Demo (Scholarship Quick-Start)";
  }
}

function toggleAddSourceBox() {
  const box = document.getElementById("add-source-box");
  box.style.display = box.style.display === "none" ? "block" : "none";
}

async function submitCustomSource() {
  if (!currentSessionId) {
    alert("Please initialize a session first.");
    return;
  }

  const activeTab = document.querySelector(".tab-btn.active").dataset.tab;
  let sourceObj = {};

  if (activeTab === "tab-url") {
    const url = document.getElementById("source-url-input").value.trim();
    if (!url) {
      alert("Please enter a valid URL.");
      return;
    }
    sourceObj = { url };
  } else {
    const title = document.getElementById("source-title-input").value.trim();
    const pasted_text = document.getElementById("source-paste-input").value.trim();
    if (!pasted_text) {
      alert("Please paste text content.");
      return;
    }
    sourceObj = { pasted_text, title: title || "Pasted Document" };
  }

  const submitBtn = document.getElementById("btn-submit-source");
  submitBtn.disabled = true;
  submitBtn.innerText = "Ingesting...";

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/sources`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sources: [sourceObj] })
    });
    await res.json();

    // Reset fields
    document.getElementById("source-url-input").value = "";
    document.getElementById("source-title-input").value = "";
    document.getElementById("source-paste-input").value = "";
    toggleAddSourceBox();

    // Reload sources
    await loadSources();
  } catch (err) {
    alert("Failed to add source: " + err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerText = "Ingest Source";
  }
}

async function loadSources() {
  if (!currentSessionId) return;

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/sources`);
    const data = await res.json();
    currentSources = data.sources || [];

    const countBadge = document.getElementById("sources-count-badge");
    countBadge.innerText = `${currentSources.length} Source${currentSources.length === 1 ? '' : 's'} Ingested`;

    const indepBadge = document.getElementById("source-independence-badge");
    const indepData = data.independence;
    if (indepBadge && indepData && indepData.total_sources > 0) {
      indepBadge.style.display = "inline-flex";
      indepBadge.innerText = indepData.badge_text;
      if (indepData.total_sources > indepData.independent_sources) {
        indepBadge.className = "badge badge-independence has-copies";
        indepBadge.title = `⚡ Near-duplicate detection: ${indepData.total_sources} sources ingested, but only ${indepData.independent_sources} independent original(s). Copies count as 1 source.`;
      } else {
        indepBadge.className = "badge badge-independence";
        indepBadge.title = "All sources appear independent.";
      }
    }

    const grid = document.getElementById("sources-grid");
    grid.innerHTML = "";

    currentSources.forEach(s => {
      const card = document.createElement("div");
      card.className = "source-card";

      let authClass = "badge-secondary";
      if (s.authority === "official") authClass = "badge-official";
      if (s.authority === "low") authClass = "badge-low";

      const pubDate = s.published_date || "Undated";
      const origin = s.published_date_origin || "none";
      const dateBadge = `<span class="date-origin-pill">📅 ${pubDate} (via ${origin})</span>`;

      const isCopy = s.is_original === false;
      const copyBadge = isCopy
        ? `<span class="source-copy-pill" title="Near-duplicate of ${escapeHtml(s.copied_from_title || 'original source')}">📋 Copy of Original</span>`
        : `<span class="source-original-pill">⭐ Original Source</span>`;

      card.innerHTML = `
        <div class="source-card-header">
          <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
            <span class="badge ${authClass}">${(s.authority || 'low').toUpperCase()}</span>
            ${copyBadge}
          </div>
          <div style="display: flex; gap: 0.4rem; align-items: center;">
            <button class="btn btn-outline btn-small" style="font-size: 0.72rem; padding: 0.2rem 0.5rem;" onclick="recheckSource('${s.id}')" title="Re-fetch content and check for changes">🔄 Re-check</button>
            ${dateBadge}
          </div>
        </div>
        <h4 class="source-card-title">${escapeHtml(s.title || "Untitled Document")}</h4>
        <div class="source-meta">
          <span>${s.url ? escapeHtml(s.url) : 'Pasted Text'}</span>
          <span>• ${s.text_length} chars</span>
          <span style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-dim);" title="SHA-256: ${escapeHtml(s.content_hash || '')}">• hash: ${(s.content_hash || '').slice(0, 10)}...</span>
        </div>
        <p class="source-preview">${escapeHtml(s.text_preview)}</p>
      `;

      grid.appendChild(card);
    });
  } catch (err) {
    console.error("Failed to load sources:", err);
  }
}

async function runExtraction() {
  if (!currentSessionId) {
    alert("Please initialize a session first.");
    return;
  }
  if (currentSources.length === 0) {
    alert("Please add at least one source before running extraction.");
    return;
  }

  const btn = document.getElementById("btn-run-extraction");
  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> Extracting & Verifying Claims...`;

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/extract`, {
      method: "POST"
    });
    await res.json();

    // Show Results section
    document.getElementById("results-section").style.display = "block";
    document.getElementById("results-section").scrollIntoView({ behavior: "smooth" });

    // Load claims, matrix, and gap detection
    await loadClaims();
    await loadGaps();
    await loadMatrix();

  } catch (err) {
    alert("Extraction failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span class="btn-icon">⚡</span> Extract & Verify Claims`;
  }
}

async function loadClaims() {
  if (!currentSessionId) return;

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/claims`);
    const data = await res.json();
    currentClaims = data.claims || [];

    const verifiedClaims = currentClaims.filter(c => c.verified);
    const rejectedClaims = currentClaims.filter(c => !c.verified);

    document.getElementById("stat-verified-count").innerText = verifiedClaims.length;
    document.getElementById("stat-rejected-count").innerText = rejectedClaims.length;
    document.getElementById("count-sourced-tab").innerText = verifiedClaims.length;
    document.getElementById("count-rejected-tab").innerText = rejectedClaims.length;

    document.getElementById("based-on-sources-text").innerText = `Based only on the ${currentSources.length} sources provided.`;

    // Fetch and display Red-Team verifier counter
    try {
      const rtRes = await fetch(`/api/sessions/${currentSessionId}/red-team`);
      const rtData = await rtRes.json();
      const pillRt = document.getElementById("pill-redteam");
      const statRt = document.getElementById("stat-redteam-counter");
      if (pillRt && statRt && rtData.extracted_count > 0) {
        pillRt.style.display = "flex";
        statRt.innerText = rtData.counter_text;
        pillRt.title = `Red-team refutation audit: ${rtData.counter_text}`;
      }
    } catch (e) {
      console.warn("Red-team counter load error:", e);
    }

    if (['sourced', 'rejected', 'all'].includes(currentActiveTab)) {
      renderClaimsView();
    }
  } catch (err) {
    console.error("Failed to load claims:", err);
  }
}

async function loadGaps() {
  if (!currentSessionId) return;

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/detect`, {
      method: "POST"
    });
    const data = await res.json();
    currentGaps = data.gaps || [];
    currentChecklist = data.checklist || [];

    document.getElementById("count-gaps-tab").innerText = currentGaps.length;
    document.getElementById("count-checklist-tab").innerText = currentChecklist.length;

    // Update Version/Period Banner Bar
    const currentVP = data.current_version_period || data.current_cycle;
    const isAssumed = data.is_version_period_assumed || data.is_cycle_assumed;
    const vpDisplay = document.getElementById("display-current-cycle");
    const modePill = document.getElementById("cycle-mode-pill");
    const desc = document.getElementById("cycle-banner-desc");
    const overrideInput = document.getElementById("input-override-cycle");

    if (vpDisplay) {
      vpDisplay.innerText = currentVP || "Not detected";
    }
    if (modePill) {
      if (data.version_period_warning && (data.version_period_warning.toLowerCase().includes("ended") || data.version_period_warning.toLowerCase().includes("assumed"))) {
        modePill.className = "badge badge-critical";
        modePill.innerText = "Period Expired (Assumed) ⚠️";
        if (desc) desc.innerHTML = `<span style="color: var(--accent-red); font-weight: 600;">⚠️ ${escapeHtml(data.version_period_warning)}</span>`;
      } else if (data.version_period_warning) {
        modePill.className = "badge badge-amber";
        modePill.innerText = "Unconfirmed Period ⚠️";
        if (desc) desc.innerHTML = `<span style="color: var(--accent-amber); font-weight: 600;">⚠️ ${escapeHtml(data.version_period_warning)}</span>`;
      } else if (isAssumed) {
        modePill.className = "badge badge-low";
        modePill.innerText = "Assumed from newest source";
        if (desc) desc.innerText = "Inferred dynamically from newest official source document. You can override it to the right.";
      } else {
        modePill.className = "badge badge-official";
        modePill.innerText = "User Override (Active)";
        if (desc) desc.innerText = "Explicitly set by user. To restore automatic detection, click Reset.";
      }
    }
    if (overrideInput && (!overrideInput.value || overrideInput.value === currentVP)) {
      overrideInput.value = currentVP || "";
    }

    // Update Independence Stats and Badges
    const indep = data.independence;
    if (indep && indep.total_sources > 0) {
      const pillIndep = document.getElementById("pill-independence");
      const statIndepNum = document.getElementById("stat-independence-num");
      if (pillIndep) {
        pillIndep.style.display = "flex";
        if (statIndepNum) statIndepNum.innerText = indep.badge_text;
        if (indep.total_sources > indep.independent_sources) {
          pillIndep.className = "stat-pill stat-independence has-copies";
          pillIndep.title = `⚡ Near-duplicate detection: ${indep.total_sources} sources, but only ${indep.independent_sources} independent original(s). Copies count as 1 source.`;
        } else {
          pillIndep.className = "stat-pill stat-independence";
          pillIndep.title = "All sources appear independent.";
        }
      }

      const indepBadge = document.getElementById("source-independence-badge");
      if (indepBadge) {
        indepBadge.style.display = "inline-flex";
        indepBadge.innerText = indep.badge_text;
        if (indep.total_sources > indep.independent_sources) {
          indepBadge.className = "badge badge-independence has-copies";
        } else {
          indepBadge.className = "badge badge-independence";
        }
      }
    }

    if (currentActiveTab === 'gaps') renderGapsView();
    if (currentActiveTab === 'checklist') renderChecklistView();
  } catch (err) {
    console.error("Gap detection error:", err);
  }
}

async function applyCycleOverride() {
  if (!currentSessionId) return;
  const input = document.getElementById("input-override-cycle");
  const newVP = input ? input.value.trim() : "";
  if (!newVP) {
    alert("Please enter a version or period (e.g. 2025, Fall 2025, Gen 7, or 2025-26)");
    return;
  }

  const btn = document.getElementById("btn-apply-cycle-override");
  btn.disabled = true;
  btn.innerText = "Updating...";

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/version-period`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_version_period: newVP })
    });
    await res.json();
    btn.disabled = false;
    btn.innerText = "Apply";
    await loadGaps();
    await loadMatrix();
  } catch (err) {
    alert("Error overriding version/period: " + err.message);
    btn.disabled = false;
    btn.innerText = "Apply";
  }
}

async function resetCycleOverride() {
  if (!currentSessionId) return;
  const btn = document.getElementById("btn-reset-cycle-override");
  btn.disabled = true;

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/version-period`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_version_period: null })
    });
    await res.json();
    btn.disabled = false;
    const input = document.getElementById("input-override-cycle");
    if (input) input.value = "";
    await loadGaps();
    await loadMatrix();
  } catch (err) {
    alert("Error resetting version/period: " + err.message);
    btn.disabled = false;
  }
}

async function loadMatrix() {
  if (!currentSessionId) return;

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/matrix`);
    currentMatrix = await res.json();

    const score = currentMatrix.stats ? currentMatrix.stats.coverage_score : 0;
    const badge = document.getElementById("count-matrix-coverage");
    if (badge) badge.innerText = `${score}%`;

    if (currentActiveTab === 'matrix') {
      renderMatrixView();
    }
  } catch (err) {
    console.error("Matrix load error:", err);
  }
}

function switchResultsTab(tab) {
  currentActiveTab = tab;
  
  // Update buttons
  const tabs = ['sourced', 'matrix', 'gaps', 'checklist', 'rejected', 'all'];
  tabs.forEach(t => {
    const btn = document.getElementById(`tab-btn-${t}`);
    if (btn) btn.classList.toggle("active", t === tab);
  });

  const claimsBox = document.getElementById("claims-container");
  const matrixBox = document.getElementById("matrix-container");
  const gapsBox = document.getElementById("gaps-container");
  const checklistBox = document.getElementById("checklist-container");

  claimsBox.style.display = "none";
  matrixBox.style.display = "none";
  gapsBox.style.display = "none";
  checklistBox.style.display = "none";

  if (tab === 'matrix') {
    matrixBox.style.display = "flex";
    if (!currentMatrix) {
      loadMatrix();
    } else {
      renderMatrixView();
    }
  } else if (tab === 'gaps') {
    gapsBox.style.display = "flex";
    renderGapsView();
  } else if (tab === 'checklist') {
    checklistBox.style.display = "flex";
    renderChecklistView();
  } else {
    claimsBox.style.display = "flex";
    renderClaimsView();
  }
}

function setMatrixFilter(filter) {
  currentMatrixFilter = filter;
  renderMatrixView();
}

function renderMatrixView() {
  const container = document.getElementById("matrix-container");
  if (!container) return;
  container.innerHTML = "";

  if (!currentMatrix || !currentMatrix.matrix || currentMatrix.matrix.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 2.5rem; color: var(--text-dim);">
        <p style="font-size: 1.1rem; font-weight: 600;">Coverage Matrix is empty.</p>
        <p style="font-size: 0.85rem; margin-top: 0.4rem;">Ingest sources and run extraction to generate the matrix.</p>
      </div>
    `;
    return;
  }

  const { stats, sources, matrix, version_period_warning, cycle_warning, current_version_period, current_cycle } = currentMatrix;
  const currentVP = current_version_period || current_cycle;
  const vpWarning = version_period_warning || cycle_warning;

  // 1. Metric Header Bar
  const headerBar = document.createElement("div");
  headerBar.className = "matrix-header-bar";
  headerBar.innerHTML = `
    <div class="matrix-stats-group">
      <div class="matrix-stat-pill matrix-stat-score">
        <span>📊</span>
        <div>
          <strong style="font-size: 1.1rem;">${stats.coverage_score}%</strong>
          <span style="font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); margin-left: 0.3rem;">Coverage (${stats.covered_facets}/${stats.total_facets})</span>
        </div>
      </div>
      <div class="matrix-stat-pill matrix-stat-darkspot">
        <span>🌑</span>
        <div>
          <strong style="font-size: 1.1rem;">${stats.dark_spots_count}</strong>
          <span style="font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); margin-left: 0.3rem;">Dark Spots</span>
        </div>
      </div>
      <div class="matrix-stat-pill matrix-stat-conflict">
        <span>⚡</span>
        <div>
          <strong style="font-size: 1.1rem;">${stats.conflicts_count}</strong>
          <span style="font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); margin-left: 0.3rem;">Discrepancies</span>
        </div>
      </div>
      <div class="matrix-stat-pill" style="border-color: rgba(255,255,255,0.15);">
        <span>📅</span>
        <span style="font-size: 0.82rem; font-weight: 600;">Version / Period: ${escapeHtml(currentVP || 'Unset')}</span>
      </div>
      <div class="matrix-stat-pill ${(currentMatrix.independence && currentMatrix.independence.total_sources > currentMatrix.independence.independent_sources) ? 'stat-independence has-copies' : ''}" style="border-color: rgba(139,92,246,0.35);">
        <span>🛡️</span>
        <span style="font-size: 0.82rem; font-weight: 700; font-family: var(--font-mono); color: #c084fc;">${escapeHtml((currentMatrix.independence && currentMatrix.independence.badge_text) || 'Independence')}</span>
      </div>
    </div>

    <!-- Filter Buttons -->
    <div class="matrix-filter-bar">
      <button class="matrix-filter-btn ${currentMatrixFilter === 'all' ? 'active' : ''}" onclick="setMatrixFilter('all')">All Facets (${matrix.length})</button>
      <button class="matrix-filter-btn ${currentMatrixFilter === 'darkspots' ? 'active' : ''}" onclick="setMatrixFilter('darkspots')">🌑 Dark Spots (${stats.dark_spots_count})</button>
      <button class="matrix-filter-btn ${currentMatrixFilter === 'conflicts' ? 'active' : ''}" onclick="setMatrixFilter('conflicts')">⚡ Conflicts (${stats.conflicts_count})</button>
      <button class="matrix-filter-btn ${currentMatrixFilter === 'covered' ? 'active' : ''}" onclick="setMatrixFilter('covered')">✓ Covered (${stats.covered_facets})</button>
    </div>
  `;
  container.appendChild(headerBar);

  // 2. Warning Alert (if any)
  if (vpWarning) {
    const alertBox = document.createElement("div");
    alertBox.className = "matrix-cycle-alert";
    alertBox.innerHTML = `
      <span style="font-size: 1.25rem;">⚠️</span>
      <div>
        <strong>Version / Period Notice:</strong> ${escapeHtml(vpWarning)}
      </div>
    `;
    container.appendChild(alertBox);
  }

  // 3. Filter Matrix Rows
  let filteredRows = matrix;
  if (currentMatrixFilter === 'darkspots') {
    filteredRows = matrix.filter(r => r.status === 'dark_spot');
  } else if (currentMatrixFilter === 'conflicts') {
    filteredRows = matrix.filter(r => r.status === 'conflict');
  } else if (currentMatrixFilter === 'covered') {
    filteredRows = matrix.filter(r => r.status !== 'dark_spot');
  }

  // 4. Matrix Table
  const tableWrap = document.createElement("div");
  tableWrap.className = "matrix-table-wrap";

  let tableHtml = `
    <table class="matrix-table">
      <thead>
        <tr>
          <th style="min-width: 240px;">Target Facet / Specification</th>
          ${sources.map(s => `
            <th>
              <div class="matrix-source-header">
                <div style="display: flex; gap: 0.3rem; align-items: center; justify-content: center; flex-wrap: wrap;">
                  <span class="badge badge-${s.authority}">${s.authority.toUpperCase()}</span>
                  ${s.is_original === false ? `<span class="source-copy-pill" style="font-size: 0.65rem;" title="Near-duplicate copy of original">📋 Copy</span>` : ''}
                </div>
                <span class="matrix-source-title" title="${escapeHtml(s.title)}">${escapeHtml(s.title)}</span>
                <span style="font-size: 0.72rem; color: var(--text-dim);">${escapeHtml(s.published_date || 'Undated')}</span>
              </div>
            </th>
          `).join('')}
          <th style="min-width: 170px;">Consensus / Status</th>
        </tr>
      </thead>
      <tbody>
  `;

  filteredRows.forEach(row => {
    let rowClass = "matrix-row-normal";
    if (row.status === 'dark_spot') rowClass = "matrix-row-dark-spot";
    if (row.status === 'conflict') rowClass = "matrix-row-conflict";
    if (row.status === 'version_period_difference' || row.status === 'time_difference') rowClass = "matrix-row-timediff";

    const importanceClass = `importance-${row.importance || 'high'}`;

    tableHtml += `
      <tr class="${rowClass}">
        <td class="matrix-facet-cell">
          <div style="display: flex; align-items: center; gap: 0.4rem; justify-content: space-between;">
            <span class="matrix-facet-name">${escapeHtml(row.facet_name)}</span>
            <span class="importance-pill ${importanceClass}">${(row.importance || 'high').toUpperCase()}</span>
          </div>
          <p class="matrix-facet-desc">${escapeHtml(row.description || '')}</p>
          <div style="display: flex; gap: 0.35rem; margin-top: 0.25rem;">
            <span class="meta-pill" style="font-size: 0.7rem;">${row.expected_type}</span>
            ${row.is_deadline ? '<span class="deadline-pill" style="font-size: 0.65rem;">📅 Deadline</span>' : ''}
          </div>
          ${row.status === 'dark_spot' ? `<div class="matrix-darkspot-badge">🌑 DARK SPOT (BLINDSPOT)</div>` : ''}
        </td>
    `;

    sources.forEach(s => {
      const cell = row.cells[s.id] || { has_claim: false };
      if (!cell.has_claim) {
        tableHtml += `
          <td class="matrix-cell-empty">
            <span style="opacity: 0.4;">—</span>
          </td>
        `;
      } else {
        let cellClass = "matrix-cell-has-claim";
        let cellIcon = "✓";
        if (cell.is_conflicting) {
          cellClass += " matrix-cell-conflict";
          cellIcon = "⚡";
        } else if (cell.is_outdated) {
          cellClass += " matrix-cell-outdated";
          cellIcon = "⏳";
        }

        const vpTag = (cell.version_period || cell.cycle) ? `<span class="matrix-cell-cycle">${escapeHtml(cell.version_period || cell.cycle)}</span>` : '';

        tableHtml += `
          <td class="${cellClass}">
            <div class="matrix-cell-content">
              <div class="matrix-cell-top">
                <span class="matrix-cell-val">${escapeHtml(cell.value_raw)}</span>
                ${vpTag}
              </div>
              <div class="matrix-cell-quote">
                “${escapeHtml(cell.exact_quote.slice(0, 90))}...”
              </div>
              <button class="btn-cell-inspect" onclick="inspectClaimEvidence('${cell.claim_id}')">
                🔍 Verify Quote
              </button>
            </div>
          </td>
        `;
      }
    });

    let statusPillClass = "matrix-status-corroborated";
    if (row.status === 'dark_spot') statusPillClass = "matrix-status-darkspot";
    if (row.status === 'conflict') statusPillClass = "matrix-status-conflict";
    if (row.status === 'partial_overlap') statusPillClass = "matrix-status-overlap";
    if (row.status === 'version_period_difference' || row.status === 'time_difference') statusPillClass = "matrix-status-timediff";
    if (row.status === 'single_source') statusPillClass = "matrix-status-single";

    tableHtml += `
        <td class="matrix-consensus-cell">
          <span class="matrix-status-pill ${statusPillClass}">${escapeHtml(row.status_label)}</span>
          <span style="font-size: 0.72rem; color: var(--text-dim); display: block; margin-top: 0.35rem;">
            Found in ${row.sources_covered} of ${row.total_sources} source(s)
          </span>
        </td>
      </tr>
    `;
  });

  tableHtml += `
      </tbody>
    </table>
  `;

  tableWrap.innerHTML = tableHtml;
  container.appendChild(tableWrap);
}

function renderGapsView() {
  const container = document.getElementById("gaps-container");
  container.innerHTML = "";

  if (currentGaps.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 2.5rem; color: var(--text-dim);">
        <p style="font-size: 1.1rem; font-weight: 600;">No information gaps or conflicts detected.</p>
        <p style="font-size: 0.85rem; margin-top: 0.4rem;">All target facets have corroborated coverage across sources.</p>
      </div>
    `;
    return;
  }

  currentGaps.forEach(g => {
    const card = document.createElement("div");
    card.className = "gap-card";

    let gapTypeClass = "gap-type-single";
    let icon = "🔍";
    if (g.gap_type === "conflict") {
      gapTypeClass = "gap-type-conflict";
      icon = "⚡";
    } else if (g.gap_type === "partial_overlap") {
      gapTypeClass = "gap-type-overlap";
      icon = "📋";
    } else if (g.gap_type === "version_period_difference" || g.gap_type === "time_difference") {
      gapTypeClass = "gap-type-timediff";
      icon = "⏳";
    } else if (g.gap_type === "missing") {
      gapTypeClass = "gap-type-missing";
      icon = "🌑";
    } else if (g.gap_type === "outdated") {
      gapTypeClass = "gap-type-outdated";
      icon = "📅";
    } else if (g.gap_type === "deadline_passed") {
      gapTypeClass = "gap-type-passed";
      icon = "🚨";
    }

    let sourcesHtml = "";
    if (g.sources_involved && g.sources_involved.length > 0) {
      sourcesHtml = `
        <div class="gap-sources-box">
          <div class="gap-sources-title">Sources Involved:</div>
          ${g.sources_involved.map(s => `
            <div class="gap-source-item">
              <span class="badge badge-${s.authority}">${(s.authority || 'source').toUpperCase()}</span>
              <strong>${escapeHtml(s.source_title)}</strong>:
              <span class="code-val">${escapeHtml(s.value || 'N/A')}</span>
              ${s.quote ? `<span class="source-snippet">“${escapeHtml(s.quote)}”</span>` : ''}
            </div>
          `).join('')}
        </div>
      `;
    }

    card.innerHTML = `
      <div class="gap-header">
        <div class="gap-header-left">
          <span class="gap-icon">${icon}</span>
          <div>
            <div class="gap-badges">
              <span class="gap-pill ${gapTypeClass}">${escapeHtml((g.conflict_taxonomy || g.gap_type).replace(/_/g, ' ').toUpperCase())}</span>
              <span class="priority-pill priority-${g.priority}">${g.priority.toUpperCase()} PRIORITY</span>
            </div>
            <h3 class="gap-title">${escapeHtml(g.title)}</h3>
          </div>
        </div>
      </div>

      <p class="gap-desc">${escapeHtml(g.description)}</p>

      ${sourcesHtml}

      <div class="gap-action-box">
        <div class="gap-consequence">
          <strong>Risk if unverified:</strong> ${escapeHtml(g.consequence)}
        </div>
        <div class="gap-action-text">
          ➔ <strong>Action Needed:</strong> ${escapeHtml(g.action_needed)}
        </div>
        ${g.email_draft ? `
          <div style="margin-top: 0.6rem;">
            <button class="btn btn-secondary btn-small" style="font-size: 0.75rem; padding: 0.25rem 0.6rem;" onclick="openEmailModalById('${g.id}')">
              ✉️ Draft Inquiry to Official Body
            </button>
          </div>
        ` : ''}
      </div>
    `;

    container.appendChild(card);
  });
}

function renderChecklistView() {
  const container = document.getElementById("checklist-container");
  container.innerHTML = "";

  if (currentChecklist.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 2.5rem; color: var(--text-dim);">
        <p style="font-size: 1.1rem; font-weight: 600;">Checklist is empty.</p>
        <p style="font-size: 0.85rem; margin-top: 0.4rem;">No verification gaps remaining to resolve.</p>
      </div>
    `;
    return;
  }

  currentChecklist.forEach((item, idx) => {
    const el = document.createElement("div");
    el.className = "checklist-item";
    el.id = `chk-row-${idx}`;

    el.innerHTML = `
      <input type="checkbox" class="checklist-checkbox" id="chk-${idx}" onchange="toggleChecklistItem(${idx})">
      <div class="checklist-content">
        <div class="checklist-top">
          <span class="priority-pill priority-${item.priority}">${item.priority.toUpperCase()}</span>
          <h4 class="checklist-title">${escapeHtml(item.title)}</h4>
        </div>
        <div class="checklist-action">
          ➔ <strong>Next Step:</strong> ${escapeHtml(item.action_needed)}
        </div>
        <div class="checklist-consequence">
          ⚠️ <strong>Risk if ignored:</strong> ${escapeHtml(item.consequence)}
        </div>
        ${item.email_draft ? `
          <div style="margin-top: 0.5rem;">
            <button class="btn btn-secondary btn-small" style="font-size: 0.72rem; padding: 0.2rem 0.5rem;" onclick="openEmailModalById('${item.id}')">
              ✉️ Draft Inquiry to Official Body
            </button>
          </div>
        ` : ''}
      </div>
    `;

    container.appendChild(el);
  });
}

function toggleChecklistItem(idx) {
  const checkbox = document.getElementById(`chk-${idx}`);
  const row = document.getElementById(`chk-row-${idx}`);
  if (checkbox && row) {
    row.classList.toggle("checked", checkbox.checked);
  }
}

function renderClaimsView() {
  const container = document.getElementById("claims-container");
  container.innerHTML = "";

  let list = currentClaims;
  if (currentActiveTab === 'sourced') {
    list = currentClaims.filter(c => c.verified);
  } else if (currentActiveTab === 'rejected') {
    list = currentClaims.filter(c => !c.verified);
  }

  if (list.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 2.5rem; color: var(--text-dim);">
        <p style="font-size: 1.1rem; font-weight: 600;">No claims in this category.</p>
        <p style="font-size: 0.85rem; margin-top: 0.4rem;">Select another tab to inspect findings.</p>
      </div>
    `;
    return;
  }

  list.forEach(c => {
    const card = document.createElement("div");
    card.className = `claim-card ${c.verified ? 'claim-card-verified' : 'claim-card-rejected'}`;

    let authClass = "badge-secondary";
    if (c.source_authority === "official") authClass = "badge-official";
    if (c.source_authority === "low") authClass = "badge-low";

    const scorePct = Math.round(c.verification_score * 100);
    const scoreBadge = c.verified
      ? `<span class="badge badge-live">✓ ${scorePct}% Quote Match</span>`
      : `<span class="badge badge-low">✗ Code Rejected</span>`;

    let redteamBadge = "";
    if (c.verified) {
      if (c.survived_redteam && c.redteam_status !== "uncertain") {
        redteamBadge = `<span class="badge" style="background:#e0f2fe; color:#0369a1;" title="Passed second-pass adversarial refutation check">🛡️ Red-Team Survived</span>`;
      } else {
        redteamBadge = `<span class="badge" style="background:#fef3c7; color:#b45309;" title="${escapeHtml(c.redteam_notes || 'Demoted: Refuted by second-pass adversarial check')}">⚠️ Demoted: Uncertain</span>`;
      }
    }

    const vp = c.version_period || c.cycle;
    const vpBadge = vp ? `<span class="chip">Period: ${escapeHtml(vp)}</span>` : '';
    const scopeBadge = c.scope ? `<span class="chip">Scope: ${escapeHtml(c.scope)}</span>` : '';

    let rejectionHtml = "";
    if (!c.verified) {
      rejectionHtml = `
        <div class="rejection-banner">
          <span>❌ Code Verification Blocked:</span>
          <strong>${escapeHtml(c.rejection_reason || "Quote or value not found in real text")}</strong>
        </div>
      `;
    }

    let redteamNotesHtml = "";
    if (c.verified && (!c.survived_redteam || c.redteam_status === "uncertain")) {
      redteamNotesHtml = `
        <div style="font-size: 0.75rem; color: #d97706; background: rgba(217, 119, 6, 0.1); border-left: 3px solid #d97706; padding: 0.35rem 0.6rem; border-radius: 0 4px 4px 0; margin-top: 0.4rem;">
          <strong>⚠️ Red-Team Demoted to Uncertain:</strong> ${escapeHtml(c.redteam_notes || "Claim could not be authoritatively substantiated under adversarial scrutiny.")}
        </div>
      `;
    }

    card.innerHTML = `
      <div class="claim-header">
        <span class="facet-badge">${escapeHtml(c.facet.replace(/_/g, ' '))}</span>
        <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
          ${scoreBadge}
          ${redteamBadge}
          <span class="badge ${authClass}">${c.source_authority}</span>
        </div>
      </div>

      <div class="claim-val-row">
        <span class="claim-value">${escapeHtml(c.value_raw)}</span>
        <div style="display: flex; gap: 0.35rem;">
          ${vpBadge}
          ${scopeBadge}
        </div>
      </div>

      ${rejectionHtml}

      <div class="claim-quote-box">
        “${escapeHtml(c.exact_quote)}”
      </div>

      ${redteamNotesHtml}

      <div class="claim-card-footer">
        <span>Source: <strong>${escapeHtml(c.source_title || "Document")}</strong></span>
        <button class="btn-inspect" onclick="inspectClaimEvidence('${c.id}')">
          🔍 View in Raw Source
        </button>
      </div>
    `;

    container.appendChild(card);
  });
}

function inspectClaimEvidence(claimId) {
  const claim = currentClaims.find(c => c.id === claimId);
  if (!claim) return;

  const source = currentSources.find(s => s.id === claim.source_id);
  if (!source) return;

  document.getElementById("modal-source-title").innerText = source.title || "Source Document";
  document.getElementById("modal-source-url").innerText = source.url || "Pasted text";
  document.getElementById("modal-exact-quote").innerText = `“${claim.exact_quote}”`;

  const authBadge = document.getElementById("modal-authority-badge");
  authBadge.innerText = (source.authority || "low").toUpperCase();
  authBadge.className = `badge badge-${source.authority}`;

  const scorePct = Math.round(claim.verification_score * 100);
  document.getElementById("modal-match-score").innerText = `Verification Match: ${scorePct}%`;

  // Render document text with highlight span
  const docContainer = document.getElementById("modal-doc-text");
  const fullText = source.text || "";

  if (claim.quote_offset_start !== null && claim.quote_offset_end !== null) {
    const before = fullText.slice(0, claim.quote_offset_start);
    const highlighted = fullText.slice(claim.quote_offset_start, claim.quote_offset_end);
    const after = fullText.slice(claim.quote_offset_end);

    docContainer.innerHTML = `${escapeHtml(before)}<mark class="highlight-span" id="target-highlight">${escapeHtml(highlighted)}</mark>${escapeHtml(after)}`;

    setTimeout(() => {
      const el = document.getElementById("target-highlight");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 150);
  } else {
    docContainer.innerHTML = `<span style="color: #f87171; font-weight: bold;">[NO MATCHED SPAN IN REAL TEXT - CLAIM REJECTED]</span>\n\n` + escapeHtml(fullText);
  }

  document.getElementById("source-modal").style.display = "flex";
}

function closeSourceModal() {
  document.getElementById("source-modal").style.display = "none";
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ==========================================
// Change Watch & Re-Check Handlers
// ==========================================

async function recheckSource(sourceId) {
  try {
    const res = await fetch(`/api/sources/${sourceId}/recheck`, { method: "POST" });
    const data = await res.json();
    const changeNote = "Note: any text change counts, including small page edits";
    if (data.changed) {
      alert(`⚠️ Change Detected in Source!\n\n${data.summary}\n\n${changeNote}\n\nOld Hash: ${data.old_hash.slice(0, 12)}...\nNew Hash: ${data.new_hash.slice(0, 12)}...`);
    } else {
      alert(`✓ Source Re-Checked: ${data.summary}\n\n${changeNote}`);
    }
    await loadSources();
  } catch (err) {
    alert("Re-check failed: " + err.message);
  }
}

// ==========================================
// Email Inquiry Draft Modal Handlers
// ==========================================

function openEmailModalById(gapId) {
  let draft = null;
  const foundGap = currentGaps.find(g => g.id === gapId);
  if (foundGap && foundGap.email_draft) {
    draft = foundGap.email_draft;
  } else {
    const foundChk = currentChecklist.find(c => c.id === gapId);
    if (foundChk && foundChk.email_draft) draft = foundChk.email_draft;
  }

  if (!draft) {
    alert("No draft inquiry available for this item.");
    return;
  }
  openEmailModal(draft);
}

function openEmailModal(draft) {
  document.getElementById("modal-email-title").innerText = `Inquiry: ${draft.facet_name || 'Official Clarification'}`;
  
  if (draft.recipient_quote) {
    document.getElementById("modal-email-recipient").innerText = `To: ${draft.recipient} (Quoted in '${draft.recipient_source}': “${draft.recipient_quote}”)`;
  } else {
    document.getElementById("modal-email-recipient").innerText = `To: ${draft.recipient}`;
  }

  document.getElementById("modal-email-subject").value = draft.subject;
  document.getElementById("modal-email-body").value = draft.body;
  document.getElementById("email-draft-modal").style.display = "flex";
}

function closeEmailModal() {
  document.getElementById("email-draft-modal").style.display = "none";
}

function copyEmailDraft() {
  const subject = document.getElementById("modal-email-subject").value;
  const body = document.getElementById("modal-email-body").value;
  const recipient = document.getElementById("modal-email-recipient").innerText;
  const text = `${recipient}\nSubject: ${subject}\n\n${body}`;

  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById("btn-copy-email");
    const orig = btn.innerText;
    btn.innerText = "✓ Copied to Clipboard!";
    setTimeout(() => { btn.innerText = orig; }, 2000);
  }).catch(() => {
    alert("Failed to copy text. Please select and copy manually.");
  });
}

// ==========================================
// Audit-Trail Export Handlers
// ==========================================

function exportAuditTrailJson() {
  if (!currentSessionId) {
    alert("Please initialize or select a session first.");
    return;
  }
  window.open(`/api/sessions/${currentSessionId}/export/json`, "_blank");
}

function exportAuditTrailHtml() {
  if (!currentSessionId) {
    alert("Please initialize or select a session first.");
    return;
  }
  window.open(`/api/sessions/${currentSessionId}/export/html`, "_blank");
}

