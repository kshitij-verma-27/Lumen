from pathlib import Path

app_path = Path("frontend/app.js")
with open(app_path, "r", encoding="utf-8") as f:
    code = f.read()

# Update showInvestigateView to show the chat view in home-view
code = code.replace(
    'function showInvestigateView() {\n  hideAllViews();\n  const v = document.getElementById("notebook-view");',
    'function showInvestigateView() {\n  hideAllViews();\n  const v = document.getElementById("home-view");'
)

# Update openNewInvestigation
old_open_new = """function openNewInvestigation() {
  window.location.hash = "#/investigate";
  const docTitle = document.getElementById("doc-title-text");
  const goalInput = document.getElementById("goal-input");
  if (docTitle) docTitle.innerText = "New Research Investigation";
  if (goalInput) goalInput.value = "New Research Investigation";
}"""

new_open_new = """function openNewInvestigation() {
  currentSessionId = null;
  chatAttachedSources = [];
  renderComposerSourceChips();
  const input = document.getElementById("chat-input");
  if (input) input.value = "";
  const emptyState = document.getElementById("chat-empty-state");
  if (emptyState) emptyState.style.display = "flex";
  const msgList = document.getElementById("chat-messages-list");
  if (msgList) msgList.innerHTML = "";
  window.location.hash = "#/";
  showHomeView();
  if (window.innerWidth <= 768) {
    const sidebar = document.getElementById("sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (sidebar) sidebar.classList.remove("drawer-open");
    if (backdrop) backdrop.classList.remove("active");
  }
}"""

code = code.replace(old_open_new, new_open_new)

# Update loadHistoricalSession to render chat message
old_hist = """function loadHistoricalSession(sessionId, title) {
  currentSessionId = sessionId;
  const titleEl = document.getElementById("doc-title-text");
  const goalInput = document.getElementById("goal-input");
  if (titleEl) titleEl.innerText = title;
  if (goalInput) goalInput.value = title;
  openNotebookView();
  loadSources();
  loadClaims();
  loadGaps();
  loadMatrix();
  renderSidebarHistory();
}"""

new_hist = """async function loadHistoricalSession(sessionId, title) {
  currentSessionId = sessionId;
  const titleEl = document.getElementById("doc-title-text");
  const goalInput = document.getElementById("goal-input");
  if (titleEl) titleEl.innerText = title;
  if (goalInput) goalInput.value = title;
  
  if (window.innerWidth <= 768) {
    const sidebar = document.getElementById("sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (sidebar) sidebar.classList.remove("drawer-open");
    if (backdrop) backdrop.classList.remove("active");
  }

  showHomeView();
  await loadSources();
  await loadClaims();
  await loadGaps();
  await loadMatrix();

  const emptyState = document.getElementById("chat-empty-state");
  if (emptyState) emptyState.style.display = "none";

  const msgList = document.getElementById("chat-messages-list");
  if (msgList) {
    const assistantMsgId = `assistant-msg-${Date.now()}`;
    msgList.innerHTML = `
      <div class="chat-msg user-msg">
        <div class="msg-header">
          <div class="msg-author"><span>👤</span> <span>You</span></div>
          <div class="msg-time">Past investigation</div>
        </div>
        <div class="user-query-text">${escapeHtml(title)}</div>
      </div>
      <div class="chat-msg assistant-msg" id="${assistantMsgId}">
        <div class="msg-header">
          <div class="msg-author"><span>📓</span> <span style="font-family: var(--font-serif); font-weight: 600;">Lumen</span></div>
          <div class="msg-time">Completed</div>
        </div>
        <div id="${assistantMsgId}-content"></div>
      </div>
    `;

    let indData = { count: currentSources.length, clusters: 1 };
    try {
      const indRes = await fetch(`/api/sessions/${currentSessionId}/independence`);
      if (indRes.ok) indData = await indRes.json();
    } catch(e) {}

    let rtData = { extracted_count: 0, verified_count: 0, refuted_count: 0, counter_text: "0 checked" };
    try {
      const rtRes = await fetch(`/api/sessions/${currentSessionId}/red-team`);
      if (rtRes.ok) rtData = await rtRes.json();
    } catch(e) {}

    renderChatAssistantResult(assistantMsgId, title, currentSources, indData, rtData);
  }

  renderSidebarHistory();
}"""

code = code.replace(old_hist, new_hist)

with open(app_path, "w", encoding="utf-8") as f:
    f.write(code)

print("Successfully updated routing and history in frontend/app.js")
