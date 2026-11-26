export function workspaceView(result, inputs, busy, ui) {
  const {escapeHtml: esc, gridTable: table, cash, count, percent} = ui;
  const candidates = result?.candidates || [];
  const plan = result?.plan, review = result?.review, ledger = result?.ledger;
  const disabled = busy ? "disabled" : "";
  const fields = (items, type) => items.map(([key,label,min,max]) => `<label>${label}<input name="${key}" type="${type}" ${min == null ? "" : `min="${min}" max="${max}"`} value="${esc(inputs[key])}" required></label>`).join("");
  return `<div class="desk-monthly">
    <section class="card desk-builder">
      <div class="desk-card-header"><h2>1. Strategy hub</h2><span class="desk-tag">Research candidates</span></div>
      <p>Load existing MA templates from the migrated hub with a current NSE Nifty 100 snapshot. Templates are not confirmed entry signals or stock recommendations.</p>
      <form id="workspace-load" class="stack">
        <label>Candidate source<select name="source"><option value="ma" ${inputs.source!=="ai"?"selected":""}>Existing MA templates</option><option value="ai" ${inputs.source==="ai"?"selected":""}>Configured AI model</option></select></label>
        <p class="note">AI generation uses your saved LLM selection and may consume provider quota. Model confidence is not a calibrated probability. Provider failure is reported without substituting templates.</p>
        <label>NSE symbols (optional, up to five)<input name="symbols" maxlength="200" value="${esc(inputs.symbols)}" placeholder="Blank: five highest-turnover covered stocks"></label>
        <button ${disabled}>Load strategy candidates</button>
      </form>
      ${result?.market ? `<p class="note">${esc(result.market.source)} · close ${esc(result.market.asOf)}. Symbols are selected by session liquidity, not predicted returns.</p>` : ""}
      ${table(["Candidate","Source","Catalogue weights","Stocks"], candidates.map(c=>[esc(c.name),esc(c.source),count(c.weight_total)+" total · "+Object.keys(c.parameter_weights).length+" entries",esc((c.selected_stocks||[]).join(", "))]), "No candidates loaded.")}
    </section>
    <section class="card desk-builder">
      <div class="desk-card-header"><h2>2. Arena review</h2><span class="desk-tag">Read-only comparison</span></div>
      <p>Every candidate receives the same evaluation data. Holdout data is excluded from selection. A configured historical research bundle is required to measure performance.</p>
      <form id="workspace-arena" class="stack">
        <div class="form-grid">${fields([["evalStart","Evaluation starts"],["evalEnd","Evaluation ends"],["holdoutStart","Holdout starts"],["holdoutEnd","Holdout ends"]],"date")}</div>
        <label class="check"><input type="checkbox" name="compareHoldout" ${inputs.compareHoldout ? "checked" : ""}>Compare frozen finalists on the holdout</label>
        <button ${busy || !candidates.length ? "disabled" : ""}>Run Arena review</button>
      </form>
      ${review ? `<p class="note">${esc(review.scope)}</p>${(review.issues||[]).map(issue=>`<p role="status">${esc(issue)}</p>`).join("")}
        ${table(["Candidate","Evidence","Evaluation net return","Drawdown","Trades"],review.ranking.map(r=>[esc(r.name),esc(r.label),r.label==="measured"?percent(r.metrics.total_return):"Unmeasured",r.label==="measured"?percent(r.metrics.max_drawdown):"—",r.label==="measured"?count(r.metrics.total_trades):"—"]),"No rankings.")}
        ${review.holdout ? table(["Frozen finalist","Holdout evidence","Holdout net return"],review.holdout.comparisons.map(r=>[esc(r.name),esc(r.label),r.label==="measured"?percent(r.metrics.total_return):"Unmeasured"]),"No measured finalists for holdout comparison.") : '<p class="note">Holdout not examined.</p>'}` : ""}
    </section>
    <section class="card desk-builder">
      <div class="desk-card-header"><h2>3. Risk plan and paper execution</h2><span class="desk-tag">Live execution locked</span></div>
      <p>Sizing uses the migrated BudgetManager and execution bridge. Simulated fills use reference closes, not live broker prices. Targets are scenarios, not predicted ROI. Plans expire after ten minutes and can execute once.</p>
      <form id="workspace-plan" class="stack">
        <label>Strategy candidate<select name="candidate" required><option value="">Choose a candidate</option>${candidates.map(c=>`<option value="${esc(c.name)}" ${inputs.candidate===c.name?"selected":""}>${esc(c.name)}</option>`).join("")}</select></label>
        <div class="form-grid">${fields([["capital","Starting paper capital (INR)",1000,1000000000],["risk","Maximum loss per trade (INR)",1,50000000],["buffer","Cash buffer (%)",10,90]],"number")}</div>
        <button ${busy || !review || ledger?.halted ? "disabled" : ""}>Build risk-sized paper plan</button>
      </form>
      <div class="actions"><button class="${ledger?.halted?"secondary":"danger"}" data-action="workspace-halt" ${disabled}>${ledger?.halted?"Resume paper execution":"Halt paper execution"}</button><button class="secondary" data-action="workspace-refresh" ${disabled}>Refresh workspace</button></div>
      ${plan ? `<p>${esc(plan.note)}</p>${table(["Stock","Qty","Entry reference","Stop","Target scenario","Risk at stop","Decision"],plan.orders.map(o=>[esc(o.symbol),count(o.shares),cash(o.entry_price),cash(o.stop_loss),cash(o.target),cash(o.risk_at_stop),esc(o.approved?o.deciding_limit:o.rejection_reason||"Blocked")]),"No sized orders.")}
        <p>Position value ${cash(plan.total_position_value)} · gross risk at stops ${cash(plan.total_risk_at_stops)}. Fees apply; gaps can exceed stop-based risk.</p>
        <button data-action="workspace-paper" ${busy||!plan.tradable||plan.consumed||ledger?.halted?"disabled":""}>${plan.consumed?"Paper plan consumed":"Simulate approved paper plan"}</button>` : ""}
      <p>Paper cash ${ledger?.cash==null?"Not started":cash(ledger.cash)} · ${Object.keys(ledger?.holdings||{}).length} simulated positions · ${ledger?.halted?"HALTED":"Paper enabled"}</p>
      ${table(["Stock","Simulated qty","Reference fill","Cash debit","Status"],(ledger?.fills||[]).map(f=>[esc(f.symbol),count(f.shares),cash(f.entry_price),cash(f.cashDebit),esc(f.status)]),"No paper fills.")}
      <h3>Recent audit reports</h3>${table(["Report","Kind","Created"],(result?.reports||[]).slice().reverse().map(r=>[esc(r.run_id),esc(r.kind),esc(r.started_at)]),"No workspace runs yet.")}
    </section>
  </div>`;
}
