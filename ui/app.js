/* Browser adapter for the existing two-model LangGraph workflow. */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { catalog: null, examples: new Map(), material: null, upload: null,
  result: null, busy: false, loadingExample: false, selectionVersion: 0 };
const CUSTOM_DESIGN = { id_column: "", independence: "", randomized: null,
  assignment: "", variables: {}, typical_outcome: "" };
const NODE_LABELS = {
  plan_analysis: ["Plan", "Model A chooses a supported method and statistical target"],
  prepare_data_summary: ["Data profile", "Python reads the current CSV version"],
  llm_diagnostics: ["Semantic checks", "Model A reviews meanings, design and goal alignment"],
  stat_diagnostics: ["Statistical checks", "Python checks values and method requirements"],
  merge_diagnostics: ["Merge checks", "Join the parallel diagnostics and select the next route"],
  request_clarification: ["Human decisions", "Pause for explicit record-level answers"],
  apply_corrections: ["Apply decisions", "Save a new data version and audit trail"],
  run_statistical_test: ["Calculate", "Python computes the statistical result"],
  build_stats_block: ["Protect evidence", "Fix numbers, hypotheses and required limitations"],
  draft_report: ["Draft", "Model A interprets the protected result"],
  check_report: ["Program check", "Verify numbers, decision and required content"],
  review_report: ["Independent review", "Model B reviews the draft against original evidence"],
  revise_report: ["Revise once", "Model A addresses the review and program feedback"],
  deliver_report: ["Deliver", "Release the validated interpretation"],
  issue_notice: ["Stop", "Explain why no validated report was delivered"],
  save_session: ["Session memory", "Keep the latest successful evidence for follow-ups"],
  handle_followup: ["Route follow-up", "Decide which evidence to reuse or recompute"]
};

function el(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function replace(id, ...children) { $(id).replaceChildren(...children); }
function textValue(value) {
  if (value === undefined || value === null || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
function notice(text, kind = "running") {
  const box = $("operationNotice");
  box.textContent = text;
  box.dataset.kind = kind;
  box.hidden = !text;
}
function progress(id, text, kind = "running") {
  $(id).textContent = text;
  $(id).dataset.kind = kind;
}
function inputsChanged() {
  if (!state.result || state.busy) return;
  const message = "The inputs have changed. The displayed result belongs to the previous analysis/session. Run analysis to use the new inputs.";
  if ($("notice").textContent !== message) {
    $("notice").textContent = message;
    notice(message, "attention");
  }
  progress("progress", "");
}
function setBusy(busy) {
  state.busy = busy;
  for (const input of document.querySelectorAll("button, select, textarea, input")) input.disabled = busy;
  $("uploadLabel").classList.toggle("disabled", busy);
  if (!busy) {
    $("run").disabled = state.loadingExample || (!state.material && !state.upload);
    $("case").disabled = !state.catalog;
    $("downloadCsv").disabled = !state.material;
    $("confidence").disabled = state.result?.stats_block?.method === "chi_square_independence";
  }
}
async function getJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  let payload;
  try { payload = await response.json(); }
  catch { throw new Error("The local server returned an unreadable response."); }
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status}).`);
  return payload;
}
function modeHelp() {
  const models = state.catalog?.models || {};
  $("modeHelp").textContent = $("mode").value === "mock"
    ? "Mock mode uses fixed, rule-based agent stand-ins. Python calculations and workflow checks are real. Start with the supplied English questions; this mode does not measure LLM performance."
    : `Real mode calls Model A (${textValue(models.model_a)}) and Model B (${textValue(models.model_b)}). Questions, user-stated design, profiles and statistical evidence are sent to the configured providers. Local Ollama calls may take several minutes.`;
}
function table(columns, rows) {
  const result = el("table");
  const head = el("thead"), heading = el("tr");
  for (const column of columns) heading.append(el("th", column));
  head.append(heading);
  result.append(head);
  const body = el("tbody");
  for (const row of rows || []) {
    const line = el("tr");
    for (let i = 0; i < columns.length; i++) line.append(el("td", textValue(Array.isArray(row) ? row[i] : row[columns[i]])));
    body.append(line);
  }
  result.append(body);
  return result;
}
function showPreview(id, preview) {
  if (!preview?.columns?.length) { replace(id, el("p", "No preview is available.", "muted")); return; }
  replace(id, table(preview.columns, preview.preview || []),
    el("p", `${textValue(preview.rows)} rows in this data version. Preview shows only the first records.`, "muted"));
}
function download(text, filename, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = el("a");
  link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exampleGuide(example) {
  const container = el("div");
  container.append(el("strong", "Expected behavior"), el("p", example.expected || example.description));
  if (example.followup) container.append(el("strong", "Try a follow-up"), el("p", example.followup));
  container.append(el("span", "Synthetic teaching data; these are demonstration scenarios.", "muted"));
  replace("caseGuide", container);
}
function useCustom() {
  state.material = null;
  $("material").hidden = true;
  $("caseNote").textContent = "Use a CSV with a unique header and one record per row. Confirm the study facts below before running.";
  replace("caseGuide", el("p", "Describe which columns are numeric or categorical, their meaning, and the observation design. The assistant must not infer these facts from your CSV."));
  $("designConfirmLabel").hidden = false;
  $("designDetails").open = true;
  $("designConfirm").checked = false;
  $("designInfo").value = JSON.stringify(CUSTOM_DESIGN, null, 2);
  $("question").value = "";
  setBusy(false);
}
async function selectExample() {
  inputsChanged();
  const version = ++state.selectionVersion;
  const id = $("case").value;
  state.upload = null;
  $("file").value = "";
  $("fileInfo").textContent = "";
  if (id === "custom") { useCustom(); return; }
  const example = state.examples.get(id);
  state.material = null;
  state.loadingExample = true;
  $("run").disabled = true;
  $("downloadCsv").disabled = true;
  $("caseNote").textContent = "Loading example data…";
  progress("progress", "");
  try {
    const material = await getJson(`/examples/${encodeURIComponent(id)}.json`);
    if (version !== state.selectionVersion) return;
    state.material = material;
    $("question").value = material.question || example.question || "";
    $("designInfo").value = JSON.stringify(material.design_info || example.design_info || {}, null, 2);
    $("designConfirmLabel").hidden = true;
    $("designConfirm").checked = false;
    $("designDetails").open = false;
    $("caseNote").textContent = example.description;
    exampleGuide(example);
    $("csvInfo").textContent = `${material.filename} · ${material.rows} rows · ${material.columns.length} columns`;
    showPreview("materialPreview", material);
    $("material").hidden = false;
  } catch (error) {
    if (version === state.selectionVersion) {
      $("caseNote").textContent = "The example could not be loaded.";
      progress("progress", error.message, "error");
    }
  } finally {
    if (version === state.selectionVersion) { state.loadingExample = false; setBusy(false); }
  }
}
function metadata() {
  let design;
  try { design = JSON.parse($("designInfo").value); }
  catch { throw new Error("Design metadata must be valid JSON. Check quotation marks, commas and brackets."); }
  if (!design || typeof design !== "object" || Array.isArray(design)) throw new Error("Design metadata must be a JSON object.");
  if (state.upload) {
    if (!$("designConfirm").checked) throw new Error("Confirm your uploaded dataset's study design and variable metadata before running.");
    if (!String(design.independence || "").trim()) throw new Error("Describe the observation design in the independence field. State paired or clustered observations if applicable.");
    if (!design.variables || typeof design.variables !== "object" || !Object.keys(design.variables).length) throw new Error("Define the analysis variables and their types in design metadata.");
    for (const [name, variable] of Object.entries(design.variables)) {
      if (!variable || !["numeric", "categorical"].includes(variable.type) || !String(variable.meaning || "").trim()) {
        throw new Error(`Define type (numeric or categorical) and meaning for ${name}.`);
      }
    }
  }
  return design;
}

async function runJob(action, values, progressId) {
  if (state.busy) return;
  setBusy(true);
  const began = Date.now();
  const activeMode = values.mode || state.result?.mode || "mock";
  const title = action === "resume" ? "Applying your decisions" : action === "followup" ? "Running follow-up" : "Running analysis";
  progress(progressId, `${title}…`);
  notice(`${title}. Please keep this tab open.`, "running");
  if (state.result) $("notice").textContent = "A new request is running. The results currently displayed belong to the previous request.";
  try {
    const submitted = await getJson("/api", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, ...values }) });
    if (!submitted.job_id) throw new Error("The server did not return a job identifier.");
    while (true) {
      const job = await getJson(`/api/jobs/${encodeURIComponent(submitted.job_id)}`);
      if (job.status === "failed") throw new Error(job.error || "The request failed. Inspect the server configuration and try again.");
      if (job.status === "completed") {
        if (!job.result) throw new Error("The server completed the request without a result.");
        renderResult(job.result);
        const paused = job.result.status === "needs_clarification";
        const stopped = job.result.status === "stopped";
        const message = paused ? "Paused for your decisions. Review the flagged records below." : stopped ? "Analysis stopped. The reason is shown in the result." : "Report delivered. Inspect the plan and execution trail below.";
        progress(progressId, message, paused || stopped ? "attention" : "success");
        if (progressId !== "progress") progress("progress", message, paused || stopped ? "attention" : "success");
        notice(message, paused || stopped ? "attention" : "success");
        break;
      }
      const seconds = Math.floor((Date.now() - began) / 1000);
      const detail = `${title}… ${seconds}s elapsed. ${activeMode === "real" ? "Real model calls can take several minutes." : "The workflow is computing and validating the result."}`;
      progress(progressId, detail);
      notice(detail, "running");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } catch (error) {
    progress(progressId, error.message, "error");
    notice(error.message, "error");
    if (state.result) $("notice").textContent = `The new request failed: ${error.message} The result below is from request ${state.result.request_number}; it has not been updated.`;
  } finally { setBusy(false); }
}
function renderPairs(target, entries) {
  const list = el("dl", null, "key-values");
  for (const [name, value] of entries) {
    if (value === "" || value === undefined || value === null || (Array.isArray(value) && !value.length)) continue;
    list.append(el("dt", name));
    const description = el("dd");
    if (Array.isArray(value)) {
      const items = el("ul");
      for (const item of value) items.append(el("li", textValue(item)));
      description.append(items);
    } else description.textContent = textValue(value);
    list.append(description);
  }
  replace(target, list.childElementCount ? list : el("p", "No plan was produced for this request.", "muted"));
}
function renderMetrics(result) {
  const sb = result.stats_block || {}, v = sb.values || {};
  if (!Object.keys(v).length) { replace("metrics"); $("hypotheses").hidden = true; return; }
  const metrics = [];
  if (sb.method === "welch_t_test") metrics.push(["Mean difference", v.mean_difference, `${v.group_1} minus ${v.group_2}`]);
  if (sb.method === "pearson_correlation") metrics.push(["Pearson correlation", v.r, "Linear association"]);
  if (sb.method === "chi_square_independence") metrics.push(["Cramer's V", v.cramers_v, "Strength of association"]);
  if (sb.method === "simple_linear_regression") metrics.push(["Estimated slope", v.slope, "Outcome change per predictor unit"]);
  metrics.push(["p-value", v.p_value, `Two-sided test · α = ${v.alpha}`]);
  if (v.ci_lower !== undefined) metrics.push([`${v.confidence_level} confidence interval`, `${v.ci_lower} to ${v.ci_upper}`, "Interval for the estimated parameter"]);
  else metrics.push(["Observations", v.n || v.n_included, "No effect interval implemented for this method"]);
  replace("metrics", ...metrics.map(([label, value, note]) => {
    const card = el("div", null, "metric");
    card.append(el("span", label), el("strong", textValue(value)), el("small", note));
    return card;
  }));
  replace("hypotheses", el("strong", sb.method_label), el("p", sb.hypotheses),
    el("p", `Decision at α = ${v.alpha}: ${sb.decision === "reject_H0" ? "Reject H0." : "Do not reject H0. This is not evidence that the null hypothesis is true."}`));
  if (sb.method === "welch_t_test") {
    const wrap = el("div", null, "table-wrap");
    wrap.append(table(["Group", "n", "Mean", "SD"], [[v.group_1, v.n_group_1, v.mean_group_1, v.sd_group_1], [v.group_2, v.n_group_2, v.mean_group_2, v.sd_group_2]]));
    $("hypotheses").append(wrap);
  }
  if (sb.method === "chi_square_independence" && sb.observed?.counts) {
    const wrap = el("div", null, "table-wrap");
    const observed = sb.observed;
    wrap.append(table(["Observed counts", ...observed.col_labels], observed.counts.map((counts, index) => [observed.row_labels[index], ...counts])));
    $("hypotheses").append(wrap);
  }
  $("hypotheses").hidden = false;
}
function renderReport(text, target = "reportText") {
  const container = $(target);
  container.replaceChildren();
  const lines = String(text || "").split(/\r?\n/);
  let paragraph = [], list = null;
  function flush() { if (paragraph.length) { container.append(el("p", paragraph.join("\n"))); paragraph = []; } }
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    if (/^\s*\|/.test(line)) {
      flush(); list = null;
      const block = [];
      while (index < lines.length && /^\s*\|/.test(lines[index])) block.push(lines[index++]);
      index--;
      const cells = block.map((row) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim()));
      const rows = cells.slice(1).filter((row) => !row.every((cell) => /^:?-+:?$/.test(cell)));
      const wrap = el("div", null, "table-wrap"); wrap.append(table(cells[0], rows)); container.append(wrap);
    } else if (/^\s*-\s+/.test(line)) {
      flush();
      if (!list) { list = el("ul"); container.append(list); }
      list.append(el("li", line.replace(/^\s*-\s+/, "")));
    } else if (!line.trim()) { flush(); list = null; }
    else { list = null; paragraph.push(line); }
  }
  flush();
}
function jsonSection(title, value, open = false) {
  const section = el("details"); section.open = open;
  section.append(el("summary", title), el("pre", JSON.stringify(value || {}, null, 2)));
  return section;
}
function renderChecks(result) {
  const semantic = result.llm_diagnostics || {};
  const content = el("div");
  if (Object.keys(semantic).length) {
    content.append(el("h3", "Model A · semantic diagnostic"));
    for (const [key, label] of [["variable_meanings", "Variable meanings"], ["design_assessment", "Study design"], ["goal_alignment", "Goal alignment"], ["distribution_notes", "Distribution notes"]]) {
      if (semantic[key]) content.append(el("strong", label), el("p", semantic[key]));
    }
    if (semantic.issues?.length) content.append(jsonSection("Semantic findings", semantic.issues, true));
  }
  const diagnostic = result.stat_diagnostics || {};
  if (Object.keys(diagnostic).length) {
    content.append(el("h3", "Python · deterministic diagnostic"));
    if (diagnostic.findings?.length) {
      const items = el("ul");
      for (const finding of diagnostic.findings) items.append(el("li", `${textValue(finding.record_id)} / ${textValue(finding.field)}: ${textValue(finding.check)} — ${finding.detail || finding.value_as_written || "review requested"}`));
      content.append(items);
    }
    if (diagnostic.method_findings?.length) {
      for (const finding of diagnostic.method_findings) content.append(el("p", finding.detail || textValue(finding), "error-text"));
    }
    content.append(jsonSection("Full diagnostic evidence", diagnostic));
  }
  if (result.errors?.length) content.append(jsonSection("Request errors", result.errors, true));
  if (!content.childElementCount) content.append(el("p", "Diagnostics were not completed for this request.", "muted"));
  replace("checks", content);
}
function renderReview(result) {
  const content = el("div");
  for (const [title, verdict] of [["Program check", result.program_check], ["Model B · independent interpretation review", result.review]]) {
    content.append(el("h3", title));
    if (!verdict || !Object.keys(verdict).length) content.append(el("p", "Not reached for this request.", "muted"));
    else {
      content.append(el("p", verdict.passed ? "Passed for the final draft." : "Did not pass for the final draft.", verdict.passed ? "success-text" : "error-text"));
      if (verdict.summary) content.append(el("p", verdict.summary));
      const items = verdict.issues || verdict.problems;
      if (items?.length) content.append(jsonSection("Review feedback", items, true));
    }
  }
  content.append(el("p", "Independent model review and deterministic checks reduce errors; this is not a human evaluation score or proof of statistical validity.", "muted"));
  replace("reviewContent", content);
}
function renderTrace(result) {
  const rows = (result.trace || []).filter((entry) => !entry.request_number || entry.request_number === result.request_number);
  replace("trace", ...rows.map((entry, index) => {
    const name = typeof entry === "string" ? entry : entry.node;
    const [title, description] = NODE_LABELS[name] || [name, "Workflow step"];
    const item = el("li", null, "trace-item");
    item.append(el("strong", `${index + 1}. ${title}`), el("span", description));
    if (typeof entry === "object") {
      const seconds = Number(entry.end ?? entry.ended) - Number(entry.start ?? entry.started);
      const timing = Number.isFinite(seconds) ? ` · ${Math.max(0, seconds).toFixed(1)}s` : "";
      item.append(el("span", `${entry.status || "completed"}${timing} · ${entry.data_version || result.data_version || ""}`));
      item.dataset.status = entry.status || "completed";
    }
    return item;
  }));
  if (result.status === "needs_clarification") {
    const item = el("li", null, "trace-item");
    item.append(el("strong", "Paused · human decisions"), el("span", "No correction or statistical test will proceed without your answers."));
    item.dataset.status = "pending";
    $("trace").append(item);
  }
}
function renderClarification(result) {
  const requests = result.clarification?.requests || [];
  $("clarify").hidden = result.status !== "needs_clarification";
  $("clarificationRejected").textContent = (result.clarification?.previous_rejections || []).join("\n");
  const elements = requests.map((request, index) => {
    const card = el("fieldset", null, "request-card");
    card.dataset.requestId = request.request_id;
    card.append(el("legend", `${index + 1}. ${request.record_id || "Record"} · ${request.field || "Field"}`));
    card.append(el("p", request.question || "Review this flagged value."));
    card.append(el("p", `${request.check}: value as written ${JSON.stringify(request.value_as_written ?? "")}`, "muted"));
    if (request.detail) card.append(el("p", request.detail, "muted"));
    const label = el("label", "Your action");
    label.htmlFor = `decision-${index}`;
    const select = el("select"); select.id = label.htmlFor; select.className = "decision-action"; select.required = true;
    const empty = el("option", "Select an action…"); empty.value = ""; empty.disabled = true; empty.selected = true; select.append(empty);
    const names = { correct: "Correct this value", exclude: "Exclude this record", verify: "Verify the recorded value", stop: "Stop the analysis" };
    for (const action of request.allowed_responses || []) { const option = el("option", names[action] || action); option.value = action; select.append(option); }
    const valueBox = el("div"); valueBox.className = "correction-value"; valueBox.hidden = true;
    const valueLabel = el("label", "Confirmed replacement value"); valueLabel.htmlFor = `value-${index}`;
    const input = el("input"); input.id = valueLabel.htmlFor; input.type = "text"; input.className = "decision-value";
    if (request.field_type === "numeric") input.inputMode = "decimal";
    valueBox.append(valueLabel, input);
    if (request.valid_levels?.length) valueBox.append(el("p", `Valid labels: ${request.valid_levels.join(", ")}. Exact spelling is required.`, "muted"));
    if (request.valid_range) valueBox.append(el("p", `User-stated range: ${request.valid_range.join(" to ")}.`, "muted"));
    const reasonLabel = el("label", "Source or reason"); reasonLabel.htmlFor = `reason-${index}`;
    const reason = el("textarea"); reason.id = reasonLabel.htmlFor; reason.className = "decision-reason"; reason.rows = 2;
    reason.placeholder = "Describe what you checked or why this decision is appropriate.";
    card.append(label, select, valueBox, reasonLabel, reason);
    select.addEventListener("change", () => { valueBox.hidden = select.value !== "correct"; input.required = select.value === "correct"; reason.required = select.value !== "stop"; });
    return card;
  });
  replace("clarificationRequests", ...elements);
  progress("clarifyProgress", "");
}
function renderResult(result) {
  state.result = result;
  $("empty").hidden = true;
  $("output").hidden = false;
  $("status").textContent = result.status === "delivered" ? "Report delivered" : result.status === "needs_clarification" ? "Paused for your decisions" : "Analysis stopped";
  $("modeBadge").textContent = result.mode === "real" ? "REAL · two models" : "MOCK · rule-based agents";
  $("resultContext").textContent = `Request ${result.request_number || 1} · Data ${result.data_version || "v1"} · ${result.question || ""}`;
  const messages = [];
  if (result.mode !== "real") messages.push("Mock mode demonstrates workflow behavior with rule-based agents; these results do not evaluate LLM reasoning.");
  if (result.status === "stopped") messages.push("No validated inferential report was delivered. Any statistics displayed were computed before the stop and are not an approved interpretation.");
  if (result.status === "needs_clarification") messages.push("Data issues require your explicit answers. No records have been silently corrected or excluded.");
  $("notice").textContent = messages.join(" ");
  renderClarification(result);
  renderMetrics(result);
  $("interpretation").hidden = !result.report;
  $("reportTitle").textContent = result.status === "delivered" ? "Validated report" : "Workflow notice";
  const interpretation = result.interpretation || {};
  if (result.status === "delivered" && interpretation.interpretation) {
    replace("reportText", el("p", interpretation.interpretation));
    if (interpretation.limitations?.length) {
      const limitations = el("ul");
      for (const limitation of interpretation.limitations) limitations.append(el("li", typeof limitation === "string" ? limitation : limitation.text));
      $("reportText").append(el("strong", "Limitations"), limitations);
    }
  } else renderReport(result.report || "");
  $("fullReportDetails").hidden = result.status !== "delivered";
  renderReport(result.report || "", "fullReport");
  const plan = result.plan || {};
  renderPairs("plan", [["Method", result.stats_block?.method_label || plan.method], ["Target parameter", plan.target_parameter],
    ["Outcome", plan.outcome], ["Group", plan.group], ["Group order", plan.group_1_label ? `${plan.group_1_label} minus ${plan.group_2_label}` : ""],
    ["Predictor / first variable", plan.x], ["Outcome / second variable", plan.y], ["Null hypothesis", plan.null_hypothesis],
    ["Alternative hypothesis", plan.alternative_hypothesis], ["Why this method", plan.method_rationale], ["Design notes", plan.design_notes]]);
  renderChecks(result); renderReview(result); renderTrace(result);
  showPreview("preview", result.preview);
  const audit = result.correction_log || [];
  $("auditDetails").hidden = !audit.length;
  replace("audit", el("p", `Current data version: ${result.data_version}. Original input is retained; decisions are applied to a new version.`, "muted"),
    table(["Record", "Field", "Action", "Old value", "New value", "Source / reason", "Version"], audit.map((entry) => [entry.record_id, entry.field, entry.action, entry.old_value, entry.new_value, entry.reason, `${entry.from_version} → ${entry.to_version}`])));
  const calls = (result.model_calls || []).filter((entry) => !entry.request_number || entry.request_number === result.request_number);
  replace("modelCalls", calls.length ? table(["Node", "Agent action", "Model", "Mode", "Status"], calls.map((entry) => [entry.node, entry.method, entry.model, entry.mode, entry.status])) : el("p", "No model calls were made for this request.", "muted"));
  $("followSection").hidden = !result.can_followup;
  $("followSection").querySelector("p").textContent = "Re-explanation reuses the saved statistics. A new confidence level recomputes the interval. A new supported question replans the analysis. Follow-ups use the displayed session and its original execution mode, even if you change the input panel. To use new data or a different subset, start a new analysis with a new CSV.";
  $("confidence").disabled = result.stats_block?.method === "chi_square_independence";
  $("confidence").title = result.stats_block?.method === "chi_square_independence" ? "A confidence interval for Cramer's V is not implemented." : "Recompute this analysis with a 99% confidence interval.";
  $("follow").value = "";
  progress("followProgress", "");
}

$("case").addEventListener("change", selectExample);
$("mode").addEventListener("change", () => { modeHelp(); inputsChanged(); });
$("question").addEventListener("input", inputsChanged);
$("designInfo").addEventListener("input", () => { $("designConfirm").checked = false; inputsChanged(); });
$("designConfirm").addEventListener("change", inputsChanged);
$("file").addEventListener("change", async () => {
  const file = $("file").files[0];
  if (!file || state.busy) return;
  const version = ++state.selectionVersion;
  state.loadingExample = false;
  if (file.size > 4 * 1024 * 1024) { progress("progress", "Choose a CSV smaller than 4 MB.", "error"); $("file").value = ""; return; }
  try {
    const csv = await file.text();
    if (version !== state.selectionVersion) return;
    inputsChanged();
    $("case").value = "custom";
    useCustom();
    state.upload = { csv, filename: file.name };
    $("fileInfo").textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB. Enter its question and design metadata below.`;
    progress("progress", "CSV selected. Complete the study design and variable definitions before running.", "attention");
    setBusy(false);
  } catch { progress("progress", "The CSV could not be read. Try another file.", "error"); }
});
$("downloadCsv").addEventListener("click", () => { if (state.material) download(state.material.csv, state.material.filename, "text/csv;charset=utf-8"); });
$("downloadReport").addEventListener("click", () => { if (state.result?.report) download(state.result.report, `analysis-request-${state.result.request_number || 1}.txt`, "text/plain;charset=utf-8"); });
$("run").addEventListener("click", () => {
  try {
    const question = $("question").value.trim();
    if (!question) throw new Error("Enter a research question.");
    const values = { question, mode: $("mode").value, design_info: metadata() };
    if (state.upload) Object.assign(values, state.upload, { design_confirmed: $("designConfirm").checked });
    else if (state.material) values.example = $("case").value;
    else throw new Error("Select a built-in case or upload a CSV.");
    runJob("analyze", values, "progress");
  } catch (error) { progress("progress", error.message, "error"); notice(error.message, "error"); }
});
$("clarificationForm").addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    const cards = [...document.querySelectorAll(".request-card")];
    const stopping = cards.find((card) => card.querySelector(".decision-action").value === "stop");
    if (stopping) { runJob("resume", { session_id: state.result.session_id, answers: [{ request_id: stopping.dataset.requestId, action: "stop", reason: "" }] }, "clarifyProgress"); return; }
    const answers = cards.map((card) => {
      const action = card.querySelector(".decision-action").value;
      const reason = card.querySelector(".decision-reason").value.trim();
      if (!action) throw new Error("Select an action for every flagged item, or stop the analysis.");
      if (!reason) throw new Error("Supply a source or reason for every correction, exclusion or verification.");
      const answer = { request_id: card.dataset.requestId, action, reason };
      if (action === "correct") {
        answer.new_value = card.querySelector(".decision-value").value.trim();
        if (!answer.new_value) throw new Error("Enter a confirmed replacement value for each correction.");
      }
      return answer;
    });
    runJob("resume", { session_id: state.result.session_id, answers }, "clarifyProgress");
  } catch (error) { progress("clarifyProgress", error.message, "error"); notice(error.message, "error"); }
});
$("stop").addEventListener("click", () => {
  const request = state.result?.clarification?.requests?.find((item) => item.allowed_responses?.includes("stop"));
  if (request) runJob("resume", { session_id: state.result.session_id, answers: [{ request_id: request.request_id, action: "stop", reason: "" }] }, "clarifyProgress");
});
function followup(question) {
  if (!question.trim()) { progress("followProgress", "Enter a follow-up question.", "error"); return; }
  runJob("followup", { session_id: state.result.session_id, question: question.trim() }, "followProgress");
}
$("explain").addEventListener("click", () => followup("Explain the existing result in simpler language, including what the hypothesis test does and does not establish."));
$("confidence").addEventListener("click", () => followup("Recalculate the same analysis with a 99% confidence interval."));
$("followRun").addEventListener("click", () => followup($("follow").value));

async function initialize() {
  try {
    state.catalog = await getJson("/api/catalog");
    state.examples = new Map(state.catalog.examples.map((example) => [example.id, example]));
    replace("case", ...state.catalog.examples.map((example) => { const option = el("option", example.title); option.value = example.id; return option; }),
      (() => { const option = el("option", "Upload my CSV"); option.value = "custom"; return option; })());
    $("case").disabled = false;
    $("mode").value = state.catalog.default_mode || "mock";
    modeHelp();
    await selectExample();
  } catch (error) {
    $("caseNote").textContent = "The local workspace could not be loaded.";
    progress("progress", error.message, "error"); notice(error.message, "error");
  }
}
initialize();
