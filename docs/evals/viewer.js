// Native details provide the complete experience without JavaScript.
const evalItems = [...document.querySelectorAll('.eval-item')];

// Keep the overview compact: opening a row closes the previous row.
evalItems.forEach(item => item.addEventListener('toggle', () => {
  if (item.open) evalItems.forEach(other => { if (other !== item) other.open = false; });
}));

function revealAnchor() {
  let id;
  try { id = decodeURIComponent(location.hash.slice(1)); }
  catch { return; }
  const target = document.getElementById(id);
  if (!target) return;
  let parent = target.parentElement;
  while (parent) {
    if (parent.tagName === 'DETAILS') parent.open = true;
    parent = parent.parentElement;
  }
  if (target.tagName === 'DETAILS') target.open = true;
  requestAnimationFrame(() => target.scrollIntoView({block: 'start'}));
}

window.addEventListener('hashchange', revealAnchor);
revealAnchor();

// Runs are explicit: loading this page only fetches the two input descriptions.
const runnableList = document.getElementById('runnable-list');
const catalogStatus = document.getElementById('catalog-status');
const catalogRetry = document.getElementById('catalog-retry');
let running = false;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function field(parent, label, value, className) {
  if (!value) return;
  const container = element('div', null, className);
  container.append(element('h4', label), element('p', value));
  parent.append(container);
}

function renderResults(container, result) {
  const checks = result.structural_checks;
  const judgments = result.judgments;
  if (result.status !== 'completed' || !Array.isArray(judgments) || judgments.length !== 3 ||
      new Set(judgments.map(row => row.case_id)).size !== 3 || !checks?.three_unique_results ||
      (result.eval_id === 'E06' && (!checks.source_excluded || judgments.some(row => row.case_id === '156133')))) {
    throw new Error('De run bevat geen geldige drie unieke resultaten. Probeer opnieuw.');
  }
  const structural = element('p', '3 unieke uitspraken' +
    (checks.source_excluded === true ? ' · Nixon (156133) uitgesloten' : ' · Bronzaak kan zichzelf terugvinden'), 'run-checks');
  const scale = element('p', 'AI-relevantie: 0 niet relevant · 1 zijdelings · 2 bruikbaar · 3 sterk. Zoekscore is de lokale overeenkomstscore.', 'grade-scale');
  const list = element('ol', null, 'judgments');
  judgments.forEach(row => {
    const item = element('li', null, 'judgment');
    const heading = element('div', null, 'judgment-heading');
    heading.append(element('h4', row.title), element('span', `${row.grade} / 3`, 'grade'));
    item.append(heading, element('p', `Zaak ${row.case_id} · Zoekscore ${Number(row.score).toFixed(4)}`, 'judgment-meta'));
    item.append(element('p', row.reasoning, 'judgment-reason'), element('blockquote', row.quote));
    list.append(item);
  });
  const provenance = element('details', null, 'run-provenance');
  provenance.append(element('summary', 'Rungegevens en beperkingen'));
  const details = element('dl');
  [
    ['Run', result.run_id], ['Model', result.model],
    ['Duur', `${Number(result.duration_seconds).toFixed(1)} seconden`],
    ['Corpus', result.corpus_version], ['Zoekmethode', result.ranking_version],
    ['Lokaal resultaatbestand', result.artifact_name],
  ].forEach(([label, value]) => details.append(element('dt', label), element('dd', value)));
  provenance.append(details);
  const limitations = element('ul');
  (result.limitations || []).forEach(text => limitations.append(element('li', text)));
  provenance.append(limitations);
  container.replaceChildren(structural, scale, list, provenance);
}

async function runEval(evalRecord, button, status, results) {
  if (running) return;
  running = true;
  document.querySelectorAll('.run-button').forEach(node => { node.disabled = true; });
  button.textContent = 'Bezig…';
  status.textContent = 'Zoeken en beoordelen… Dit kan even duren. Houd deze pagina open.';
  status.className = 'run-status';
  results.replaceChildren();
  results.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(`/api/evals/${encodeURIComponent(evalRecord.id)}/run`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'De eval kon niet worden uitgevoerd.');
    if (result.eval_id !== evalRecord.id) throw new Error('De ontvangen run hoort niet bij deze eval.');
    renderResults(results, result);
    status.textContent = 'Uitgevoerd · AI-beoordeling, geen juridisch keurmerk.';
    status.className = 'run-status completed';
    button.textContent = 'Opnieuw uitvoeren';
  } catch (error) {
    status.textContent = `Niet uitgevoerd: ${error.message}. Je kunt het opnieuw proberen.`;
    status.className = 'run-status failed';
    button.textContent = 'Opnieuw proberen';
  } finally {
    running = false;
    results.setAttribute('aria-busy', 'false');
    document.querySelectorAll('.run-button').forEach(node => { node.disabled = false; });
  }
}

function renderRunnable(evalRecord) {
  const section = element('article', null, 'runnable-eval');
  section.id = `run-${evalRecord.id}`;
  const heading = element('div', null, 'run-heading');
  const title = element('h3', (evalRecord.id === 'E06' ? 'E06 · ' : '') + evalRecord.title);
  title.id = `${section.id}-title`;
  section.setAttribute('aria-labelledby', title.id);
  const mode = evalRecord.input_mode === 'query' ? 'Alleen vraag' : 'Document + vraag';
  heading.append(title, element('span', mode, 'run-mode'));
  section.append(heading);
  const input = element('div', null, 'run-input');
  if (evalRecord.document_label) {
    field(input, 'Document', `${evalRecord.source_case.name} · ${evalRecord.document_label}`);
    input.append(element('p', 'Het volledige vaste demodocument wordt samen met de vraag doorzocht. De bronzaak kan zichzelf terugvinden.', 'input-note'));
  }
  field(input, 'Exacte zoekvraag · Engels', evalRecord.query, 'run-query');
  input.querySelector('.run-query p').lang = 'en';
  if (evalRecord.query_nl) {
    const translation = element('details', null, 'english-query');
    translation.append(element('summary', 'Nederlandse leesvertaling'), element('p', evalRecord.query_nl));
    input.append(translation);
  }
  if (evalRecord.id === 'E06') {
    input.append(element('p', `${evalRecord.source_case.name} (${evalRecord.source_case.id}) is de herkomst van de vraag. Alleen de vraag gaat naar de zoekfunctie; de bronzaak wordt vóór selectie van de drie resultaten uitgesloten.`, 'input-note'));
  }
  section.append(input);
  field(section, 'Verwacht gedrag', evalRecord.expected_behavior, 'run-expectation');
  field(section, 'Waarom deze eval?', evalRecord.why, 'run-purpose');
  const action = element('div', null, 'run-action');
  const button = element('button', 'Start eval', 'run-button');
  button.type = 'button';
  button.dataset.evalId = evalRecord.id;
  button.setAttribute('aria-label', `Start eval: ${evalRecord.id === 'E06' ? 'E06' : 'algemene relevantie'}`);
  const status = element('p', 'Nog niet uitgevoerd', 'run-status');
  status.id = `${section.id}-status`;
  status.setAttribute('role', 'status');
  button.setAttribute('aria-describedby', status.id);
  const results = element('div', null, 'run-results');
  results.id = `${section.id}-results`;
  results.setAttribute('aria-label', `Resultaten ${evalRecord.id}`);
  button.addEventListener('click', () => runEval(evalRecord, button, status, results));
  action.append(button, status);
  section.append(action, results);
  return section;
}

async function loadCatalog() {
  catalogRetry.hidden = true;
  catalogStatus.hidden = false;
  catalogStatus.textContent = 'Evalinvoer laden…';
  try {
    const response = await fetch('/api/evals');
    if (!response.ok) throw new Error('Catalogus niet beschikbaar');
    const catalog = await response.json();
    const evals = ['relevance', 'E06'].map(id => catalog.evals.find(row => row.id === id && row.runnable));
    if (evals.some(row => !row)) throw new Error('Twee uitvoerbare evals ontbreken');
    runnableList.replaceChildren(...evals.map(renderRunnable));
    catalogStatus.hidden = true;
    revealAnchor();
  } catch {
    catalogStatus.textContent = 'Runnen is niet beschikbaar. Open deze pagina via de lokale evalserver. De 25 scenario-ontwerpen hieronder kun je wel lezen.';
    catalogRetry.hidden = false;
  }
}

catalogRetry.addEventListener('click', loadCatalog);
loadCatalog();
