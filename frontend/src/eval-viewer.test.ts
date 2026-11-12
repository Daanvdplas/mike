// @vitest-environment happy-dom
/// <reference types="node" />
import { expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
const viewerScript = readFileSync('../evals/web/viewer.js', 'utf8');

it('toont alleen B1 en E06 met één methodekeuze en één startknop per eval', async () => {
  document.body.innerHTML = '<p id="catalog-status"></p><button id="catalog-retry"></button><div id="runnable-list"></div>';
  const fixture = JSON.parse(readFileSync('../evals/data/deterministic_b1.json', 'utf8'));
  const expected = fixture.expected_cases;
  const evals = [{id: 'B1', title: fixture.title, input_mode: 'query', query: fixture.query, expected_cases: expected, runnable: true},
    {id: 'E06', title: 'E06', input_mode: 'query', query: 'Exact English question', source_excluded: true, expected_behavior: 'Expected legal issue', runnable: true}];
  const makeRun = (method: string, evalId: string) => {
    const ids = evalId === 'B1' ? (method === 'opinion_chunks' ? [expected[0].case_id, expected[1].case_id, 'other'] : [expected[0].case_id, 'other', 'another']) : ['a', 'b', 'c'];
    const expectations = expected.map((row: any) => ({case_id: row.case_id, title: row.title, found: ids.includes(row.case_id), rank: ids.includes(row.case_id) ? ids.indexOf(row.case_id) + 1 : null}));
    const hitCount = expectations.filter((row: any) => row.found).length;
    return {run_id: `${evalId}-${method}`, eval_id: evalId, status: 'completed', retrieval_method: method,
      structural_checks: {three_unique_results: true, source_excluded: evalId === 'E06'}, judge_status: 'not_requested', judgments: [],
      hit_count: hitCount, expected_count: 2, passed: hitCount === 2, expectations, fixture_version: 'appeal-bond-b1-v2', fixture_sha256: 'fixture-sha',
      input_sha256: 'same-input', corpus_version: 'current-corpus', ranking_version: 'cosine-max-v1', duration_seconds: 1,
      search_response: {results: ids.map(case_id => ({case_id, title: case_id, score: .8, passage: {text: `Exact source ${case_id}.`, source_section: method === 'head_matter' ? 'head_matter' : 'majority'}}))}};
  };
  const fetcher = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/evals') return new Response(JSON.stringify({evals, judge_available: false}));
    const evalId = url.split('/')[3];
    const payload = JSON.parse(String(options!.body));
    return new Response(JSON.stringify({eval_id: evalId, status: 'completed', runs: payload.retrieval_methods.map((method: string) => makeRun(method, evalId)), comparison: {overlap_count: 2}}));
  });
  vi.stubGlobal('fetch', fetcher);
  try {
    new Function(viewerScript)();
    await vi.waitFor(() => expect(document.querySelector('#run-B1')).not.toBeNull());
    expect(document.querySelectorAll('.runnable-eval')).toHaveLength(2);
    expect(document.querySelectorAll('.run-button')).toHaveLength(2);
    expect(document.querySelector('select[aria-label="Evaluatie kiezen"]')).toBeNull();
    expect(document.querySelector('#run-B1-compare')).toBeNull();
    const localJudge = document.querySelector<HTMLInputElement>('#run-E06 input[type="checkbox"]')!;
    expect(localJudge.checked).toBe(false);
    expect(localJudge.disabled).toBe(true);
    expect(document.body.textContent).not.toContain('Andere scenario’s vergelijken');
    for (const evalId of ['B1', 'E06']) {
      const card = document.querySelector<HTMLDetailsElement>(`#run-${evalId}`)!;
      expect(card.open).toBe(false); card.open = true;
      const method = card.querySelector<HTMLSelectElement>(`select[aria-label="Zoekmethode voor ${evalId}"]`)!;
      expect(method).not.toBeNull(); expect(method.options.length).toBe(3); method.value = 'both';
      card.querySelector<HTMLButtonElement>('.run-button')!.click();
      await vi.waitFor(() => expect(card.querySelectorAll('.method-result')).toHaveLength(2));
      const payload = JSON.parse(String(fetcher.mock.calls.at(-1)![1]!.body));
      expect(payload.retrieval_methods).toEqual(['opinion_chunks', 'head_matter']);
      expect(payload.judge).toBe(evalId === 'B1' ? undefined : false);
      card.open = false; card.open = true;
      expect(card.querySelectorAll('.method-result')).toHaveLength(2);
    }
    expect(document.querySelector('#run-B1 .run-results')!.textContent).toContain('Geslaagd — 2 van 2');
    expect(document.querySelector('#run-B1 .run-results')!.textContent).toContain('Niet geslaagd — 1 van 2');
    expect(document.querySelector('#run-B1 input[type="checkbox"]')).toBeNull();
    fetcher.mockImplementationOnce(async () => new Response(JSON.stringify({error: {
      code: 'index_context_mismatch', message: 'Deze index past niet bij B1.', retryable: false,
    }}), {status: 409}));
    const b1Button = document.querySelector<HTMLButtonElement>('#run-B1 .run-button')!;
    b1Button.click();
    await vi.waitFor(() => expect(document.querySelector('#run-B1 .run-status')!.textContent).toContain('Deze index past niet bij B1.'));
    expect(document.querySelector('#run-B1 .run-status')!.textContent).not.toContain('opnieuw proberen');
    expect(b1Button.disabled).toBe(true);
    expect(document.querySelector('#run-B1 .run-results')!.children).toHaveLength(0);
    expect(document.querySelector<HTMLButtonElement>('#run-E06 .run-button')!.disabled).toBe(false);
  } finally { vi.unstubAllGlobals(); }
});

it.each([false, true])('houdt zoekmethode en optioneel beoordelingsmodel gescheiden (catalogusfout: %s)', async (catalogFailed) => {
  document.body.innerHTML = '<p id="catalog-status"></p><button id="catalog-retry"></button><div id="runnable-list"></div><div id="diagnostic-list"></div>';
  const fixture = JSON.parse(readFileSync('../evals/data/deterministic_b1.json', 'utf8'));
  const record = {id: 'E06', title: 'Synthetic E06', input_mode: 'query', query: 'Exact question', source_excluded: true,
    source_case: {id: '156133', name: 'Source case'}, expected_behavior: 'Synthetic expectation', runnable: true};
  const fixed = {id: 'B1', title: fixture.title, input_mode: 'query', query: fixture.query, expected_cases: fixture.expected_cases, runnable: true,
    comparison_variant: {id: 'B1-compare', input_mode: 'query', query: fixture.query, runnable: true}};
  let payload: any;
  let returnedJudgeStatus: string | undefined;
  let incompleteJudgments = false;
  const alternate = 'openai/gpt-4.1-2025-04-14';
  const fetcher = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/evals') return new Response(JSON.stringify({evals: [fixed, record], diagnostic_evals: [record], judge_available: true}));
    if (url === '/api/models') return new Response(JSON.stringify({models: [{id: 'openai/gpt-4.1-mini-2025-04-14', label: 'Mini'}, {id: alternate, label: 'Full'}], default_model: alternate}), {status: catalogFailed ? 503 : 200});
    payload = JSON.parse(String(options!.body));
    return new Response(JSON.stringify({eval_id: 'E06', status: 'completed', runs: payload.retrieval_methods.map((method: string) => ({
      run_id: method, eval_id: 'E06', status: 'completed', retrieval_method: method,
      structural_checks: {three_unique_results: true, source_excluded: true}, judge_status: returnedJudgeStatus ?? (payload.judge ? 'completed' : 'not_requested'),
      requested_model: payload.model, model: payload.judge ? 'gpt-4.1-2025-04-14' : null, duration_seconds: 1,
      search_response: {results: ['a', 'b', 'c'].map(case_id => ({case_id, title: case_id, score: .8, passage: {text: `Exact source ${case_id}.`, source_section: method === 'head_matter' ? 'head_matter' : 'majority'}}))},
      judgments: payload.judge ? (incompleteJudgments ? [] : ['a', 'b', 'c'].map(case_id => ({case_id, grade: 2, reasoning: 'Synthetic judgment.', quote: `Exact source ${case_id}.`}))) : [],
    })), comparison: {overlap_count: 3}}));
  });
  vi.stubGlobal('fetch', fetcher);
  try {
    new Function(viewerScript)();
    await vi.waitFor(() => expect(document.querySelector('#run-E06')).not.toBeNull());
    const card = document.querySelector<HTMLDetailsElement>('#run-E06')!; card.open = true;
    const button = card.querySelector<HTMLButtonElement>('[data-eval-id="E06"]')!;
    const method = card.querySelector<HTMLSelectElement>('select[aria-label="Zoekmethode voor E06"]')!; method.value = 'both';
    const judge = card.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    expect(judge.checked).toBe(true);
    expect(fetcher.mock.calls.some(([url]) => url === '/api/models')).toBe(true);
    expect(fetcher.mock.calls.some(([url]) => url.endsWith('/run'))).toBe(false);
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
    if (!catalogFailed) {
      expect(card.querySelector('.run-results')!.textContent).toContain('gpt-4.1-2025-04-14');
      expect(card.querySelectorAll('.grade')).toHaveLength(6);
      expect(card.querySelector('.judgment-reason')!.textContent).toBe('Synthetic judgment.');
      expect(card.querySelector('blockquote')!.textContent).toBe('Exact source a.');
      for (const status of ['not_requested', 'failed', 'completed']) {
        returnedJudgeStatus = status; incompleteJudgments = status === 'completed';
        button.click();
        await vi.waitFor(() => expect(card.querySelector('.run-status')!.textContent).toContain('Niet uitgevoerd:'));
        expect(card.querySelectorAll('.method-result')).toHaveLength(0);
        expect(card.querySelectorAll('.grade')).toHaveLength(0);
        expect(card.querySelector('.run-status')!.textContent).not.toContain('Uitgevoerd · AI-beoordeling');
      }
    } else {
      expect(card.querySelector('.run-status')!.textContent).toContain('lokale zoekresultaten');
      expect(card.querySelectorAll('.grade')).toHaveLength(0);
    }
    expect(document.querySelector('#run-B1-compare .eval-model-select')).toBeNull();
  } finally { vi.unstubAllGlobals(); }
});
