const app = document.querySelector("#app");
const paper = '<span class="badge">PAPER MODE</span>';
const demoEmail = "trader@example.com";
const demoPassword = "WeeklyDemo123!";
const demoCode = "123456";
const limits = { stock: 20, stop: 4, weekly: 3, cash: 10 };
const defaultExecution = { funding: "paper", paperCapital: 25000, cashBuffer: 10, scenarioMove: 5, paperAuto: true };
const defaultConfig = { model: "", objective: "Build a selective weekly delivery basket prioritizing net edge and liquidity.", maxPositions: 5, execution: defaultExecution };
let config = defaultConfig;
try {
  config = { ...defaultConfig, ...JSON.parse(localStorage.getItem("si-trader-strategy-config")) };
  config.execution = { ...defaultExecution, ...config.execution };
} catch {
  // Use defaults when browser storage is unavailable.
}
const state = {
  parameterPreview: null, parameterSymbol: "", parameterReportMessage: "", preferParameterPreview: false,
  replayInputs: {bundleId: "", decision: "", isin: ""}, replayResult: null, replayMessage: "", replayError: false,
  monthlyInputs: {start: "", end: "", capital: 1000000, includeAI: false, testPriceInputs: false, bundleId: ""}, monthlyResult: null, monthlyFeedback: "", monthlyError: false,
  models: [], lab: null, labResult: null, labSymbol: "", labHorizon: 10, committee: null, committeeHoldings: "", evidence: null, fullCatalogue: null, watchlist: null, researchProposal: null, researchObjective: "", plan: null, tab: "home", snapshot: null, syncing: false, brokerError: "",
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
      <h1>Build and test Nifty 100 strategies.</h1>
      <p>Run weekly strategies with simulated fills, or test a monthly strategy against historical data.</p>
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

function strategyConfig() {
  const draft = config;
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
        <button ${state.busy || !state.models.length ? "disabled" : ""}>Save configuration</button>
        <p class="note">Weekly evaluates all 48 catalogue parameters by role. See Weekly for the evidence and ranking weights.</p>
      </div>
      ${feedback()}
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

function home() {
  return `<div class="desk-strategy-cards">
    <section class="card">
      <h2>Weekly strategy</h2>
      <p>Generate a cash-sized Nifty 100 basket and review the simulated fills.</p>
      <p class="note">${config.model ? "Model selected · " + escapeHtml(config.model) : "Setup required · Select an Ollama model"}</p>
      <button data-action="tab" data-tab="weekly">Open weekly strategy</button>
    </section>
    <section class="card">
      <h2>Monthly strategy</h2>
      <p>Generate an AI factor proposal and compare it with the fixed and defensive strategies.</p>
      <p class="note">Historical backtests require a point-in-time research bundle.</p>
      <button data-action="tab" data-tab="monthly">Open monthly strategy</button>
    </section>
  </div>`;
}

function parameterRunPanel(report) {
  const selected = state.preferParameterPreview ? state.parameterPreview || report : report || state.parameterPreview;
  const symbol = selected?.symbols.includes(state.parameterSymbol) ? state.parameterSymbol : "";
  const labels = {preview: "Evidence preview", weekly: "Weekly paper run", monthly: "Monthly proposal"};
  const evidenceLink = (url, label) => url.startsWith("https://")
    ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
    : escapeHtml(label);
  return `<section class="card desk-card parameter-run">
    <div class="desk-card-header"><h2>48-Parameter Run Report</h2>
      <span class="desk-tag">${selected ? labels[selected.mode] : "Evidence"}</span></div>
    <div class="desk-copy">
      <p>Review which inputs affected this strategy and which observations are still missing.</p>
      <div class="actions"><button class="secondary" data-action="parameter-preview" ${state.busy ? "disabled" : ""}>Refresh evidence preview</button>
        ${report && state.preferParameterPreview ? '<button class="secondary" data-action="parameter-run">Show strategy run report</button>' : ""}</div>
      ${state.parameterReportMessage ? `<p role="status">${escapeHtml(state.parameterReportMessage)}</p>` : ""}
      ${selected ? `<p><strong>${count(selected.complete)}/${count(selected.total)} complete</strong> · NSE close ${escapeHtml(selected.marketAsOf)}</p>` : ""}
      ${selected?.mode === "monthly" ? '<p class="note">These observations informed the proposal. The backtest reads its own dated historical bundle.</p>' : ""}
      ${selected?.mode === "weekly" ? '<p class="note">Known failed checks exclude stocks. Missing observations remain unknown in this paper simulation.</p>' : ""}
      ${selected?.symbols.length ? `<label for="parameter-symbol">Inspect a basket stock</label>
        <select id="parameter-symbol"><option value="">Nifty 100 coverage</option>${selected.symbols.map(name =>
          `<option value="${escapeHtml(name)}" ${symbol === name ? "selected" : ""}>${escapeHtml(name)}</option>`).join("")}</select>` : ""}
      ${selected?.errors.map(issue => `<p class="note">${escapeHtml(issue)}</p>`).join("") || ""}
    </div>
    ${selected ? `<details class="desk-copy"><summary>Provider retrieval</summary>
      ${gridTable(["Provider", "Status", "Observations"], selected.sourceFeeds.map(item =>
        [escapeHtml(item.name), escapeHtml(item.status), count(item.observations)]), "No provider status is available.")}</details>
      <details class="desk-copy" open><summary>Parameter details</summary>
        ${gridTable(["Parameter", "Role", "Strategy use", "Coverage", "Issues", "Latest evidence", "Sources"], selected.rows.map(item => {
          const observation = item.stockEvidence[symbol];
          const issues = [[item.unknown, "unknown"], [item.stale, "stale"], [item.invalid, "invalid"], [item.conflicts, "conflicts"]]
            .filter(([total]) => total > 0).map(([total, label]) => count(total) + " " + label).join(" · ");
          const use = item.use + (item.weight === null ? "" : " · weight " + item.weight)
            + (item.excludedStocks ? " · " + item.excludedStocks + " excluded" : "");
          return [escapeHtml(item.label), escapeHtml(item.role), escapeHtml(use), count(item.available) + "/" + count(item.expected),
            issues || "—", symbol ? (observation ? escapeHtml(String(observation.value)) + " · " + escapeHtml(observation.asOf)
              + (observation.outcome ? " · " + escapeHtml(observation.outcome) : "") : "Unknown for this stock") : count(item.latestObservation),
            observation ? evidenceLink(observation.source, "Open source") : item.sources.map((url, index) => evidenceLink(url, url.startsWith("https://") ? "Source " + (index + 1) : url)).join(" · ") || "—"];
        }), "")}
      </details>` : ""}
  </section>`;
}

function weekly() {
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
      <form id="strategy"><button ${state.busy || state.halted || !config.model ? "disabled" : ""}>${state.busy ? "Running strategy…" : "Run weekly strategy"}</button></form>
      ${!config.model ? '<div class="actions"><button class="secondary" data-action="config">Set up Ollama model</button></div>' : ""}
      ${state.halted ? '<p role="status">Weekly paper runs are paused. Select Reset kill switch to continue.</p>' : ""}
      ${plan ? `<p class="note">Maximum paper exposure after market dials · ${count(plan.maximumPaperExposurePct)}%</p>` : ""}
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
        <div class="desk-card-header"><h2>Price-move scenario</h2></div>
        <p>Net scenarios after estimated costs and taxes.</p>
        ${["Downside", "Flat price", "Upside"].map((label, index) => `<div class="roi-row"><span>${label}
          ${run ? ["−" + run.scenarioMove + "%", "0%", "+" + run.scenarioMove + "%"][index] : ""}</span>
          <strong class="${scenarios[index] < 0 ? "negative" : scenarios[index] > 0 ? "positive" : ""}">${percent(scenarios[index])}</strong>
          <small>${cash(run?.scenarioPnl?.[index])}</small></div>`).join("")}
        <p class="note">Scenario based on price changes you set. It does not predict market returns.</p>
      </section>
    </div>
    ${parameterRunPanel(plan?.parameterRunReport)}`;
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
    <div class="desk-card-header"><h2>AI factor proposal</h2><span class="desk-tag">Research only</span></div>
    <p>One agent proposes factor weights. A second flags test risks. Compare the result to the frozen monthly baseline before using it.</p>
    <form id="strategy-builder" class="stack">
      <label for="research-objective">Research objective</label>
      <textarea id="research-objective" name="objective" rows="3" maxlength="500" required placeholder="Example: Test a stronger quality tilt while maintaining momentum and low-volatility exposure.">${escapeHtml(state.researchObjective)}</textarea>
      <div class="actions"><button ${state.busy || !config.model ? "disabled" : ""}>${state.busy ? "Research agents working…" : "Generate monthly proposal"}</button>
      ${plan ? '<button type="button" class="secondary" data-action="export-research">Export proposal</button>' : ""}</div>
    </form>
    <p class="note">${config.model ? "Model: " + escapeHtml(config.model) : "Select an installed model to generate a proposal."}</p>
    ${!config.model ? '<button class="secondary" data-action="config">Set up Ollama model</button>' : ""}
    ${feedback()}
    ${plan ? `<div class="builder-result">
      <h2>Test hypothesis</h2><p>${escapeHtml(plan.hypothesis)}</p>
      ${gridTable(["Factor", "Baseline", "AI proposal"], Object.entries(plan.weights).map(([key, weight]) =>
        [escapeHtml(labels[key] || key), count(plan.baseline_weights[key]), count(weight)]), "")}
      <h2>Data availability</h2><p>Evidence at NSE close ${escapeHtml(plan.evidence_as_of)}</p>
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
    <div class="actions desk-copy"><button data-action="load-evidence" ${state.busy ? "disabled" : ""}>${state.busy ? "Checking feeds…" : "Refresh data feeds"}</button><button class="secondary" data-action="tab" data-tab="full">Inspect full catalogue coverage</button></div>
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
      ${!result.providerConfigured ? '<p class="desk-copy note">No additional evidence source is configured.</p>' : ""}
      ${result.status === "research_only" ? `<p class="desk-copy">${result.parametersUsed} parameters reviewed by role · ${result.eligibleStocks} stocks passed filters and vetoes.</p>
        ${gridTable(["Stock", "Close", "Research score", "Observed flags"], stocks.map(item =>
          [`<strong>${escapeHtml(item.symbol)}</strong><small>${escapeHtml(item.company)}</small>`, cash(item.close), count(item.score), escapeHtml(item.flags.join(", ") || "—")]), "No stocks passed the full risk screen.")}
        <details class="desk-copy"><summary>Score weights and market dials</summary>
          ${gridTable(["Parameter", "Output"], [
            ...Object.entries(result.weights).map(([key, weight]) => [escapeHtml(key), weight.toFixed(2) + "% weight"]),
            ...Object.entries(result.marketDial).map(([key, value]) => [escapeHtml(key), count(value) + " / 100 — research context"]),
          ], "")}</details>` : ""}
      ${result.sourceFeeds?.length ? gridTable(["Provider", "Retrieval", "Observations"], result.sourceFeeds.map(feed =>
        [escapeHtml(feed.name), escapeHtml(feed.status), count(feed.observations)]), "") : ""}
      ${gridTable(["Parameter", "Role", "Coverage", "Stale", "Invalid", "Conflicts", "Latest dated evidence", "Required value", "Sources"], result.parameters.map(item => [
        escapeHtml(item.label), escapeHtml(item.role), `${item.available}/${item.expected} · ${item.ready ? "Ready" : "Missing or invalid"}`,
        count(item.stale), count(item.invalid), count(item.conflicts), count(item.latestObservation), escapeHtml(item.contract),
        escapeHtml(item.sources.join(", ") || "—"),
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

function monthlyComparison() {
  const inputs = state.monthlyInputs;
  const result = state.monthlyResult;
  const comparisons = result?.comparisons;
  const first = comparisons?.[0];
  const recovery = downside => downside.worst_drawdown_to_recovery_sessions ?? "Unrecovered";
  const labels = {monthly_defensive: "Defensive trend", monthly_challenger: "AI factor challenger",
    monthly_sector_momentum: "Sector-relative momentum", monthly_downside_risk: "Downside beta and gap risk",
    monthly_trade_capacity: "Trade-capacity buy cap"};
  const hitRate = (outcomes, horizon) => {
    const item = outcomes?.[horizon];
    return item?.winRatePct == null ? "—" : percent(item.winRatePct) + " (" + count(item.observed) + "/" + count(item.attempts) + ")";
  };
  const rows = first ? [
    ["Monthly baseline", percent(first.baseline_total_roi_pct), percent(first.baseline_net_cagr_pct),
      percent(first.baseline_max_drawdown_pct), percent(first.baseline_downside.downside_capture_pct),
      count(recovery(first.baseline_downside)), percent(first.baseline_turnover_pct), hitRate(first.baseline_ranking, 5), hitRate(first.baseline_ranking, 21)],
    ...comparisons.map(item => [
      labels[item.variant] || escapeHtml(item.variant),
      percent(item.challenger_total_roi_pct), percent(item.challenger_net_cagr_pct),
      percent(item.challenger_max_drawdown_pct), percent(item.variant_downside.downside_capture_pct),
      count(recovery(item.variant_downside)), percent(item.variant_turnover_pct), hitRate(item.variant_ranking, 5), hitRate(item.variant_ranking, 21),
    ]),
  ] : [];
  return `<section class="card desk-card">
    <div class="desk-card-header"><h2>Historical backtest</h2><span class="desk-tag">Historical research</span></div>
    <p class="desk-copy">Enter an unseen holdout period. Check the historical bundle before running all strategies on the same data and costs.</p>
    <p class="desk-copy note"><a href="https://github.com/prakashchinnadurai1408/SI-trader/blob/si-trader-app/nifty100_weekly/MONTHLY_BACKTEST.md#historical-data-intake" target="_blank" rel="noopener noreferrer">Set up the historical data bundle</a></p>
    <form id="monthly-comparison" class="desk-copy">
      <label for="monthly-start">First holdout month</label>
      <input id="monthly-start" name="start" type="month" required value="${escapeHtml(inputs.start)}">
      <label for="monthly-end">Last holdout month</label>
      <input id="monthly-end" name="end" type="month" required value="${escapeHtml(inputs.end)}">
      <label for="monthly-capital">Starting capital (INR)</label>
      <input id="monthly-capital" name="capital" type="number" min="1" max="1000000000" required value="${escapeHtml(inputs.capital)}">
      <label for="monthly-bundle">Archived bundle fingerprint (optional)</label>
      <input id="monthly-bundle" name="bundleId" pattern="[a-f0-9]{64}" maxlength="64" value="${escapeHtml(inputs.bundleId)}">
      <p class="note">Leave blank to use the configured research bundle.</p>
      <label class="check"><input type="checkbox" name="testPriceInputs" ${inputs.testPriceInputs ? "checked" : ""}>
        Test sector momentum, downside risk, and trade capacity separately</label>
      <label class="check"><input type="checkbox" name="includeAI" ${state.researchProposal && inputs.includeAI ? "checked" : ""}
        ${state.researchProposal ? "" : "disabled"}> Include the current AI factor challenger</label>
      ${state.researchProposal ? "" : '<p class="note">Generate a monthly proposal above to include it here.</p>'}
      ${state.monthlyFeedback ? `<p class="message ${state.monthlyError ? "error" : ""}" role="${state.monthlyError ? "alert" : "status"}">${escapeHtml(state.monthlyFeedback)}</p>` : ""}
      <div class="actions">
        <button class="secondary" value="check" ${state.busy ? "disabled" : ""}>Check data readiness</button>
        <button value="run" ${state.busy ? "disabled" : ""}>Run monthly comparison</button>
      </div>
    </form>
    ${result ? `<div class="desk-copy">
      <p role="status"><strong>${result.readiness.ready ? "Research bundle passed the data checks." : "Research bundle needs attention."}</strong></p>
      ${result.readiness.complete_months === undefined ? "" :
        `<p>${count(result.readiness.complete_months)} holdout months · ${count(result.readiness.sessions)} trading sessions</p>`}
      ${result.readiness.issues.length ? "<ul>" + result.readiness.issues.map(issue => "<li>" + escapeHtml(issue) + "</li>").join("") + "</ul>" : ""}
      ${first ? `<p>Baseline Gate G1 <strong>${escapeHtml(result.baselineGate.status)}</strong> · Nifty 100 TRI total return <strong>${percent(first.benchmark_total_roi_pct)}</strong> · Starting capital <strong>${cash(result.capital)}</strong></p>
      <p class="note">${result.archived ? "Archived bundle" : "Input fingerprint"} <code class="research-fingerprint">${escapeHtml(result.bundleId)}</code></p>` : ""}
    </div>` : ""}
    ${result?.experimentIssues?.length ? `<ul class="desk-copy">${result.experimentIssues.map(item =>
      `<li><strong>${escapeHtml(item.name)}</strong> · ${escapeHtml(item.issue)}</li>`).join("")}</ul>` : ""}
    ${first ? `<p class="desk-copy note">Top-rank hit rates show adjusted close-to-close outperformance versus Nifty 100 TRI, with observed samples / eligible samples. Portfolio returns include modeled costs.</p>
      ${gridTable(["Strategy", "Net total return", "Net CAGR", "Max drawdown", "Downside capture", "Recovery sessions",
        "Average rebalance turnover", "5-session rank hit rate", "21-session rank hit rate"], rows, "")}` : ""}
  </section>`;
}

function researchReplay() {
  const inputs = state.replayInputs;
  const result = state.replayResult;
  return `<section class="card desk-card">
    <div class="desk-card-header"><h2>Replay a month-end decision</h2></div>
    <p class="desk-copy">Use an archived bundle to see the evidence and baseline rank that were available for one stock on the decision date.</p>
    <form id="research-replay" class="desk-copy">
      <div class="form-grid">
        <label for="replay-bundle">Archived bundle fingerprint
          <input id="replay-bundle" name="bundleId" required pattern="[a-f0-9]{64}" maxlength="64" value="${escapeHtml(inputs.bundleId)}">
        </label>
        <label for="replay-decision">Month-end decision session
          <input id="replay-decision" name="decision" type="date" required value="${escapeHtml(inputs.decision)}">
        </label>
        <label for="replay-isin">Stock ISIN
          <input id="replay-isin" name="isin" required pattern="[A-Za-z]{2}[A-Za-z0-9]{9}[0-9]" maxlength="12" value="${escapeHtml(inputs.isin)}">
        </label>
      </div>
      <div class="actions"><button class="secondary" ${state.busy ? "disabled" : ""}>Replay decision</button></div>
      ${state.replayMessage ? `<p class="message ${state.replayError ? "error" : ""}" role="${state.replayError ? "alert" : "status"}">${escapeHtml(state.replayMessage)}</p>` : ""}
    </form>
    ${result ? `<div class="desk-copy">
      <p><strong>${escapeHtml(result.symbol)}</strong> · ${escapeHtml(result.sector)} · ${escapeHtml(result.decisionDate)}</p>
      <p>Snapshot known on ${escapeHtml(result.knownOn)} · Close ${cash(result.close)} · Baseline rank ${result.rank ?? "Unavailable"} · Target equity ${count(result.targetExposurePct.toFixed(1))}%</p>
      <p>${result.failedChecks.length ? "Failed checks · " + escapeHtml(result.failedChecks.join(", ")) : "No failed checks in the archived snapshot."}</p>
      ${gridTable(["Factor", "Archived value"], Object.entries(result.factors).map(([key, value]) =>
        [escapeHtml(key.replaceAll("_", " ")), count(value)]), "")}
      <p class="note">Source declarations · ${escapeHtml(Object.values(result.declaredSources).join(" · "))}</p>
    </div>` : ""}
  </section>`;
}

function strategyLab() {
  const lab = state.lab;
  const result = state.labResult;
  const metrics = [
    ["Beta vs Nifty 100 TRI", "beta"], ["Annualized regression intercept", "annualizedInterceptPct", "%"],
    ["EWMA volatility, annualized", "ewmaVolPct", "%"], ["21-session momentum", "momentum21Pct", "%"],
    ["63-session momentum", "momentum63Pct", "%"], ["14-session RSI", "rsi14"], ["14-session ATR", "atr14", " INR"],
  ];
  return `<div class="desk-lab">
    <section class="card desk-run">
      <div><h2>Nifty 100 research workspace</h2><p>Compare monthly strategy ideas, inspect market breadth, and test stock downside scenarios.</p></div>
      <button data-action="load-lab" ${state.busy ? "disabled" : ""}>${state.busy ? "Working…" : "Refresh NSE snapshot"}</button>
      ${feedback()}
    </section>
    ${lab ? `<div class="desk-metrics">
      ${metric("Stocks up", count(lab.breadth.up), "Of " + count(lab.breadth.dailyCovered) + " with daily data")}
      ${metric("Stocks down", count(lab.breadth.down), "Flat: " + count(lab.breadth.flat))}
      ${metric("Median five-session move", percent(lab.breadth.medianFivePct), "Nifty 100 constituents")}
      ${metric("NSE close", escapeHtml(lab.market.asOf), lab.market.covered + "/" + lab.market.universeSize + " covered")}
    </div>
    <section class="card desk-card">
      <div class="desk-card-header"><h2>Research strategies</h2><span class="desk-tag">Paper research</span></div>
      ${gridTable(["Strategy", "What to test"], lab.presets.map(item =>
        [escapeHtml(item.name), escapeHtml(item.description)]), "")}
      <div class="actions desk-copy">
        <button class="secondary" data-action="tab" data-tab="monthly">Open monthly strategy</button>
        <button class="secondary" data-action="tab" data-tab="committee">Open three-agent review</button>
        <button class="secondary" data-action="tab" data-tab="full">Check full catalogue</button>
      </div>
    </section>
    <section class="card desk-card">
      <div class="desk-card-header"><h2>Industry breadth</h2></div>
      ${gridTable(["Industry", "Stocks", "Median five-session move"], lab.industries.map(item =>
        [escapeHtml(item.name), count(item.covered), percent(item.median_five_pct)]), "No industry had enough observations.")}
    </section>
    <section class="card desk-feeds">
      <div class="desk-card-header"><h2>Stock diagnostics</h2><span class="desk-tag">Scenario analysis</span></div>
      <form id="quant-diagnostics" class="desk-copy">
        <label for="lab-symbol">NSE stock</label>
        <select id="lab-symbol" name="symbol" required ${!lab.historyConfigured ? "disabled" : ""}>
          <option value="">Choose a symbol</option>${lab.symbols.map(symbol =>
            `<option value="${escapeHtml(symbol)}" ${state.labSymbol === symbol ? "selected" : ""}>${escapeHtml(symbol)}</option>`).join("")}
        </select>
        <label for="lab-horizon">Trading sessions</label>
        <input id="lab-horizon" name="horizon" type="number" min="5" max="30" value="${count(state.labHorizon)}" required ${!lab.historyConfigured ? "disabled" : ""}>
        <div class="actions"><button ${state.busy || !lab.historyConfigured ? "disabled" : ""}>Run stock diagnostics</button></div>
      </form>
      ${!lab.historyConfigured ? '<p class="desk-copy note">Set SI_TRADER_STRATEGY_BUNDLE in the server environment to enable diagnostics on verified-format historical inputs.</p>' : ""}
      ${result ? `<p class="desk-copy"><strong>${escapeHtml(result.symbol)}</strong> · ${escapeHtml(result.asOf)} · ${count(result.sessions)} sessions · Close ${cash(result.close)}</p>
        ${gridTable(["Diagnostic", "Value"], metrics.map(([label, key, suffix]) => [label, count(result.metrics[key]) + (suffix || "")]), "")}
        ${result.trailingInputs ? `<details class="desk-copy" open><summary>Price inputs to test</summary>
          <p class="note">Sector peers from the ${escapeHtml(result.featureSnapshot)} membership snapshot. Spread and order book data are outside the traded-value estimate.</p>
          ${gridTable(["Input", "Value"], [
            ["21-session sector-relative return", percent(result.trailingInputs.relative21 == null ? null : result.trailingInputs.relative21 * 100)],
            ["63-session sector-relative return", percent(result.trailingInputs.relative63 == null ? null : result.trailingInputs.relative63 * 100)],
            ["Downside beta", count(result.trailingInputs.downside_beta)],
            ["90th-percentile overnight downside gap", percent(result.trailingInputs.gap_risk == null ? null : result.trailingInputs.gap_risk * 100)],
            ["20-session median traded value", cash(result.trailingInputs.median_turnover)],
          ], "")}</details>` : ""}
        <details class="desk-copy" open><summary>Simulated return range</summary>
          <p class="note">${escapeHtml(result.stress.assumption)}. Scenario percentiles do not predict actual returns.</p>
          ${gridTable(["Session", ...result.stress.percentiles.map(value => "P" + value)],
            result.stress.days.map((day, i) => [count(day), ...result.stress.returnsPct[i].map(percent)]), "")}
        </details>` : ""}
    </section>` : ""}
  </div>`;
}

const arenaStrategies = {
  weekly: "weekly Nifty 100 paper strategy",
  monthly: "monthly Nifty 100 baseline and each completed comparison variant",
  watchlist: "Nifty 100 research watchlist ranking",
  full: "full 48-parameter Nifty 100 research screen",
  committee: "Nifty 100 three-agent research strategy",
};

function arenaCommand(tab) {
  const toPct = value => Number.isFinite(value) ? value.toFixed(2) + "%" : "unmeasured";
  const strategy = arenaStrategies[tab];
  const pieces = [
    "Review the " + strategy + ". Give each solver identical admissible evidence and have the judge review anonymized proposals.",
    "Check point-in-time timing and membership, source coverage, verified vetoes, realistic fills and costs, and overfitting.",
    "Rank by defensible out-of-sample net return, drawdown, turnover and evidence quality. Cite the measured result or state insufficient evidence. Agent agreement is not predictive accuracy.",
    "Keep this review read-only. Leave broker actions, strategy promotion, and order submission outside the review.",
  ];
  if (tab === "monthly") {
    const result = state.monthlyResult;
    if (result?.comparisons?.length) {
      const baseline = result.comparisons[0];
      pieces.push("Matched comparison " + result.readiness.start + " to " + result.readiness.end + ", bundle " + result.bundleId
        + ", baseline net CAGR " + toPct(baseline.baseline_net_cagr_pct) + ", maximum drawdown " + toPct(baseline.baseline_max_drawdown_pct) + ".");
      for (const item of result.comparisons) {
        pieces.push(item.variant + " net CAGR " + toPct(item.challenger_net_cagr_pct)
          + ", maximum drawdown " + toPct(item.challenger_max_drawdown_pct) + ", average turnover " + toPct(item.variant_turnover_pct) + ".");
      }
      if (result.experimentIssues?.length) pieces.push(result.experimentIssues.length + " price-input experiments were skipped.");
    } else {
      pieces.push("No completed matched historical comparison is available in this session. Recommend the next test and abstain from declaring a performance winner.");
    }
  } else {
    const weekly = state.plan?.parameterRunReport;
    const result = {weekly, watchlist: state.watchlist, full: state.fullCatalogue, committee: state.committee}[tab];
    if (result && Number.isInteger(result.complete) && Number.isInteger(result.total)) {
      pieces.push("Catalogue coverage " + result.complete + " of " + result.total + " complete.");
    }
    pieces.push("This view is research or paper only. Review the 48-Parameter Run Report and require a separate chronological, cost-adjusted benchmark comparison before ranking predictive performance.");
  }
  return '/arena "' + pieces.join(" ") + '" n=3 strategy=judge';
}

function arenaReview(tab) {
  if (!arenaStrategies[tab]) return "";
  return `<details class="card desk-arena">
    <summary>Review with /arena</summary>
    <p>Copy a review brief for Claude Code. Reviewers compare the same evidence and flag what still needs testing.</p>
    <label for="arena-command">Claude Code command</label>
    <textarea id="arena-command" rows="5" readonly>${escapeHtml(arenaCommand(tab))}</textarea>
    <div class="actions"><button class="secondary" data-action="copy-arena">Copy /arena command</button>
      <span id="arena-status" role="status"></span></div>
  </details>`;
}

function dashboard() {
  const primary = [["home", "Home"], ["weekly", "Weekly"], ["monthly", "Monthly"], ["feeds", "Data feeds"], ["portfolio", "Portfolio"]];
  const tools = [["lab", "Strategy Lab"], ["watchlist", "Top 10 watchlist"], ["full", "Full 48 research"], ["committee", "Three-agent review"], ["execution", "Execution"]];
  const titles = {weekly: "Weekly strategy", monthly: "Monthly strategy"};
  const title = titles[state.tab] || [...primary, ...tools].find(([key]) => key === state.tab)[1];
  const navButton = ([key, label]) => `<button data-action="tab" data-tab="${key}" ${state.tab === key ? 'aria-current="page"' : ""}>${label}</button>`;
  const brokerTab = ["portfolio", "execution"].includes(state.tab);
  const linked = state.snapshot && ["funds", "holdings", "positions", "orders", "trades"].some(key => state.snapshot[key]?.value !== undefined);
  return `<div class="desk">
    <aside class="desk-nav">
      <div class="desk-brand"><span aria-hidden="true">W</span><div>WeeklyAlpha<small>Nifty 100 workspace</small></div></div>
      <nav aria-label="Trading workspace">
        <div class="desk-primary-links">
          ${primary.map(navButton).join("")}
          <button data-action="config" ${state.busy ? "disabled" : ""}>Settings</button>
        </div>
        <details class="desk-more-links" ${state.moreLinksOpen ? "open" : ""}>
          <summary>Research &amp; execution</summary>
          <div>${tools.map(navButton).join("")}</div>
        </details>
      </nav>
      <div class="desk-nav-status">${paper}<small>InvestRight · Read-only</small></div>
    </aside>
    <main class="desk-main">
      <header class="desk-header">
        <div><h1 tabindex="-1">${title}</h1>
          ${brokerTab ? `<p><span class="connection-dot ${linked ? "connected" : ""}"></span>
            ${linked ? "InvestRight · Read-only · " + tradeTime(state.snapshot.asOf) + " IST" : "InvestRight · Read-only data unavailable"}</p>` : ""}
        </div>
        ${brokerTab ? `<button class="secondary" data-action="refresh" ${state.syncing ? "disabled" : ""}>${state.syncing ? "Syncing…" : "Refresh broker"}</button>` : ""}
        ${state.tab === "weekly" ? `<button class="${state.halted ? "secondary" : "danger"}" data-action="${state.halted ? "resume" : "halt"}">${state.halted ? "Reset kill switch" : "Kill switch"}</button>` : ""}
      </header>
      ${arenaReview(state.tab)}
      ${state.tab === "monthly" ? `<div class="desk-monthly">${builder()}${monthlyComparison()}${researchReplay()}${parameterRunPanel(state.researchProposal?.parameterRunReport)}</div>` :
        state.tab === "portfolio" ? portfolio() : state.tab === "execution" ? executionView() :
        state.tab === "watchlist" ? watchlistView() : state.tab === "feeds" ? evidenceView() :
        state.tab === "full" ? fullCatalogueView() : state.tab === "committee" ? committeeView() :
        state.tab === "lab" ? strategyLab() : state.tab === "weekly" ? weekly() : home()}
    </main>
  </div>`;
}

app.addEventListener("toggle", event => {
  if (event.target.matches(".desk-more-links")) state.moreLinksOpen = event.target.open;
}, true);

setInterval(() => {
  if (state.view === "dashboard" && ["portfolio", "execution"].includes(state.tab) && !document.hidden) refreshBroker();
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
  if (event.target.form?.id === "research-replay") state.replayInputs[event.target.name] = event.target.value;
  if (event.target.form?.id === "monthly-comparison") {
    const field = event.target.name;
    state.monthlyInputs[field] = event.target.type === "checkbox" ? event.target.checked : event.target.value;
  }
});

app.addEventListener("change", event => {
  if (event.target.id === "parameter-symbol") {
    state.parameterSymbol = event.target.value;
    render();
    document.querySelector("#parameter-symbol")?.focus({preventScroll: true});
  }
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
  } else if (event.target.id === "monthly-comparison" && !state.busy) {
    const run = event.submitter?.value === "run";
    state.monthlyInputs = {start: form.get("start"), end: form.get("end"), capital: Number(form.get("capital")),
      includeAI: form.has("includeAI"), testPriceInputs: form.has("testPriceInputs"), bundleId: form.get("bundleId").trim()};
    state.monthlyResult = null;
    state.busy = true;
    state.monthlyFeedback = run ? "Checking the dataset and running the monthly strategies." : "Checking historical data coverage.";
    state.monthlyError = false;
    show();
    try {
      state.monthlyResult = await request("/api/monthly-comparison", {...state.monthlyInputs, run,
        challenger: state.monthlyInputs.includeAI ? {
          kind: state.researchProposal.kind, schema_version: state.researchProposal.schema_version,
          weights: state.researchProposal.weights,
        } : null});
      if (state.monthlyResult.archived) {
        state.replayInputs.bundleId = state.monthlyResult.bundleId;
        state.replayInputs.decision = state.monthlyResult.lastDecision;
        state.replayResult = null;
        state.replayMessage = "";
      }
      state.monthlyFeedback = "";
    } catch (error) {
      state.monthlyFeedback = error.message;
      state.monthlyError = true;
    } finally {
      state.busy = false;
      render();
    }
  } else if (event.target.id === "research-replay" && !state.busy) {
    state.replayInputs = {bundleId: form.get("bundleId").trim(), decision: form.get("decision"),
      isin: form.get("isin").trim().toUpperCase()};
    state.replayResult = null;
    state.replayMessage = "Checking the archived evidence.";
    state.replayError = false;
    state.busy = true;
    render();
    try {
      state.replayResult = await request("/api/research-replay", state.replayInputs);
      state.replayMessage = "";
    } catch (error) {
      state.replayMessage = error.message;
      state.replayError = true;
    } finally {
      state.busy = false;
      render();
    }
  } else if (event.target.id === "quant-diagnostics" && !state.busy) {
    state.labSymbol = form.get("symbol");
    state.labHorizon = Number(form.get("horizon"));
    state.labResult = null;
    state.busy = true;
    show("Calculating stock diagnostics.");
    try {
      state.labResult = await request("/api/quant-diagnostics", {symbol: state.labSymbol, horizon: state.labHorizon});
      show("Historical diagnostics ready.");
    } catch (error) {
      show(error.message, true);
    } finally {
      state.busy = false;
      render();
    }
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
      state.preferParameterPreview = false;
      state.parameterReportMessage = "";
      show("Proposal ready. Include it in the historical backtest below or export it.");
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
    const execution = {
      funding: form.get("funding"), paperCapital: Number(form.get("paperCapital")),
      cashBuffer: Number(form.get("cashBuffer")), scenarioMove: Number(form.get("scenarioMove")),
      paperAuto: form.get("paperAuto") === "on",
    };
    config = {model, objective, maxPositions: Number(form.get("maxPositions")), execution};
    localStorage.setItem("si-trader-strategy-config", JSON.stringify(config));
    state.view = "dashboard";
    show("AI strategy configuration saved.");
  } else if (event.target.id === "strategy" && !state.busy && !state.halted && config.model) {
    state.busy = true;
    show("Fetching NSE data, generating the basket, and sizing it to available cash.");
    try {
      const result = await request("/api/strategy", config);
      if (state.halted) return;
      state.plan = result;
      state.preferParameterPreview = false;
      state.parameterReportMessage = "";
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
    case "parameter-run":
      state.preferParameterPreview = false;
      state.parameterReportMessage = "";
      render();
      break;
    case "parameter-preview":
      if (state.busy) break;
      state.busy = true;
      state.parameterReportMessage = "Fetching dated evidence.";
      render();
      try {
        state.parameterPreview = await request("/api/parameter-run-report");
        state.preferParameterPreview = true;
        state.parameterReportMessage = "Evidence preview refreshed.";
      } catch (error) {
        state.parameterReportMessage = error.message;
      } finally {
        state.busy = false;
        render();
      }
      break;
    case "catalogue-readiness":
      await loadFullCatalogue(false);
      break;
    case "full-catalogue":
      if (state.fullCatalogue?.ready && config.model) await loadFullCatalogue(true);
      break;
    case "load-lab":
      if (state.busy) break;
      state.busy = true;
      show("Fetching current Nifty 100 coverage.");
      try {
        state.lab = await request("/api/strategy-lab");
        show("NSE research snapshot ready.");
      } catch (error) {
        show(error.message, true);
      } finally {
        state.busy = false;
        render();
      }
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
    case "copy-arena": {
      const command = document.querySelector("#arena-command");
      const status = document.querySelector("#arena-status");
      try {
        await navigator.clipboard.writeText(command.value);
        status.textContent = "Copied. Paste the command into Claude Code.";
      } catch {
        command.focus();
        command.select();
        status.textContent = "Command selected. Press Ctrl+C to copy.";
      }
      break;
    }
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
      state.view = "config";
      await loadModels();
      break;
    case "models":
      await loadModels();
      break;
    case "dashboard":
      state.view = "dashboard";
      show();
      if (["portfolio", "execution"].includes(state.tab) && !state.snapshot) refreshBroker();
      break;
    case "tab":
      state.tab = event.target.closest("[data-tab]").dataset.tab;
      state.moreLinksOpen = ["lab", "watchlist", "full", "committee", "execution"].includes(state.tab);
      show();
      document.querySelector(".desk-header h1").focus();
      if (state.tab === "weekly" || ["portfolio", "execution"].includes(state.tab)) refreshBroker();
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
