UI_URI = "ui://journey-checklist/checklist.html"


CHECKLIST_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Journey checklist</title>
  <style>
    :root { color-scheme: light; --ink:#17211d; --muted:#68756d; --paper:#f7f5ef; --card:#fffdf8; --line:#dfe3db; --teal:#0b776e; --gold:#d6a63b; --red:#a13f3f; }
    * { box-sizing:border-box; }
    body { margin:0; background:radial-gradient(circle at 92% 0,#d9eee6 0,transparent 34%),var(--paper); color:var(--ink); font:15px/1.45 "Avenir Next","Trebuchet MS",sans-serif; }
    main { max-width:760px; margin:auto; padding:28px 18px 48px; }
    header { display:flex; justify-content:space-between; gap:18px; align-items:flex-start; margin-bottom:22px; }
    h1,h2,h3,p { margin:0; } h1 { font:700 32px/1.05 Georgia,serif; letter-spacing:-.03em; } h2 { font-size:18px; } h3 { font-size:13px; text-transform:uppercase; letter-spacing:.1em; color:var(--muted); }
    .eyebrow { color:var(--teal); font-size:11px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; margin-bottom:7px; }
    .context { color:var(--muted); margin-top:8px; }
    .summary { background:var(--ink); color:white; border-radius:18px; padding:17px 18px; min-width:130px; text-align:right; }
    .summary strong { display:block; font:700 26px Georgia,serif; color:#e9c66d; }
    section { background:color-mix(in srgb,var(--card) 92%,transparent); border:1px solid var(--line); border-radius:16px; padding:16px; margin-top:14px; box-shadow:0 8px 24px #18352b0a; }
    .section-head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:10px; }
    .items { display:grid; gap:8px; }
    .item { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px; border:1px solid var(--line); border-radius:12px; padding:10px 11px; background:#fff; }
    .item.done { opacity:.58; } .item.done .item-name { text-decoration:line-through; } .item.not-needed { background:#f1f2ed; }
    .item-name { font-weight:700; overflow-wrap:anywhere; } .item-note { color:var(--muted); font-size:12px; overflow-wrap:anywhere; }
    .source { color:var(--muted); font-size:11px; } .source.direct { color:var(--teal); }
    button { border:1px solid var(--line); border-radius:999px; padding:8px 12px; background:#fff; color:var(--ink); font:inherit; cursor:pointer; } button:hover,button:focus-visible { border-color:var(--teal); outline:3px solid #0b776e33; } button.primary { background:var(--teal); border-color:var(--teal); color:#fff; } button.danger { color:var(--red); }
    .actions { display:flex; flex-wrap:wrap; gap:8px; } .empty { color:var(--muted); padding:8px 0; }
    form { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:8px; } input { min-width:0; border:1px solid var(--line); border-radius:10px; padding:10px 11px; background:#fff; color:var(--ink); font:inherit; } input:focus { outline:3px solid #0b776e33; border-color:var(--teal); }
    .hint { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:10px 0; border-top:1px solid var(--line); } .hint:first-of-type { border-top:0; } .hint p { color:var(--muted); font-size:13px; } .error { color:var(--red); background:#fff0ed; border-color:#efc2bb; }
    @media (max-width:460px) { main { padding:20px 12px 36px; } header { display:block; } .summary { margin-top:14px; text-align:left; } .item { grid-template-columns:auto minmax(0,1fr); } .item .actions { grid-column:2; } }
  </style>
</head>
<body>
<main>
  <header>
    <div><div class="eyebrow">journey checklist</div><h1 id="title">Waiting for a journey</h1><p id="context" class="context">Open this tool from an existing journey.</p></div>
    <div class="summary"><strong id="remaining">—</strong><span>remaining</span></div>
  </header>
  <div id="message" aria-live="polite"></div>
  <section><div class="section-head"><h2>Checklist</h2><div class="actions"><button id="modules" type="button">Browse modules</button><button id="refresh" type="button">Refresh composition</button><button id="blueprint" type="button">Remember items</button></div></div><div id="groups"></div></section>
  <section><div class="section-head"><h2>Add something</h2></div><form id="add-form"><label class="sr-only" for="new-item">Item name</label><input id="new-item" name="name" maxlength="200" placeholder="e.g. portable umbrella" required><button class="primary" type="submit">Add item</button></form></section>
  <section id="hints-section" hidden><div class="section-head"><h2>Useful next steps</h2></div><div id="hints"></div></section>
</main>
<script>
  const pending = new Map(); let nextId = 1; let journey = null;
  const $ = (id) => document.getElementById(id);
  function envelope(message) {
    const candidate = message?.params ?? message?.structuredContent ?? message?.result?.structuredContent ?? message?.result ?? message;
    if (candidate?.structuredContent?.summary) return candidate.structuredContent;
    if (candidate?.summary) return candidate;
    const text = candidate?.content?.find?.((part) => part.type === 'text')?.text;
    try { return JSON.parse(text); } catch (_) { return null; }
  }
  window.addEventListener('message', (event) => {
    const data = event.data || {};
    if (data.id && pending.has(data.id)) { const call = pending.get(data.id); pending.delete(data.id); data.error ? call.reject(new Error(data.error.message || 'Tool call failed')) : call.resolve(data.result); return; }
    if (data.method === 'ui/notifications/tool-result') { const incoming = envelope(data); if (incoming) apply(incoming); return; }
    if (data.method === 'ui/notifications/tool-cancelled') { showError(data.params?.reason || 'Tool call cancelled.'); return; }
    if (data.method === 'ui/notifications/tool-input') return;
  });
  function sendRequest(method, params) { return new Promise((resolve, reject) => { const id = `journey-${nextId++}`; pending.set(id, {resolve, reject}); window.parent.postMessage({jsonrpc:'2.0', id, method, params}, '*'); }); }
  function sendNotification(method, params = {}) { window.parent.postMessage({jsonrpc:'2.0', method, params}, '*'); }
  function callTool(name, args) { return sendRequest('tools/call', {name, arguments:args}).then(envelope); }
  function apply(result) {
    if (result.error) { showError(result.error.message || 'The change was rejected.'); return; }
    const next = result.affected?.journey || result.affected?.target?.id && result.affected.target;
    if (next?.items) {
      journey = next;
      render();
      const hasComposition = (next.selected_modules || []).length ||
        (next.unresolved_choices || []).length || (result.conflicts || []).length;
      if (hasComposition) renderComposition(next, result); else renderHints(result.next_steps || []);
    } else renderHints(result.next_steps || []);
  }
  function showError(text) { $('message').innerHTML = `<section class="error" role="alert">${escapeHtml(text)}</section>`; }
  function clearError() { $('message').innerHTML = ''; }
  function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
  function render() {
    clearError(); $('title').textContent = journey.name; const context = Object.entries(journey.context || {}).filter(([,v]) => v != null).map(([k,v]) => `${k.replaceAll('_',' ')}: ${v}`).join(' · '); $('context').textContent = context || 'No context added yet'; $('remaining').textContent = journey.remaining_count;
    const groups = {}; journey.items.forEach((item) => (groups[item.group || 'Other'] ||= []).push(item)); const root = $('groups'); root.innerHTML = '';
    if (!journey.items.length) { root.innerHTML = '<p class="empty">Nothing here yet. Add the first thing you want to remember.</p>'; return; }
    Object.entries(groups).forEach(([group, items]) => { const section = document.createElement('div'); section.innerHTML = `<h3>${escapeHtml(group)}</h3><div class="items"></div>`; const list = section.querySelector('.items'); items.forEach((item) => list.appendChild(itemNode(item))); root.appendChild(section); });
  }
  function itemNode(item) {
    const row = document.createElement('div'); row.className = `item ${item.packed ? 'done' : ''} ${item.not_needed ? 'not-needed' : ''}`;
    const path = item.source.path?.length ? ` · ${item.source.path.map(escapeHtml).join(' → ')}` : '';
    row.innerHTML = `<input type="checkbox" aria-label="Mark ${escapeHtml(item.name)} packed" ${item.packed ? 'checked' : ''} ${item.not_needed ? 'disabled' : ''}><div><div class="item-name">${escapeHtml(item.name)} <span class="source ${item.source.kind === 'direct' ? 'direct' : ''}">${escapeHtml(item.source.kind)}${path}</span></div><div class="item-note">${item.quantity}${item.unit ? ` ${escapeHtml(item.unit)}` : ''}${item.note ? ` · ${escapeHtml(item.note)}` : ''}</div></div><div class="actions"><button type="button" data-edit>Edit</button><button class="danger" type="button" data-remove>Remove</button></div>`;
    row.querySelector('input').addEventListener('change', () => mutate('update_items', {target_type:'journey', target_id:journey.id, updates:[{item_id:item.id, packed:row.querySelector('input').checked}]}));
    row.querySelector('[data-edit]').addEventListener('click', () => { const name = prompt('Item name', item.name); if (name === null) return; const group = prompt('Group (blank to clear)', item.group || ''); if (group === null) return; const quantity = prompt('Quantity', item.quantity); if (quantity === null) return; const unit = prompt('Unit (blank to clear)', item.unit || ''); if (unit === null) return; const note = prompt('Note (blank to clear)', item.note || ''); if (note === null) return; const parsedQuantity = Number(quantity); if (!Number.isInteger(parsedQuantity) || parsedQuantity < 1) return showError('Quantity must be a positive whole number.'); const next = {name:name.trim(), group:group.trim() || null, quantity:parsedQuantity, unit:unit.trim() || null, note:note.trim() || null}; const updates = Object.fromEntries(Object.entries(next).filter(([key, value]) => value !== item[key] && !(value === null && item[key] == null))); if (Object.keys(updates).length) mutate('update_items', {target_type:'journey', target_id:journey.id, updates:[{item_id:item.id, ...updates}]}); });
    row.querySelector('[data-remove]').addEventListener('click', () => { if (confirm(`Remove ${item.name}?`)) mutate('remove_items', {target_type:'journey', target_id:journey.id, item_ids:[item.id]}); }); return row;
  }
  async function mutate(tool, args) { try { const result = await callTool(tool,args); apply(result); } catch (error) { showError(error.message); } }
  $('add-form').addEventListener('submit', (event) => { event.preventDefault(); const name = $('new-item').value.trim(); if (!name || !journey) return; mutate('add_items', {target_type:'journey', target_id:journey.id, items:[{name}]}); $('new-item').value = ''; });
  $('blueprint').addEventListener('click', () => { if (!journey) return; const direct = journey.items.filter((item) => item.source.kind === 'direct'); if (!direct.length) return showError('Add a direct item before remembering it.'); const args = {journey_id:journey.id, item_ids:direct.map((item) => item.id)}; if (journey.source_blueprint_id) args.blueprint_id = journey.source_blueprint_id; else { const name = prompt('New blueprint name'); if (!name) return; args.new_blueprint_name = name; } if (confirm('Save these direct items to the blueprint?')) mutate('promote_items', args); });
  $('modules').addEventListener('click', async () => { if (!journey) return; try { const result = await callTool('list_modules', {}); showModules(result.affected?.modules || []); } catch (error) { showError(error.message); } });
  $('refresh').addEventListener('click', () => { if (journey) mutate('refresh_composition', {target_type:'journey', target_id:journey.id}); });
  function showModules(modules) { if (!modules.length) return showError('No reusable modules yet.'); const section = $('hints-section'); section.hidden = false; $('hints').innerHTML = modules.map((module) => `<div class="hint"><p><strong>${escapeHtml(module.name)}</strong><br>${module.common_item_count} common item(s) · ${(module.variants || []).join(', ') || 'no variants'}</p><span class="actions"><button data-module="${module.id}">Include common</button>${(module.variants || []).map((variant) => `<button data-module="${module.id}" data-variant="${escapeHtml(variant)}">${escapeHtml(variant)}</button>`).join('')}</span></div>`).join(''); $('hints').querySelectorAll('[data-module]').forEach((button) => button.addEventListener('click', () => mutate('include_module', {target_type:'journey', target_id:journey.id, module_id:button.dataset.module, ...(button.dataset.variant ? {variant:button.dataset.variant} : {})}))); }
  function renderComposition(target, result) {
    const unresolved = target.unresolved_choices || result.affected?.unresolved_choices || [];
    const selected = target.selected_modules || [];
    const conflicts = result.conflicts || result.affected?.conflicts || [];
    if (!selected.length && !unresolved.length && !conflicts.length) return;
    const section = $('hints-section'); section.hidden = false;
    const modules = selected.length ? `<div class="hint"><p><strong>Modules in this checklist</strong><br>${selected.map((module) => `${escapeHtml(module.name)}${module.variant ? ` · ${escapeHtml(module.variant)}` : ''}`).join(' · ')}</p></div>` : '';
    const variants = selected.flatMap((module) => module.variant ? [] : (module.available_variants || []).map((variant) => `<button data-variant-selection="${escapeHtml(module.selection_id)}" data-module="${escapeHtml(module.module_id)}" data-variant="${escapeHtml(variant)}">${escapeHtml(module.name)} · ${escapeHtml(variant)}</button>`));
    const variantChoices = variants.length ? `<div class="hint"><p><strong>Choose a module variant</strong></p><span class="actions">${variants.join('')}</span></div>` : '';
    const choices = unresolved.map((choice) => `<div class="hint"><p><strong>${escapeHtml(choice.label)}</strong><br>${escapeHtml(choice.module_name)} · choose one</p><span class="actions">${choice.options.map((option) => `<button data-choice="${escapeHtml(choice.choice_id)}" data-option="${escapeHtml(option.option_key)}" data-selection="${escapeHtml(choice.selection_id)}">${escapeHtml(option.name)}</button>`).join('')}</span></div>`).join('');
    const refresh = conflicts.length ? '<div class="hint"><p>Conflicts preserved; review the current checklist.</p><button data-refresh>Refresh</button></div>' : '';
    $('hints').innerHTML = modules + variantChoices + choices + refresh;
    $('hints').querySelectorAll('[data-variant-selection]').forEach((button) => button.addEventListener('click', () => mutate('include_module', {target_type:'journey', target_id:journey.id, module_id:button.dataset.module, variant:button.dataset.variant, selection_id:button.dataset.variantSelection})));
    $('hints').querySelectorAll('[data-choice]').forEach((button) => button.addEventListener('click', () => mutate('select_module_option', {target_type:'journey', target_id:journey.id, selection_id:button.dataset.selection, choice_id:button.dataset.choice, option_key:button.dataset.option})));
    $('hints').querySelector('[data-refresh]')?.addEventListener('click', () => mutate('refresh_composition', {target_type:'journey', target_id:journey.id}));
  }
  function renderHints(hints) { const section = $('hints-section'); if (!hints.length) { section.hidden = true; return; } section.hidden = false; $('hints').innerHTML = hints.map((hint, index) => `<div class="hint"><p>${escapeHtml(hint.reason)}${hint.needs.length ? `<br>Needs: ${escapeHtml(hint.needs.join(', '))}` : ''}</p><button data-hint="${index}">Open</button></div>`).join(''); $('hints').querySelectorAll('[data-hint]').forEach((button) => button.addEventListener('click', () => activateHint(hints[button.dataset.hint]))); }
  async function activateHint(hint) { const args = {...hint.arguments}; for (const need of hint.needs || []) { if (need === 'blueprint_id or new_blueprint_name') { const blueprintId = prompt('Existing blueprint ID (blank to create a new one)'); if (blueprintId) args.blueprint_id = blueprintId; else { const name = prompt('New blueprint name'); if (!name) return; args.new_blueprint_name = name; } continue; } const value = prompt(`Provide ${need}`); if (!value) return; args[need] = need === 'duration_days' ? Number(value) : value; } if (hint.requires_confirmation && !confirm(hint.reason)) return; mutate(hint.tool, args); }
  async function initialize() { try { await sendRequest('ui/initialize', {protocolVersion:'2026-01-26', clientInfo:{name:'journey-checklist', version:'0.1.0'}, appCapabilities:{availableDisplayModes:['inline']}}); sendNotification('ui/notifications/initialized'); } catch (error) { showError(error.message || 'Unable to connect to the MCP host.'); } }
  initialize();
</script>
</body>
</html>"""
