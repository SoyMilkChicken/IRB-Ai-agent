const state = {
  currentStep: 1,
  evaluation: null,
  drafts: {
    consent: "",
    recruitment: "",
    data_handling: "",
  },
  aiMode: "unknown",
};

const form = document.getElementById("intakeForm");
const screens = Array.from(document.querySelectorAll(".screen"));
const stepButtons = Array.from(document.querySelectorAll(".step"));
const healthBanner = document.getElementById("healthBanner");
const summaryCard = document.getElementById("summaryCard");
const flagList = document.getElementById("flagList");
const progressFill = document.getElementById("progressFill");
const progressLabel = document.getElementById("progressLabel");
const apiBaseUrl = resolveApiBaseUrl();

function normalizeApiBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function resolveApiBaseUrl() {
  let fromQuery = "";
  try {
    const params = new URLSearchParams(window.location.search);
    fromQuery = params.get("apiBaseUrl") || "";
  } catch {
    fromQuery = "";
  }

  const fromConfig = window.IRB_COPILOT_CONFIG?.apiBaseUrl || "";
  const fromStorage = (() => {
    try {
      return localStorage.getItem("irb-copilot-api-base-url") || "";
    } catch {
      return "";
    }
  })();

  const resolved = normalizeApiBaseUrl(fromQuery || fromConfig || fromStorage);
  if (fromQuery && resolved) {
    try {
      localStorage.setItem("irb-copilot-api-base-url", resolved);
    } catch {
      // Ignore storage errors.
    }
  }
  return resolved;
}

function apiUrl(path) {
  return apiBaseUrl ? `${apiBaseUrl}${path}` : path;
}

function getStepTitle(step) {
  const btn = stepButtons.find((node) => Number(node.dataset.step) === step);
  return btn?.dataset.stepTitle || btn?.textContent?.trim() || `Step ${step}`;
}

function restartAnimation(el, className) {
  if (!el) return;
  el.classList.remove(className);
  // Force reflow so the animation restarts on repeated step changes.
  void el.offsetWidth;
  el.classList.add(className);
}

function updateProgressUI() {
  const total = screens.length;
  const progress = Math.round((state.currentStep / total) * 100);
  if (progressFill) {
    progressFill.style.width = `${progress}%`;
  }
  if (progressLabel) {
    progressLabel.textContent = `Step ${state.currentStep} of ${total} · ${getStepTitle(state.currentStep)}`;
  }
}

function setStep(step) {
  state.currentStep = Math.max(1, Math.min(5, step));
  for (const screen of screens) {
    const isActive = Number(screen.dataset.screen) === state.currentStep;
    screen.classList.toggle("active", isActive);
    if (isActive) {
      restartAnimation(screen, "screen--animate");
    }
  }
  for (const button of stepButtons) {
    button.classList.toggle("active", Number(button.dataset.step) === state.currentStep);
  }
  document.body.dataset.currentStep = String(state.currentStep);
  updateProgressUI();
}

function getCheckboxValues(name) {
  return Array.from(form.querySelectorAll(`input[name="${name}"]:checked`)).map((el) => el.value);
}

function getFormData() {
  const fd = new FormData(form);
  return {
    studyTitle: fd.get("studyTitle") || "",
    institution: fd.get("institution") || "",
    courseName: fd.get("courseName") || "",
    projectPurpose: fd.get("projectPurpose") || "",
    dataCollectionMethods: getCheckboxValues("dataCollectionMethods"),
    participantGroups: getCheckboxValues("participantGroups"),
    recruiterRole: fd.get("recruiterRole") || "undecided",
    includesMinors: fd.get("includesMinors") || "unknown",
    participationVoluntary: fd.get("participationVoluntary") === "on",
    offersExtraCredit: fd.get("offersExtraCredit") === "on",
    alternativeActivityProvided: fd.get("alternativeActivityProvided") === "on",
    aiAffectsOfficialGrades: fd.get("aiAffectsOfficialGrades") === "on",
    researchSeparateFromGrades: fd.get("researchSeparateFromGrades") === "on",
    collectsIdentifiers: fd.get("collectsIdentifiers") === "on",
    collectsEducationRecords: fd.get("collectsEducationRecords") === "on",
    collectsSensitive: fd.get("collectsSensitive") === "on",
    deidentifyBeforeAnalysis: fd.get("deidentifyBeforeAnalysis") === "on",
    identifierTypes: getCheckboxValues("identifierTypes"),
    storageLocation: fd.get("storageLocation") || "",
    accessRoles: fd.get("accessRoles") || "",
    retentionPeriod: fd.get("retentionPeriod") || "",
    thirdPartyTools: fd.get("thirdPartyTools") || "",
  };
}

async function apiPost(path, body) {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function renderSummary(evaluation) {
  const summary = evaluation.summary || {};
  const counts = summary.flagCounts || { high: 0, medium: 0, low: 0 };
  const humanSubjects = summary.likelyHumanSubjectsResearch ? "Likely yes" : "Unclear";
  const minimalRisk = summary.likelyMinimalRisk ? "Possibly minimal risk" : "Needs closer review";
  const nextSteps = (summary.nextSteps || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("");

  summaryCard.classList.remove("muted");
  summaryCard.innerHTML = `
    <div class="summary-grid">
      <div>
        <p class="label">Human subjects research</p>
        <p class="value">${escapeHtml(humanSubjects)}</p>
      </div>
      <div>
        <p class="label">Risk profile</p>
        <p class="value">${escapeHtml(minimalRisk)}</p>
      </div>
      <div>
        <p class="label">Flags</p>
        <p class="value">${counts.high} high / ${counts.medium} medium / ${counts.low} low</p>
      </div>
    </div>
    <div class="notes">
      <p class="label">Next steps</p>
      <ul>${nextSteps || "<li>Draft materials and review with your advisor.</li>"}</ul>
    </div>
  `;
  restartAnimation(summaryCard, "surface-pop");
}

function renderFlags(evaluation) {
  flagList.innerHTML = "";
  const flags = evaluation.flags || [];
  if (!flags.length) {
    const el = document.createElement("div");
    el.className = "card muted";
    el.innerHTML = "<p>No rule-based flags were triggered. You should still review institution-specific IRB requirements.</p>";
    flagList.append(el);
    return;
  }
  const tpl = document.getElementById("flagTemplate");
  for (const [index, flag] of flags.entries()) {
    const node = tpl.content.firstElementChild.cloneNode(true);
    const pill = node.querySelector(".severity-pill");
    pill.textContent = flag.severity.toUpperCase();
    pill.dataset.severity = flag.severity;
    node.querySelector(".flag-title").textContent = flag.title;
    node.querySelector(".flag-rationale").textContent = flag.rationale;
    const list = node.querySelector(".flag-actions");
    for (const action of flag.actions || []) {
      const li = document.createElement("li");
      li.textContent = action;
      list.append(li);
    }
    node.style.setProperty("--stagger", `${index * 55}ms`);
    flagList.append(node);
  }
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function checkHealth() {
  try {
    const res = await fetch(apiUrl("/api/health"));
    const data = await res.json();
    state.aiMode = data.aiMode || "unknown";
    const modeLabel = state.aiMode === "openai" ? "AI API connected" : "Template fallback mode";
    const backendLabel = apiBaseUrl ? `Backend: ${apiBaseUrl}. ` : "Backend: same origin. ";
    healthBanner.textContent = `${modeLabel}. ${backendLabel}${data.note || ""}`;
    healthBanner.dataset.mode = state.aiMode;
    restartAnimation(healthBanner, "surface-pop");
  } catch (err) {
    const backendLabel = apiBaseUrl ? ` (${apiBaseUrl})` : "";
    healthBanner.textContent = `Unable to reach backend${backendLabel}: ${err.message}`;
    healthBanner.dataset.mode = "error";
    restartAnimation(healthBanner, "surface-pop");
  }
}

async function runEvaluation() {
  const intake = getFormData();
  const button = document.getElementById("evaluateBtn");
  button.disabled = true;
  button.textContent = "Running...";
  try {
    const data = await apiPost("/api/evaluate", { intake });
    state.evaluation = data.evaluation;
    renderSummary(state.evaluation);
    renderFlags(state.evaluation);
    persistLocal();
  } catch (err) {
    summaryCard.classList.add("muted");
    summaryCard.innerHTML = `<p>Error: ${escapeHtml(err.message)}</p>`;
  } finally {
    button.disabled = false;
    button.textContent = "Run Pre-Screen";
  }
}

function getDraftTextarea(docType) {
  return document.querySelector(`[data-textarea-for="${docType}"]`);
}

function setDraftStatus(docType, text, kind = "info") {
  const el = document.querySelector(`[data-status-for="${docType}"]`);
  el.textContent = text;
  el.dataset.kind = kind;
}

async function ensureEvaluation() {
  if (state.evaluation) return;
  await runEvaluation();
}

async function generateDraft(docType) {
  await ensureEvaluation();
  const intake = getFormData();
  setDraftStatus(docType, "Generating draft...", "pending");
  try {
    const data = await apiPost("/api/draft", {
      intake,
      evaluation: state.evaluation,
      docType,
    });
    const draft = data.draft || {};
    state.drafts[docType] = draft.text || "";
    getDraftTextarea(docType).value = state.drafts[docType];
    restartAnimation(getDraftTextarea(docType), "textarea-flash");
    const modeLabel = draft.mode === "openai" ? "AI draft" : "Template draft";
    const warning = draft.warning ? ` (${draft.warning})` : "";
    setDraftStatus(docType, `${modeLabel} generated${warning}`, draft.mode === "openai" ? "success" : "warning");
    persistLocal();
  } catch (err) {
    setDraftStatus(docType, `Error: ${err.message}`, "error");
  }
}

async function rewriteDraft(docType, goal) {
  const textarea = getDraftTextarea(docType);
  const sourceText = textarea.value.trim();
  if (!sourceText) {
    setDraftStatus(docType, "Generate or paste draft text before rewriting.", "warning");
    return;
  }
  setDraftStatus(docType, `Rewriting (${goal.replaceAll("_", " ")})...`, "pending");
  try {
    const data = await apiPost("/api/rewrite", {
      text: sourceText,
      goal,
      intake: getFormData(),
    });
    const rewrite = data.rewrite || {};
    textarea.value = rewrite.text || sourceText;
    state.drafts[docType] = textarea.value;
    restartAnimation(textarea, "textarea-flash");
    const modeLabel = rewrite.mode === "openai" ? "AI rewrite" : "Rule-based rewrite";
    const warning = rewrite.warning ? ` (${rewrite.warning})` : "";
    setDraftStatus(docType, `${modeLabel} applied${warning}`, rewrite.mode === "openai" ? "success" : "warning");
    persistLocal();
  } catch (err) {
    setDraftStatus(docType, `Error: ${err.message}`, "error");
  }
}

async function generateAllDrafts() {
  const button = document.getElementById("generateAllBtn");
  button.disabled = true;
  button.textContent = "Generating...";
  try {
    await generateDraft("consent");
    await generateDraft("recruitment");
    await generateDraft("data_handling");
  } finally {
    button.disabled = false;
    button.textContent = "Generate All Drafts";
  }
}

function exportBundle() {
  const reviewChecked = document.getElementById("humanReviewCheckbox").checked;
  if (!reviewChecked) {
    alert("Please confirm human review is required before exporting the draft bundle.");
    return;
  }

  const intake = getFormData();
  const evaluation = state.evaluation || { summary: {}, flags: [] };
  const parts = [];
  parts.push("IRB COPILOT DRAFT BUNDLE (MVP)");
  parts.push("Generated for IRB preparation support only. Not IRB approval.");
  parts.push("");
  parts.push("=== PROJECT INTAKE (JSON) ===");
  parts.push(JSON.stringify(intake, null, 2));
  parts.push("");
  parts.push("=== PRE-SCREEN EVALUATION (JSON) ===");
  parts.push(JSON.stringify(evaluation, null, 2));
  parts.push("");
  parts.push("=== CONSENT DRAFT ===");
  parts.push(state.drafts.consent || "[No draft generated]");
  parts.push("");
  parts.push("=== RECRUITMENT DRAFT ===");
  parts.push(state.drafts.recruitment || "[No draft generated]");
  parts.push("");
  parts.push("=== DATA HANDLING DRAFT ===");
  parts.push(state.drafts.data_handling || "[No draft generated]");
  parts.push("");

  const blob = new Blob([parts.join("\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const safeTitle = (intake.studyTitle || "irb-copilot").replace(/[^a-z0-9-_]+/gi, "_").slice(0, 40);
  a.download = `${safeTitle || "irb-copilot"}_draft_bundle.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function persistLocal() {
  const payload = {
    intake: getFormData(),
    evaluation: state.evaluation,
    drafts: {
      consent: getDraftTextarea("consent").value,
      recruitment: getDraftTextarea("recruitment").value,
      data_handling: getDraftTextarea("data_handling").value,
    },
  };
  localStorage.setItem("irb-copilot-mvp", JSON.stringify(payload));
}

function restoreLocal() {
  const raw = localStorage.getItem("irb-copilot-mvp");
  if (!raw) return;
  try {
    const saved = JSON.parse(raw);
    const intake = saved.intake || {};
    for (const [key, value] of Object.entries(intake)) {
      const fields = form.querySelectorAll(`[name="${CSS.escape(key)}"]`);
      if (!fields.length) continue;
      const first = fields[0];
      if (first.type === "checkbox") {
        if (Array.isArray(value)) {
          for (const field of fields) {
            field.checked = value.includes(field.value);
          }
        } else {
          first.checked = Boolean(value);
        }
      } else if (first.tagName === "SELECT" || first.tagName === "TEXTAREA" || first.type === "text") {
        first.value = value ?? "";
      }
    }

    state.evaluation = saved.evaluation || null;
    if (state.evaluation) {
      renderSummary(state.evaluation);
      renderFlags(state.evaluation);
    }

    for (const docType of ["consent", "recruitment", "data_handling"]) {
      const text = saved.drafts?.[docType] || "";
      state.drafts[docType] = text;
      getDraftTextarea(docType).value = text;
      if (text) setDraftStatus(docType, "Restored from local draft", "info");
    }
  } catch {
    // Ignore corrupted local cache.
  }
}

document.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const stepButton = target.closest(".step");

  if (target.matches("[data-nav]")) {
    const direction = target.dataset.nav;
    setStep(state.currentStep + (direction === "next" ? 1 : -1));
    return;
  }

  if (stepButton) {
    setStep(Number(stepButton.dataset.step));
    return;
  }

  if (target.id === "evaluateBtn") {
    await runEvaluation();
    return;
  }

  if (target.id === "generateAllBtn") {
    await generateAllDrafts();
    return;
  }

  if (target.id === "exportBtn") {
    exportBundle();
    return;
  }

  if (target.matches("[data-action='generate']")) {
    const docType = target.dataset.doc;
    await generateDraft(docType);
    return;
  }

  if (target.matches("[data-action='rewrite']")) {
    const docType = target.dataset.doc;
    const goal = target.dataset.goal;
    await rewriteDraft(docType, goal);
    return;
  }
});

for (const el of form.querySelectorAll("input, select, textarea")) {
  el.addEventListener("change", persistLocal);
  el.addEventListener("input", () => {
    if (el.tagName === "TEXTAREA" || (el instanceof HTMLInputElement && el.type === "text")) {
      persistLocal();
    }
  });
}

restoreLocal();
checkHealth();
setStep(1);
