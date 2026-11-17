const app = document.querySelector("#app");
const paper = '<span class="badge">PAPER MODE</span>';
const demoEmail = "trader@example.com";
const demoPassword = "WeeklyDemo123!";
const demoCode = "123456";
const limits = { stock: 20, stop: 4, weekly: 3, cash: 10 };
const defaultExecution = { funding: "paper", paperCapital: 25000, cashBuffer: 10, scenarioMove: 5, paperAuto: true };
const defaultConfig = { model: "", objective: "Build a selective weekly delivery basket prioritizing net edge and liquidity.", maxPositions: 5, parameters: [], execution: defaultExecution };
let config = defaultConfig;
try {
  config = { ...defaultConfig, ...JSON.parse(localStorage.getItem("si-trader-strategy-config")) };
  config.execution = { ...defaultExecution, ...config.execution };
} catch {
  // Use defaults when browser storage is unavailable.
}
const state = {
  models: [], committee: null, committeeHoldings: "", evidence: null, fullCatalogue: null, watchlist: null, researchProposal: null, researchObjective: "", plan: null, draft: null, tab: "overview", snapshot: null, syncing: false, brokerError: "",
  view: "signin", busy: false,
  halted: sessionStorage.getItem("si-trader-halted") === "true",
  broker: "Access to be confirmed", message: "", error: false,
};
const money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

function escapeHtml(text) {
  const entities = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(text).replace(/[&<>"']/g, character => entities[character]);
}

function steps(active) {
  return '<div class="steps">' + ["1 Sign in", "2 Authenticator code", "3 Connect broker"]
    .map((step, index) => index === active ? '<strong aria-current="step">' + step + '</strong>' : step)
    .join(" · ") + "</div>";
}

function feedback() {
  if (!state.message) return "";
  const role = state.error ? "alert" : "status";
  return '<p class="message ' + (state.error ? "error" : "") + '" role="' + role + '">' +
    escapeHtml(state.message) + '</p>';
}

function signIn() {
  const mfa = state.view === "mfa";
  return `<main class="sign">
    <section class="hero">
      <div class="brand">Nifty100 WeeklyAlpha</div>
      <h1>Run your weekly Nifty 100 plan inside limits you set.</h1>
      <p>Paper mode by default. Review and approve your weekly basket before recording it as a paper plan.</p>
      ${paper}
    </section>
    <section class="card">
      ${steps(mfa ? 1 : 0)}
      <h1>${mfa ? "Authenticator code" : "Sign in"}</h1>
      <form id="${mfa ? "mfa" : "signin"}">
        ${mfa ? `<label for="code">Six-digit code</label>
          <input id="code" name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required placeholder="000000">
          <button>Continue to broker setup</button>` :
          `<label for="email">Email</label>
          <input id="email" name="email" type="email" autocomplete="off" placeholder="you@example.com" required>
          <label for="password">Password</label>
          <input id="password" name="password" type="password" autocomplete="off" minlength="12" placeholder="At least 12 characters" required>
          <button>Continue to authenticator code</button>`}
      </form>
      <p class="note">Local demo. ${mfa ? "Use demo code <strong>" + demoCode + "</strong>." :
        "Use <strong>" + demoEmail + "</strong> and <strong>" + demoPassword + "</strong>. Enter your broker credentials only on InvestRight."}</p>
      ${feedback()}
    </section>
  </main>`;
}

function row(label, value) {
  return `<div class="row"><span>${label}</span><span>${value}</span></div>`;
}

function broker() {
  const pending = '<span class="badge">Pending</span>';
  return `<main class="page">
    <div class="topline">${steps(2)}${paper}</div>
    <h1>Connect your broker</h1>
    <div class="broker-grid">
      <div class="stack">
        <section class="card">
          <h2>1. Choose your broker</h2>
          ${row("<strong>HDFC Securities · InvestRight</strong>", '<span class="badge">' + escapeHtml(state.broker) + '</span>')}
          ${row("Another broker with a trading API", '<span class="muted">Adapter required</span>')}
        </section>
        <section class="card">
          <h2>2. Sign in on your broker’s own page</h2>
          <p>InvestRight opens in a new tab. To check API access, configure your InvestRight API key and access token in the PowerShell session running SI-Trader.</p>
          <div class="actions">
            <a class="button" href="https://investright.hdfcsec.com/login" target="_blank" rel="noopener noreferrer">Continue to broker login</a>
            <button class="secondary" data-action="verify" ${state.busy ? "disabled" : ""}>${state.busy ? "Checking…" : "Check API access"}</button>
            <button class="secondary" data-action="dashboard" ${state.busy ? "disabled" : ""}>Open paper dashboard</button>
          </div>
          ${feedback()}
        </section>
      </div>
      <section class="card">
        <h2>3. Checks before live trading</h2>
        ${["Static IP registered", "Algo-ID issued", "Trade-only permission", "Daily token refresh"].map(label => row(label, pending)).join("")}
        <p class="note">Live trading is locked in this build.</p>
      </section>
    </div>
  </main>`;
}

function parameterCatalogue(parameters) {
  if (!parameters?.length) return "";
  const enabled = parameters.filter(item => item.enabled);
  const rows = parameters.map(item => `<tr>
    <th scope="row">${escapeHtml(item.label)}</th>
    <td>${item.enabled ? "On" : "Off"}${item.protected ? " · Protected" : ""}</td>
    <td>${escapeHtml(item.role)}</td><td>${escapeHtml(item.weight)}</td>
    <td>${escapeHtml(item.source)}</td><td>${escapeHtml(item.refresh)}</td><td>${escapeHtml(item.availability)}</td>
  </tr>`).join("");
  return `<section>
    <h2>Parameter catalogue</h2>
    <p>${enabled.length} of ${parameters.length} enabled · ${enabled.reduce((sum, item) => sum + item.weight, 0)} weight points.
      Refresh schedules describe intended data updates.</p>
    <div class="catalogue-table" tabindex="0" aria-label="AI parameter catalogue">
      <table><thead><tr><th>Parameter</th><th>Enabled</th><th>Role</th><th>Weight</th><th>Source</th><th>Refresh</th><th>Data status</th></tr></thead>
      <tbody>${rows}</tbody></table>
    </div>
  </section>`;
}

function strategyConfig() {
  const draft = state.draft || config;
  const execution = draft.execution || defaultExecution;
  const options = state.models.map(model =>
    `<option value="${escapeHtml(model)}" ${draft.model === model ? "selected" : ""}>${escapeHtml(model)}</option>`
  ).join("");
  return `<main class="page config-page">
    <div class="topline"><button class="secondary" data-action="dashboard" ${state.busy ? "disabled" : ""}>Back to dashboard</button>${paper}</div>
    <h1>Strategy configuration</h1>
    <form class="card stack" id="config">
      <section>
        <h2>LLM configuration</h2>
        <p>Provider: Ollama (local)</p>
        <label for="model">Model</label>
        <select id="model" name="model" required><option value="">Select an installed model</option>${options}</select>
        <div class="actions"><button type="button" class="secondary" data-action="models" ${state.busy ? "disabled" : ""}>Check Ollama connection</button></div>
      </section>
      <section>
        <h2>AI strategy</h2>
        <label for="objective">Strategy objective</label>
        <textarea id="objective" name="objective" rows="3" maxlength="500" required>${escapeHtml(draft.objective)}</textarea>
        <label for="max-positions">Maximum basket positions</label>
        <input id="max-positions" name="maxPositions" type="number" min="1" max="10" value="${escapeHtml(draft.maxPositions)}" required>
      </section>
      <section>
        <h2>Cash sizing &amp; paper execution</h2>
        <div class="form-grid">
          <label>Capital source<select name="funding">
            <option value="paper" ${execution.funding === "paper" ? "selected" : ""}>Paper capital</option>
            <option value="broker" ${execution.funding === "broker" ? "selected" : ""}>InvestRight available cash</option>
          </select></label>
          <label>Paper capital (₹)<input name="paperCapital" type="number" min="0" max="10000000000" step=".01" value="${escapeHtml(execution.paperCapital)}" required></label>
          <label>Minimum cash buffer (%)<input name="cashBuffer" type="number" min="10" max="90" step=".1" value="${escapeHtml(execution.cashBuffer)}" required></label>
          <label>ROI price scenario (±%)<input name="scenarioMove" type="number" min=".1" max="25" step=".1" value="${escapeHtml(execution.scenarioMove)}" required></label>
        </div>
        <label class="check"><input type="checkbox" name="paperAuto" ${execution.paperAuto ? "checked" : ""}> Simulate fills automatically on every strategy run</label>
        <p class="note">InvestRight cash sizes the simulation. Live order submission is disabled.</p>
      </section>
      <div class="actions">
        <button name="intent" value="generate" ${state.busy || !state.models.length ? "disabled" : ""}>Generate parameters with AI</button>
        <button class="secondary" name="intent" value="save" ${state.busy || !state.models.length ? "disabled" : ""}>Save configuration</button>
      </div>
      ${feedback()}
      ${parameterCatalogue(draft.parameters)}
    </form>
  </main>`;
}

async function loadModels() {
  state.busy = true;
  show("Checking Ollama…");
  try {
    const result = await request("/api/models");
    state.models = result.models;
    show(state.models.length ? "Ollama is connected." : "Ollama is connected. Install a model to generate a strategy.", !state.models.length);
  } catch (error) {
    state.models = [];
    show(error.message, true);
  } finally {
    state.busy = false;
    render();
  }
}

const cash = value => typeof value === "number" && Number.isFinite(value) ? money.format(value) : "—";
const percent = value => typeof value === "number" ? `${value > 0 ? "+" : ""}${value.toFixed(2)}%` : "—";
const count = value => (typeof value === "number" || (typeof value === "string" && value.trim() !== "")) ? escapeHtml(value) : "—";
const tradeTime = value => value ? new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }) : "—";

function brokerValue(key) {
  return state.snapshot?.[key]?.value;
}

function gridTable(columns, rows, empty) {
  return `<div class="desk-table" tabindex="0"><table><thead><tr>${columns.map(item => `<th scope="col">${item}</th>`).join("")}</tr></thead>
    <tbody>${rows.length ? rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("") :
      `<tr><td class="empty" colspan="${columns.length}">${escapeHtml(empty)}</td></tr>`}</tbody></table></div>`;
}

function brokerPanel(key, name, columns, transform) {
  const rows = brokerValue(key);
  const message = state.snapshot?.[key]?.error || state.brokerError || (rows ? "No records returned." : "Waiting for broker data.");
  return `<section class="card desk-card"><div class="desk-card-header"><h2>${name}</h2><span class="muted">${rows ? rows.length + " records" : "Unavailable"}</span></div>
    ${gridTable(columns, (rows || []).map(transform), message)}</section>`;
}

const brokerStock = row => escapeHtml(row.company_name || row.underlying_symbol || row.security_id || row.isin || "—");
const brokerMoney = value => value === null || value === undefined || String(value).trim() === "" ? "—" : cash(Number(String(value).replace(/,/g, "")));

function portfolio() {
  return [
    brokerPanel("holdings", "InvestRight holdings", ["Stock", "Exchange", "Held qty", "Average price", "Close"], item =>
      [brokerStock(item), escapeHtml(item.exchange || "—"), count(item.quantity), brokerMoney(item.average_price), brokerMoney(item.close_price)]),
    brokerPanel("positions", "InvestRight positions", ["Stock", "Product", "Net qty", "Avg. buy", "Realised P/L"], item =>
      [brokerStock(item), escapeHtml(item.product || "—"), count(item.net_qty), brokerMoney(item.average_buy_price), brokerMoney(item.realised_pl_overall_position)]),
  ].join("");
}

function executionView() {
  const run = state.plan?.execution;
  return `<section class="card desk-card">
    <div class="desk-card-header"><h2>Paper fills</h2><span class="desk-tag">Simulation</span></div>
    ${gridTable(["Stock", "Filled qty", "Reference close", "Cash debit", "Status"], (run?.fills || []).map(item =>
      [escapeHtml(item.symbol), count(item.quantity), cash(item.price), cash(item.cashRequired), escapeHtml(item.status)]),
      "No simulated fills for this run.")}
  </section>` + [
    brokerPanel("orders", "InvestRight orders", ["Stock", "Side", "Order qty", "Filled qty", "Average price", "Status", "Time"], item =>
      [brokerStock(item), escapeHtml(item.transaction_type || "—"), count(item.quantity), count(item.filled_quantity),
       brokerMoney(item.average_price), escapeHtml(item.status || "—"), escapeHtml(item.order_timestamp || "—")]),
    brokerPanel("trades", "InvestRight executed trades", ["Stock", "Side", "Qty", "Price", "Time"], item =>
      [brokerStock(item), escapeHtml(item.transaction_type || "—"), count(item.traded_quantity ?? item.trade_quantity ?? item.filled_quantity ?? item.quantity),
       brokerMoney(item.trade_price ?? item.traded_price ?? item.average_price), escapeHtml(item.trade_timestamp || item.order_timestamp || "—")]),
  ].join("");
}

function metric(label, value, detail) {
  return `<section class="card desk-metric"><h2>${label}</h2><strong>${value}</strong><span>${detail}</span></section>`;
}

function overview() {
  const plan = state.plan;
  const run = plan?.execution;
  const market = plan?.market;
  const fills = run?.fills?.length || 0;
  const source = config.execution.funding === "broker" ? "InvestRight cash" : "Paper capital";
  const rows = (plan?.basket || []).map(item => [
    `<strong>${escapeHtml(item.symbol)}</strong><small>${escapeHtml(item.company_name)}</small>`,
    count(item.quantity), cash(item.price), count(item.weight) + "%", cash(item.cashRequired),
    percent(item.scenarioRoi?.[2]), escapeHtml(item.reason),
  ]);
  const scenarios = run?.scenarioRoi || [null, null, null];
  return `
    <div class="desk-metrics">
      ${metric("Available broker cash", cash(brokerValue("funds")), state.snapshot?.funds?.error ? "Broker data unavailable" : "InvestRight cash balance")}
      ${metric("Run budget", cash(run?.budget ?? (config.execution.funding === "paper" ? config.execution.paperCapital : brokerValue("funds"))), run ? (plan.funding === "broker" ? "InvestRight cash" : "Paper capital") : source)}
      ${metric("Estimated cash debit", cash(run?.allocated), run ? cash(run.cashRemaining) + " remains" : "After estimated entry costs")}
      ${metric("Simulated fills", run ? fills : "—", run ? "Reference close • " + tradeTime(run.asOf) : "Appears after a paper run")}
    </div>
    <section class="card desk-run">
      <div><h2>Weekly AI strategy</h2><p>${config.model ? escapeHtml(config.model) + " · " + escapeHtml(source) + " · " + (config.execution.paperAuto ? "Automatic paper fills" : "Preview only") : "Choose a model and capital source in Strategy settings."}</p></div>
      <form id="strategy"><button ${state.busy || state.halted || !config.model ? "disabled" : ""}>${state.busy ? "Running strategy…" : "Run AI strategy"}</button></form>
      ${feedback()}
    </section>
    <div class="desk-analysis">
      <section class="card desk-card desk-basket">
        <div class="desk-card-header"><h2>${plan?.title ? escapeHtml(plan.title) : "Proposed basket"}</h2><span class="desk-tag">Paper</span></div>
        ${plan?.thesis ? `<p class="desk-copy">${escapeHtml(plan.thesis)}</p>` : ""}
        ${gridTable(["Stock", "Buy qty", "NSE close", "Weight", "Cash debit", "Upside ROI", "AI rationale"], rows, "Run the strategy to see cash-sized positions.")}
        ${market ? `<p class="desk-copy note">${escapeHtml(market.source)} · ${escapeHtml(market.asOf)} · ${market.covered}/${market.universeSize} covered.</p>
          <p class="desk-copy note">Live checks pending: ${escapeHtml(market.unverifiedChecks.join(", "))}.</p>` : ""}
      </section>
      <section class="card desk-card roi">
        <div class="desk-card-header"><h2>Modeled ROI</h2></div>
        <p>Net scenarios after estimated costs and taxes.</p>
        ${["Downside", "Flat price", "Upside"].map((label, index) => `<div class="roi-row"><span>${label}
          ${run ? ["−" + run.scenarioMove + "%", "0%", "+" + run.scenarioMove + "%"][index] : ""}</span>
          <strong class="${scenarios[index] < 0 ? "negative" : scenarios[index] > 0 ? "positive" : ""}">${percent(scenarios[index])}</strong>
          <small>${cash(run?.scenarioPnl?.[index])}</small></div>`).join("")}
        <p class="note">Scenario based on price changes you set. It does not predict market returns.</p>
      </section>
    </div>`;
}

async function refreshBroker() {
  if (state.syncing) return;
  state.syncing = true;
  if (state.view === "dashboard") render();
  try {
    state.snapshot = await request("/api/broker");
    state.brokerError = "";
  } catch (error) {
    state.brokerError = error.message;
    state.snapshot = null;
  } finally {
    state.syncing = false;
    if (state.view === "dashboard") render();
  }
}

function builder() {
  const plan = state.researchProposal;
  const labels = {
    quality: "Quality", momentum: "6/12-month momentum", volatility: "Low volatility",
    value: "Value", ownership: "Ownership", earnings_revisions: "Earnings revisions", news_sentiment: "News sentiment",
  };
  return `<section class="card desk-builder">
    <div class="desk-card-header"><h2>Build a monthly research challenger</h2><span class="desk-tag">Research only</span></div>
    <p>One agent proposes factor weights. A second flags test risks. Compare the result to the frozen monthly baseline before using it.</p>
    <form id="strategy-builder" class="stack">
      <label for="research-objective">Research objective</label>
      <textarea id="research-objective" name="objective" rows="3" maxlength="500" required placeholder="Example: Test a stronger quality tilt while maintaining momentum and low-volatility exposure.">${escapeHtml(state.researchObjective)}</textarea>
      <div class="actions"><button ${state.busy || !config.model ? "disabled" : ""}>${state.busy ? "Research agents working…" : "Build research strategy"}</button>
      ${plan ? '<button type="button" class="secondary" data-action="export-research">Export proposal</button>' : ""}</div>
    </form>
    <p class="note">${config.model ? "Model: " + escapeHtml(config.model) : "Select an installed model in Strategy settings."} A verified holdout dataset is required to measure ROI.</p>
    ${feedback()}
    ${plan ? `<div class="builder-result">
      <h2>Test hypothesis</h2><p>${escapeHtml(plan.hypothesis)}</p>
      ${gridTable(["Factor", "Baseline", "AI proposal"], Object.entries(plan.weights).map(([key, weight]) =>
        [escapeHtml(labels[key] || key), count(plan.baseline_weights[key]), count(weight)]), "")}
      <h2>Data availability</h2>
      <ul>${Object.entries(plan.catalogue_status).map(([key, value]) => `<li>${escapeHtml(key)} · ${count(value)}</li>`).join("")}</ul>
      <h2>Reviewer risk checks</h2><ul>${plan.risks.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      <h2>Before interpreting returns</h2><ul>${plan.blockers.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>` : ""}
  </section>`;
}

function watchlistView() {
  const watch = state.watchlist;
  const pending = watch?.parameters.filter(item => item.status === "Feed pending").length;
  const used = watch?.parameters.filter(item => item.weight !== null || item.status === "Used as liquidity filter").length;
  return `<section class="card desk-builder">
    <div class="desk-card-header"><h2>Top 10 Nifty 100 watchlist</h2><span class="desk-tag">Research only</span></div>
    <p>All 48 parameters are listed. The LLM weights only the inputs approved for this research ranking. See Data feeds for additional evidence.</p>
    <form id="watchlist"><button ${state.busy || !config.model ? "disabled" : ""}>${state.busy ? "Refreshing NSE and ranking…" : "Build Top 10 watchlist"}</button></form>
    ${!config.model ? "<p class='note'>Choose an Ollama model in Strategy settings.</p>" : ""}
    ${feedback()}
    ${watch ? `<div class="builder-result">
      <p>NSE close ${escapeHtml(watch.market.asOf)} · ${watch.market.covered}/${watch.market.universeSize} covered ·
      ${used} inputs used · ${pending} excluded from scoring or filtering.</p>
      ${gridTable(["Stock", "Close", "1 session", "5 sessions", "Turnover (₹ cr)", "Score"], watch.stocks.map(item => [
        `<strong>${escapeHtml(item.symbol)}</strong><small>${escapeHtml(item.company)}</small>`,
        cash(item.close), percent(item.daily_change_pct), percent(item.five_session_change_pct), count(item.turnover_crore), count(item.score),
      ]), "No stocks passed the available-data screen.")}
      <p class="note">Risk checks pending: ${escapeHtml(watch.market.unverifiedChecks.join(", "))}. This ranks observed inputs and cannot submit orders.</p>
      <details><summary>All ${watch.parameters.length} requested parameters</summary>
        ${gridTable(["Parameter", "Role", "Status", "Score weight", "Source", "Refresh"], watch.parameters.map(item =>
          [escapeHtml(item.label), escapeHtml(item.role), escapeHtml(item.status), count(item.weight), escapeHtml(item.source), escapeHtml(item.refresh)]), "")}
      </details>
    </div>` : ""}
  </section>`;
}

function evidenceView() {
  const result = state.evidence;
  const observed = result?.parameters.filter(item => item.status === "Observed NSE evidence").length;
  const evidenceRows = result?.parameters.map(item => {
    const sample = item.sample?.[0] || item.importedSample?.[0];
    const source = /^https:\/\//i.test(item.source)
      ? `<a href="${escapeHtml(item.source)}" target="_blank" rel="noopener noreferrer">Source</a>`
      : escapeHtml(item.source);
    return [escapeHtml(item.label), escapeHtml(item.role), escapeHtml(item.status),
      count(item.covered), count(item.imported), count(item.staleImported), escapeHtml(item.refresh), source,
      sample ? `<details><summary>${escapeHtml(sample.symbol)} · ${escapeHtml(sample.asOf.slice(0, 10))}</summary><pre>${escapeHtml(JSON.stringify(sample.value, null, 2))}</pre></details>` : "—"];
  }) || [];
  return `<section class="card desk-feeds">
    <div class="desk-card-header"><h2>Parameter data coverage</h2><span class="desk-tag">Research evidence</span></div>
    <p class="desk-copy">Inspect what each feed supplied. Advisory data stays separate from score weights and veto decisions.</p>
    <div class="actions desk-copy"><button data-action="load-evidence" ${state.busy ? "disabled" : ""}>${state.busy ? "Checking feeds…" : "Refresh data feeds"}</button></div>
    <div class="desk-copy">${feedback()}</div>
    ${result ? `<p class="desk-copy note">NSE close ${escapeHtml(result.market.asOf)} ·
      ${result.parameters.length} catalogue rows · ${observed} supplemental rows with NSE observations.
      The Covered count counts equities with visible evidence. A missing observation gives no risk clearance.</p>
      ${result.localFeedError ? `<p class="desk-copy error" role="alert">${escapeHtml(result.localFeedError)}</p>` : ""}
      ${gridTable(["Parameter", "Role", "Status", "Covered", "Imported", "Stale", "Refresh", "Source", "Example"], evidenceRows, "")}` : ""}
  </section>`;
}

function fullCatalogueView() {
  const result = state.fullCatalogue;
  const stocks = result?.stocks || [];
  return `<section class="card desk-feeds">
    <div class="desk-card-header"><h2>Full 48-parameter screen</h2><span class="desk-tag">Research only</span></div>
    <p class="desk-copy">All 48 parameters need current, typed evidence. Stock-level fields need all 100 constituents.
       The model sees a summary of every parameter. Filters and vetoes are applied before scoring.</p>
    <div class="actions desk-copy">
      <button class="secondary" data-action="catalogue-readiness" ${state.busy ? "disabled" : ""}>Check full catalogue</button>
      <button data-action="full-catalogue" ${state.busy || !result?.ready || !config.model ? "disabled" : ""}>Run full AI screen</button>
    </div>
    <div class="desk-copy">${feedback()}</div>
    ${!config.model ? '<p class="desk-copy note">Select an Ollama model in Strategy settings to run a complete screen.</p>' : ""}
    ${result ? `<p class="desk-copy"><strong>${result.complete}/${result.total} parameters complete</strong> · NSE ${escapeHtml(result.market.asOf)}</p>
      ${result.errors.map(error => `<p class="desk-copy error" role="alert">${escapeHtml(error)}</p>`).join("")}
      ${!result.providerConfigured ? '<p class="desk-copy note">No full-catalogue provider file is configured.</p>' : ""}
      ${result.status === "research_only" ? `<p class="desk-copy">${result.parametersUsed} parameters reviewed by role · ${result.eligibleStocks} stocks passed filters and vetoes.</p>
        ${gridTable(["Stock", "Close", "Research score", "Observed flags"], stocks.map(item =>
          [`<strong>${escapeHtml(item.symbol)}</strong><small>${escapeHtml(item.company)}</small>`, cash(item.close), count(item.score), escapeHtml(item.flags.join(", ") || "—")]), "No stocks passed the full risk screen.")}
        <details class="desk-copy"><summary>Score weights and market dials</summary>
          ${gridTable(["Parameter", "Output"], [
            ...Object.entries(result.weights).map(([key, weight]) => [escapeHtml(key), weight.toFixed(2) + "% weight"]),
            ...Object.entries(result.marketDial).map(([key, value]) => [escapeHtml(key), count(value) + " / 100 — research context"]),
          ], "")}</details>` : ""}
      ${gridTable(["Parameter", "Role", "Coverage", "Stale", "Invalid", "Required value"], result.parameters.map(item => [
        escapeHtml(item.label), escapeHtml(item.role), `${item.available}/${item.expected} · ${item.ready ? "Ready" : "Missing or invalid"}`,
        count(item.stale), count(item.invalid), escapeHtml(item.contract),
      ]), "")}` : ""}
  </section>`;
}

async function loadFullCatalogue(run) {
  if (state.busy) return;
  state.busy = true;
  show(run ? "Verifying all inputs, then running the AI screen." : "Checking all 48 parameters.");
  try {
    state.fullCatalogue = await request(run ? "/api/full-catalogue" : "/api/catalogue-readiness",
      run ? {model: config.model, objective: config.objective} : undefined);
    const result = state.fullCatalogue;
    show(result.ready
      ? (run ? "Full research screen complete. Trade submission is unavailable." : "All 48 inputs meet the data contract.")
      : "Full run blocked until every parameter has usable data.");
  } catch (error) {
    state.fullCatalogue = null;
    show(error.message, true);
  } finally {
    state.busy = false;
    render();
  }
}

function committeeView() {
  const result = state.committee;
  const list = values => escapeHtml(values.join(", ") || "None");
  return `<section class="card desk-feeds">
    <div class="desk-card-header"><h2>Maker, Checker &amp; Umpire</h2><span class="desk-tag">Research only</span></div>
    <p class="desk-copy">Get a second opinion on the shortlist. Partial evidence supports research only. Investment sizing and orders are unavailable.</p>
    <form id="research-committee" class="desk-copy">
      <label for="committee-holdings">Held NSE symbols for exit review (optional)</label>
      <input id="committee-holdings" name="holdings" value="${escapeHtml(state.committeeHoldings)}" placeholder="Comma-separated NSE symbols">
      <div class="actions"><button ${state.busy || !config.model ? "disabled" : ""}>${state.busy ? "Agents reviewing…" : "Run three-agent review"}</button></div>
    </form>
    ${!config.model ? '<p class="desk-copy note">Select a model in Strategy settings.</p>' : ""}
    <div class="desk-copy">${feedback()}</div>
    ${result ? `<div class="builder-result">
      <p class="desk-copy"><strong>${result.complete}/${result.total} parameters complete</strong> · NSE ${escapeHtml(result.market.asOf)}</p>
      ${result.dataErrors.map(error => `<p class="desk-copy error">${escapeHtml(error)}</p>`).join("")}
      <p class="desk-copy"><strong>Maker shortlist</strong> · ${list(result.maker)}</p>
      <p class="desk-copy"><strong>Checker exclusions</strong> · ${list(result.checkerAvoids)}${result.checkerRejectedStrategy ? " · Checker rejected the research shortlist" : ""}</p>
      <p class="desk-copy"><strong>Downside scenarios</strong> · ${list(result.scenarios)}</p>
      <p class="desk-copy"><strong>Umpire research priorities</strong></p>
      ${gridTable(["Stock", "Close", "1 session", "5 sessions", "Research weight", "Unverified risk checks"],
        result.researchPriorities.map(item => [escapeHtml(item.symbol), cash(item.close), percent(item.daily_pct),
          percent(item.five_session_pct), count(item.research_weight_pct) + "%", count(item.missing_risk_count)]), "No priorities passed reconciliation.")}
      <p class="desk-copy"><strong>Held stocks flagged for exit review</strong></p>
      ${gridTable(["Stock", "Review reason", "Known failures"], result.reviewExits.map(item =>
        [escapeHtml(item.symbol), escapeHtml(item.reason), list(item.knownFailures)]), "No held stocks flagged.")}
      ${result.outsideUniverseHoldings.length ? `<p class="desk-copy note">Outside current Nifty 100 coverage: ${list(result.outsideUniverseHoldings)}.</p>` : ""}
      <p class="desk-copy note">Weights are research priorities. They are not proposed order sizes.</p>
    </div>` : ""}
  </section>`;
}

function dashboard() {
  const tabs = [["overview", "Strategy overview"], ["builder", "AI strategy builder"], ["watchlist", "Top 10 watchlist"], ["feeds", "Data feeds"], ["full", "Full 48 research"], ["committee", "Three-agent review"], ["portfolio", "Holdings & positions"], ["execution", "Execution"]];
  const linked = state.snapshot && ["funds", "holdings", "positions", "orders", "trades"].some(key => state.snapshot[key]?.value !== undefined);
  return `<div class="desk">
    <aside class="desk-nav">
      <div class="desk-brand"><span aria-hidden="true">W</span><div>WeeklyAlpha<small>Nifty 100 workspace</small></div></div>
      <nav aria-label="Trading workspace">
        ${tabs.map(([key, label]) => `<button data-action="tab" data-tab="${key}" ${state.tab === key ? 'aria-current="page"' : ""}>${label}</button>`).join("")}
        <button data-action="config" ${state.busy ? "disabled" : ""}>Strategy settings</button>
      </nav>
      <div class="desk-nav-status">${paper}<small>InvestRight · Read-only</small></div>
    </aside>
    <main class="desk-main">
      <header class="desk-header">
        <div><h1>${tabs.find(([key]) => key === state.tab)[1]}</h1>
          <p><span class="connection-dot ${linked ? "connected" : ""}"></span>
            ${linked ? "InvestRight snapshot · " + tradeTime(state.snapshot.asOf) + " IST" : "InvestRight data unavailable"} · refreshes every 30 s</p></div>
        <div class="actions">
          <button class="secondary" data-action="refresh" ${state.syncing ? "disabled" : ""}>${state.syncing ? "Syncing…" : "Refresh broker"}</button>
          <button class="${state.halted ? "secondary" : "danger"}" data-action="${state.halted ? "resume" : "halt"}">${state.halted ? "Reset kill switch" : "Kill switch"}</button>
        </div>
      </header>
      ${state.tab === "portfolio" ? portfolio() : state.tab === "execution" ? executionView() : state.tab === "builder" ? builder() : state.tab === "watchlist" ? watchlistView() : state.tab === "feeds" ? evidenceView() : state.tab === "full" ? fullCatalogueView() : state.tab === "committee" ? committeeView() : overview()}
    </main>
  </div>`;
}

setInterval(() => {
  if (state.view === "dashboard" && state.tab !== "builder" && !document.hidden) refreshBroker();
}, 30000);

function render() {
  app.innerHTML = state.view === "config" ? strategyConfig() : state.view === "dashboard" ? dashboard() : state.view === "broker" ? broker() : signIn();
}

function show(message = "", error = false) {
  state.message = message;
  state.error = error;
  render();
}

async function request(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The local request failed.");
  return result;
}

app.addEventListener("input", event => {
  if (event.target.id === "research-objective") state.researchObjective = event.target.value;
  if (event.target.id === "committee-holdings") state.committeeHoldings = event.target.value;
});

app.addEventListener("submit", async event => {
  event.preventDefault();
  const form = new FormData(event.target);
  if (event.target.id === "signin") {
    if (form.get("email") !== demoEmail || form.get("password") !== demoPassword) {
      show("Use the local demo credentials shown below the form.", true);
      return;
    }
    state.view = "mfa";
    show();
    document.querySelector("#code").focus();
  } else if (event.target.id === "mfa") {
    if (form.get("code") !== demoCode) {
      show("Enter the displayed demo code to continue.", true);
      document.querySelector("#code").focus();
      return;
    }
    state.view = "broker";
    show();
  } else if (event.target.id === "research-committee" && !state.busy && config.model) {
    const holdings = form.get("holdings").split(",").map(item => item.trim().toUpperCase()).filter(Boolean);
    state.busy = true;
    state.committee = null;
    show("Maker, Checker and Umpire are reviewing in sequence. This may take a few minutes.");
    try {
      state.committee = await request("/api/research-committee", {model: config.model, objective: config.objective, holdings});
      show("Three-agent review complete.");
    } catch (error) {
      show(error.message, true);
    } finally {
      state.busy = false;
      render();
    }
  } else if (event.target.id === "watchlist" && !state.busy && config.model) {
    state.busy = true;
    state.watchlist = null;
    show("Fetching published NSE data and choosing ranking weights.");
    try {
      state.watchlist = await request("/api/watchlist", {model: config.model, objective: config.objective});
      show(`Ranked ${state.watchlist.stocks.length} stocks using the connected inputs.`);
    } catch (error) {
      show(error.message, true);
    } finally {
      state.busy = false;
      render();
    }
  } else if (event.target.id === "strategy-builder" && !state.busy && config.model) {
    state.researchObjective = form.get("objective").trim();
    if (!state.researchObjective) {
      show("Enter a research objective.", true);
      return;
    }
    state.busy = true;
    state.researchProposal = null;
    show("Generating a proposal, then running the second-agent review.");
    try {
      state.researchProposal = await request("/api/strategy-builder", {
        model: config.model, objective: state.researchObjective,
      });
      show("Research proposal ready. Export it for matched backtests.");
    } catch (error) {
      show(error.message, true);
    } finally {
      state.busy = false;
      render();
    }
  } else if (event.target.id === "config" && !state.busy) {
    const model = form.get("model");
    const objective = form.get("objective").trim();
    if (!state.models.includes(model) || !objective) {
      show("Select an installed model and enter a strategy objective.", true);
      return;
    }
    const prior = state.draft || config;
    const execution = {
      funding: form.get("funding"), paperCapital: Number(form.get("paperCapital")),
      cashBuffer: Number(form.get("cashBuffer")), scenarioMove: Number(form.get("scenarioMove")),
      paperAuto: form.get("paperAuto") === "on",
    };
    const settings = { model, objective, maxPositions: Number(form.get("maxPositions")), execution };
    if (event.submitter?.value === "generate") {
      state.draft = { ...settings, parameters: [] };
      state.busy = true;
      show("Generating the parameter catalogue. This can take a few minutes.");
      try {
        const result = await request("/api/parameters", settings);
        state.draft.parameters = result.parameters;
        show("AI catalogue generated. Review it, then save the configuration.");
      } catch (error) {
        show(error.message, true);
      } finally {
        state.busy = false;
        render();
      }
      return;
    }
    const matching = prior.model === model && prior.objective === objective;
    config = { ...settings, parameters: matching ? prior.parameters : [] };
    localStorage.setItem("si-trader-strategy-config", JSON.stringify(config));
    state.draft = null;
    state.tab = "overview";
    state.view = "dashboard";
    show("AI strategy configuration saved.");
  } else if (event.target.id === "strategy" && !state.busy && !state.halted && config.model) {
    state.busy = true;
    show("Fetching NSE data, generating the basket, and sizing it to available cash.");
    try {
      const result = await request("/api/strategy", config);
      if (state.halted) return;
      state.plan = result;
      config.parameters = result.parameters;
      localStorage.setItem("si-trader-strategy-config", JSON.stringify(config));
      state.message = result.message || (result.execution.fills.length
        ? `${result.execution.fills.length} simulated fills. View the fill details in Execution.`
        : `${result.basket.length} candidates sized. No paper fills recorded.`);
    } catch (error) {
      if (!state.halted) {
        state.message = error.message;
        state.error = true;
      }
    } finally {
      state.busy = false;
      render();
    }
  }
});

app.addEventListener("click", async event => {
  const action = event.target.closest("[data-action]")?.dataset.action;
  switch (action) {
    case "catalogue-readiness":
      await loadFullCatalogue(false);
      break;
    case "full-catalogue":
      if (state.fullCatalogue?.ready && config.model) await loadFullCatalogue(true);
      break;
    case "load-evidence":
      if (state.busy) break;
      state.busy = true;
      show("Checking open NSE sources and configured local evidence.");
      try {
        state.evidence = await request("/api/catalogue-evidence");
        show("Feed coverage refreshed.");
      } catch (error) {
        state.evidence = null;
        show(error.message, true);
      } finally {
        state.busy = false;
        render();
      }
      break;
    case "export-research": {
      if (!state.researchProposal) break;
      const url = URL.createObjectURL(new Blob([JSON.stringify(state.researchProposal, null, 2)], {type: "application/json"}));
      const link = document.createElement("a");
      link.href = url;
      link.download = "monthly-challenger.json";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      break;
    }
    case "config":
      state.draft = null;
      state.view = "config";
      await loadModels();
      break;
    case "models":
      await loadModels();
      break;
    case "dashboard":
      state.view = "dashboard";
      show();
      if (!state.snapshot) refreshBroker();
      break;
    case "tab":
      state.tab = event.target.closest("[data-tab]").dataset.tab;
      render();
      break;
    case "refresh":
      await refreshBroker();
      break;
    case "verify":
      if (state.busy) return;
      state.busy = true;
      show();
      try {
        const result = await request("/api/holdings");
        state.broker = "Read-only access verified";
        state.message = `InvestRight returned ${result.count} holdings.`;
      } catch (error) {
        state.broker = "Access to be confirmed";
        state.message = error.message;
        state.error = true;
      } finally {
        state.busy = false;
        render();
      }
      break;
    case "halt":
      state.halted = true;
      sessionStorage.setItem("si-trader-halted", "true");
      show("Paper strategy runs are paused in this tab.");
      break;
    case "resume":
      if (state.busy) return;
      state.halted = false;
      sessionStorage.removeItem("si-trader-halted");
      show("Paper dashboard controls restored.");
      break;

  }
});

render();
