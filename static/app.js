const state = {
  currentStep: 1,
  evaluation: null,
  profileCatalog: [],
  defaultProfileId: "",
  activeProfile: null,
  readiness: null,
  importResult: null,
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
const profileSelect = document.getElementById("irbProfileSelect");
const profileMetaCard = document.getElementById("profileMetaCard");
const readinessStatus = document.getElementById("readinessStatus");
const readinessSummaryCard = document.getElementById("readinessSummaryCard");
const readinessDetails = document.getElementById("readinessDetails");
const sectionChecklistCard = document.getElementById("sectionChecklistCard");
const importOrgNameInput = document.getElementById("importOrgNameInput");
const importOrgWebsiteInput = document.getElementById("importOrgWebsiteInput");
const importIrbUrlInput = document.getElementById("importIrbUrlInput");
const importRawTextInput = document.getElementById("importRawTextInput");
const importStatus = document.getElementById("importStatus");
const importResultCard = document.getElementById("importResultCard");
const applyImportedProfileBtn = document.getElementById("applyImportedProfileBtn");
const apiBaseUrl = resolveApiBaseUrl();
const backendApiKey = resolveBackendApiKey();

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

function resolveBackendApiKey() {
  let fromQuery = "";
  try {
    const params = new URLSearchParams(window.location.search);
    fromQuery = params.get("backendApiKey") || params.get("apiKey") || "";
  } catch {
    fromQuery = "";
  }

  const fromConfig = window.IRB_COPILOT_CONFIG?.backendApiKey || "";
  const fromStorage = (() => {
    try {
      return localStorage.getItem("irb-copilot-backend-api-key") || "";
    } catch {
      return "";
    }
  })();

  const resolved = String(fromQuery || fromConfig || fromStorage || "").trim();
  if (fromQuery && resolved) {
    try {
      localStorage.setItem("irb-copilot-backend-api-key", resolved);
    } catch {
      // Ignore storage errors.
    }
  }
  return resolved;
}

function buildApiHeaders(includeJsonContentType = false) {
  const headers = {};
  if (includeJsonContentType) {
    headers["Content-Type"] = "application/json";
  }
  if (backendApiKey) {
    headers["X-API-Key"] = backendApiKey;
  }
  return headers;
}

function apiUrl(path) {
  return apiBaseUrl ? `${apiBaseUrl}${path}` : path;
}

function getImporterInputs() {
  return {
    organizationName: importOrgNameInput?.value?.trim() || "",
    organizationWebsite: importOrgWebsiteInput?.value?.trim() || "",
    irbPageUrl: importIrbUrlInput?.value?.trim() || "",
    rawPolicyText: importRawTextInput?.value?.trim() || "",
  };
}

function _strFromField(field) {
  if (!field) return "";
  return String(field.value || "").trim();
}

function setImportStatus(text, kind = "info") {
  if (!importStatus) return;
  importStatus.textContent = text;
  importStatus.dataset.kind = kind;
}

function renderProfileOptions(preferredId = "") {
  if (!profileSelect) return;
  const fallback = state.defaultProfileId || state.profileCatalog[0]?.id || "";
  const selectedId = preferredId || profileSelect.value || fallback;
  profileSelect.innerHTML = state.profileCatalog.map((profile) => {
    const label = profile.shortName || profile.name || profile.id;
    return `<option value="${escapeHtml(profile.id)}">${escapeHtml(label)}</option>`;
  }).join("") || '<option value="">No profiles available</option>';
  if (state.profileCatalog.some((profile) => profile.id === selectedId)) {
    profileSelect.value = selectedId;
  } else {
    profileSelect.value = fallback;
  }
}

function renderImportResult(importResult) {
  if (!importResultCard) return;
  if (!importResult) {
    importResultCard.className = "card muted compact-card";
    importResultCard.innerHTML = "<p>Importer output will appear here (confidence, warnings, sources, and detected requirements).</p>";
    return;
  }

  const confidence = Number(importResult.confidence || 0);
  const confidencePct = Math.round(confidence * 100);
  const warnings = importResult.warnings || [];
  const notes = importResult.notes || [];
  const signals = importResult.signals || [];
  const docs = importResult.documentLinks || [];
  const sources = importResult.sources || [];
  const profileDraft = importResult.profileDraft || {};
  const stats = importResult.stats || {};

  const profileLabel = profileDraft.shortName || profileDraft.name || profileDraft.id || "Imported profile";
  const confidenceKind = confidence >= 0.72 ? "success" : confidence >= 0.5 ? "warning" : "error";
  setImportStatus(`Import completed for "${profileLabel}" (${confidencePct}% confidence).`, confidenceKind);

  const signalsList = signals.length
    ? `<ul>${signals.map((signal) => `<li><strong>${escapeHtml(signal.label)}</strong>: ${escapeHtml(signal.summary)} (${Number(signal.evidenceCount || 0)} hits)</li>`).join("")}</ul>`
    : "<p>No strong requirement signals detected.</p>";
  const warningsList = warnings.length
    ? `<ul class="import-warning-list">${warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "<p>No warnings listed.</p>";
  const notesList = notes.length
    ? `<ul class="import-note-list">${notes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "<p>No notes listed.</p>";
  const docsList = docs.length
    ? `<ul>${docs.map((doc) => `<li><a href="${escapeHtml(doc)}" target="_blank" rel="noopener noreferrer">${escapeHtml(doc)}</a></li>`).join("")}</ul>`
    : "<p>No document links detected.</p>";
  const sourceList = sources.length
    ? `<ul class="import-source-list">
        ${sources.slice(0, 8).map((source) => `
          <li class="import-source-item">
            <p class="import-source-url">${escapeHtml(source.url || "Unknown source")}</p>
            <p class="import-source-meta">${escapeHtml(source.status || "unknown")} · ${escapeHtml(source.contentType || "content type unknown")}${source.httpStatus ? ` · HTTP ${Number(source.httpStatus)}` : ""}</p>
            ${source.error ? `<p class="import-source-meta">${escapeHtml(source.error)}</p>` : ""}
          </li>
        `).join("")}
      </ul>`
    : "<p>No sources reported.</p>";

  importResultCard.className = "card compact-card";
  importResultCard.innerHTML = `
    <div class="import-result-grid">
      <article class="import-result-block">
        <h4>Draft Profile</h4>
        <p class="import-confidence">${escapeHtml(profileLabel)}</p>
        <p class="import-source-meta">ID: ${escapeHtml(profileDraft.id || "n/a")}</p>
      </article>
      <article class="import-result-block">
        <h4>Confidence</h4>
        <p class="import-confidence">${confidencePct}%</p>
        <p class="import-source-meta">Fetched ${Number(stats.fetchedSourceCount || 0)} of ${Number(stats.candidateSourceCount || 0)} sources</p>
      </article>
      <article class="import-result-block">
        <h4>Signals</h4>
        <p class="import-confidence">${Number(stats.signalCount || 0)}</p>
        <p class="import-source-meta">Detected requirement signal groups</p>
      </article>
    </div>
    <div class="import-result-grid">
      <article class="import-result-block">
        <h4>Detected Requirements</h4>
        ${signalsList}
      </article>
      <article class="import-result-block">
        <h4>Warnings</h4>
        ${warningsList}
      </article>
      <article class="import-result-block">
        <h4>Notes</h4>
        ${notesList}
      </article>
    </div>
    <article class="import-result-block">
      <h4>Possible Form/Template Links</h4>
      ${docsList}
    </article>
    <article class="import-result-block">
      <h4>Fetched Sources</h4>
      ${sourceList}
    </article>
  `;
  restartAnimation(importResultCard, "surface-pop");
}

function appendOrUpdateProfile(profile) {
  if (!profile || !profile.id) return;
  const index = state.profileCatalog.findIndex((item) => item.id === profile.id);
  if (index >= 0) {
    state.profileCatalog[index] = profile;
  } else {
    state.profileCatalog.push(profile);
  }
}

async function apiGet(path) {
  const res = await fetch(apiUrl(path), {
    headers: buildApiHeaders(false),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
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
    irbProfileId: fd.get("irbProfileId") || state.defaultProfileId || "",
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
    headers: buildApiHeaders(true),
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function getDraftsFromUI() {
  return {
    consent: getDraftTextarea("consent")?.value || "",
    recruitment: getDraftTextarea("recruitment")?.value || "",
    data_handling: getDraftTextarea("data_handling")?.value || "",
  };
}

function getSelectedProfileMeta() {
  const selectedId = getFormData().irbProfileId;
  return state.profileCatalog.find((p) => p.id === selectedId) || state.activeProfile || null;
}

function renderProfileMeta(profile, note) {
  if (!profileMetaCard) return;
  if (!profile) {
    profileMetaCard.className = "card muted profile-meta-card";
    profileMetaCard.innerHTML = `<p>${escapeHtml(note || "No IRB profile loaded yet.")}</p>`;
    return;
  }
  profileMetaCard.className = "card profile-meta-card";
  profileMetaCard.innerHTML = `
    <div class="profile-meta-grid">
      <div>
        <p class="label">Profile</p>
        <p class="value">${escapeHtml(profile.shortName || profile.name || "IRB Profile")}</p>
      </div>
      <div>
        <p class="label">IRB Workflow</p>
        <p class="value">${escapeHtml(profile.irbOfficeLabel || "IRB")}</p>
      </div>
      <div>
        <p class="label">Version</p>
        <p class="value">${escapeHtml(profile.version || "1.0")}</p>
      </div>
    </div>
    <p class="profile-meta-desc">${escapeHtml(profile.description || "")}</p>
    ${note ? `<p class="profile-meta-note">${escapeHtml(note)}</p>` : ""}
  `;
  restartAnimation(profileMetaCard, "surface-pop");
}

function setReadinessStatus(text, kind = "info") {
  if (!readinessStatus) return;
  readinessStatus.textContent = text;
  readinessStatus.dataset.kind = kind;
}

function resetReadinessView(message) {
  if (readinessSummaryCard) {
    readinessSummaryCard.className = "card muted compact-card";
    readinessSummaryCard.innerHTML = `<p>${escapeHtml(message || "Run the readiness check to view profile-based submission readiness.")}</p>`;
  }
  if (readinessDetails) {
    readinessDetails.innerHTML = "";
  }
  if (sectionChecklistCard) {
    sectionChecklistCard.className = "card muted compact-card";
    sectionChecklistCard.innerHTML = "<p>Section mapping checklist will appear here.</p>";
  }
}

function invalidateReadiness(message) {
  state.readiness = null;
  setReadinessStatus(message || "Readiness check is outdated. Run it again after changes.", "warning");
  resetReadinessView(message || "Form or draft changes detected. Rerun readiness check.");
}

function renderReadinessSections(readiness) {
  if (!readinessDetails) return;
  const sections = [];

  const pushListSection = (title, items, formatter, kind = "neutral") => {
    if (!items || !items.length) return;
    sections.push(`
      <section class="readiness-block readiness-block--${kind}">
        <h4>${escapeHtml(title)}</h4>
        <ul>
          ${items.map((item) => `<li>${formatter(item)}</li>`).join("")}
        </ul>
      </section>
    `);
  };

  pushListSection(
    "Blocking Items",
    readiness.blockingItems || [],
    (item) => escapeHtml(item),
    "danger",
  );
  pushListSection(
    "Missing Intake Fields",
    readiness.missingFields || [],
    (item) => `<strong>${escapeHtml(item.label || item.key)}</strong>: ${escapeHtml(item.reason || "Missing")}`,
    "warning",
  );
  pushListSection(
    "Missing Drafts",
    readiness.missingDrafts || [],
    (item) => `<strong>${escapeHtml(item.label || item.docType)}</strong>: ${escapeHtml(item.reason || "Not generated")}`,
    "warning",
  );
  pushListSection(
    "Required Manual Attachments",
    readiness.missingManualAttachments || [],
    (item) => `<strong>${escapeHtml(item.label || item.id)}</strong>: ${escapeHtml(item.reason || "Required attachment")}`,
    "warning",
  );
  pushListSection(
    "Placeholder Issues",
    readiness.placeholderFindings || [],
    (item) => `<strong>${escapeHtml(item.label || item.docType)}</strong>: ${escapeHtml(item.placeholder)} (${Number(item.count || 1)}x)`,
    "warning",
  );
  pushListSection(
    "Warnings",
    readiness.warningItems || [],
    (item) => escapeHtml(item),
    "neutral",
  );
  pushListSection(
    "Next Steps",
    readiness.nextSteps || [],
    (item) => escapeHtml(item),
    "success",
  );

  if (!sections.length) {
    readinessDetails.innerHTML = '<section class="readiness-block"><h4>Readiness</h4><p>No issues listed.</p></section>';
    return;
  }
  readinessDetails.innerHTML = sections.join("");
}

function renderSectionChecklist(readiness) {
  if (!sectionChecklistCard) return;
  const profile = readiness.profile || {};
  const checklist = readiness.sectionChecklist || [];
  if (!checklist.length) {
    sectionChecklistCard.className = "card muted compact-card";
    sectionChecklistCard.innerHTML = "<p>No section mapping checklist available for the selected profile.</p>";
    return;
  }

  const rows = checklist.map((item) => {
    const badge = `<span class="check-badge" data-state="${escapeHtml(item.status || "review_needed")}">${escapeHtml(item.statusLabel || "Review")}</span>`;
    return `
      <li class="section-item">
        <div class="section-item__top">
          <div>
            <p class="section-item__title">${escapeHtml(item.sectionLabel || item.sectionId)}</p>
            <p class="section-item__meta">${escapeHtml(item.sourceType || "source")} · ${escapeHtml(item.sourceKey || "")}</p>
          </div>
          ${badge}
        </div>
        ${item.notes ? `<p class="section-item__note">${escapeHtml(item.notes)}</p>` : ""}
      </li>
    `;
  }).join("");

  sectionChecklistCard.className = "card compact-card";
  sectionChecklistCard.innerHTML = `
    <div class="compact-card__head">
      <p class="label">IRB Section Mapping</p>
      <p class="compact-card__title">${escapeHtml(profile.shortName || profile.name || "Selected Profile")}</p>
    </div>
    <ul class="section-checklist">${rows}</ul>
  `;
}

function renderReadiness(readiness) {
  state.readiness = readiness;
  const summary = readiness.summary || {};
  const readyAdvisor = summary.readyForAdvisorReview ? "Yes" : "Not yet";
  const readyPacket = summary.readyForIrbDraftPacket ? "Yes" : "Not yet";

  if (readinessSummaryCard) {
    readinessSummaryCard.className = "card compact-card";
    readinessSummaryCard.innerHTML = `
      <div class="summary-grid summary-grid--readiness">
        <div>
          <p class="label">Advisor Review Ready</p>
          <p class="value">${escapeHtml(readyAdvisor)}</p>
        </div>
        <div>
          <p class="label">IRB Draft Packet Ready</p>
          <p class="value">${escapeHtml(readyPacket)}</p>
        </div>
        <div>
          <p class="label">Blocking / Warning</p>
          <p class="value">${Number(summary.blockingCount || 0)} / ${Number(summary.warningCount || 0)}</p>
        </div>
        <div>
          <p class="label">Missing Fields</p>
          <p class="value">${Number(summary.missingFieldCount || 0)}</p>
        </div>
        <div>
          <p class="label">Missing Drafts</p>
          <p class="value">${Number(summary.missingDraftCount || 0)}</p>
        </div>
        <div>
          <p class="label">Placeholders</p>
          <p class="value">${Number(summary.placeholderIssueCount || 0)}</p>
        </div>
      </div>
      <div class="notes">
        <p class="label">Notes</p>
        <ul>${(readiness.notes || []).map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>
      </div>
    `;
    restartAnimation(readinessSummaryCard, "surface-pop");
  }

  renderReadinessSections(readiness);
  renderSectionChecklist(readiness);

  const kind = summary.readyForIrbDraftPacket ? "success" : summary.blockingCount ? "error" : "warning";
  setReadinessStatus("Readiness check complete.", kind);
}

async function loadProfiles() {
  try {
    const data = await apiGet("/api/profiles");
    state.profileCatalog = Array.isArray(data.profiles) ? data.profiles : [];
    state.defaultProfileId = data.defaultProfileId || state.profileCatalog[0]?.id || "";
    state.activeProfile = data.activeProfile || state.profileCatalog.find((p) => p.id === state.defaultProfileId) || null;

    const currentValue = profileSelect?.value || "";
    let savedProfileId = "";
    try {
      const raw = localStorage.getItem("irb-copilot-mvp");
      const parsed = raw ? JSON.parse(raw) : {};
      savedProfileId = parsed?.intake?.irbProfileId || "";
    } catch {
      savedProfileId = "";
    }
    const preferredId = currentValue || savedProfileId || state.defaultProfileId;
    renderProfileOptions(preferredId);

    renderProfileMeta(getSelectedProfileMeta());
    renderImportResult(state.importResult);
    persistLocal();
  } catch (err) {
    if (profileSelect) {
      profileSelect.innerHTML = '<option value="">Profile load failed</option>';
    }
    renderProfileMeta(null, `Unable to load profile catalog: ${err.message}`);
    setImportStatus("Profile catalog unavailable. Importer can still generate draft output.", "warning");
  }
}

async function runProfileImport() {
  const button = document.getElementById("importProfileBtn");
  const inputs = getImporterInputs();
  const fallbackOrg = _strFromField(form.querySelector('input[name="institution"]'));
  const orgName = inputs.organizationName || fallbackOrg;
  if (!orgName) {
    setImportStatus("Organization name is required for importer.", "warning");
    return;
  }

  if (button) {
    button.disabled = true;
    button.textContent = "Importing...";
  }
  setImportStatus("Running importer...", "pending");
  renderImportResult(null);

  try {
    const intake = getFormData();
    const data = await apiPost("/api/import-profile", {
      organizationName: orgName,
      organizationWebsite: inputs.organizationWebsite,
      irbPageUrl: inputs.irbPageUrl,
      rawPolicyText: inputs.rawPolicyText,
      baseProfileId: intake.irbProfileId || state.defaultProfileId,
    });

    state.importResult = data.importResult || null;
    if (Array.isArray(data.profiles)) {
      state.profileCatalog = data.profiles;
    }
    if (data.activeProfile) {
      state.activeProfile = data.activeProfile;
    }

    if (state.importResult?.profileDraft?.id) {
      applyImportedProfileBtn.disabled = false;
    }
    renderImportResult(state.importResult);
    persistLocal();
  } catch (err) {
    setImportStatus(`Importer error: ${err.message}`, "error");
    renderImportResult({
      confidence: 0,
      warnings: [`Importer failed: ${err.message}`],
      notes: ["Check organization name/URL and try again."],
      signals: [],
      sources: [],
      documentLinks: [],
      profileDraft: {},
      stats: {},
    });
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Import Profile Draft";
    }
  }
}

function applyImportedProfile() {
  const profile = state.importResult?.profileDraft;
  if (!profile || !profile.id) {
    setImportStatus("No imported profile draft to apply yet.", "warning");
    return;
  }
  appendOrUpdateProfile(profile);
  renderProfileOptions(profile.id);
  state.activeProfile = getSelectedProfileMeta();
  renderProfileMeta(state.activeProfile, "Imported profile applied. Verify warnings before relying on it.");
  invalidateReadiness("Profile changed. Rerun readiness check.");
  setImportStatus(`Applied imported profile "${profile.shortName || profile.name || profile.id}".`, "success");
  persistLocal();
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
    const res = await fetch(apiUrl("/api/health"), {
      headers: buildApiHeaders(false),
    });
    const data = await res.json();
    state.aiMode = data.aiMode || "unknown";
    const modeLabel = state.aiMode === "openai" ? "AI API connected" : "Template fallback mode";
    const backendLabel = apiBaseUrl ? `Backend: ${apiBaseUrl}. ` : "Backend: same origin. ";
    const authWarning = data.authRequired && !backendApiKey
      ? " Backend requires an API key; set backendApiKey in config.js or URL query param."
      : "";
    healthBanner.textContent = `${modeLabel}. ${backendLabel}${data.note || ""}${authWarning}`;
    healthBanner.dataset.mode = authWarning ? "warning" : state.aiMode;
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
    state.activeProfile = data.profile || getSelectedProfileMeta() || state.activeProfile;
    renderSummary(state.evaluation);
    renderFlags(state.evaluation);
    renderProfileMeta(state.activeProfile);
    invalidateReadiness("Risk flags changed. Rerun readiness check.");
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

async function runReadinessCheck() {
  const button = document.getElementById("runReadinessBtn");
  const intake = getFormData();
  if (button) {
    button.disabled = true;
    button.textContent = "Checking...";
  }
  setReadinessStatus("Running readiness check...", "pending");
  try {
    await ensureEvaluation();
    const data = await apiPost("/api/readiness", {
      profileId: intake.irbProfileId,
      intake,
      evaluation: state.evaluation,
      drafts: getDraftsFromUI(),
    });
    renderReadiness(data.readiness || {});
    persistLocal();
  } catch (err) {
    setReadinessStatus(`Error: ${err.message}`, "error");
    resetReadinessView(`Readiness check failed: ${err.message}`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Run Readiness Check";
    }
  }
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
    invalidateReadiness("Draft content changed. Rerun readiness check.");
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
    invalidateReadiness("Draft content changed. Rerun readiness check.");
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
  const readiness = state.readiness || { summary: {}, notes: ["Readiness check not run yet."] };
  const importResult = state.importResult || {
    notes: ["No profile import was run in this session."],
  };
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
  parts.push("=== PROFILE READINESS (JSON) ===");
  parts.push(JSON.stringify(readiness, null, 2));
  parts.push("");
  parts.push("=== IMPORTED PROFILE RESULT (JSON) ===");
  parts.push(JSON.stringify(importResult, null, 2));
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
    activeProfile: state.activeProfile,
    defaultProfileId: state.defaultProfileId,
    profileCatalog: state.profileCatalog,
    readiness: state.readiness,
    importResult: state.importResult,
    importerInputs: getImporterInputs(),
    drafts: {
      ...getDraftsFromUI(),
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
    state.profileCatalog = Array.isArray(saved.profileCatalog) ? saved.profileCatalog : state.profileCatalog;
    state.defaultProfileId = saved.defaultProfileId || state.defaultProfileId;
    state.activeProfile = saved.activeProfile || state.activeProfile;
    state.importResult = saved.importResult || state.importResult;
    if (saved.importerInputs) {
      if (importOrgNameInput) importOrgNameInput.value = saved.importerInputs.organizationName || "";
      if (importOrgWebsiteInput) importOrgWebsiteInput.value = saved.importerInputs.organizationWebsite || "";
      if (importIrbUrlInput) importIrbUrlInput.value = saved.importerInputs.irbPageUrl || "";
      if (importRawTextInput) importRawTextInput.value = saved.importerInputs.rawPolicyText || "";
    }
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
    state.readiness = saved.readiness || null;
    if (state.readiness) {
      renderReadiness(state.readiness);
    } else {
      resetReadinessView();
      setReadinessStatus("No readiness check yet.", "info");
    }

    for (const docType of ["consent", "recruitment", "data_handling"]) {
      const text = saved.drafts?.[docType] || "";
      state.drafts[docType] = text;
      getDraftTextarea(docType).value = text;
      if (text) setDraftStatus(docType, "Restored from local draft", "info");
    }

    renderProfileMeta(state.activeProfile);
    renderImportResult(state.importResult);
    if (state.importResult?.profileDraft?.id && applyImportedProfileBtn) {
      applyImportedProfileBtn.disabled = false;
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

  if (target.id === "importProfileBtn") {
    await runProfileImport();
    return;
  }

  if (target.id === "applyImportedProfileBtn") {
    applyImportedProfile();
    return;
  }

  if (target.id === "generateAllBtn") {
    await generateAllDrafts();
    return;
  }

  if (target.id === "runReadinessBtn") {
    await runReadinessCheck();
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
  el.addEventListener("change", () => {
    if (el instanceof HTMLSelectElement && el.name === "irbProfileId") {
      state.activeProfile = getSelectedProfileMeta();
      renderProfileMeta(state.activeProfile);
    }
    if (el.name) {
      invalidateReadiness("Form values changed. Rerun readiness check.");
    }
  });
  el.addEventListener("input", () => {
    if (el.tagName === "TEXTAREA" || (el instanceof HTMLInputElement && el.type === "text")) {
      persistLocal();
      if (el.getAttribute("name")) {
        invalidateReadiness("Form values changed. Rerun readiness check.");
      }
    }
  });
}

restoreLocal();
loadProfiles();
checkHealth();
setStep(1);
