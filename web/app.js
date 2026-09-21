"use strict";

(() => {
  const FIELDS = ["shipper", "consignee", "notify_party", "port_of_loading", "port_of_discharge", "container_count", "gross_weight_kg"];
  const FIELD_NAMES = {shipper: "Shipper", consignee: "Consignee", notify_party: "Notify party", port_of_loading: "Port of loading", port_of_discharge: "Port of discharge", container_count: "Container count", gross_weight_kg: "Gross weight (kg)"};
  const CATEGORY_NAMES = {BL_COMPARISON: "Bill of Lading comparison", SI_REQUEST: "Shipping Instruction request", INVOICE_QUERY: "Invoice query", GENERAL: "General correspondence", SPAM: "Spam"};
  const state = {cases: [], selected: null, report: null, health: null, tab: "verify", detailRequest: 0, busy: false, files: null};
  const $ = (id) => document.getElementById(id);
  const text = (value, fallback = "—") => value === null || value === undefined || value === "" ? fallback : typeof value === "object" ? JSON.stringify(value) : String(value);
  const list = (value) => Array.isArray(value) ? value : value ? [value] : [];
  const node = (tag, className, value) => { const n = document.createElement(tag); if (className) n.className = className; if (value !== undefined) n.textContent = text(value, ""); return n; };
  const clear = (target) => target.replaceChildren();
  const nameOf = (field) => FIELD_NAMES[field] || text(field).replace(/_/g, " ");
  const safeStorage = {get(key) { try { return localStorage.getItem(key); } catch { return null; } }, set(key, value) { try { localStorage.setItem(key, value); } catch { /* Storage is optional. */ } }};
  const caseId = (report) => text(report.id || report.email_id, "");
  const emailOf = (report) => report.email || {};
  const subjectOf = (report) => text(emailOf(report).subject || report.subject || report.email_id, "Untitled email");
  const categoryOf = (report) => CATEGORY_NAMES[report.category || report.classification?.category] || text(report.category || report.classification?.category, "Unclassified").replace(/_/g, " ");
  const isComparison = (report) => (report.category || report.classification?.category) === "BL_COMPARISON";
  const formatTime = (value) => { if (!value) return "Time not recorded"; const d = new Date(value); return Number.isNaN(d.getTime()) ? text(value) : new Intl.DateTimeFormat(undefined, {dateStyle: "medium", timeStyle: "short"}).format(d); };
  const statusInfo = (status) => ({OK: ["Verified clean", "clean"], MISMATCH: ["Discrepancy", "defect"], NEEDS_REVIEW: ["Needs review", "review"]}[status] || [text(status, "Not analyzed"), "neutral"]);
  function badge(status, custom) { const [label, cls] = statusInfo(status); return node("span", "badge " + cls, custom || label); }
  function caseBadge(report) { return isComparison(report) || report.status === "NEEDS_REVIEW" ? badge(report.status) : report.classification?.needs_review ? badge("NEEDS_REVIEW", "Routing uncertain") : node("span", "badge neutral", "Classified only"); }
  function hasReview(report) { if (typeof report.reviewed === "boolean") return report.reviewed; return Boolean(report.review || report.reviewed_at || list(report.audit).some((event) => /review/.test(text(event.action || event.event || event.type, "").toLowerCase()))); }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 240000);
    try {
      const init = {...options, signal: controller.signal};
      if (options.body && !(options.body instanceof FormData)) { init.body = JSON.stringify(options.body); init.headers = {...options.headers, "Content-Type": "application/json"}; }
      const response = await fetch(path, init);
      const raw = await response.text();
      let data;
      try { data = raw ? JSON.parse(raw) : {}; } catch { throw new Error("The service returned an unexpected response. Check that Harborlight is running."); }
      if (!response.ok) { const e = new Error(typeof data.detail === "string" ? data.detail : text(data.detail || data.error, "The request could not be completed.")); e.status = response.status; throw e; }
      return data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("This request took too long. Refresh the queue to check whether processing completed before trying again.");
      if (error instanceof TypeError) throw new Error("Cannot reach Harborlight. Check that the local service is running, then refresh.");
      throw error;
    } finally { clearTimeout(timer); }
  }

  function toast(message, error = false) {
    const item = node("div", "toast" + (error ? " error" : ""), message);
    $("toast-region").append(item);
    setTimeout(() => item.remove(), error ? 12000 : 6500);
  }

  function setBusy(busy, label) {
    state.busy = busy;
    for (const id of ["seed-demo", "empty-demo", "save-review", "retry-case", "simulate-changes", "submit-import"]) $(id).disabled = busy;
    for (const item of document.querySelectorAll(".case-card")) item.disabled = busy;
    if (label) $("import-progress").textContent = label;
  }

  function cloudConfigured(health) {
    const ai = health?.ai;
    return Boolean(ai && (ai === true || ai.cloud_configured === true || ai.configured === true || ai.available === true || ai.enabled === true));
  }

  async function loadHealth() {
    try {
      state.health = await api("/api/health");
      const cloud = cloudConfigured(state.health);
      $("connection-dot").className = "connection-dot online";
      $("connection-label").textContent = cloud ? "Cloud AI available" : "Local mode active";
      const ocr = state.health.ocr;
      const ocrAvailable = ocr === true || ocr?.available === true || ocr?.configured === true;
      $("runtime-copy").textContent = cloud ? "Local by default. Cloud document processing requires your opt-in." : "No cloud requests. Local ML and evidence checks" + (ocrAvailable ? " with OCR." : ". OCR availability depends on server setup.");
      for (const id of ["import-ai", "retry-ai"]) { $(id).disabled = !cloud; $(id).title = cloud ? "Opt in to send email and document text to the configured AI provider." : "Configure cloud AI on the server to enable this option."; if (!cloud) $(id).checked = false; }
      $("service-alert").hidden = true;
    } catch (error) {
      $("connection-dot").className = "connection-dot offline";
      $("connection-label").textContent = "Service unavailable";
      $("runtime-copy").textContent = "Start the Harborlight service and refresh to reconnect.";
      $("service-alert").textContent = error.message;
      $("service-alert").hidden = false;
      for (const id of ["import-ai", "retry-ai"]) $(id).disabled = true;
    }
  }

  async function loadCases(preferredId, options = {}) {
    const data = await api("/api/cases");
    state.cases = list(data.cases);
    const stats = data.stats || {};
    $("stat-total").textContent = stats.total ?? state.cases.length;
    $("stat-clean").textContent = stats.clean ?? state.cases.filter((r) => isComparison(r) && r.status === "OK").length;
    $("stat-mismatch").textContent = stats.mismatches ?? state.cases.filter((r) => r.status === "MISMATCH").length;
    $("stat-review").textContent = stats.review ?? state.cases.filter((r) => r.status === "NEEDS_REVIEW").length;
    $("audit-integrity").textContent = data.audit_valid === false ? "! Audit integrity check failed" : data.audit_valid === true ? "✓ Audit chain verified" : "○ Audit integrity unavailable";
    $("audit-integrity").className = "integrity-status" + (data.audit_valid === false ? " invalid" : "");
    if (data.audit_valid === false) toast("The audit chain failed its integrity check. Inspect the audit records before relying on this workspace.", true);
    const desired = preferredId || state.selected;
    const match = state.cases.find((r) => caseId(r) === desired);
    const first = [...state.cases].sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0))[0];
    state.selected = match ? caseId(match) : first ? caseId(first) : null;
    renderQueue();
    if (state.selected && !options.skipDetail) await selectCase(state.selected, {keepTab: options.keepTab});
    else if (!state.selected) { state.report = null; $("empty-state").hidden = false; $("case-detail").hidden = true; }
  }

  function filteredCases() {
    const query = $("case-search").value.trim().toLowerCase();
    const status = $("status-filter").value;
    return state.cases.filter((r) => (status === "all" || (status === "CLASSIFIED" ? !isComparison(r) : r.status === status && (status !== "OK" || isComparison(r)))) && (!query || [r.email_id, r.id, subjectOf(r), emailOf(r).from, categoryOf(r), r.summary].map((v) => text(v, "")).join(" ").toLowerCase().includes(query))).sort((a, b) => $("case-sort").value === "newest" ? (Date.parse(b.created_at || "") || 0) - (Date.parse(a.created_at || "") || 0) : Number(b.risk_score || 0) - Number(a.risk_score || 0));
  }

  function updateQuickFilters() {
    const current = $("status-filter").value;
    for (const button of document.querySelectorAll(".queue-shortcut")) {
      const active = button.dataset.filter === current;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    }
  }

  function renderQueue() {
    updateQuickFilters();
    const target = $("case-list"); clear(target);
    const cases = filteredCases();
    $("queue-count").textContent = cases.length + " of " + state.cases.length + " cases" + (state.cases.length ? " · " + state.cases.filter(hasReview).length + " reviewed" : "");
    if (!cases.length) { target.append(node("p", "queue-empty", state.cases.length ? "No cases match these filters." : "Your next shipment starts here. Import documents or load the demonstration.")); return; }
    for (const report of cases) {
      const id = caseId(report);
      const button = node("button", "case-card" + (state.selected === id ? " selected" : "")); button.type = "button";
      button.disabled = state.busy;
      button.setAttribute("aria-pressed", String(state.selected === id));
      button.setAttribute("aria-label", subjectOf(report) + ", " + caseBadge(report).textContent);
      button.classList.add(report.status === "MISMATCH" ? "case-has-difference" : report.status === "NEEDS_REVIEW" ? "case-needs-review" : "case-other");
      const top = node("div", "case-card-top"); top.append(node("span", "case-card-id", report.email_id || id), caseBadge(report));
      const bottom = node("div", "case-card-bottom");
      const defects = list(report.defect_fields).length;
      bottom.append(node("span", "", hasReview(report) ? "✓ Human reviewed" : !isComparison(report) ? report.classification?.needs_review ? "Routing needs confirmation" : "No comparison required" : defects ? defects + " field" + (defects === 1 ? "" : "s") + " to inspect" : report.status === "OK" ? "Seven fields aligned" : "Evidence needs attention"), node("span", "case-card-risk", "RISK " + text(report.risk_score, "—")));
      const meta = node("div", "case-card-meta");
      meta.append(node("span", "", categoryOf(report)), node("time", "", formatTime(report.created_at)));
      button.append(top, node("h3", "", subjectOf(report)), meta, bottom);
      button.addEventListener("click", () => selectCase(id).catch((e) => toast(e.message, true)));
      target.append(button);
    }
  }

  async function selectCase(id, options = {}) {
    const request = ++state.detailRequest;
    state.selected = id; state.report = null; renderQueue();
    $("detail-panel").setAttribute("aria-busy", "true");
    try {
      const report = await api("/api/cases/" + encodeURIComponent(id));
      if (request !== state.detailRequest) return;
      state.report = report;
      if (!options.keepTab) state.tab = "verify";
      renderReport();
    } catch (error) {
      if (request === state.detailRequest) { $("case-detail").hidden = true; $("empty-state").hidden = false; }
      throw error;
    } finally { if (request === state.detailRequest) $("detail-panel").setAttribute("aria-busy", "false"); }
  }

  function rowsFor(report) {
    if (!isComparison(report)) return [];
    const rows = list(report.rows);
    return FIELDS.map((field) => rows.find((row) => row.field === field) || {field, si: null, bl: null, outcome: "uncertain", reason: "No comparison evidence is available for this field."});
  }

  function renderReport() {
    const r = state.report; if (!r) return;
    $("empty-state").hidden = true; $("case-detail").hidden = false;
    $("detail-id").textContent = "CASE / " + text(r.email_id || r.id);
    $("detail-status").replaceChildren(caseBadge(r));
    $("detail-origin").textContent = r.data_origin === "synthetic_demo" ? "Synthetic demo data" : r.data_origin === "user_import" ? "Imported data" : "Origin not recorded";
    $("detail-origin").className = "origin-badge" + (r.data_origin === "synthetic_demo" ? " synthetic" : "");
    $("detail-title").textContent = subjectOf(r);
    const email = emailOf(r);
    $("detail-sender").textContent = text(email.from, "Sender not provided") + " · " + formatTime(r.created_at);
    $("risk-value").textContent = text(r.risk_score);
    $("detail-summary").textContent = text(r.summary, "Inspect the evidence and record a human review.");
    renderDecisionBrief(r);
    $("classification-category").textContent = categoryOf(r);
    const classification = r.classification || {};
    const score = Number(classification.confidence);
    $("classification-confidence").textContent = Number.isFinite(score) && classification.confidence != null ? (score <= 1 ? score * 100 : score).toFixed(1) + " / 100" : "Not available";
    $("analysis-mode").textContent = aiMode(r.ai);
    const reason = $("classification-reason"); clear(reason);
    reason.append(node("p", "", classification.reason || "No routing explanation was recorded."));
    reason.append(node("p", "", "Method: " + text(classification.method) + ". Routing scores are uncalibrated model scores, not a probability that this decision is correct."));
    if (classification.scores && typeof classification.scores === "object") reason.append(node("p", "", "Candidate scores: " + Object.entries(classification.scores).map(([key, value]) => key.replace(/_/g, " ") + " " + (typeof value === "number" ? value.toFixed(3) : text(value))).join(" · ")));
    if (r.ai) reason.append(node("p", "", aiExplanation(r.ai)));
    if (list(r.risk_components).length) reason.append(node("p", "", "Risk factors: " + list(r.risk_components).map((component) => component.label ? component.label + " (+" + component.points + ")" : text(component)).join("; ") + ". Risk is a prioritization aid, not a shipment approval."));
    const comparison = isComparison(r);
    $("verify-tab-label").textContent = comparison ? "Field verification" : "Email routing";
    $("fields-count").hidden = !comparison;
    $("classification-only").hidden = comparison;
    for (const id of ["comparison-intro", "comparison-table-wrap", "evidence-legend"]) $(id).hidden = !comparison;
    $("routing-title").textContent = categoryOf(r).toLowerCase().replace(/^./, (char) => char.toUpperCase());
    $("routing-copy").textContent = classification.reason || r.summary || "This email belongs to a workflow that does not require SI versus BL comparison.";
    const uncertainRouting = classification.needs_review || (!comparison && r.status === "NEEDS_REVIEW");
    $("routing-eyebrow").textContent = uncertainRouting ? "ROUTING UNCERTAIN · HUMAN REVIEW REQUIRED" : "CLASSIFIED · NO COMPARISON REQUIRED";
    $("routing-scope").textContent = uncertainRouting ? "The proposed email category needs human confirmation. Open the review desk to choose the correct workflow. SI and BL fields have not been verified for this case." : "The email's request was classified. SI and BL fields have not been verified for this case.";
    $("fields-count").textContent = "7";
    $("sources-count").textContent = list(r.documents).length;
    const reasons = $("case-reasons"); clear(reasons);
    for (const item of list(r.reasons)) reasons.append(node("p", "reason-item", typeof item === "string" ? item : item.reason || item.message || text(item)));
    if (r.status === "NEEDS_REVIEW" && !list(r.reasons).length) reasons.append(node("p", "reason-item", comparison ? "Evidence is incomplete or uncertain. This case cannot be marked clean without further review." : "Email routing is uncertain. A reviewer must confirm or correct the category."));
    renderComparison(r); renderSources(r); renderReview(r); renderAudit(r);
    $("review-state").textContent = hasReview(r) ? "Human review recorded · Evidence and source files preserved" : "Machine analysis · Awaiting human review";
    activateTab(state.tab);
  }

  function renderDecisionBrief(report) {
    const comparison = isComparison(report);
    const rows = rowsFor(report);
    const differences = rows.filter((row) => row.outcome === "mismatch").length;
    const uncertain = rows.filter((row) => !["match", "mismatch"].includes(row.outcome)).length;
    const aligned = rows.filter((row) => row.outcome === "match").length;
    const requiresReview = report.status === "NEEDS_REVIEW" || report.classification?.needs_review;
    const brief = $("decision-brief");
    brief.className = "decision-brief " + (requiresReview ? "brief-review" : differences ? "brief-discrepancy" : comparison ? "brief-clean" : "brief-routing");
    let title, description;
    if (!comparison) {
      title = requiresReview ? "Confirm this email’s routing" : "Email classified for the right workflow";
      description = requiresReview ? "The proposed category needs a human decision. Review the original email before confirming the route." : "This email was classified. SI and BL field verification is outside this case’s workflow.";
    } else if (uncertain || requiresReview) {
      title = "Evidence needs a human decision";
      description = `${uncertain} of 7 fields need more evidence${differences ? `; ${differences} confirmed difference${differences === 1 ? "" : "s"} also found` : ""}. Inspect source excerpts before recording a review.`;
    } else if (differences) {
      title = `${differences} confirmed difference${differences === 1 ? "" : "s"} found`;
      description = "The Bill of Lading differs from the Shipping Instruction. Examine the flagged fields and their source excerpts before deciding.";
    } else {
      title = "All seven fields align";
      description = "The extracted values match the Shipping Instruction. Review the source evidence before recording a human decision.";
    }
    $("brief-eyebrow").textContent = comparison ? "VERIFICATION / DECISION BRIEF" : "ROUTING / DECISION BRIEF";
    $("brief-title").textContent = title;
    $("brief-description").textContent = description;
    const facts = $("brief-facts"); clear(facts);
    if (comparison) {
      for (const [label, count, kind] of [["Different", differences, "difference"], ["Needs evidence", uncertain, "uncertain"], ["Aligned", aligned, "aligned"]]) {
        const item = node("span", "brief-fact " + kind);
        item.append(node("strong", "", String(count)), node("span", "", label)); facts.append(item);
      }
    } else { facts.append(node("span", "brief-fact routing", "Category: " + categoryOf(report))); }
    facts.append(node("span", "brief-fact provenance", hasReview(report) ? "✓ Review recorded" : "Human decision pending"));
    $("brief-evidence").textContent = list(report.documents).length ? "Inspect sources ↗" : "View email context ↗";
  }

  function aiMode(ai) {
    if (!ai || ai === false) return "Local verification";
    if (ai.used === true || ai.status === "used" || ai.status === "success" || ai.status === "completed") return list(ai.errors).length ? "Cloud · partial fallback" : "Cloud-assisted";
    if (ai.error || list(ai.errors).length || ai.status === "failed" || ai.status === "error") return "Local · AI failed";
    return "Local verification";
  }

  function aiExplanation(ai) {
    if (!ai) return "No cloud AI was used.";
    if (typeof ai === "string") return "AI status: " + ai;
    const used = ai.used === true || ["used", "success", "completed"].includes(ai.status);
    const message = ai.reason || ai.error || (!used ? ai.message : "");
    return (used ? "Cloud AI was used" : "Cloud AI was not used") + (ai.provider ? " · Provider: " + text(ai.provider) : "") + (ai.model ? " · Model: " + text(ai.model) : "") + (message ? ". " + text(message) : ".") + (ai.status ? " Status: " + text(ai.status) + "." : "") + (list(ai.errors).length ? " Cloud processing issues: " + list(ai.errors).map((e) => text(e)).join("; ") : "");
  }

  function findSourceIndex(r, kind, evidence) {
    if (Number.isInteger(evidence?.source_index)) return evidence.source_index;
    const documents = list(r.documents);
    const candidates = documents.filter((d) => !d.missing && String(d.kind).toUpperCase() === kind);
    const doc = documents.find((d) => !d.missing && evidence?.filename && d.filename === evidence.filename) || (candidates.length === 1 ? candidates[0] : null);
    if (!doc) return null;
    return Number.isInteger(doc.source_index) ? doc.source_index : documents.indexOf(doc);
  }

  function attachmentUrl(r, index) { return "/api/cases/" + encodeURIComponent(caseId(r)) + "/attachments/" + encodeURIComponent(index); }

  function fieldCell(r, row, side) {
    const cell = node("td");
    const value = row[side];
    const missing = value === null || value === undefined || value === "";
    cell.append(node("span", "field-value" + (missing ? " missing" : ""), missing ? "Not available" : value));
    const evidence = row[side + "_evidence"] || {};
    const snippet = evidence.evidence || evidence.snippet || evidence.text;
    const page = evidence.page;
    const method = evidence.method;
    const citation = node("details", "source-citation");
    const sourceLocation = evidence.locator || (page ? "Page " + page : "");
    const summary = node("summary", "", sourceLocation ? sourceLocation + " · Source" : snippet || method ? "View source" : "Evidence unavailable");
    const body = node("div", "citation-body");
    if (evidence.filename) body.append(node("p", "", evidence.filename));
    body.append(node("p", "", "Method: " + text(method, "Not recorded") + (sourceLocation ? " · " + sourceLocation : "")));
    if (evidence.confidence != null) { const score = Number(evidence.confidence); body.append(node("p", "", "Extraction score: " + (Number.isFinite(score) ? (score <= 1 ? score * 100 : score).toFixed(0) + " / 100" : text(evidence.confidence)) + " (heuristic)")); }
    body.append(snippet ? node("blockquote", "", snippet) : node("p", "", "No source excerpt was captured. Inspect the original attachment before making a correction."));
    const norm = row[side + "_normalized"];
    if (norm != null && norm !== value) body.append(node("p", "", "Normalized: " + text(norm)));
    if (evidence.original_value !== undefined) body.append(node("p", "", "Original extraction: " + text(evidence.original_value)));
    if (evidence.original) body.append(node("p", "", "Original extraction: " + text(evidence.original.value)));
    if (evidence.review_note) body.append(node("p", "", evidence.review_note));
    if (evidence.corrected_by || evidence.reviewer) body.append(node("p", "", "Correction by: " + text(evidence.corrected_by || evidence.reviewer)));
    const index = findSourceIndex(r, side.toUpperCase(), evidence);
    if (index !== null) { const link = node("a", "", "Download original ↗"); link.href = attachmentUrl(r, index); link.download = ""; body.append(link); }
    citation.append(summary, body); cell.append(citation); return cell;
  }

  function renderComparison(r) {
    const body = $("comparison-body"); clear(body);
    const priority = {mismatch: 0, uncertain: 1, match: 2};
    const displayRows = rowsFor(r).slice().sort((a, b) =>
      (priority[a.outcome] ?? 1) - (priority[b.outcome] ?? 1));
    for (const row of displayRows) {
      const tr = node("tr", "field-" + (row.outcome || "uncertain"));
      const label = node("td", "field-label");
      label.append(node("strong", "", nameOf(row.field)));
      if (row.outcome === "mismatch") label.append(node("span", "field-flag", "Difference found"));
      else if (row.outcome !== "match") label.append(node("span", "field-flag uncertain", "Check evidence"));
      const outcome = node("td");
      const status = row.outcome === "match" ? "OK" : row.outcome === "mismatch" ? "MISMATCH" : "NEEDS_REVIEW";
      outcome.append(badge(status, row.outcome === "match" ? "Match" : row.outcome === "mismatch" ? "Different" : "Uncertain"));
      if (row.reason) outcome.append(node("span", "row-reason", row.reason));
      if (row.outcome === "mismatch") tr.setAttribute("aria-label", nameOf(row.field) + ": confirmed difference");
      if (row.outcome !== "match" && row.outcome !== "mismatch") tr.setAttribute("aria-label", nameOf(row.field) + ": insufficient evidence");
      tr.append(label, fieldCell(r, row, "si"), fieldCell(r, row, "bl"), outcome); body.append(tr);
    }
  }

  function renderSources(r) {
    const target = $("source-list"); clear(target);
    const docs = list(r.documents);
    if (!docs.length) target.append(node("p", "queue-empty", "No readable source documents were attached to this case."));
    docs.forEach((doc, index) => {
      const card = node("article", "source-card");
      const main = node("div", "source-main");
      const filename = text(doc.filename, "Attachment " + (index + 1));
      main.append(node("h4", "", filename));
      const methods = [...new Set(list(doc.pages).map((p) => p.method).filter(Boolean))];
      main.append(node("p", "source-meta", text(doc.kind, "UNKNOWN") + " · " + list(doc.pages).length + " page(s)" + (methods.length ? " · " + methods.join(", ") : "")));
      for (const warning of list(doc.warnings)) main.append(node("p", "source-warning", warning));
      if (doc.error) main.append(node("p", "source-warning", "Extraction issue: " + text(doc.error)));
      if (doc.sha256) main.append(node("p", "source-hash", "SHA-256 " + doc.sha256));
      card.append(node("span", "file-icon", filename.includes(".") ? filename.split(".").pop().slice(0, 5).toUpperCase() : "FILE"), main);
      if (!doc.missing) { const link = node("a", "", "Download ↗"); link.href = attachmentUrl(r, Number.isInteger(doc.source_index) ? doc.source_index : index); link.download = ""; card.append(link); }
      target.append(card);
    });
    const metadata = $("email-metadata"); clear(metadata);
    const email = emailOf(r);
    for (const [label, value] of [["Email ID", r.email_id || email.email_id], ["From", email.from], ["Subject", email.subject]]) { metadata.append(node("dt", "", label), node("dd", "", text(value))); }
    $("email-body").textContent = text(email.body || email.text || email.content, "Email body was not provided.");
  }

  function renderReview(r) {
    const comparison = isComparison(r);
    const editableSides = ["si", "bl"].filter((side) => { const docs = list(r.documents).filter((doc) => doc.kind === side.toUpperCase()); return docs.length === 1 && !docs[0].error && !docs[0].missing; });
    $("correct-decision-option").hidden = !comparison;
    $("correct-decision-option").disabled = !comparison || !editableSides.length;
    $("simulate-changes").hidden = false;
    $("review-intro-copy").textContent = comparison ? "Confirm the email category and correct extracted values using source evidence. Preview their effect, then record your decision. This review does not approve a shipment or send an email." : "Inspect the email context and routing explanation, then confirm or correct the category. Preview the result before recording your review. Original documents remain available when the workflow changes.";
    $("reviewer-name").value = safeStorage.get("harborlight-reviewer") || "";
    $("review-decision").value = "confirm";
    $("review-category").value = r.category || r.classification?.category || "GENERAL";
    $("review-note").value = "";
    $("review-version").textContent = text(r.version, "1");
    $("correction-fields").hidden = true;
    $("simulation-result").hidden = true;
    const grid = $("correction-grid"); clear(grid);
    for (const row of rowsFor(r)) {
      grid.append(node("p", "correction-label", nameOf(row.field)));
      for (const [side, label] of [["si", "Shipping Instruction"], ["bl", "Bill of Lading"]]) {
        const wrapper = node("label", "", label);
        const input = node("input"); input.type = "text"; input.value = text(row[side], ""); input.id = "correction-" + side + "-" + row.field; input.dataset.side = side; input.dataset.field = row.field; input.dataset.original = input.value; input.autocomplete = "off"; input.maxLength = 2000;
        if (!editableSides.includes(side)) { input.disabled = true; input.placeholder = "Re-import a readable, unambiguous source"; input.title = "This source is missing, unreadable or ambiguous. Re-import the correct source document before editing its fields."; }
        input.setAttribute("aria-label", label + " — " + nameOf(row.field)); input.addEventListener("input", () => { $("simulation-result").hidden = true; });
        wrapper.append(input); grid.append(wrapper);
      }
    }
    updateReviewCategoryControls();
  }

  function updateReviewCategoryControls() {
    if (!state.report) return;
    const originalComparison = isComparison(state.report);
    const selectedComparison = $("review-category").value === "BL_COMPARISON";
    const hasEditableInput = Boolean($("correction-grid").querySelector("input:not(:disabled)"));
    $("correct-decision-option").hidden = !originalComparison || !selectedComparison;
    $("correct-decision-option").disabled = !originalComparison || !selectedComparison || !hasEditableInput;
    if ($("correct-decision-option").disabled) $("review-decision").value = "confirm";
    $("correction-fields").hidden = $("review-decision").value !== "correct";
    $("category-help").textContent = selectedComparison && !originalComparison ? "Preview will compare the preserved source documents. Record this category first to inspect the resulting field evidence and make any extraction corrections." : "Confirm this routing or choose the correct workflow. Your selection and review note are recorded together.";
  }

  function corrections() {
    const result = {si: {}, bl: {}};
    if (!state.report || !isComparison(state.report) || $("review-category").value !== "BL_COMPARISON" || $("review-decision").value !== "correct") return result;
    for (const input of $("correction-grid").querySelectorAll("input")) {
      if (!input.disabled && input.value !== input.dataset.original) result[input.dataset.side][input.dataset.field] = input.value;
    }
    return result;
  }

  function renderAudit(r) {
    const target = $("audit-timeline"); clear(target);
    const events = list(r.audit || r.audit_events);
    if (!events.length) { target.append(node("li", "queue-empty", "No audit events were included in this case response.")); return; }
    for (const event of [...events].reverse()) {
      const item = node("li", "audit-event");
      const action = text(event.action || event.event || event.type, "Case event").replace(/_/g, " ");
      item.append(node("h4", "", action.charAt(0).toUpperCase() + action.slice(1)));
      const stamp = event.created_at || event.timestamp || event.at || event.time;
      const time = node("time", "", formatTime(stamp)); if (stamp && !Number.isNaN(Date.parse(stamp))) time.dateTime = new Date(stamp).toISOString(); item.append(time);
      const payload = event.payload || event.details || event.data || {};
      if (event.reviewer || payload.reviewer || event.actor) item.append(node("p", "", "Recorded by " + text(event.reviewer || payload.reviewer || event.actor)));
      if (event.note || payload.note || event.summary) item.append(node("p", "", event.note || payload.note || event.summary));
      const detail = node("details"); detail.append(node("summary", "", "Inspect event record"), node("pre", "", JSON.stringify(event, null, 2))); item.append(detail); target.append(item);
    }
  }

  function activateTab(name, focus = false) {
    if (!["verify", "sources", "review", "history"].includes(name)) name = "verify";
    state.tab = name;
    for (const tab of document.querySelectorAll("[data-tab]")) { const selected = tab.dataset.tab === name; tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1; $("panel-" + tab.dataset.tab).hidden = !selected; if (selected && focus) tab.focus(); }
  }

  async function seedDemo() {
    if (state.busy) return;
    setBusy(true); const button = $("seed-demo"); const old = button.textContent; button.textContent = "Preparing demo…";
    try { const result = await api("/api/demo", {method: "POST", body: {}}); $("status-filter").value = "all"; $("case-search").value = ""; await loadCases(); toast("Demonstration ready. Explore clean cases, discrepancies and missing evidence."); if (list(result.errors).length) toast(list(result.errors).map((e) => text(e.message || e)).join("; "), true); }
    catch (error) { toast(error.message, true); }
    finally { setBusy(false); button.textContent = old; }
  }

  function openImport() { $("import-dialog").showModal(); }
  function selectedFiles() { return state.files || Array.from($("import-files").files || []); }
  function showSelectedFiles() {
    const files = selectedFiles(); const area = $("selected-files");
    if (!files.length) { area.textContent = "No files selected"; area.classList.remove("has-files"); return; }
    area.classList.add("has-files"); clear(area);
    area.append(node("strong", "", files.length + " file" + (files.length === 1 ? "" : "s") + " ready for verification"));
    const names = node("span", "", files.slice(0, 4).map((file) => file.name).join(" · ") + (files.length > 4 ? ` · +${files.length - 4} more` : ""));
    area.append(names);
  }

  async function importFiles(event) {
    event.preventDefault(); if (state.busy) return;
    const files = selectedFiles(); if (!files.length) { toast("Choose a ZIP bundle or email and attachment files first.", true); return; }
    const form = new FormData(); for (const file of files) form.append("files", file, file.name); form.append("use_ai", String($("import-ai").checked));
    setBusy(true); $("import-progress").hidden = false; $("import-progress").className = "import-progress"; $("import-progress").textContent = "Reading documents and comparing the evidence. Scanned attachments can take a little longer…";
    $("submit-import").textContent = "Verifying…";
    try {
      const result = await api("/api/import", {method: "POST", body: form});
      const errors = list(result.errors);
      const count = typeof result.processed === "number" ? result.processed : list(result.cases).length;
      const preferred = list(result.cases)[0];
      $("status-filter").value = "all"; $("case-search").value = "";
      await loadCases(preferred ? typeof preferred === "string" ? preferred : caseId(preferred) : undefined);
      if (errors.length) {
        $("import-progress").className = "import-progress error";
        $("import-progress").textContent = count + " case(s) processed. The following items need attention:\n" + errors.map((e) => typeof e === "string" ? e : text(e.filename || e.email_id, "Item") + ": " + text(e.message || e.error || e.detail || e)).join("\n");
      } else {
        $("import-dialog").close(); $("import-form").reset(); $("import-files").required = true;
        state.files = null; showSelectedFiles(); $("import-progress").hidden = true;
        $("receipt-title").textContent = count + " case" + (count === 1 ? "" : "s") + " processed successfully";
        $("receipt-description").textContent = "The verification queue is updated. Inspect findings and source evidence below." + (list(result.ignored_files).length ? " " + list(result.ignored_files).length + " unrelated file(s) were ignored." : "");
        $("import-receipt").hidden = false;
        toast(count + " case" + (count === 1 ? "" : "s") + " processed. The evidence is ready to inspect.");
      }
    } catch (error) { $("import-progress").className = "import-progress error"; $("import-progress").textContent = error.message; }
    finally { setBusy(false); $("submit-import").textContent = "Verify documents →"; }
  }

  async function simulate() {
    if (!state.report || state.busy) return;
    const id = caseId(state.report);
    setBusy(true); $("simulate-changes").textContent = "Calculating…";
    try {
      const result = await api("/api/cases/" + encodeURIComponent(id) + "/simulate", {method: "POST", body: {corrections: corrections(), category: $("review-category").value}});
      if (id !== state.selected) return;
      const target = $("simulation-result"); clear(target); target.hidden = false;
      target.append(node("h4", "", "Preview only · Nothing saved"));
      const outcomes = node("div", "simulation-outcomes"); outcomes.append(caseBadge(result.before || state.report), node("span", "", "→"), caseBadge(result.after || state.report)); target.append(outcomes);
      target.append(node("p", "", result.after?.summary || "Preview calculated using your proposed extraction corrections."));
      if (result.before?.category !== result.after?.category) target.append(node("p", "", "Email category: " + categoryOf(result.before || state.report) + " → " + categoryOf(result.after || state.report)));
      if (result.before?.risk_score != null && result.after?.risk_score != null) target.append(node("p", "", "Risk score: " + result.before.risk_score + " → " + result.after.risk_score));
      const changes = list(result.changes);
      const ul = node("ul");
      for (const change of changes) ul.append(node("li", "", typeof change === "string" ? change : change.field ? nameOf(change.field) + ": " + text(change.before ?? change.from ?? change.old) + " → " + text(change.after ?? change.to ?? change.new) : text(change)));
      if (changes.length) target.append(ul); else target.append(node("p", "", "No extracted values changed. Your category confirmation and review will be recorded in the audit trail."));
      target.append(node("p", "", "The original source files remain unchanged. Record the review to persist your decision."));
    } catch (error) { toast(error.message, true); }
    finally { setBusy(false); $("simulate-changes").textContent = "Preview impact ↗"; }
  }

  async function saveReview(event) {
    event.preventDefault(); if (!state.report || state.busy) return;
    if (!$("review-form").reportValidity()) return;
    const reviewer = $("reviewer-name").value.trim(); const note = $("review-note").value.trim();
    if (!reviewer || !note) { toast("Enter a reviewer name and a meaningful review note.", true); return; }
    const id = caseId(state.report); const correctionsValue = corrections();
    if ($("review-decision").value === "correct" && !Object.keys(correctionsValue.si).length && !Object.keys(correctionsValue.bl).length) { toast("Change at least one extracted value, or choose “Keep extracted values”.", true); return; }
    setBusy(true); $("save-review").textContent = "Recording…";
    try {
      const report = await api("/api/cases/" + encodeURIComponent(id) + "/review", {method: "POST", body: {version: state.report.version, reviewer, note, category: $("review-category").value, corrections: correctionsValue, decision: $("review-decision").value}});
      safeStorage.set("harborlight-reviewer", reviewer);
      if (id === state.selected) { state.report = report; state.tab = "history"; renderReport(); }
      await loadCases(state.selected, {skipDetail: true});
      toast("Review recorded. Your decision and its evidence are preserved in the audit trail.");
    } catch (error) {
      if (error.status === 409) toast("This case changed since you opened it. Your draft is still visible. Copy any notes you need, then refresh the case and review the latest version.", true);
      else toast(error.message, true);
    } finally { setBusy(false); $("save-review").textContent = "Record review ✓"; }
  }

  async function retryCase() {
    if (!state.report || state.busy) return;
    const id = caseId(state.report); setBusy(true); $("retry-case").textContent = "Re-analyzing…";
    try {
      const result = await api("/api/cases/" + encodeURIComponent(id) + "/retry", {method: "POST", body: {use_ai: $("retry-ai").checked}});
      if (id === state.selected) { state.report = result; state.tab = "verify"; renderReport(); }
      await loadCases(state.selected, {skipDetail: true}); toast("Source documents re-analyzed. Inspect the refreshed findings.");
    } catch (error) { toast(error.message, true); }
    finally { setBusy(false); $("retry-case").textContent = "Re-analyze ↻"; }
  }

  $("case-search").addEventListener("input", renderQueue);
  $("status-filter").addEventListener("change", renderQueue);
  $("case-sort").addEventListener("change", renderQueue);
  for (const button of document.querySelectorAll(".queue-shortcut")) button.addEventListener("click", () => { $("status-filter").value = button.dataset.filter; renderQueue(); });
  $("brief-evidence").addEventListener("click", () => activateTab("sources", true));
  $("brief-review").addEventListener("click", () => activateTab("review", true));
  $("dismiss-receipt").addEventListener("click", () => { $("import-receipt").hidden = true; });
  for (const id of ["seed-demo", "empty-demo"]) $(id).addEventListener("click", seedDemo);
  for (const id of ["open-import", "open-import-rail"]) $(id).addEventListener("click", openImport);
  for (const id of ["close-import", "cancel-import"]) $(id).addEventListener("click", () => $("import-dialog").close());
  $("import-form").addEventListener("submit", importFiles);
  $("import-files").addEventListener("change", () => { state.files = null; showSelectedFiles(); });
  $("dismiss-intro").addEventListener("click", () => { $("intro-banner").hidden = true; safeStorage.set("harborlight-intro-dismissed", "yes"); });
  if (safeStorage.get("harborlight-intro-dismissed") === "yes") $("intro-banner").hidden = true;
  $("refresh-cases").addEventListener("click", async () => { if (state.busy) return; $("refresh-cases").disabled = true; try { await Promise.all([loadHealth(), loadCases(state.selected, {keepTab: true})]); toast("Workspace refreshed."); } catch (error) { toast(error.message, true); } finally { $("refresh-cases").disabled = false; } });
  $("goto-review").addEventListener("click", () => activateTab("review", true));
  $("review-decision").addEventListener("change", () => { $("correction-fields").hidden = $("review-decision").value !== "correct"; $("simulation-result").hidden = true; });
  $("review-category").addEventListener("change", () => { updateReviewCategoryControls(); $("simulation-result").hidden = true; });
  $("review-form").addEventListener("submit", saveReview);
  $("simulate-changes").addEventListener("click", simulate);
  $("retry-case").addEventListener("click", retryCase);
  for (const tab of document.querySelectorAll("[data-tab]")) {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
    tab.addEventListener("keydown", (event) => { const names = ["verify", "sources", "review", "history"]; const index = names.indexOf(tab.dataset.tab); let next; if (event.key === "ArrowRight") next = names[(index + 1) % names.length]; if (event.key === "ArrowLeft") next = names[(index + names.length - 1) % names.length]; if (event.key === "Home") next = names[0]; if (event.key === "End") next = names[names.length - 1]; if (next) { event.preventDefault(); activateTab(next, true); } });
  }
  const dropZone = $("drop-zone");
  for (const type of ["dragenter", "dragover"]) dropZone.addEventListener(type, (event) => { event.preventDefault(); dropZone.classList.add("dragover"); });
  for (const type of ["dragleave", "drop"]) dropZone.addEventListener(type, (event) => { event.preventDefault(); dropZone.classList.remove("dragover"); });
  dropZone.addEventListener("drop", (event) => { if (!event.dataTransfer?.files?.length) return; state.files = Array.from(event.dataTransfer.files); try { $("import-files").files = event.dataTransfer.files; } catch { $("import-files").required = false; } showSelectedFiles(); });
  Promise.all([loadHealth(), loadCases()]).catch((error) => { $("queue-count").textContent = "Service not connected"; toast(error.message, true); });
})();
