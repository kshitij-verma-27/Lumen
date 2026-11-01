from pathlib import Path

# Patch index.html
html_path = Path("frontend/index.html")
html = html_path.read_text(encoding="utf-8")

html = html.replace("Red-Team Audit", "Double-Check Audit")
html = html.replace("Adversarial quote refutation active", "Double-check: Verifies quotes against source text")
html = html.replace("official seeds audited", "official sources audited")
html = html.replace("official seeds", "official sources")
html = html.replace("live official seeds", "live official sources")
html = html.replace("BLINDSPOT ENGINE", "FINDS WHAT IS MISSING")
html = html.replace("Research Notebook & Blindspot Engine", "Research Notebook & Information-Gap Engine")

html_path.write_text(html, encoding="utf-8")

# Patch app.js
app_path = Path("frontend/app.js")
app_js = app_path.read_text(encoding="utf-8")

app_js = app_js.replace("Loading 29 official seeds...", "Loading 29 official sources...")
app_js = app_js.replace("Red-Team Survived", "Double-Check Verified")
app_js = app_js.replace("Red-Team Demoted", "Double-Check Flagged")
app_js = app_js.replace("Red-team refutation audit:", "Double-check quote audit:")
app_js = app_js.replace("No critical blindspots or conflicts detected", "No critical missing items or conflicts detected")

# Also update executeHomeInvestigate to forward to handleComposerSubmit
old_exec_home = """async function executeHomeInvestigate() {
  const searchInput = document.getElementById("home-search-input");
  const query = searchInput ? searchInput.value.trim() : "";
  if (!query) {
    openNotebookView();
    const titleEl = document.getElementById("doc-title-text");
    const goalInput = document.getElementById("goal-input");
    if (titleEl) titleEl.innerText = "National Means-cum-Merit Scholarship Scheme";
    if (goalInput) goalInput.value = "What are the exact eligibility criteria, parental income limit, and application deadline for National Means-cum-Merit Scholarship?";
    return;
  }

  const titleEl = document.getElementById("doc-title-text");
  const goalInput = document.getElementById("goal-input");
  if (titleEl) titleEl.innerText = query;
  if (goalInput) goalInput.value = query;

  openNotebookView();
  try {
    await generateFacetsWithAI();
  } catch (e) {
    console.warn("AI facet generation:", e);
  }
  await initializeSession();
}"""

new_exec_home = """async function executeHomeInvestigate() {
  const searchInput = document.getElementById("home-search-input");
  const chatInput = document.getElementById("chat-input");
  const query = (searchInput && searchInput.value.trim()) || (chatInput && chatInput.value.trim()) || "What are the exact eligibility criteria and deadline for National Scholarship Scheme?";
  if (chatInput) chatInput.value = query;
  handleComposerSubmit();
}

async function launch1ClickDemo() {
  runOneClickDemo();
}

async function launchTopicInvestigation(topicId) {
  selectSuggestion(topicId);
}"""

app_js = app_js.replace(old_exec_home, new_exec_home)

app_path.write_text(app_js, encoding="utf-8")

print("Successfully updated plain language in index.html and app.js")
