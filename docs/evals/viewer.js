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

// Runs are explicit: loading this page only fetches the canonical input descriptions.
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

const methodNames = {opinion_chunks: 'Oordeelpassages (B)', head_matter: 'Head matter (A)'};

function renderMethod(run) {
  const hits = run.search_response?.results;
  const checks = run.structural_checks;
  if (run.status !== 'completed' || !methodNames[run.retrieval_method] || !Array.isArray(hits) || hits.length !== 3 ||
      new Set(hits.map(row => row.case_id)).size !== 3 || !checks?.three_unique_results ||
      (run.eval_id !== 'relevance' && (!checks.source_excluded || hits.some(row => (run.excluded_case_ids || []).includes(row.case_id))))) {
    throw new Error('De run bevat geen geldige drie unieke resultaten. Probeer opnieuw.');
  }
  const judged = run.judge_status === 'completed';
  if (judged && (!Array.isArray(run.judgments) || run.judgments.length !== 3 ||
      new Set(run.judgments.map(row => row.case_id)).size !== 3 ||
      run.judgments.some(row => !hits.some(hit => hit.case_id === row.case_id)))) {
    throw new Error('De AI-beoordeling hoort niet bij deze drie resultaten.');
  }
  const section = element('section', null, 'method-result');
  section.append(element('h3', methodNames[run.retrieval_method], 'method-title'));
  section.append(element('p', '3 unieke uitspraken' +
    (checks.source_excluded ? ' · Bronzaak uitgesloten' : ' · Bronzaak kan zichzelf terugvinden'), 'run-checks'));
  section.append(element('p', judged ? 'AI-relevantie: 0 niet relevant · 1 zijdelings · 2 bruikbaar · 3 sterk.' : 'Lokale overeenkomstscores · geen AI-relevantiebeoordeling.', 'grade-scale'));
  const list = element('ol', null, 'judgments');
  hits.forEach(hit => {
    const judgment = judged ? run.judgments.find(row => row.case_id === hit.case_id) : undefined;
    const item = element('li', null, 'judgment');
    const heading = element('div', null, 'judgment-heading');
    heading.append(element('h4', hit.title));
    if (judgment) heading.append(element('span', `${judgment.grade} / 3`, 'grade'));
    const source = hit.passage.source_section === 'head_matter' ? 'Redactioneel voorwerk' : 'Meerderheidsoordeel';
    item.append(heading, element('p', `Zaak ${hit.case_id} · Overeenkomst ${Number(hit.score).toFixed(4)} · ${source}`, 'judgment-meta'));
    if (judgment) item.append(element('p', judgment.reasoning, 'judgment-reason'));
    item.append(element('blockquote', judgment ? judgment.quote : hit.passage.text));
    list.append(item);
  });
  const provenance = element('details', null, 'run-provenance');
  provenance.append(element('summary', 'Rungegevens en beperkingen'));
  const details = element('dl');
  [
    ['Run', run.run_id], ['Zoekmethode', methodNames[run.retrieval_method]],
    ['AI-beoordelaar', run.model || 'Niet aangevraagd'],
    ['Duur', `${Number(run.duration_seconds).toFixed(1)} seconden`],
    ['Invoer SHA-256', run.input_sha256], ['Corpus', run.corpus_version], ['Ranking', run.ranking_version],
    ['Embeddingmodel', JSON.stringify(run.retrieval_manifest?.embedding || {})],
    ['Lokaal resultaatbestand', run.artifact_name],
  ].forEach(([label, value]) => details.append(element('dt', label), element('dd', value)));
  provenance.append(details);
  const limitations = element('ul');
  (run.limitations || []).forEach(text => limitations.append(element('li', text)));
  provenance.append(limitations);
  section.append(list, provenance);
  return section;
}

function renderResults(container, result) {
  if (result.status !== 'completed' || !Array.isArray(result.runs) || !result.runs.length || result.runs.length > 2 ||
      new Set(result.runs.map(run => run.retrieval_method)).size !== result.runs.length) {
    throw new Error('De ontvangen vergelijking is ongeldig.');
  }
  const grid = element('div', null, 'method-results');
  result.runs.forEach(run => grid.append(renderMethod(run)));
  const contents = [];
  if (result.runs.length === 2) {
    const overlap = result.comparison?.overlap_count;
    if (!Number.isInteger(overlap) || overlap < 0 || overlap > 3) throw new Error('De vergelijking mist geldige overlapgegevens.');
    contents.push(element('p', `${overlap} van de 3 uitspraken komen in beide lijsten voor. Overlap zegt niets over juridische kwaliteit.`, 'comparison-summary'));
    const wrapper = element('div', null, 'table-scroll');
    const table = element('table', null, 'rank-comparison');
    const caption = element('caption', 'Positie per uitspraak');
    const headings = element('tr');
    ['Uitspraak', ...result.runs.map(run => methodNames[run.retrieval_method])].forEach(label => {
      const header = element('th', label); header.scope = 'col'; headings.append(header);
    });
    const head = element('thead'); head.append(headings);
    const body = element('tbody');
    const cases = new Map();
    result.runs.forEach(run => run.search_response.results.forEach(hit => cases.set(hit.case_id, hit.title)));
    cases.forEach((title, id) => {
      const row = element('tr');
      row.append(element('td', title));
      result.runs.forEach(run => {
        const rank = run.search_response.results.findIndex(hit => hit.case_id === id);
        row.append(element('td', rank < 0 ? '—' : String(rank + 1)));
      });
      body.append(row);
    });
    table.append(caption, head, body); wrapper.append(table); contents.push(wrapper);
  }
  container.replaceChildren(...contents, grid);
}

async function runEval(evalRecord, button, status, results, selector, judge) {
  if (running) return;
  const methods = selector.value === 'both' ? ['opinion_chunks', 'head_matter'] : [selector.value];
  const judgeEnabled = judge.checked;
  running = true;
  document.querySelectorAll('.run-button, .method-selector, .scenario-selector, .judge-choice input').forEach(node => { node.disabled = true; });
  button.textContent = 'Bezig…';
  status.textContent = judgeEnabled ? 'Zoeken en beoordelen… Houd deze pagina open.' : 'Lokaal zoeken en resultaten vergelijken…';
  status.className = 'run-status';
  results.replaceChildren();
  results.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(`/api/evals/${encodeURIComponent(evalRecord.id)}/run`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({retrieval_methods: methods, judge: judgeEnabled}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'De eval kon niet worden uitgevoerd.');
    if (result.eval_id !== evalRecord.id || !Array.isArray(result.runs) ||
        JSON.stringify(result.runs.map(run => run.retrieval_method)) !== JSON.stringify(methods)) {
      throw new Error('De ontvangen run hoort niet bij deze eval of zoekmethode.');
    }
    renderResults(results, result);
    status.textContent = judgeEnabled ? 'Uitgevoerd · AI-beoordeling, geen juridisch keurmerk.' : 'Uitgevoerd · lokale zoekresultaten, geen juridische kwaliteitsmeting.';
    status.className = 'run-status completed';
    button.textContent = 'Opnieuw uitvoeren';
  } catch (error) {
    status.textContent = `Niet uitgevoerd: ${error.message}. Je kunt het opnieuw proberen.`;
    status.className = 'run-status failed';
    button.textContent = 'Opnieuw proberen';
  } finally {
    running = false;
    results.setAttribute('aria-busy', 'false');
    document.querySelectorAll('.run-button, .method-selector, .scenario-selector').forEach(node => { node.disabled = false; });
    document.querySelectorAll('.judge-choice input').forEach(node => { node.disabled = node.dataset.available !== 'true'; });
  }
}

function renderRunnable(evalRecord, judgeAvailable) {
  const section = element('article', null, 'runnable-eval');
  section.id = `run-${evalRecord.id}`;
  const heading = element('div', null, 'run-heading');
  const title = element('h3', (evalRecord.id !== 'relevance' ? `${evalRecord.id} · ` : '') + evalRecord.title);
  title.id = `${section.id}-title`;
  section.setAttribute('aria-labelledby', title.id);
  const mode = {query: 'Alleen vraag', document: 'Alleen document', combined: 'Document + vraag'}[evalRecord.input_mode];
  heading.append(title, element('span', mode, 'run-mode'));
  section.append(heading);
  const input = element('div', null, 'run-input');
  if (evalRecord.document_label) {
    field(input, 'Document', `${evalRecord.source_case.name} · ${evalRecord.document_label}`);
    input.append(element('p', evalRecord.source_excluded ? 'De volledige meerderheidstekst wordt gebruikt, niet het leesfragment. De bronzaak wordt vóór top drie uitgesloten.' : 'Het volledige vaste demodocument wordt samen met de vraag doorzocht. De bronzaak kan zichzelf terugvinden.', 'input-note'));
  }
  field(input, 'Exacte zoekvraag · Engels', evalRecord.query, 'run-query');
  const queryText = input.querySelector('.run-query p');
  if (queryText) queryText.lang = 'en';
  if (evalRecord.query_nl) {
    const translation = element('details', null, 'english-query');
    translation.append(element('summary', 'Nederlandse leesvertaling'), element('p', evalRecord.query_nl));
    input.append(translation);
  }
  if (evalRecord.source_excluded) {
    input.append(element('p', `${evalRecord.source_case.name} (${evalRecord.source_case.id}) is de scenariobron en wordt vóór selectie van de drie resultaten uitgesloten.`, 'input-note'));
  }
  section.append(input);
  field(section, 'Verwacht gedrag', evalRecord.expected_behavior, 'run-expectation');
  field(section, 'Waarom deze eval?', evalRecord.why, 'run-purpose');
  const choices = element('div', null, 'run-choices');
  const methodLabel = element('label', 'Zoekmethode');
  const selector = element('select', null, 'method-selector');
  selector.setAttribute('aria-label', `Zoekmethode voor ${evalRecord.id}`);
  [['opinion_chunks', methodNames.opinion_chunks], ['head_matter', methodNames.head_matter], ['both', 'Vergelijk beide']].forEach(([value, text]) => {
    const option = element('option', text); option.value = value; selector.append(option);
  });
  methodLabel.append(selector);
  const judgeLabel = element('label', null, 'judge-choice');
  const judge = element('input'); judge.type = 'checkbox'; judge.checked = false;
  judge.disabled = !judgeAvailable; judge.dataset.available = String(judgeAvailable);
  judgeLabel.append(judge, document.createTextNode(' AI-beoordeling via Orq (extra kosten)' + (judgeAvailable ? '' : ' · niet beschikbaar')));
  choices.append(methodLabel, judgeLabel);
  section.append(choices);
  const action = element('div', null, 'run-action');
  const button = element('button', 'Start eval', 'run-button');
  button.type = 'button';
  button.dataset.evalId = evalRecord.id;
  button.setAttribute('aria-label', `Start eval: ${evalRecord.id === 'relevance' ? 'algemene relevantie' : evalRecord.id}`);
  const status = element('p', 'Nog niet uitgevoerd', 'run-status');
  status.id = `${section.id}-status`;
  status.setAttribute('role', 'status');
  button.setAttribute('aria-describedby', status.id);
  const results = element('div', null, 'run-results');
  results.id = `${section.id}-results`;
  results.setAttribute('aria-label', `Resultaten ${evalRecord.id}`);
  button.addEventListener('click', () => runEval(evalRecord, button, status, results, selector, judge));
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
    const evals = catalog.evals.filter(row => row.runnable);
    if (!evals.length || new Set(evals.map(row => row.id)).size !== evals.length) throw new Error('Uitvoerbare evals ontbreken of staan dubbel');
    const choices = element('label', 'Evaluatie', 'eval-selection');
    const selector = element('select', null, 'method-selector scenario-selector');
    selector.setAttribute('aria-label', 'Evaluatie kiezen');
    evals.forEach(record => {
      const option = element('option', `${record.id === 'relevance' ? 'Demo' : record.id} · ${record.title}`);
      option.value = record.id; selector.append(option);
    });
    choices.append(selector);
    const active = element('div');
    const choose = () => {
      const record = evals.find(row => row.id === selector.value);
      active.replaceChildren(renderRunnable(record, catalog.judge_available === true));
    };
    selector.addEventListener('change', choose);
    const initial = location.hash.startsWith('#run-') ? location.hash.slice(5) : '';
    if (evals.some(row => row.id === initial)) selector.value = initial;
    choose();
    runnableList.replaceChildren(choices, active);
    document.querySelectorAll('[data-run-eval]').forEach(link => { link.onclick = () => {
      if (running) return false;
      selector.value = link.dataset.runEval; choose();
    }; });
    catalogStatus.hidden = true;
    revealAnchor();
  } catch {
    catalogStatus.textContent = 'Runnen is niet beschikbaar. Open deze pagina via de lokale evalserver. De 25 scenario-ontwerpen hieronder kun je wel lezen.';
    catalogRetry.hidden = false;
  }
}

catalogRetry.addEventListener('click', loadCatalog);
loadCatalog();
