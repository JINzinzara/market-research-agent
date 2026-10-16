"use strict";
const $ = (selector) => document.querySelector(selector);
let activeRecord = null;
let activeEvaluation = null;
let previousPriceControls = null;

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

async function checkBackend(needsOpenAI) {
  let status;
  try { status = await api("/api/status"); }
  catch { throw new Error("서버 상태를 확인할 수 없습니다. 기존 서버를 종료하고 저장소에서 PYTHONPATH=src .venv/bin/python -m market_agent serve로 다시 시작해 주세요."); }
  if (status.api_contract !== "research-live-v1") throw new Error("화면과 서버 버전이 다릅니다. 최신 서버를 재시작하고 화면을 새로고침해 주세요.");
  if (needsOpenAI && !status.openai_key_configured) throw new Error("서버에 OPENAI_API_KEY가 없습니다. 키를 export한 같은 터미널에서 서버를 다시 시작해 주세요.");
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
  button.onclick = () => {
    $("#question").value = button.dataset.question;
    $("#web").checked = button.dataset.web === "true";
    $("#web").onchange();
    $("#question").focus();
  };
});
$("#mode").onchange = () => {
  const live = $("#mode").value === "live";
  $("#scenario").disabled = live;
  if (live) $("#scenario").value = "none";
  $("#mode-note").textContent = live
    ? "Binance 공개 시장 API를 실제 호출합니다. 실패한 종목은 데모 값으로 대체하지 않습니다."
    : "합성 시세 · 기준 시각 2026-10-16 00:00 UTC. 실제 시장을 나타내지 않습니다.";
};
$("#web").onchange = () => {
  const web = $("#web").checked;
  if (web) {
    if (!$("#mode").disabled) previousPriceControls = [$("#mode").value, $("#planner").value];
    $("#mode").value = "live"; $("#planner").value = "openai";
  } else if ($("#mode").disabled && previousPriceControls) {
    [$("#mode").value, $("#planner").value] = previousPriceControls;
  }
  $("#mode").disabled = web;
  $("#planner").disabled = web;
  $("#mode").onchange();
  if (web) $("#mode-note").textContent = "실제 웹 검색과 인용 보고서를 요청합니다. OpenAI 키가 필요하며 모델·검색 비용이 발생합니다. 가격 조회는 지원 종목과 기간이 있을 때만 실행합니다.";
};
$("#web").onchange();

$("#research-form").onsubmit = async (event) => {
  event.preventDefault();
  const button = $("#run-button");
  button.disabled = true;
  $("#feedback").textContent = $("#web").checked
    ? "웹에서 뉴스·공식 거시 자료를 조사하고 인용 보고서를 만들고 있습니다…"
    : $("#planner").value !== "baseline"
    ? `${$("#planner").value === "ollama" ? "로컬 Ollama" : "OpenAI GPT-6 Astra"}에 계획을 요청하고 있습니다. 모델 호출 제한은 300초입니다.`
    : "요청을 검증하고 근거를 수집하고 있습니다…";
  try {
    await checkBackend($("#planner").value === "openai");
    const record = await api("/api/research", {
      question: $("#question").value, mode: $("#mode").value,
      planner: $("#planner").value, scenario: $("#scenario").value,
      web: $("#web").checked,
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
  const origin = record.replay_of ? "RECORDED HTTP REPLAY" : record.request.web ? "WEB NEWS & MACRO" : record.request.mode === "demo" ? "SYNTHETIC DEMO" : "LIVE BINANCE API";
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
  $("#failure-notice").textContent = record.failures.map((failure) => `${failure.symbol}: ${failure.type}`).join(" · ") + " — 확인에 실패한 수집 항목의 근거는 제외했습니다.";
  const citations = new Map(result.sources.map((source) => [source.source_id, source]));
  $("#report-text").replaceChildren(...result.answer.split("\n\n").map((paragraph) => {
    const node = element("p");
    for (const part of paragraph.split(/(\[web-\d+\])/g)) {
      const source = citations.get(part.slice(1, -1));
      if (!source || !/^\[web-\d+\]$/.test(part)) { node.append(document.createTextNode(part)); continue; }
      const link = element("a", part);
      const url = new URL(source.url);
      if (["https:", "http:"].includes(url.protocol)) link.href = url.href;
      link.target = "_blank"; link.rel = "noopener noreferrer"; link.title = source.title;
      node.append(link);
    }
    return node;
  }));
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
  $("#execution-summary").textContent = `${record.metrics.http_calls} HTTP · ${record.metrics.llm_calls} LLM${record.replay_of ? " (replayed)" : ""}${record.request.web ? ` · ${record.metrics.web_search_calls} hosted searches · ${record.metrics.citation_count} cited URLs` : ""} · ${record.metrics.duration_ms} ms`;
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
  $("#eval-feedback").textContent = "실제 웹 조사와 인용 결과를 기록하고 있습니다. 모델·검색 비용이 발생하며 답변 정확도는 별도 검토합니다…";
  try {
    await checkBackend(true);
    activeEvaluation = await api("/api/evaluate", {limit: Number($("#benchmark-limit").value)});
    $("#eval-results").hidden = false;
    $("#eval-score").textContent = `${activeEvaluation.operational_completed} / ${activeEvaluation.total} executions · accuracy pending review`;
    const cases = $("#eval-cases"); cases.replaceChildren();
    for (const item of activeEvaluation.cases) {
      const failed = item.run.result.status === "error";
      const row = element("div", undefined, `eval-case${failed ? " failed" : ""}`);
      const label = element("div", item.evaluation_id);
      label.append(element("p", `${item.coverage.cited_hits}/${item.coverage.gold_urls} reference URLs cited`));
      row.append(label, element("span", `${item.run.result.status} · review pending`)); cases.append(row);
    }
    const summary = activeEvaluation.summary;
    $("#eval-feedback").textContent = `${activeEvaluation.evaluated_at} · ${activeEvaluation.suite} · ${activeEvaluation.wall_duration_ms} ms · input ${summary.tokens.input.total ?? "unknown"} / output ${summary.tokens.output.total ?? "unknown"} tokens · 총 비용 미측정 · 의미 평가 검토 대기`;
  } catch (error) { $("#eval-feedback").textContent = `평가 실패: ${error.message}`; }
  finally { button.disabled = false; }
};
