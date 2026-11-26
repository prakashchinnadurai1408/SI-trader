import {workspaceView} from "./workspace.js";
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
  workspace: null,
  workspaceInputs: {symbols: "", candidate: "", capital: 25000, risk: 500, buffer: 10, evalStart: "2023-01-01", evalEnd: "2024-12-31", holdoutStart: "2025-01-01", holdoutEnd: "2025-12-31", compareHoldout: false},
  hosted: false, authLoading: true, authEmail: "",
  parameterPreview: null, parameterSymbol: "", parameterReportMessage: "", preferParameterPreview: false,
  replayInputs: {bundleId: "", decision: "", isin: ""}, replayResult: null, replayMessage: "", replayError: false,
  monthlyInputs: {start: "", end: "", capital: 1000000, includeAI: false, testPriceInputs: false, bundleId: ""}, monthlyResult: null, monthlyFeedback: "", monthlyError: false,
  providers: [], profiles: [], connectionDraft: {}, providerModels: [],
  models: [], modelDraft: "", modelTest: null, lab: null, labResult: null, labSymbol: "", labHorizon: 10, committee: null, committeeHoldings: "", evidence: null, fullCatalogue: null, watchlist: null, researchProposal: null, researchObjective: "", plan: null, tab: "home", snapshot: null, syncing: false, brokerError: "",
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
      ${state.hosted ? '<p class="note">Hosted workspace · operator sign-in</p>' : steps(mfa ? 1 : 0)}
      <h1>${mfa ? "Authenticator code" : "Sign in"}</h1>
      <form id="${mfa ? "mfa" : "signin"}">
        ${mfa ? `<label for="code">Six-digit code</label>
          <input id="code" name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required placeholder="000000">
          <button>Continue to broker setup</button>` :
          `<label for="email">Email</label>
          <input id="email" name="email" type="email" autocomplete="username" value="${escapeHtml(state.authEmail)}" placeholder="you@example.com" required>
          <label for="password">Password</label>
          <input id="password" name="password" type="password" autocomplete="off" minlength="12" placeholder="At least 12 characters" required>
          <button ${state.busy ? "disabled" : ""}>${state.hosted ? "Sign in" : "Continue to authenticator code"}</button>`}
      </form>
      <p class="note">${state.hosted ? "Use the operator account configured for this deployment. Broker credentials belong only on your broker's website." : "Local demo. " + (mfa ? "Use demo code <strong>" + demoCode + "</strong>." :
        "Use <strong>" + demoEmail + "</strong> and <strong>" + demoPassword + "</strong>. Enter your broker credentials only on InvestRight.")}</p>
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
          <p>InvestRight opens in a new tab. To check API access, configure your InvestRight API key and access token in the environment of the server running SI-Trader.</p>
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
  return `<main class="page config-page">
    <div class="topline"><button class="secondary" data-action="dashboard" ${state.busy ? "disabled" : ""}>Back to dashboard</button>${paper}</div>
    <h1>Strategy configuration</h1>
    <form class="card stack" id="config">
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
        <button ${state.busy ? "disabled" : ""}>Save configuration</button>
        <p class="note">Weekly evaluates all 48 catalogue parameters by role. See Weekly for the evidence and ranking weights.</p>
      </div>
      ${feedback()}
    </form>
  </main>`;
}

function modelLabel(id) {
  const profile = state.profiles.find(item => "profile:" + item.id === id);
  return profile ? profile.label + " · " + profile.model : id;
}

function llmConfig() {
  const tested = state.modelTest;
  const available = state.models.includes(state.modelDraft);
  return `<main class="page config-page">
    <div class="topline"><button class="secondary" data-action="dashboard" ${state.busy ? "disabled" : ""}>Back to dashboard</button>${paper}</div>
    <h1>LLM Configuration</h1>
    <form class="card stack" id="llm-config">
      <section>
        <h2>Active strategy model</h2>
        <p>Use a saved cloud connection or a local Ollama model.</p>
        <p class="note">This model is shared by Weekly, Monthly and the research screens.</p>
        <label for="llm-model">Available models</label>
        <select id="llm-model" name="model" required ${state.busy || !state.models.length ? "disabled" : ""}>
          <option value="">Select a model</option>
          ${state.models.map(model => `<option value="${escapeHtml(model)}" ${state.modelDraft === model ? "selected" : ""}>${escapeHtml(modelLabel(model))}</option>`).join("")}
        </select>
        <p class="note">Saved model · ${escapeHtml(modelLabel(config.model) || "None selected")}</p>
      </section>
      <div class="actions">
        <button type="button" class="secondary" data-action="models" ${state.busy ? "disabled" : ""}>Refresh connections</button>
        <button class="secondary" value="test" ${state.busy || !available ? "disabled" : ""}>Test model</button>
        <button value="save" ${state.busy || !available ? "disabled" : ""}>Save model</button>
      </div>
      ${tested?.model === state.modelDraft ? `<p class="note">Last response time · ${count((tested.elapsedMs / 1000).toFixed(1))} seconds</p>` : ""}
      <p class="note">Ollama uses the service configured for the SI-Trader server, defaulting to 127.0.0.1:11434. Available models must be installed on that service.</p>
      ${feedback()}
    </form>
    <form class="card stack" id="cloud-connection">
      <h2>${state.connectionDraft.id ? "Edit connection" : "Add model connection"}</h2>
      <p class="note">A test sends a short prompt. Cloud strategy runs send research evidence to the selected provider. API keys are encrypted in the server's configured private storage.</p>
      <label for="provider">Provider</label>
      <select id="provider" name="provider" required ${state.busy ? "disabled" : ""}>
        ${state.providers.map(item => `<option value="${escapeHtml(item.id)}" ${(state.connectionDraft.provider || "claude") === item.id ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
      </select>
      <label for="connection-label">Connection name</label>
      <input id="connection-label" name="label" maxlength="80" required value="${escapeHtml(state.connectionDraft.label || "")}" placeholder="My research model">
      <label for="connection-model">Model ID</label>
      <input id="connection-model" name="model" list="provider-model-options" maxlength="160" required autocomplete="off" value="${escapeHtml(state.connectionDraft.model || "")}" placeholder="Exact model ID from your provider">
      <datalist id="provider-model-options">${state.providerModels.map(id => `<option value="${escapeHtml(id)}"></option>`).join("")}</datalist>
      <p class="note">Use the exact provider model ID here. Your sign-in email belongs in the sign-in screen.</p>
      <label for="connection-endpoint">API base URL</label>
      <input id="connection-endpoint" name="endpoint" type="url" required value="${escapeHtml(state.connectionDraft.endpoint || state.providers.find(item => item.id === (state.connectionDraft.provider || "claude"))?.endpoint || "")}">
      <label for="api-key">API key</label>
      <input id="api-key" name="apiKey" type="password" autocomplete="off" maxlength="8192" ${state.connectionDraft.hasKey ? "" : "required"} placeholder="${state.connectionDraft.hasKey ? "Leave blank to retain the saved key" : "Enter provider API key"}">
      <div class="actions">
        <button ${state.busy ? "disabled" : ""}>Save connection</button>
        <button type="button" class="secondary" data-action="provider-models" ${state.busy ? "disabled" : ""}>Load available models</button>
        ${state.connectionDraft.id ? '<button type="button" class="secondary" data-action="new-connection">Add another connection</button>' : ""}
      </div>
    </form>
    <section class="card stack">
      <h2>Saved connections</h2>
      ${state.profiles.length ? gridTable(["Connection", "Provider", "Model", "Key", "Actions"], state.profiles.map(item => [
        escapeHtml(item.label), escapeHtml(state.providers.find(p => p.id === item.provider)?.label || item.provider),
        escapeHtml(item.model), item.hasKey ? "Saved and encrypted" : "Key missing",
        `<div class="actions"><button class="secondary" data-action="edit-connection" data-id="${escapeHtml(item.id)}">Edit</button>
        <button class="secondary" data-action="test-connection" data-id="${escapeHtml(item.id)}" ${state.busy || !item.hasKey ? "disabled" : ""}>Test</button>
        <button class="secondary" data-action="delete-key" data-id="${escapeHtml(item.id)}" ${state.busy || !item.hasKey ? "disabled" : ""}>Delete key</button>
        <button class="secondary" data-action="delete-connection" data-id="${escapeHtml(item.id)}" ${state.busy ? "disabled" : ""}>Delete connection</button></div>`,
      ]), "") : '<p class="note">Save a cloud connection above. Ollama models appear in the available models list.</p>'}
    </section>
  </main>`;
}

async function loadModels() {
  state.busy = true;
  show("Loading model connections.");
  try {
    const result = await request("/api/models");
    state.models = result.models;
    state.profiles = result.profiles;
    state.providers = result.providers;
    if (!state.models.includes(state.modelDraft)) {
      state.modelDraft = state.models.includes(config.model) ? config.model : "";
    }
    show(result.error || (state.models.length ? "Model connections loaded." : "Add a cloud connection or start Ollama to choose a model."), Boolean(result.error));
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
      <p class="note">${config.model ? "Model selected · " + escapeHtml(modelLabel(config.model)) : "Setup required · Select an Ollama model"}</p>
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
      <div><h2>Weekly AI strategy</h2><p>${config.model ? escapeHtml(modelLabel(config.model)) + " · " + escapeHtml(source) + " · " + (config.execution.paperAuto ? "Automatic paper fills" : "Preview only") : "Choose a model to run a paper strategy."}</p></div>
      <form id="strategy"><button ${state.busy || state.halted || !config.model ? "disabled" : ""}>${state.busy ? "Running strategy…" : "Run weekly strategy"}</button></form>
      ${!config.model ? '<div class="actions"><button class="secondary" data-action="llm-config">Configure LLM</button></div>' : ""}
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
    <p class="note">${config.model ? "Model: " + escapeHtml(modelLabel(config.model)) : "Select a model to generate a proposal."}</p>
    ${!config.model ? '<button class="secondary" data-action="llm-config">Configure LLM</button>' : ""}
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
    ${!config.model ? "<p class='note'>Choose a model in LLM Configuration.</p>" : ""}
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
    ${!config.model ? '<p class="desk-copy note">Select a model in LLM Configuration to run a complete screen.</p>' : ""}
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
    ${!config.model ? '<p class="desk-copy note">Select a model in LLM Configuration.</p>' : ""}
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

function lastCompletedMonth() {
  const parts = new Intl.DateTimeFormat("en", {timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit"}).formatToParts(new Date());
  let year = Number(parts.find(item => item.type === "year").value);
  let month = Number(parts.find(item => item.type === "month").value) - 1;
  if (month === 0) { year -= 1; month = 12; }
  return year + "-" + String(month).padStart(2, "0");
}

function monthlyDateError(start, end) {
  const last = lastCompletedMonth();
  if (start > last || end > last) return "Historical backtests can end through " + last + ". Current and future months are incomplete.";
  if (start && end && start > end) return "First holdout month must be on or before the last holdout month.";
  return "";
}

function validateMonthlyDates() {
  const form = document.querySelector("#monthly-comparison");
  if (!form) return true;
  const start = form.elements.start;
  const end = form.elements.end;
  const error = monthlyDateError(start.value, end.value);
  start.setCustomValidity(error);
  end.setCustomValidity(error);
  document.querySelector("#monthly-date-validation").textContent = error;
  return !error;
}

async function generateMonthlyProposal() {
  const objective = state.researchObjective.trim() || "Test a monthly Nifty 100 quality, momentum and low-volatility factor strategy.";
  state.researchProposal = await request("/api/strategy-builder", {model: config.model, objective});
  state.monthlyInputs.includeAI = true;
  state.preferParameterPreview = false;
  state.parameterReportMessage = "";
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
      <input id="monthly-start" name="start" type="month" required max="${lastCompletedMonth()}" aria-describedby="monthly-date-help monthly-date-validation" value="${escapeHtml(inputs.start)}">
      <label for="monthly-end">Last holdout month</label>
      <input id="monthly-end" name="end" type="month" required max="${lastCompletedMonth()}" aria-describedby="monthly-date-help monthly-date-validation" value="${escapeHtml(inputs.end)}">
      <p id="monthly-date-help" class="note">Latest completed month · ${lastCompletedMonth()} (India time). Choose a historical period that was reserved for testing.</p>
      <p id="monthly-date-validation" class="message error" role="status">${escapeHtml(monthlyDateError(inputs.start, inputs.end))}</p>
      <label for="monthly-capital">Starting capital (INR)</label>
      <input id="monthly-capital" name="capital" type="number" min="1" max="1000000000" required value="${escapeHtml(inputs.capital)}">
      <label for="monthly-bundle">Archived bundle fingerprint (optional)</label>
      <input id="monthly-bundle" name="bundleId" pattern="[a-f0-9]{64}" maxlength="64" value="${escapeHtml(inputs.bundleId)}">
      <p class="note">Leave blank to use the configured research bundle.</p>
      <label class="check"><input type="checkbox" name="testPriceInputs" ${inputs.testPriceInputs ? "checked" : ""}>
        Test sector momentum, downside risk, and trade capacity separately</label>
      <label class="check"><input type="checkbox" name="includeAI" ${inputs.includeAI ? "checked" : ""}>
        Include an AI factor challenger</label>
      <p class="note">${state.researchProposal ? "The current proposal will be included when selected." :
        "When selected, Run monthly comparison checks the data, generates an AI proposal, and includes it in the test."}</p>
      ${!config.model ? '<div class="actions"><button type="button" class="secondary" data-action="llm-config">Configure LLM for AI comparison</button></div>' : ""}
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
  const primary = [["home", "Home"], ["weekly", "Weekly"], ["monthly", "Monthly"], ["workspace", "Strategy workspace"], ["feeds", "Data feeds"], ["portfolio", "Portfolio"]];
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
          <button data-action="llm-config" ${state.busy ? "disabled" : ""}>LLM Configuration</button>
          ${state.hosted ? '<button data-action="logout">Sign out</button>' : ""}
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
        state.tab === "workspace" ? feedback() + workspaceView(state.workspace, state.workspaceInputs, state.busy, {escapeHtml,gridTable,cash,count,percent}) :
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
  if (state.authLoading) { app.innerHTML = '<main class="page"><p role="status">Checking workspace access…</p></main>'; return; }
  app.innerHTML = state.view === "config" ? strategyConfig() : state.view === "llm" ? llmConfig() : state.view === "dashboard" ? dashboard() : state.view === "broker" ? broker() : signIn();
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
  if (response.status === 401 && state.hosted && path !== "/api/auth/login") {
    state.view = "signin";
    state.snapshot = null;
    render();
  }
  if (!response.ok) throw new Error((result.error || "The request failed.") + (result.requestId ? " Reference: " + result.requestId : ""));
  return result;
}

app.addEventListener("input", event => {
  if (event.target.form?.id.startsWith("workspace-")) state.workspaceInputs[event.target.name] = event.target.type === "checkbox" ? event.target.checked : event.target.type === "number" ? Number(event.target.value) : event.target.value;
  if (event.target.id === "research-objective") state.researchObjective = event.target.value;
  if (event.target.id === "committee-holdings") state.committeeHoldings = event.target.value;
  if (event.target.form?.id === "research-replay") state.replayInputs[event.target.name] = event.target.value;
  if (event.target.form?.id === "monthly-comparison") {
    const field = event.target.name;
    state.monthlyInputs[field] = event.target.type === "checkbox" ? event.target.checked : event.target.value;
    if (field === "start" || field === "end") validateMonthlyDates();
  }
});

app.addEventListener("change", event => {
  if (event.target.id === "provider") {
    state.providerModels = [];
    state.connectionDraft = {...state.connectionDraft, provider: event.target.value, hasKey: false,
      label: document.querySelector("#connection-label").value, model: document.querySelector("#connection-model").value,
      endpoint: state.providers.find(item => item.id === event.target.value)?.endpoint || ""};
    render();
  }
  if (event.target.id === "llm-model") {
    state.modelDraft = event.target.value;
    show();
    document.querySelector("#llm-model").focus({preventScroll: true});
  }
  if (event.target.id === "parameter-symbol") {
    state.parameterSymbol = event.target.value;
    render();
    document.querySelector("#parameter-symbol")?.focus({preventScroll: true});
  }
});

app.addEventListener("submit", async event => {
  event.preventDefault();
  const form = new FormData(event.target);
  if (event.target.id.startsWith("workspace-") && !state.busy) {
    await workspaceRequest({...state.workspaceInputs, model: config.model, action: event.target.id.split("-")[1]});
    return;
  }
  if (event.target.id === "signin") {
    if (state.hosted) {
      state.authEmail = form.get("email");
      state.busy = true;
      show();
      try {
        await request("/api/auth/login", {email: form.get("email"), password: form.get("password")});
        state.view = "broker";
        show();
      } catch (error) { show(error.message, true); }
      finally { state.busy = false; render(); }
      return;
    }
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
    if (!validateMonthlyDates()) { event.target.reportValidity(); return; }
    const run = event.submitter?.value === "run";
    state.monthlyInputs = {start: form.get("start"), end: form.get("end"), capital: Number(form.get("capital")),
      includeAI: form.has("includeAI"), testPriceInputs: form.has("testPriceInputs"), bundleId: form.get("bundleId").trim()};
    const comparisonInputs = {...state.monthlyInputs};
    state.monthlyResult = null;
    state.busy = true;
    state.monthlyFeedback = run ? "Checking the dataset and running the monthly strategies." : "Checking historical data coverage.";
    state.monthlyError = false;
    show();
    try {
      if (run && comparisonInputs.includeAI && !config.model) {
        throw new Error("Select and save a model in LLM Configuration to include an AI challenger.");
      }
      if (run && comparisonInputs.includeAI && !state.researchProposal) {
        state.monthlyResult = await request("/api/monthly-comparison", {...comparisonInputs, run: false, challenger: null});
        if (!state.monthlyResult.readiness.ready) {
          state.monthlyFeedback = "";
          return;
        }
        state.monthlyFeedback = "Data checks passed. Generating and reviewing the AI proposal.";
        render();
        await generateMonthlyProposal();
        state.monthlyFeedback = "Comparing the AI proposal with the baseline on the same data and costs.";
        render();
      }
      state.monthlyResult = await request("/api/monthly-comparison", {...comparisonInputs, run,
        challenger: run && comparisonInputs.includeAI && state.researchProposal ? {
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
      await generateMonthlyProposal();
      show("Proposal ready. Include it in the historical backtest below or export it.");
    } catch (error) {
      show(error.message, true);
    } finally {
      state.busy = false;
      render();
    }
  } else if (event.target.id === "cloud-connection" && !state.busy) {
    const payload = Object.fromEntries(form);
    state.connectionDraft = {...state.connectionDraft, provider: payload.provider,
      label: payload.label, model: payload.model, endpoint: payload.endpoint};
    if (state.connectionDraft.id) payload.id = state.connectionDraft.id;
    document.querySelector("#api-key").value = "";
    state.busy = true;
    try {
      const saved = await request("/api/llm-save", payload);
      payload.apiKey = "";
      state.connectionDraft = {};
      state.modelDraft = "profile:" + saved.id;
      await loadModels();
      show("Connection saved. Select Test model to verify access, then Save model to use it for strategies.");
    } catch (error) {
      show(error.message, true);
    } finally {
      payload.apiKey = "";
      state.busy = false;
      render();
    }
  } else if (event.target.id === "llm-config" && !state.busy) {
    const model = form.get("model");
    if (!state.models.includes(model)) return;
    if (event.submitter?.value === "test") {
      state.busy = true;
      state.modelTest = null;
      show("Testing a short response. A cold model may take longer to load.");
      try {
        state.modelTest = await request("/api/model-test", {model});
        show("Model responded successfully.");
      } catch (error) {
        show(error.message, true);
      } finally {
        state.busy = false;
        render();
      }
    } else {
      config = {...config, model};
      localStorage.setItem("si-trader-strategy-config", JSON.stringify(config));
      show("Model saved for all strategy screens.");
    }
  } else if (event.target.id === "config" && !state.busy) {
    const objective = form.get("objective").trim();
    if (!objective) {
      show("Enter a strategy objective.", true);
      return;
    }
    const execution = {
      funding: form.get("funding"), paperCapital: Number(form.get("paperCapital")),
      cashBuffer: Number(form.get("cashBuffer")), scenarioMove: Number(form.get("scenarioMove")),
      paperAuto: form.get("paperAuto") === "on",
    };
    config = {...config, objective, maxPositions: Number(form.get("maxPositions")), execution};
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
    case "workspace-refresh": await workspaceRequest({action:"status"}); break;
    case "workspace-halt": await workspaceRequest({action:state.workspace?.ledger.halted?"resume":"halt"}); break;
    case "workspace-paper": await workspaceRequest({action:"paper",planId:state.workspace?.plan.id}); break;
    case "logout":
      if (state.busy) break;
      try {
        await request("/api/auth/logout", {});
        window.location.reload();
      } catch (error) { show(error.message, true); }
      break;
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
      show();
      break;
    case "llm-config":
      state.view = "llm";
      state.modelDraft = config.model;
      await loadModels();
      break;
    case "models":
      await loadModels();
      break;
    case "provider-models": {
      if (state.busy) break;
      const form = document.querySelector("#cloud-connection");
      const payload = Object.fromEntries(new FormData(form));
      if (state.connectionDraft.id) payload.id = state.connectionDraft.id;
      state.connectionDraft = {...state.connectionDraft, provider: payload.provider, label: payload.label,
        model: payload.model, endpoint: payload.endpoint};
      document.querySelector("#api-key").value = "";
      state.busy = true;
      try {
        const result = await request("/api/provider-models", payload);
        state.providerModels = result.models;
        show(result.models.length + " provider models loaded. Choose a model in Model ID.");
      } catch (error) { show(error.message, true); }
      finally {
        const enteredKey = payload.apiKey;
        payload.apiKey = "";
        state.busy = false;
        render();
        document.querySelector("#api-key").value = enteredKey;
      }
      break;
    }
    case "new-connection":
      state.providerModels = [];
      state.connectionDraft = {};
      show();
      break;
    case "edit-connection": {
      const id = event.target.closest("[data-id]").dataset.id;
      state.providerModels = [];
      state.connectionDraft = {...state.profiles.find(item => item.id === id)};
      show();
      document.querySelector("#connection-label").focus();
      break;
    }
    case "test-connection": {
      if (state.busy) break;
      const id = event.target.closest("[data-id]").dataset.id;
      state.busy = true;
      show("Testing provider response.");
      try {
        state.modelTest = await request("/api/model-test", {model: "profile:" + id});
        state.modelDraft = "profile:" + id;
        show("Model responded successfully.");
      } catch (error) { show(error.message, true); }
      finally { state.busy = false; render(); }
      break;
    }
    case "delete-key":
    case "delete-connection": {
      if (state.busy) break;
      const id = event.target.closest("[data-id]").dataset.id;
      state.busy = true;
      try {
        await request(action === "delete-key" ? "/api/llm-delete-key" : "/api/llm-delete", {id});
        if (config.model === "profile:" + id) {
          config = {...config, model: ""};
          localStorage.setItem("si-trader-strategy-config", JSON.stringify(config));
        }
        if (state.connectionDraft.id === id) state.connectionDraft = {};
        state.modelTest = null;
        await loadModels();
        show(action === "delete-key" ? "Saved key deleted from this machine. You can add a replacement using Edit." : "Model connection deleted.");
      } catch (error) { show(error.message, true); }
      finally { state.busy = false; render(); }
      break;
    }
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
      if (state.tab === "workspace") await workspaceRequest({action:"status"});
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

async function workspaceRequest(payload) {
  state.busy = true; show("Working on the strategy workspace…");
  try { state.workspace = await request("/api/workspace", payload); show(); }
  catch(error) { show(error.message, true); }
  finally { state.busy = false; render(); }
}

render();
fetch("/api/auth/session").then(response => {
  if (!response.ok) throw new Error("Could not check workspace access.");
  return response.json();
}).then(session => {
  state.hosted = session.hosted;
  if (session.hosted && session.authenticated) state.view = "broker";
  state.authLoading = false;
  render();
}).catch(() => {
  app.innerHTML = '<main class="page"><p role="alert">Could not check workspace access. Reload to retry.</p></main>';
});
