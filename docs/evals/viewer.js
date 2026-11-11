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

function renderResults(container, result) {
  if (result.eval_id === 'B1') {
    renderDeterministicResults(container, result);
    return;
  }
  const checks = result.structural_checks;
  const judgments = result.judgments;
  if (result.status !== 'completed' || !Array.isArray(judgments) || judgments.length !== 3 ||
      new Set(judgments.map(row => row.case_id)).size !== 3 ||
      judgments.some(row => !Number.isInteger(row.grade) || row.grade < 0 || row.grade > 3) ||
      !checks?.three_unique_results ||
      (result.eval_id === 'E06' && (!checks.source_excluded || judgments.some(row => row.case_id === '156133')))) {
    throw new Error('De run bevat geen geldige drie unieke resultaten. Probeer opnieuw.');
  }
  const structural = element('p', '3 unieke uitspraken' +
    (checks.source_excluded === true ? ' · Nixon (156133) uitgesloten' : ' · Bronzaak kan zichzelf terugvinden'), 'run-checks');
  const scale = element('p', 'AI-relevantie: 0 niet relevant · 1 zijdelings · 2 bruikbaar · 3 sterk. Zoekscore is de lokale overeenkomstscore.', 'grade-scale');
  const useful = judgments.filter(row => row.grade >= 2).length;
  const summary = element('div', null, 'result-summary');
  summary.append(
    element('h4', `${useful} van de 3 matches bruikbaar`),
    element('p', `${3 - useful} weinig of niet relevant · AI-beoordeling`),
  );
  const gradeLabels = ['Niet relevant', 'Zijdelings', 'Bruikbaar', 'Sterk'];
  const list = element('ol', null, 'judgments');
  judgments.forEach(row => {
    const item = element('li', null, 'judgment');
    const heading = element('div', null, 'judgment-heading');
    heading.append(element('h4', row.title), element('span', `${gradeLabels[row.grade]} · ${row.grade} / 3`, 'grade'));
    item.append(heading);
    item.append(element('p', `Zaak ${row.case_id} · Zoekscore ${Number(row.score).toFixed(4)}`, 'judgment-meta'));
    item.append(element('p', row.reasoning, 'judgment-reason'), element('blockquote', row.quote));
    list.append(item);
  });
  const provenance = element('details', null, 'run-provenance');
  provenance.append(element('summary', 'Rundetails'), structural, scale);
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
  container.replaceChildren(summary, list, provenance);
}

async function runEval(evalRecord, button, status, results) {
  if (running) return;
  running = true;
  document.querySelectorAll('.run-button').forEach(node => { node.disabled = true; });
  button.textContent = 'Bezig…';
  status.hidden = false;
  status.textContent = evalRecord.id === 'B1' ? 'Zoeken en vergelijken met de twee vaste verwachte zaken…' : 'Zoeken en beoordelen… Dit kan even duren. Houd deze pagina open.';
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
    status.textContent = evalRecord.id === 'B1' ? 'Uitgevoerd · vaste referenties, zonder AI-beoordelaar.' : 'Uitgevoerd · AI-beoordeling, geen juridisch keurmerk.';
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
  const section = element('details', null, 'runnable-eval');
  section.id = `run-${evalRecord.id}`;
  const heading = element('summary', null, 'run-heading');
  const title = element('h3', evalRecord.title);
  title.id = `${section.id}-title`;
  section.setAttribute('aria-labelledby', title.id);
  const chevron = element('span', null, 'chevron');
  chevron.setAttribute('aria-hidden', 'true');
  heading.append(title, chevron);
  section.append(heading);
  const content = element('div', null, 'runnable-content');
  const info = element('details', null, 'eval-info');
  const infoToggle = element('summary', 'i');
  infoToggle.setAttribute('aria-label', 'Uitleg en beoordeling van deze eval');
  const explanation = element('div', null, 'eval-info-content');
  if (evalRecord.id === 'B1') {
    explanation.append(
      element('p', 'De twee verwachte zaak-ID’s zijn vooraf vastgelegd en worden zonder AI-beoordelaar met de drie zoekresultaten vergeleken. Hun volgorde mag wisselen; beide moeten gevonden worden.'),
      element('p', 'De derde match is onbeoordeeld. Dit zijn door agents voorgestelde, aan bronpassages gecontroleerde referenties, geen menselijke juridische goldset. Geslaagd zegt alleen dat deze twee vaste doelen zijn gevonden.'),
    );
  } else {
  explanation.append(
    element('p', 'Het systeem zoekt drie uitspraken bij de Engelse vraag. De bronzaak zelf is uitgesloten. AI beoordeelt of elke uitspraak de rechtsvraag beantwoordt; alleen vergelijkbare feiten zijn niet genoeg.'),
    element('p', '0 = niet relevant, 1 = zijdelings, 2 = bruikbaar, 3 = sterk. De samenvatting telt scores 2 en 3 als bruikbaar.'),
    element('p', 'Dit is een AI-beoordeling, zonder door mensen gecontroleerde referentie. Het is geen garantie van juridische juistheid.'),
  );
  }
  info.append(infoToggle, explanation);
  content.append(info);
  const input = element('div', null, 'run-input');
  field(input, 'Input', evalRecord.query, 'run-query');
  input.querySelector('.run-query p').lang = 'en';
  content.append(input);
  if (evalRecord.id === 'B1') {
    field(content, 'Verwachte output', evalRecord.expected_cases.map(row => `${row.title} (${row.case_id})`).join(' en ') + ' binnen de drie resultaten, ongeacht volgorde.', 'run-expectation');
  } else {
    field(content, 'Verwachte output', evalRecord.expected_behavior, 'run-expectation');
  }
  const action = element('div', null, 'run-action');
  const button = element('button', 'Start eval', 'run-button');
  button.type = 'button';
  button.dataset.evalId = evalRecord.id;
  button.setAttribute('aria-label', `Start eval: ${evalRecord.id}`);
  const status = element('p', '', 'run-status');
  status.hidden = true;
  status.id = `${section.id}-status`;
  status.setAttribute('role', 'status');
  button.setAttribute('aria-describedby', status.id);
  const results = element('div', null, 'run-results');
  results.id = `${section.id}-results`;
  results.setAttribute('aria-label', `Resultaten ${evalRecord.id}`);
  button.addEventListener('click', () => runEval(evalRecord, button, status, results));
  action.append(button, status);
  content.append(action, results);
  section.append(content);
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
    const records = ['B1', 'E06'].map(id => catalog.evals.find(row => row.id === id && row.runnable));
    if (records.some(row => !row)) throw new Error('De evals zijn niet beschikbaar');
    runnableList.replaceChildren(...records.map(renderRunnable));
    catalogStatus.hidden = true;
    revealAnchor();
  } catch {
    catalogStatus.textContent = 'Runnen is niet beschikbaar. Open deze pagina via de lokale evalserver.';
    catalogRetry.hidden = false;
  }
}

catalogRetry.addEventListener('click', loadCatalog);
loadCatalog();
