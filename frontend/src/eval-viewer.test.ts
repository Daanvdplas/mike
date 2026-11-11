// @vitest-environment happy-dom
/// <reference types="node" />
import { expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
const viewerScript = readFileSync('../docs/evals/viewer.js', 'utf8');

it('kiest een scenario en beide zoekmethodes zonder AI-beoordeling', async () => {
  document.body.innerHTML = '<p id="catalog-status"></p><button id="catalog-retry"></button><div id="runnable-list"></div><div id="diagnostic-list"></div>';
  const scenarios = JSON.parse(readFileSync('../docs/evals/scenarios.json', 'utf8')).scenarios;
  const diagnostics = scenarios.map((row: any) => ({...row, query: row.query?.en, query_nl: row.query?.nl,
    document_label: row.document ? 'Volledige meerderheidstekst' : null, source_excluded: true, runnable: true}));
  const fixture = JSON.parse(readFileSync('../docs/evals/deterministic_b1.json', 'utf8'));
  const evals = [{id: 'B1', title: fixture.title, input_mode: 'query', query: fixture.query, expected_cases: fixture.expected_cases, runnable: true,
    comparison_variant: {id: 'B1-compare', input_mode: 'query', query: fixture.query, expected_behavior: 'Geen referentiescore', runnable: true}},
    diagnostics.find((row: any) => row.id === 'E06')];
  const makeRun = (method: string, ids: string[], evalId: string) => ({
    run_id: `test-${method}`, eval_id: evalId, status: 'completed', retrieval_method: method,
    structural_checks: { three_unique_results: true, source_excluded: evalId !== 'B1-compare' }, judge_status: 'not_requested', judgments: [],
    input_sha256: 'same-input', corpus_version: 'same-corpus', ranking_version: 'cosine-max-v1', retrieval_manifest: { embedding: { model: 'same-model' } },
    artifact_name: 'test/result.json', duration_seconds: 1, limitations: ['Geen juridische kwaliteitsmeting.'],
    search_response: { results: ids.map(case_id => ({ case_id, title: `Case ${case_id}`, score: .8, passage: {
      text: `Letterlijke bronpassage ${case_id}.`, source_section: method === 'head_matter' ? 'head_matter' : 'majority',
    } })) },
  });
  const fetcher = vi.fn(async (url: string, _options?: RequestInit) => {
    if (url === '/api/evals') return new Response(JSON.stringify({evals, diagnostic_evals: diagnostics, retrieval_methods: ['opinion_chunks', 'head_matter'], judge_available: false}));
    const evalId = url.split('/')[3];
    if (evalId === 'B1') return new Response(JSON.stringify({error: {message: 'De index wijkt af van de vooraf vastgelegde corpusversie.'}}), {status: 502});
    return new Response(JSON.stringify({run_id: 'test', eval_id: evalId, status: evalId === 'B1-compare' ? 'not_scored' : 'completed', execution_status: 'completed',
      runs: [makeRun('opinion_chunks', ['1', '2', '3'], evalId), makeRun('head_matter', ['2', '3', '4'], evalId)], comparison: {shared_case_ids: ['2', '3'], overlap_count: 2}}));
  });
  vi.stubGlobal('fetch', fetcher);
  try {
    new Function(viewerScript)();
    await vi.waitFor(() => expect(document.querySelector('select[aria-label="Evaluatie kiezen"]')).not.toBeNull());
    const scenarioSelector = document.querySelector<HTMLSelectElement>('select[aria-label="Evaluatie kiezen"]')!;
    expect(scenarioSelector.options.length).toBe(25);
    expect(document.querySelector<HTMLDetailsElement>('#run-B1')!.open).toBe(false);
    expect(document.querySelector<HTMLDetailsElement>('#run-E06')!.open).toBe(false);
    expect(document.querySelector<HTMLSelectElement>('select[aria-label="Zoekmethode voor E06"]')!.options.length).toBe(3);
    const ids = [...document.querySelectorAll('[id]')].map(node => node.id);
    expect(new Set(ids).size).toBe(ids.length);
    scenarioSelector.value = 'E01';
    scenarioSelector.dispatchEvent(new Event('change', {bubbles: true}));
    expect(document.querySelector('#compare-E01')!.textContent).toContain('Alleen document');
    expect(document.querySelector('#compare-E01 .run-query')).toBeNull();
    scenarioSelector.value = 'E11';
    scenarioSelector.dispatchEvent(new Event('change', {bubbles: true}));
    expect(document.querySelector('#compare-E11')!.textContent).toContain('Document + vraag');
    scenarioSelector.value = 'E06';
    scenarioSelector.dispatchEvent(new Event('change', {bubbles: true}));
    expect(document.querySelector('select[aria-label="Zoekmethode voor scenario E06"]')).not.toBeNull();
    const select = document.querySelector<HTMLSelectElement>('select[aria-label="Zoekmethode voor scenario E06"]')!;
    select.value = 'both';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    const judge = document.querySelector<HTMLInputElement>('#compare-E06 input[type="checkbox"]')!;
    expect(judge.checked).toBe(false);
    expect(judge.disabled).toBe(true);
    document.querySelector<HTMLButtonElement>('[data-eval-id="E06"][data-kind="diagnostic"]')!.click();
    await vi.waitFor(() => expect(document.querySelectorAll('#compare-E06 .method-result').length).toBe(2));
    expect(JSON.parse(String(fetcher.mock.calls[1][1]!.body))).toEqual({ retrieval_methods: ['opinion_chunks', 'head_matter'], judge: false });
    expect(document.querySelector('#compare-E06 .comparison-summary')!.textContent).toContain('2 van de 3');
    expect(document.querySelector('#compare-E06 .run-results')!.textContent).toContain('Letterlijke bronpassage 4.');
    expect(document.querySelector('#compare-E06 .run-results')!.textContent).toContain('Head matter (A)');
    expect(document.querySelector('#compare-E06 .run-results')!.textContent).toContain('Oordeelpassages (B)');
    const diagnosticCard = document.querySelector<HTMLDetailsElement>('#compare-E06')!;
    diagnosticCard.open = false; diagnosticCard.open = true;
    expect(document.querySelectorAll('#compare-E06 .method-result')).toHaveLength(2);
    scenarioSelector.value = 'E01'; scenarioSelector.dispatchEvent(new Event('change', {bubbles: true}));
    scenarioSelector.value = 'E06'; scenarioSelector.dispatchEvent(new Event('change', {bubbles: true}));
    expect(document.querySelectorAll('#compare-E06 .method-result')).toHaveLength(2);
    const b1 = document.querySelector<HTMLDetailsElement>('#run-B1')!; b1.open = true;
    const b1Method = document.querySelector<HTMLSelectElement>('select[aria-label="Zoekmethode voor B1-compare"]')!;
    expect(b1Method).not.toBeNull(); expect(document.querySelector('#run-B1-compare input[type="checkbox"]')).toBeNull();
    b1Method.value = 'both'; document.querySelector<HTMLButtonElement>('[data-eval-id="B1-compare"]')!.click();
    await vi.waitFor(() => expect(document.querySelectorAll('#run-B1-compare .method-result')).toHaveLength(2));
    expect(document.querySelector('#run-B1-compare .run-results')!.textContent).not.toContain('Geslaagd');
    document.querySelector<HTMLButtonElement>('[data-eval-id="B1"]')!.click();
    await vi.waitFor(() => expect(document.querySelector('#run-B1-status')!.textContent).toContain('vooraf vastgelegde corpusversie'));
    expect(JSON.parse(String(fetcher.mock.calls.at(-1)![1]!.body))).toEqual({});
    expect(document.querySelectorAll('#run-B1-compare .method-result')).toHaveLength(2);
    expect(document.querySelector('.eval-list')).toBeNull(); expect(document.querySelector('.page-footer')).toBeNull();
  } finally { vi.unstubAllGlobals(); }
});

it.each([false, true])('houdt zoekmethode en optioneel beoordelingsmodel gescheiden (catalogusfout: %s)', async (catalogFailed) => {
  document.body.innerHTML = '<p id="catalog-status"></p><button id="catalog-retry"></button><div id="runnable-list"></div><div id="diagnostic-list"></div>';
  const fixture = JSON.parse(readFileSync('../docs/evals/deterministic_b1.json', 'utf8'));
  const record = {id: 'E06', title: 'Synthetic E06', input_mode: 'query', query: 'Exact question', source_excluded: true,
    source_case: {id: '156133', name: 'Source case'}, expected_behavior: 'Synthetic expectation', runnable: true};
  const fixed = {id: 'B1', title: fixture.title, input_mode: 'query', query: fixture.query, expected_cases: fixture.expected_cases, runnable: true,
    comparison_variant: {id: 'B1-compare', input_mode: 'query', query: fixture.query, runnable: true}};
  let payload: any;
  const alternate = 'openai/gpt-4.1-2025-04-14';
  const fetcher = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/evals') return new Response(JSON.stringify({evals: [fixed, record], diagnostic_evals: [record], judge_available: true}));
    if (url === '/api/models') return new Response(JSON.stringify({models: [{id: 'openai/gpt-4.1-mini-2025-04-14', label: 'Mini'}, {id: alternate, label: 'Full'}], default_model: alternate}), {status: catalogFailed ? 503 : 200});
    payload = JSON.parse(String(options!.body));
    return new Response(JSON.stringify({eval_id: 'E06', status: 'completed', runs: payload.retrieval_methods.map((method: string) => ({
      run_id: method, eval_id: 'E06', status: 'completed', retrieval_method: method,
      structural_checks: {three_unique_results: true, source_excluded: true}, judge_status: payload.judge ? 'completed' : 'not_requested',
      requested_model: payload.model, model: payload.judge ? 'gpt-4.1-2025-04-14' : null, duration_seconds: 1,
      search_response: {results: ['a', 'b', 'c'].map(case_id => ({case_id, title: case_id, score: .8, passage: {text: `Exact source ${case_id}.`, source_section: method === 'head_matter' ? 'head_matter' : 'majority'}}))},
      judgments: payload.judge ? ['a', 'b', 'c'].map(case_id => ({case_id, grade: 2, reasoning: 'Synthetic judgment.', quote: `Exact source ${case_id}.`})) : [],
    })), comparison: {overlap_count: 3}}));
  });
  vi.stubGlobal('fetch', fetcher);
  try {
    new Function(viewerScript)();
    await vi.waitFor(() => expect(document.querySelector('#run-E06')).not.toBeNull());
    const card = document.querySelector<HTMLDetailsElement>('#run-E06')!; card.open = true;
    const button = card.querySelector<HTMLButtonElement>('[data-eval-id="E06"]')!;
    const method = card.querySelector<HTMLSelectElement>('select[aria-label="Zoekmethode voor E06"]')!; method.value = 'both';
    expect(button.disabled).toBe(false);
    expect(fetcher.mock.calls.some(([url]) => url === '/api/models')).toBe(false);
    const judge = card.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    judge.checked = true; judge.dispatchEvent(new Event('change', {bubbles: true}));
    if (catalogFailed) {
      await vi.waitFor(() => expect(card.querySelector('.model-status')!.textContent).toContain('mislukt'));
      expect(button.disabled).toBe(true);
      judge.checked = false; judge.dispatchEvent(new Event('change', {bubbles: true}));
      expect(button.disabled).toBe(false);
    } else {
      await vi.waitFor(() => expect(card.querySelector<HTMLSelectElement>('.eval-model-select')!.options.length).toBe(2));
      card.querySelector<HTMLSelectElement>('.eval-model-select')!.value = alternate;
      expect(button.disabled).toBe(false);
    }
    button.click();
    await vi.waitFor(() => expect(card.querySelectorAll('.method-result')).toHaveLength(2));
    expect(payload.retrieval_methods).toEqual(['opinion_chunks', 'head_matter']);
    expect(payload.judge).toBe(!catalogFailed);
    expect(payload.model).toBe(catalogFailed ? undefined : alternate);
    if (!catalogFailed) expect(card.querySelector('.run-results')!.textContent).toContain('gpt-4.1-2025-04-14');
    expect(document.querySelector('#run-B1-compare .eval-model-select')).toBeNull();
  } finally { vi.unstubAllGlobals(); }
});
