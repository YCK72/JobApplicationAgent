"use strict";

const state = {
  jobs: [], source: null, loading: false,
  editingJobId: null, targetDraft: "",
  resolvingJobId: null, resolutionOutcome: "DEFERRED", resolutionNote: "",
  history: [], historyJob: null,
};
const elements = {
  metrics: document.querySelector("#metrics"),
  jobsBody: document.querySelector("#jobs-body"),
  emptyState: document.querySelector("#empty-state"),
  resultCount: document.querySelector("#result-count"),
  statusBreakdown: document.querySelector("#status-breakdown"),
  search: document.querySelector("#search"),
  status: document.querySelector("#status-filter"),
  category: document.querySelector("#category-filter"),
  method: document.querySelector("#method-filter"),
  review: document.querySelector("#review-filter"),
  sort: document.querySelector("#sort"),
  warning: document.querySelector("#warning"),
  reviewNotice: document.querySelector("#review-notice"),
  refresh: document.querySelector("#refresh-button"),
  syncDot: document.querySelector("#sync-dot"),
  syncLabel: document.querySelector("#sync-label"),
  syncDetail: document.querySelector("#sync-detail"),
  workbookName: document.querySelector("#workbook-name"),
  historyPanel: document.querySelector("#review-history-panel"),
  historyJob: document.querySelector("#history-job"),
  historyList: document.querySelector("#history-list"),
  historyOutcome: document.querySelector("#history-outcome-filter"),
  historyKind: document.querySelector("#history-kind-filter"),
  historyClose: document.querySelector("#history-close"),
};

const metricDefinitions = [
  ["total_jobs", "Total jobs", true],
  ["applied", "Applied"],
  ["manual_queue", "Manual queue"],
  ["review_queue", "Review queue"],
  ["needs_review", "Needs review"],
  ["in_progress", "In progress"],
  ["offers", "Offers"],
  ["rejected", "Rejected"],
];

function createNode(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function replaceChildren(parent, children) {
  parent.replaceChildren(...children);
}

function label(value) {
  if (!value) return "—";
  return String(value).toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(parsed);
}

function timeLabel(value) {
  if (!value) return "Waiting for workbook";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Workbook loaded";
  return `Updated ${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(parsed)}`;
}

function renderMetrics(metrics = {}) {
  const cards = metricDefinitions.map(([key, title, primary]) => {
    const card = createNode("article", `metric-card${primary ? " primary" : ""}`);
    card.append(createNode("strong", "", metrics[key] ?? 0), createNode("span", "", title));
    return card;
  });
  replaceChildren(elements.metrics, cards);
}

function populateSelect(select, values) {
  const current = select.value;
  const first = select.options[0].cloneNode(true);
  const options = [first, ...(values || []).map((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label(value);
    return option;
  })];
  replaceChildren(select, options);
  select.value = values && values.includes(current) ? current : "";
}

function filteredJobs() {
  const query = elements.search.value.trim().toLowerCase();
  const jobs = state.jobs.filter((job) => {
    const searchText = [job.company, job.title, job.location, job.notes, job.review_reason].filter(Boolean).join(" ").toLowerCase();
    const reviewMatch = !elements.review.value
      || (elements.review.value === "required" && job.review_required === true)
      || (elements.review.value === "clear" && job.review_required !== true);
    return (!query || searchText.includes(query))
      && (!elements.status.value || job.status === elements.status.value)
      && (!elements.category.value || job.category === elements.category.value)
      && (!elements.method.value || job.application_method === elements.method.value)
      && reviewMatch;
  });

  const sort = elements.sort.value;
  return jobs.sort((left, right) => {
    if (sort === "fit-desc") return (Number(right.fit_score) || -1) - (Number(left.fit_score) || -1);
    if (sort === "company-asc") return String(left.company || "").localeCompare(String(right.company || ""));
    return String(right.date_found || "").localeCompare(String(left.date_found || ""));
  });
}

function renderTable() {
  const jobs = filteredJobs();
  elements.resultCount.textContent = `${jobs.length} ${jobs.length === 1 ? "job" : "jobs"}`;
  elements.emptyState.hidden = jobs.length !== 0;

  const rows = jobs.map((job) => {
    const row = document.createElement("tr");
    const opportunity = document.createElement("td");
    opportunity.append(createNode("span", "job-title", job.title || "Untitled role"), createNode("span", "company", job.company || "Unknown company"));

    const fit = document.createElement("td");
    const hasFit = job.fit_score !== null && job.fit_score !== undefined && job.fit_score !== "";
    fit.append(createNode("span", `fit-score${hasFit ? "" : " missing"}`, hasFit ? Math.round(Number(job.fit_score)) : "—"));

    const status = document.createElement("td");
    status.append(createNode("span", `pill status-${String(job.status || "unknown").toLowerCase().replaceAll("_", "-")}`, label(job.status)));

    const method = document.createElement("td");
    method.append(createNode("span", "pill", label(job.application_method)));

    const review = document.createElement("td");
    review.className = "review-cell";
    if (job.review_required) {
      review.append(
        createNode("span", "review-kind", label(job.review_kind)),
        createNode("span", "review-reason", job.review_reason || "Review required."),
      );
      if (job.review_outcome) {
        review.append(createNode("span", "review-history", `${label(job.review_outcome)}: ${job.review_note || "No note"}`));
      }
      if (job.job_id && state.resolvingJobId === job.job_id) {
        const form = createNode("form", "resolution-form");
        const outcome = createNode("select", "resolution-outcome");
        for (const value of ["RESOLVED", "DEFERRED", "DISMISSED"]) {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = label(value);
          outcome.append(option);
        }
        outcome.value = state.resolutionOutcome;
        outcome.setAttribute("aria-label", `Review outcome for ${job.title || "job"}`);
        outcome.addEventListener("change", () => { state.resolutionOutcome = outcome.value; });
        const note = createNode("input", "resolution-note");
        note.type = "text";
        note.required = true;
        note.minLength = 3;
        note.maxLength = 1000;
        note.placeholder = "Required decision note";
        note.value = state.resolutionNote;
        note.setAttribute("aria-label", `Review note for ${job.title || "job"}`);
        note.addEventListener("input", () => { state.resolutionNote = note.value; });
        const save = createNode("button", "resolution-save", "Save");
        save.type = "submit";
        const cancel = createNode("button", "resolution-cancel", "Cancel");
        cancel.type = "button";
        cancel.addEventListener("click", () => {
          state.resolvingJobId = null;
          state.resolutionNote = "";
          renderTable();
        });
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          save.disabled = true;
          await submitReviewResolution(job.job_id);
        });
        form.append(outcome, note, save, cancel);
        review.append(form);
      } else if (job.job_id) {
        const decide = createNode("button", "resolution-open", "Record decision");
        decide.type = "button";
        decide.addEventListener("click", () => {
          state.resolvingJobId = job.job_id;
          state.resolutionOutcome = "DEFERRED";
          state.resolutionNote = "";
          renderTable();
        });
        review.append(decide);
      }
    } else if (job.review_outcome) {
      review.append(
        createNode("span", "review-kind resolved", label(job.review_outcome)),
        createNode("span", "review-reason", job.review_note || "Review decision recorded."),
      );
    } else {
      review.append(createNode("span", "review-clear", "No action"));
    }

    const linkCell = document.createElement("td");
    linkCell.className = "link-group";
    if (job.job_url) {
      const link = createNode("a", "open-link", "Source");
      link.href = job.job_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.setAttribute("aria-label", `Open ${job.title || "job"} listing`);
      linkCell.append(link);
    }
    if (job.application_url) {
      const link = createNode("a", "open-link apply-link", "Apply");
      link.href = job.application_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.setAttribute("aria-label", `Open ${job.title || "job"} application`);
      linkCell.append(link);
    }
    if (job.target_review_eligible && job.job_id) {
      if (state.editingJobId === job.job_id) {
        const form = createNode("form", "target-form");
        const input = createNode("input", "target-input");
        input.type = "url";
        input.required = true;
        input.placeholder = "Paste supported ATS application URL";
        input.value = state.targetDraft;
        input.setAttribute("aria-label", `Application URL for ${job.title || "job"}`);
        input.addEventListener("input", () => { state.targetDraft = input.value; });
        const save = createNode("button", "target-save", "Save");
        save.type = "submit";
        const cancel = createNode("button", "target-cancel", "Cancel");
        cancel.type = "button";
        cancel.addEventListener("click", () => {
          state.editingJobId = null;
          state.targetDraft = "";
          renderTable();
        });
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          save.disabled = true;
          await assignTarget(job.job_id);
        });
        form.append(input, save, cancel);
        linkCell.append(form);
      } else {
        const review = createNode("button", "target-review", "Set target");
        review.type = "button";
        review.addEventListener("click", () => {
          state.editingJobId = job.job_id;
          state.targetDraft = "";
          renderTable();
        });
        linkCell.append(review);
      }
    }
    if (job.job_id) {
      const history = createNode("button", "history-open", "History");
      history.type = "button";
      history.addEventListener("click", () => { openReviewHistory(job); });
      linkCell.append(history);
    }

    row.append(
      opportunity,
      createNode("td", "", job.location || "—"),
      fit,
      status,
      method,
      review,
      createNode("td", "", dateLabel(job.date_found)),
      linkCell,
    );
    return row;
  });
  replaceChildren(elements.jobsBody, rows);
}

async function assignTarget(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}/application-target`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ application_url: state.targetDraft }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || payload.reason || "Target could not be saved.");
    state.editingJobId = null;
    state.targetDraft = "";
    elements.reviewNotice.hidden = false;
    elements.reviewNotice.className = "review-notice success";
    elements.reviewNotice.textContent = `Application target saved. Pipeline result: ${label(payload.pipeline_outcome)}. ${payload.reason}`;
    await refresh();
  } catch (error) {
    elements.reviewNotice.hidden = false;
    elements.reviewNotice.className = "review-notice error";
    elements.reviewNotice.textContent = error instanceof Error ? error.message : "Target could not be saved.";
    renderTable();
  }
}

async function submitReviewResolution(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}/review-resolution`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        outcome: state.resolutionOutcome,
        note: state.resolutionNote,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || payload.reason || "Review decision could not be saved.");
    state.resolvingJobId = null;
    state.resolutionNote = "";
    elements.reviewNotice.hidden = false;
    elements.reviewNotice.className = "review-notice success";
    elements.reviewNotice.textContent = `${label(payload.outcome)} review decision saved. ${payload.reason}`;
    await refresh();
  } catch (error) {
    elements.reviewNotice.hidden = false;
    elements.reviewNotice.className = "review-notice error";
    elements.reviewNotice.textContent = error instanceof Error ? error.message : "Review decision could not be saved.";
    renderTable();
  }
}

async function openReviewHistory(job) {
  try {
    const response = await fetch(`/api/jobs/${job.job_id}/review-history`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Review history could not be loaded.");
    state.history = Array.isArray(payload.history) ? payload.history : [];
    state.historyJob = job;
    populateSelect(elements.historyOutcome, [...new Set(state.history.map((item) => item.outcome).filter(Boolean))].sort());
    populateSelect(elements.historyKind, [...new Set(state.history.map((item) => item.review_kind).filter(Boolean))].sort());
    elements.historyJob.textContent = `${job.company || "Unknown company"} — ${job.title || "Untitled role"}`;
    elements.historyPanel.hidden = false;
    renderReviewHistory();
  } catch (error) {
    elements.reviewNotice.hidden = false;
    elements.reviewNotice.className = "review-notice error";
    elements.reviewNotice.textContent = error instanceof Error ? error.message : "Review history could not be loaded.";
  }
}

function renderReviewHistory() {
  const history = state.history.filter((item) => (
    (!elements.historyOutcome.value || item.outcome === elements.historyOutcome.value)
    && (!elements.historyKind.value || item.review_kind === elements.historyKind.value)
  ));
  const rows = history.map((item) => {
    const row = createNode("article", "history-item");
    const heading = createNode("div", "history-item-heading");
    heading.append(
      createNode("span", "review-kind", label(item.outcome)),
      createNode("span", "history-date", dateLabel(item.recorded_at)),
    );
    row.append(
      heading,
      createNode("strong", "history-kind", label(item.review_kind)),
      createNode("p", "history-note", item.note || "No note recorded."),
    );
    return row;
  });
  replaceChildren(
    elements.historyList,
    rows.length ? rows : [createNode("p", "muted", "No matching review decisions.")],
  );
}

function renderStatusBreakdown() {
  const counts = new Map();
  for (const job of state.jobs) counts.set(job.status || "UNKNOWN", (counts.get(job.status || "UNKNOWN") || 0) + 1);
  const maximum = Math.max(1, ...counts.values());
  const rows = [...counts.entries()].sort((left, right) => right[1] - left[1]).map(([status, count]) => {
    const row = createNode("div", "status-row");
    const heading = createNode("div", "status-label");
    heading.append(createNode("span", "", label(status)), createNode("span", "", count));
    const track = createNode("div", "status-track");
    const bar = createNode("div", "status-bar");
    bar.style.width = `${Math.max(3, (count / maximum) * 100)}%`;
    track.append(bar);
    row.append(heading, track);
    return row;
  });
  replaceChildren(elements.statusBreakdown, rows.length ? rows : [createNode("p", "muted", "No jobs yet")]);
}

function renderSource(source) {
  state.source = source;
  elements.workbookName.textContent = source?.name || "";
  elements.syncDot.className = `sync-dot${source?.stale ? " error" : " live"}`;
  elements.syncLabel.textContent = source?.stale ? "Showing saved data" : "Live workbook connected";
  elements.syncDetail.textContent = timeLabel(source?.loaded_at);
  elements.warning.hidden = !source?.warning;
  elements.warning.textContent = source?.warning || "";
}

function showError(message) {
  elements.syncDot.className = "sync-dot error";
  elements.syncLabel.textContent = "Workbook unavailable";
  elements.syncDetail.textContent = "Check the tracker export and try again";
  elements.warning.hidden = false;
  elements.warning.textContent = message;
}

async function refresh() {
  if (state.loading) return;
  state.loading = true;
  elements.refresh.disabled = true;
  try {
    const response = await fetch("/api/jobs", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Dashboard data could not be loaded.");
    state.jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
    renderMetrics(payload.metrics);
    populateSelect(elements.status, payload.facets?.statuses);
    populateSelect(elements.category, payload.facets?.categories);
    populateSelect(elements.method, payload.facets?.methods);
    renderSource(payload.source);
    renderTable();
    renderStatusBreakdown();
  } catch (error) {
    showError(error instanceof Error ? error.message : "Dashboard data could not be loaded.");
  } finally {
    state.loading = false;
    elements.refresh.disabled = false;
  }
}

for (const control of [elements.search, elements.status, elements.category, elements.method, elements.review, elements.sort]) {
  control.addEventListener(control === elements.search ? "input" : "change", renderTable);
}
elements.refresh.addEventListener("click", refresh);
elements.historyOutcome.addEventListener("change", renderReviewHistory);
elements.historyKind.addEventListener("change", renderReviewHistory);
elements.historyClose.addEventListener("click", () => {
  elements.historyPanel.hidden = true;
  state.history = [];
  state.historyJob = null;
});

renderMetrics();
refresh();
setInterval(refresh, 5000);
