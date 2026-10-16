"use strict";
const $ = (selector) => document.querySelector(selector);
let activeRecord = null;
let activeEvaluation = null;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

function view(name) {
  for (const candidate of ["research", "runs"]) {
    $(`#${candidate}-view`).hidden = candidate !== name;
    $(`#nav-${candidate}`).classList.toggle("active", candidate === name);
    if (candidate === name) $(`#nav-${candidate}`).setAttribute("aria-current", "page");
    else $(`#nav-${candidate}`).removeAttribute("aria-current");
  }
  $("#breadcrumb").textContent = `WORKSPACE / ${name === "research" ? "RESEARCH" : "RUNS & EVALUATION"}`;
  if (name === "runs") loadHistory();
}

$("#nav-research").onclick = () => view("research");
$("#nav-runs").onclick = () => view("runs");
document.querySelectorAll("[data-question]").forEach((button) => {
  button.onclick = () => { $("#question").value = button.dataset.question; $("#question").focus(); };
});
$("#mode").onchange = () => {
  const live = $("#mode").value === "live";
  $("#scenario").disabled = live;
  if (live) $("#scenario").value = "none";
  $("#mode-note").textContent = live
    ? "Binance 공개 시장 API를 실제 호출합니다. 실패한 종목은 데모 값으로 대체하지 않습니다."
    : "합성 시세 · 기준 시각 2026-10-16 00:00 UTC. 실제 시장을 나타내지 않습니다.";
};

$("#research-form").onsubmit = async (event) => {
  event.preventDefault();
  const button = $("#run-button");
  button.disabled = true;
  $("#feedback").textContent = $("#planner").value !== "baseline"
    ? `${$("#planner").value === "ollama" ? "로컬 Ollama" : "OpenAI GPT-6 Astra"}에 계획을 요청하고 있습니다. 모델 호출 제한은 300초입니다.`
    : "요청을 검증하고 근거를 수집하고 있습니다…";
  try {
    const record = await api("/api/research", {
      question: $("#question").value, mode: $("#mode").value,
      planner: $("#planner").value, scenario: $("#scenario").value,
    });
    render(record);
    $("#feedback").textContent = "실행 기록을 저장했습니다. 결과와 누락된 근거를 확인해 주세요.";
  } catch (error) {
    $("#feedback").textContent = `실행 요청 실패: ${error.message}`;
  } finally { button.disabled = false; }
};

function render(record) {
  activeRecord = record;
  const result = record.result;
  $("#empty-state").hidden = true;
  $("#result").hidden = false;
  $("#result-status").textContent = result.status.replaceAll("_", " ");
  $("#result-status").className = `badge ${result.status}`;
  const origin = record.replay_of ? "RECORDED HTTP REPLAY" : record.request.mode === "demo" ? "SYNTHETIC DEMO" : "LIVE BINANCE API";
  $("#run-meta").textContent = `${origin} · ${record.request.planner.toUpperCase()} · as_of ${record.request.as_of} · ${record.run_id.slice(0, 8)}`;
  $("#replay-comparison").hidden = !record.comparison;
  if (record.comparison) $("#replay-comparison").textContent = record.comparison.same_result
    ? "기록된 HTTP 응답으로 현재 코드를 다시 실행했습니다. 시간 메타데이터를 제외한 결과가 같습니다."
    : `재현 실행의 결과가 달라졌습니다: ${record.comparison.original_status} → ${record.comparison.current_status}. 원본과 재현 JSON을 비교해 주세요.`;
  const cards = $("#market-cards"); cards.replaceChildren();
  for (const source of result.sources.filter((source) => source.kind === "market")) {
    const data = JSON.parse(source.content);
    const card = element("article", undefined, "market-card");
    const head = element("header");
    head.append(element("span", data.symbol));
    const negative = data.display_return_pct.startsWith("-");
    card.append(head, element("div", `${negative ? "" : "+"}${data.display_return_pct}%`, `return${negative ? " negative" : ""}`),
      element("small", `${data.open} → ${data.close} USDT`),
      element("p", `${data.start_utc.slice(0, 10)} → ${data.end_utc_exclusive.slice(0, 10)} · UTC · end exclusive`, "interval"));
    cards.append(card);
  }
  $("#failure-notice").hidden = !record.failures.length;
  $("#failure-notice").textContent = record.failures.map((failure) => `${failure.symbol}: ${failure.type}`).join(" · ") + " — 확인에 실패한 종목의 수치는 제외했습니다.";
  $("#report-text").replaceChildren(...result.answer.split("\n\n").map((paragraph) => element("p", paragraph)));
  const library = $("#sources"); library.replaceChildren();
  $("#source-count").textContent = `${result.sources.length} REFERENCES`;
  if (!result.sources.length) library.append(element("p", "수집된 근거가 없습니다.", "subtle"));
  for (const source of result.sources) {
    const item = element("div", undefined, "source-item");
    const link = element("a", `${source.title} ↗`);
    const url = new URL(source.url);
    if (["https:", "http:"].includes(url.protocol)) link.href = url.href;
    link.target = "_blank"; link.rel = "noopener noreferrer";
    item.append(link, element("small", `${source.source_id} · ${source.kind.toUpperCase()}`),
      element("small", `Recorded: ${source.retrieved_at}`));
    if (record.request.mode === "demo" && source.kind === "market") item.append(element("small", "Synthetic response; link shows the intended API request."));
    const details = element("details"); details.append(element("summary", "Inspect evidence"));
    details.append(element("pre", source.kind === "market" ? JSON.stringify(JSON.parse(source.content), null, 2) : source.content));
    item.append(details); library.append(item);
  }
  $("#execution-summary").textContent = `${record.metrics.http_calls} HTTP · ${record.metrics.llm_calls} LLM${record.replay_of ? " (replayed)" : ""} · ${record.metrics.duration_ms} ms`;
  const trace = $("#trace"); trace.replaceChildren();
  record.trace.forEach((event, i) => {
    const row = element("div", undefined, `trace-event${event.error ? " failed" : ""}`);
    const content = element("div");
    content.append(element("strong", event.tool), element("p", event.error
      ? `${event.error.type}: ${event.error.message}`
      : `${JSON.stringify(event.input || event.output)} · ${event.duration_ms ?? "—"} ms`));
    row.append(element("span", String(i + 1).padStart(2, "0"), "trace-index"), content); trace.append(row);
  });
  $("#raw-record").textContent = JSON.stringify(record, null, 2);
  view("research");
}

$("#replay-button").onclick = async () => {
  if (!activeRecord) return;
  const button = $("#replay-button"); button.disabled = true;
  $("#feedback").textContent = "저장한 응답과 오류로 현재 코드를 다시 실행합니다…";
  try {
    render(await api(`/api/runs/${activeRecord.run_id}/replay`, {}));
    $("#feedback").textContent = "재현 실행을 저장했습니다. 원본 기록은 실행 내역에서 확인할 수 있습니다.";
  } catch (error) { $("#feedback").textContent = `재현 실패: ${error.message}`; }
  finally { button.disabled = false; }
};

function download(data, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: "application/json"}));
  const link = element("a"); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("#download-button").onclick = () => activeRecord && download(activeRecord, `run-${activeRecord.run_id}.json`);
$("#download-evaluation").onclick = () => activeEvaluation && download(activeEvaluation, "evaluation.json");

async function loadHistory() {
  const history = $("#history");
  try {
    const records = await api("/api/runs"); history.replaceChildren();
    if (!records.length) history.append(element("p", "아직 저장한 실행이 없습니다. Research에서 첫 조사를 실행해 보세요.", "subtle"));
    for (const record of records) {
      const row = element("div", undefined, "history-row");
      const copy = element("div", undefined, "history-copy");
      copy.append(element("strong", record.request.question), element("small", `${record.started_at} · ${record.replay_of ? "REPLAY" : record.request.mode.toUpperCase()} · ${record.request.planner} · ${record.run_id.slice(0, 8)}`));
      const button = element("button", "Inspect ↗", "text-button");
      button.onclick = async () => {
        try { render(await api(`/api/runs/${record.run_id}`)); $("#feedback").textContent = "저장된 실행 기록을 조회하고 있습니다. 새 실행이 아닙니다."; }
        catch (error) { history.append(element("p", error.message)); }
      };
      row.append(copy, element("span", record.status.replaceAll("_", " "), `badge ${record.status}`), button); history.append(row);
    }
  } catch (error) { history.replaceChildren(element("p", `기록 조회 실패: ${error.message}`)); }
}
$("#refresh-button").onclick = loadHistory;
$("#evaluate-button").onclick = async () => {
  const button = $("#evaluate-button"); button.disabled = true;
  $("#eval-feedback").textContent = "20개 개발용 사례를 실행하고 원시 결과를 저장하고 있습니다…";
  try {
    activeEvaluation = await api("/api/evaluate", {});
    $("#eval-results").hidden = false;
    $("#eval-score").textContent = `${activeEvaluation.passed} / ${activeEvaluation.total} passed`;
    const cases = $("#eval-cases"); cases.replaceChildren();
    for (const item of activeEvaluation.cases) {
      const row = element("div", undefined, `eval-case${item.passed ? "" : " failed"}`);
      const label = element("div", item.case_id);
      if (item.errors.length) label.append(element("p", item.errors.join(" · ")));
      row.append(label, element("span", item.passed ? "PASS" : "FAIL")); cases.append(row);
    }
    $("#eval-feedback").textContent = `${activeEvaluation.evaluated_at} · development-smoke-v1 · 실제 모델 품질 미측정`;
  } catch (error) { $("#eval-feedback").textContent = `평가 실패: ${error.message}`; }
  finally { button.disabled = false; }
};
