const form = document.querySelector("#analysis-form");
const urlInput = document.querySelector("#site-url");
const analyzeButton = document.querySelector("#analyze");
const exampleButton = document.querySelector("#example");
const status = document.querySelector("#status");
const report = document.querySelector("#report");

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function panel(title, wide = false) {
  const section = element("section", undefined, wide ? "panel full" : "panel");
  section.append(element("h3", title));
  return section;
}

function field(target, label, value) {
  const items = Array.isArray(value) ? value : [value];
  if (!items.length) return;
  target.append(element("dt", label));
  if (items.length === 1) {
    target.append(element("dd", items[0]));
    return;
  }
  const values = element("dd");
  const list = element("ul");
  items.forEach((item) => list.append(element("li", item)));
  values.append(list);
  target.append(values);
}

function sourceLink(url, label) {
  const link = element("a", label, "source-link");
  const parsed = new URL(url);
  if (["https:", "http:"].includes(parsed.protocol)) {
    link.href = parsed.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
  return link;
}

function citations(parent, ids, evidence) {
  for (const id of ids) {
    const passage = evidence.get(id);
    if (!passage) continue;
    const link = element("a", id, "citation");
    link.href = "#" + passage.id;
    link.setAttribute("aria-label", "Read evidence " + id);
    link.addEventListener("click", () => {
      passage.open = true;
    });
    parent.append(link);
  }
}

function downloadReport(data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const location = URL.createObjectURL(blob);
  const link = element("a");
  link.href = location;
  link.download = "sitelens-report.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(location), 1000);
}

function showReport(data, isExample) {
  const analysis = data.analysis;
  const evidencePanel = panel("Source evidence", true);
  const evidence = new Map();
  if (isExample) evidencePanel.append(element("p", "Passages in this recorded example are shortened."));
  Object.entries(data.evidence).forEach(([id, text], index) => {
    const passage = element("details");
    passage.id = "passage-" + index;
    passage.append(element("summary", id), element("p", text));
    evidencePanel.append(passage);
    evidence.set(id, passage);
  });

  const heading = element("header", undefined, "report-head");
  const title = element("h2", data.brand.name);
  title.tabIndex = -1;
  const download = element("button", "Download JSON", "button text-button");
  download.type = "button";
  download.addEventListener("click", () => downloadReport(data));
  heading.append(
    element("p", isExample ? "Recorded example" : "Live analysis", "label"),
    title,
    sourceLink(data.source_url, data.source_url),
    element("p", data.brand.category + " · " + data.brand.summary),
  );
  citations(heading, data.brand.evidence_ids, evidence);
  const actions = element("div");
  actions.append(download);
  heading.append(actions);

  const grid = element("div", undefined, "grid");
  const seo = panel("SEO recommendations");
  const seoFields = element("dl");
  field(seoFields, "Suggested title", analysis.seo_improvements.recommended_title);
  field(seoFields, "Meta description", analysis.seo_improvements.meta_description);
  field(seoFields, "Primary keyword", analysis.seo_improvements.primary_keyword);
  field(seoFields, "Secondary keywords", analysis.seo_improvements.secondary_keywords);
  field(seoFields, "Content ideas", analysis.seo_improvements.supporting_content);
  seo.append(seoFields);

  const audience = panel("Suggested audience");
  const audienceFields = element("dl");
  field(audienceFields, "Primary", analysis.target_audience.primary);
  field(audienceFields, "Secondary", analysis.target_audience.secondary);
  field(audienceFields, "Needs", analysis.target_audience.customer_needs);
  if (audienceFields.childElementCount) audience.append(audienceFields);
  else audience.append(element("p", "The report did not identify a clear audience from this page."));

  const search = panel("Search suggestions");
  for (const query of analysis.target_search_queries) {
    const item = element("article", undefined, "item");
    item.append(
      element("h4", query.platform),
      element("p", query.query),
      element("p", query.intent + " · " + query.audience),
    );
    search.append(item);
  }

  const services = panel("Services found");
  if (!analysis.top_services.length) {
    services.append(element("p", "No services had enough evidence on this page."));
  }
  for (const service of analysis.top_services) {
    const item = element("article", undefined, "item");
    const fields = element("dl");
    field(fields, "For", service.target_customer);
    field(fields, "Benefit", service.benefit);
    item.append(element("h4", service.name), element("p", service.description), fields);
    if (service.evidence_quote) item.append(element("q", service.evidence_quote));
    const links = element("div");
    citations(links, service.evidence_ids, evidence);
    item.append(links);
    services.append(item);
  }
  data.warnings.forEach((warning) => services.append(element("p", warning)));

  const competitors = panel("Competitor comparison", true);
  competitors.append(element("p", analysis.competitor_analysis.note));
  for (const peer of analysis.competitor_analysis.competitors) {
    const item = element("article", undefined, "item");
    const name = element("h4");
    name.append(sourceLink(peer.source_url, peer.name));
    item.append(name, element("p", peer.strength), element("p", peer.positioning));
    competitors.append(item);
  }

  grid.append(seo, audience, search, services, competitors, evidencePanel);
  report.replaceChildren(heading, grid, element("p", data.interpretation));
  report.hidden = false;
  title.focus();
}

function setStatus(message, state = "") {
  status.className = state ? "status " + state : "status";
  status.textContent = message;
  status.hidden = !message;
}

async function requestReport(example, url) {
  setStatus(example ? "Opening the recorded example…" : "Reading the page and building your report…", "loading");
  report.hidden = true;
  form.setAttribute("aria-busy", "true");
  analyzeButton.disabled = true;
  exampleButton.disabled = true;
  try {
    const response = example
      ? await fetch("/example-report", { signal: AbortSignal.timeout(20000) })
      : await fetch("/link-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
        signal: AbortSignal.timeout(210000),
      });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body?.success) {
      const message = typeof body?.detail === "string" ? body.detail : "The report could not be loaded.";
      throw new Error(message);
    }
    showReport(body, example);
    setStatus(example ? "Example report loaded." : "Analysis complete.");
  } catch (error) {
    const message = error.name === "TimeoutError"
      ? "The report took too long. Try again or view the example."
      : error.message;
    setStatus(message, "error");
  } finally {
    form.removeAttribute("aria-busy");
    analyzeButton.disabled = false;
    exampleButton.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!/^https?:\/\//i.test(url)) {
    setStatus("Enter a full website URL starting with https:// or http://.", "error");
    urlInput.focus();
    return;
  }
  requestReport(false, url);
});
exampleButton.addEventListener("click", () => requestReport(true));
