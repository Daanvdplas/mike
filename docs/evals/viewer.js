function revealAnchor() {
  let id;
  try { id = decodeURIComponent(location.hash.slice(1)); }
  catch { return; }
  const target = document.getElementById(id);
  if (!target) return;
  if (target.closest('.runnable-eval')) {
    requestAnimationFrame(() => target.closest('.runnable-eval').scrollIntoView({block: 'start'}));
    return;
  }
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

// Runs are explicit: loading this page only fetches the input descriptions.
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

function renderDeterministicResults(container, result) {
  if (result.status !== 'completed' || result.expected_count !== 2 ||
      !Array.isArray(result.results) || result.results.length !== 3 ||
      !result.structural_checks?.three_unique_results || !result.structural_checks?.valid_corpus_ids ||
      new Set(result.results.map(row => row.case_id)).size !== 3) {
    throw new Error('De run bevat geen geldige drie unieke corpusresultaten.');
  }
  const summary = element('div', null, 'result-summary');
  summary.append(element('h4', `${result.passed ? 'Geslaagd' : 'Niet geslaagd'} — ${result.hit_count} van 2 verwachte zaken gevonden`));
  const expected = element('ul');
  result.expectations.forEach(row => expected.append(element('li',
    `${row.title} (${row.case_id}) · ${row.found ? `gevonden op rang ${row.rank}` : 'niet gevonden in de top 3'}`)));
  summary.append(expected);
  const list = element('ol', null, 'judgments');
  result.results.forEach(row => {
    const item = element('li', null, 'judgment');
    item.append(element('h4', `${row.rank}. ${row.title}`),
      element('p', `Zaak ${row.case_id} · Zoekscore ${Number(row.score).toFixed(4)}`, 'judgment-meta'));
    if (row.assessment === 'expected') item.append(element('p', 'Vooraf verwachte zaak'));
    list.append(item);
  });
  const details = element('details', null, 'run-provenance');
  details.append(element('summary', 'Rundetails'),
    element('p', `Fixture ${result.fixture_version} · ${result.fixture_sha256}`),
    element('p', `Corpus ${result.corpus_version} · ${result.ranking_version}`),
    element('p', `Lokaal resultaatbestand: ${result.artifact_name}`));
  (result.limitations || []).forEach(text => details.append(element('p', text)));
  container.replaceChildren(summary, list, details);
}


const methodNames = {opinion_chunks: 'Oordeelpassages (B)', head_matter: 'Head matter (A)'};

function renderMethod(run) {
  const hits = run.search_response?.results;
  const checks = run.structural_checks;
  if (run.status !== 'completed' || !methodNames[run.retrieval_method] || !Array.isArray(hits) || hits.length !== 3 ||
      new Set(hits.map(row => row.case_id)).size !== 3 || !checks?.three_unique_results ||
      (run.eval_id !== 'B1-compare' && (!checks.source_excluded || hits.some(row => (run.excluded_case_ids || []).includes(row.case_id))))) {
    throw new Error('De run bevat geen geldige drie unieke resultaten. Probeer opnieuw.');
  }
  const judged = run.judge_status === 'completed';
  if (judged && (!Array.isArray(run.judgments) || run.judgments.length !== 3 ||
      new Set(run.judgments.map(row => row.case_id)).size !== 3 ||
      run.judgments.some(row => !Number.isInteger(row.grade) || row.grade < 0 || row.grade > 3 || !hits.some(hit => hit.case_id === row.case_id)))) {
    throw new Error('De AI-beoordeling hoort niet bij deze drie resultaten.');
  }
  const section = element('section', null, 'method-result');
  section.append(element('h3', methodNames[run.retrieval_method], 'method-title'));
  section.append(element('p', '3 unieke uitspraken' +
    (checks.source_excluded ? ' · Bronzaak uitgesloten' : ' · Geen bronuitsluiting'), 'run-checks'));
  section.append(element('p', judged ? 'AI-relevantie: 0 niet relevant · 1 zijdelings · 2 bruikbaar · 3 sterk.' : 'Lokale overeenkomstscores · geen AI-relevantiebeoordeling.', 'grade-scale'));
  if (judged) {
    const useful = run.judgments.filter(row => row.grade >= 2).length;
    const summary = element('div', null, 'result-summary');
    summary.append(element('h4', `${useful} van de 3 matches bruikbaar`), element('p', `${3 - useful} weinig of niet relevant · AI-beoordeling`));
    section.append(summary);
  }
  const list = element('ol', null, 'judgments');
  hits.forEach(hit => {
    const judgment = judged ? run.judgments.find(row => row.case_id === hit.case_id) : undefined;
    const item = element('li', null, 'judgment');
    const heading = element('div', null, 'judgment-heading');
    heading.append(element('h4', hit.title));
    if (judgment) heading.append(element('span', `${['Niet relevant', 'Zijdelings', 'Bruikbaar', 'Sterk'][judgment.grade]} · ${judgment.grade} / 3`, 'grade'));
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
  if (result.eval_id === 'B1') { renderDeterministicResults(container, result); return; }
  const completed = result.status === 'completed' || (result.eval_id === 'B1-compare' && result.status === 'not_scored' && result.execution_status === 'completed');
  if (!completed || !Array.isArray(result.runs) || !result.runs.length || result.runs.length > 2 ||
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
  const methods = selector?.value === 'both' ? ['opinion_chunks', 'head_matter'] : [selector?.value || 'opinion_chunks'];
  const judgeEnabled = judge?.checked || false;
  running = true;
  document.querySelectorAll('.run-button, .method-selector, .scenario-selector, .judge-choice input').forEach(node => { node.disabled = true; });
  button.textContent = 'Bezig…';
  status.hidden = false;
  status.textContent = judgeEnabled ? 'Zoeken en beoordelen… Houd deze pagina open.' : 'Lokaal zoeken en resultaten vergelijken…';
  status.className = 'run-status';
  results.replaceChildren();
  results.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(`/api/evals/${encodeURIComponent(evalRecord.id)}/run`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(evalRecord.id === 'B1' ? {} : {retrieval_methods: methods, judge: judgeEnabled}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'De eval kon niet worden uitgevoerd.');
    if (result.eval_id !== evalRecord.id || (evalRecord.id !== 'B1' && (!Array.isArray(result.runs) ||
        JSON.stringify(result.runs.map(run => run.retrieval_method)) !== JSON.stringify(methods)))) {
      throw new Error('De ontvangen run hoort niet bij deze eval of zoekmethode.');
    }
    renderResults(results, result);
    status.hidden = false;
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

function addRunControls(content, evalRecord, judgeAvailable, scopeId, kind) {
  let selector, judge;
  if (evalRecord.id !== 'B1') {
    const choices = element('div', null, 'run-choices');
    const label = element('label', 'Zoekmethode');
    selector = element('select', null, 'method-selector');
    selector.setAttribute('aria-label', `Zoekmethode voor ${kind === 'diagnostic' ? 'scenario ' : ''}${evalRecord.id}`);
    [['opinion_chunks', methodNames.opinion_chunks], ['head_matter', methodNames.head_matter], ['both', 'Vergelijk beide']].forEach(([value, text]) => {
      const option = element('option', text); option.value = value; selector.append(option);
    });
    label.append(selector); choices.append(label);
    if (evalRecord.id !== 'B1-compare') {
      const judgeLabel = element('label', null, 'judge-choice');
      judge = element('input'); judge.type = 'checkbox'; judge.checked = false;
      judge.disabled = !judgeAvailable; judge.dataset.available = String(judgeAvailable);
      judgeLabel.append(judge, document.createTextNode(' AI-beoordeling via Orq (extra kosten)' + (judgeAvailable ? '' : ' · niet beschikbaar')));
      choices.append(judgeLabel);
    }
    content.append(choices);
  }
  const action = element('div', null, 'run-action');
  const button = element('button', evalRecord.id === 'B1-compare' ? 'Start vergelijking' : 'Start eval', 'run-button');
  button.type = 'button'; button.dataset.evalId = evalRecord.id; button.dataset.kind = kind;
  button.setAttribute('aria-label', `Start ${kind === 'diagnostic' ? 'scenario' : 'eval'}: ${evalRecord.id}`);
  const status = element('p', '', 'run-status'); status.hidden = true; status.id = `${scopeId}-status`; status.setAttribute('role', 'status');
  button.setAttribute('aria-describedby', status.id);
  const results = element('div', null, 'run-results'); results.id = `${scopeId}-results`; results.setAttribute('aria-label', `Resultaten ${evalRecord.id}`);
  button.addEventListener('click', () => runEval(evalRecord, button, status, results, selector, judge));
  action.append(button, status); content.append(action, results);
}

function renderRunnable(evalRecord, judgeAvailable, diagnostic = false) {
  const section = element('details', null, 'runnable-eval');
  section.id = `${diagnostic ? 'compare' : 'run'}-${evalRecord.id}`;
  const heading = element('summary', null, 'run-heading');
  const title = element('h3', diagnostic ? `${evalRecord.id} · ${evalRecord.title}` : evalRecord.title);
  title.id = `${section.id}-title`; section.setAttribute('aria-labelledby', title.id);
  const chevron = element('span', null, 'chevron'); chevron.setAttribute('aria-hidden', 'true'); heading.append(title, chevron); section.append(heading);
  const content = element('div', null, 'runnable-content');
  const info = element('details', null, 'eval-info');
  const toggle = element('summary', 'i'); toggle.setAttribute('aria-label', 'Uitleg en beoordeling van deze eval');
  const explanation = element('div', null, 'eval-info-content');
  if (evalRecord.id === 'B1') {
    explanation.append(element('p', 'De oorspronkelijke referentiecontrole gebruikt de vooraf vastgelegde corpus- en modelcontext. Beide verwachte zaak-ID’s moeten in de top drie staan; hun volgorde mag wisselen.'),
      element('p', 'Deze door agents voorgestelde referenties zijn geen menselijke juridische goldset. Bij een andere index geeft de vaste controle een contextfout; de afzonderlijke zoekvariant hieronder wijzigt de referentie niet.'));
  } else {
    explanation.append(element('p', 'Vergelijk lokale zoekmethodes op dezelfde invoer en index. De bronzaak wordt vóór de top drie uitgesloten. Overlap en overeenkomstscore bewijzen geen juridische relevantie.'),
      element('p', 'Optionele AI-beoordeling: 0 niet relevant, 1 zijdelings, 2 bruikbaar, 3 sterk. Scores 2 en 3 tellen als bruikbaar; dit is geen menselijke juridische referentie.'));
  }
  info.append(toggle, explanation); content.append(info);
  const input = element('div', null, 'run-input');
  if (evalRecord.document_label) {
    field(input, 'Document', `${evalRecord.source_case.name} · ${evalRecord.document_label}`);
    input.append(element('p', 'De volledige meerderheidstekst is invoer; het leesfragment is geen zoekdocument.', 'input-note'));
  }
  field(input, 'Input', evalRecord.query, 'run-query');
  const queryText = input.querySelector('.run-query p'); if (queryText) queryText.lang = 'en';
  const mode = {query: 'Alleen vraag', document: 'Alleen document', combined: 'Document + vraag'}[evalRecord.input_mode];
  input.append(element('p', mode + (evalRecord.source_excluded ? ' · Bronzaak uitgesloten' : ''), 'input-note')); content.append(input);
  field(content, 'Verwachte output', evalRecord.id === 'B1' ? evalRecord.expected_cases.map(row => `${row.title} (${row.case_id})`).join(' en ') + ' binnen de drie resultaten, ongeacht volgorde.' : evalRecord.expected_behavior, 'run-expectation');
  addRunControls(content, evalRecord, judgeAvailable, section.id, diagnostic ? 'diagnostic' : 'fixed');
  if (evalRecord.id === 'B1') {
    const variant = element('section', null, 'b1-variant'); variant.id = 'run-B1-compare';
    variant.append(element('h4', 'Zoekmethodes vergelijken · nieuwe variant'), element('p', 'Dezelfde B1-vraag, met de actuele zoekindex. Geen score van de vooraf vastgelegde referentiecontrole.', 'input-note'));
    addRunControls(variant, evalRecord.comparison_variant, false, variant.id, 'variant'); content.append(variant);
  }
  section.append(content); return section;
}

async function loadCatalog() {
  catalogRetry.hidden = true;
  catalogStatus.hidden = false;
  catalogStatus.textContent = 'Evalinvoer laden…';
  try {
    const response = await fetch('/api/evals');
    if (!response.ok) throw new Error('Catalogus niet beschikbaar');
    const catalog = await response.json();
    const records = ['B1', 'E06'].map(id => catalog.evals.find(row => row.id === id && row.runnable));
    const evals = catalog.diagnostic_evals.filter(row => row.runnable);
    if (records.some(row => !row) || !evals.length || new Set(evals.map(row => row.id)).size !== evals.length) throw new Error('Uitvoerbare evals ontbreken of staan dubbel');
    runnableList.replaceChildren(...records.map(row => renderRunnable(row, catalog.judge_available === true)));
    const diagnosticList = document.getElementById('diagnostic-list');
    if (!diagnosticList) throw new Error('De lokale vergelijkingskiezer ontbreekt');
    const choices = element('label', 'Scenario', 'eval-selection');
    const selector = element('select', null, 'method-selector scenario-selector'); selector.setAttribute('aria-label', 'Evaluatie kiezen');
    const cards = new Map();
    evals.forEach(record => {
      const option = element('option', `${record.id} · ${record.title}`); option.value = record.id; selector.append(option);
      cards.set(record.id, renderRunnable(record, catalog.judge_available === true, true));
    });
    choices.append(selector); const active = element('div');
    const choose = () => active.replaceChildren(cards.get(selector.value)); selector.addEventListener('change', choose);
    const initial = location.hash.startsWith('#compare-') ? location.hash.slice(9) : '';
    if (cards.has(initial)) selector.value = initial;
    choose(); diagnosticList.replaceChildren(choices, active);
    catalogStatus.hidden = true;
    revealAnchor();
  } catch {
    catalogStatus.textContent = 'Runnen is niet beschikbaar. Open deze pagina via de lokale evalserver.';
    catalogRetry.hidden = false;
  }
}

catalogRetry.addEventListener('click', loadCatalog);
loadCatalog();
