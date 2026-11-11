// @vitest-environment happy-dom
/// <reference types="node" />
import { expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
const viewerScript = readFileSync('../docs/evals/viewer.js', 'utf8');

it('kiest een scenario en beide zoekmethodes zonder AI-beoordeling', async () => {
  document.body.innerHTML = '<p id="catalog-status"></p><button id="catalog-retry"></button><div id="runnable-list"></div>';
  const scenarios = JSON.parse(readFileSync('../docs/evals/scenarios.json', 'utf8')).scenarios;
  const evals = [{id: 'relevance', title: 'Algemene relevantie', input_mode: 'combined', query: 'Demo question',
    source_case: {name: 'Demo source', id: 'demo'}, expected_behavior: 'Zoek', why: 'Demo', runnable: true},
    ...scenarios.map((row: any) => ({...row, query: row.query?.en, query_nl: row.query?.nl,
      document_label: row.document ? 'Volledige meerderheidstekst' : null, source_excluded: true, runnable: true}))];
  const makeRun = (method: string, ids: string[]) => ({
    run_id: `test-${method}`, eval_id: 'E06', status: 'completed', retrieval_method: method,
    structural_checks: { three_unique_results: true, source_excluded: true }, judge_status: 'not_requested', judgments: [],
    input_sha256: 'same-input', corpus_version: 'same-corpus', ranking_version: 'cosine-max-v1', retrieval_manifest: { embedding: { model: 'same-model' } },
    artifact_name: 'test/result.json', duration_seconds: 1, limitations: ['Geen juridische kwaliteitsmeting.'],
    search_response: { results: ids.map(case_id => ({ case_id, title: `Case ${case_id}`, score: .8, passage: {
      text: `Letterlijke bronpassage ${case_id}.`, source_section: method === 'head_matter' ? 'head_matter' : 'majority',
    } })) },
  });
  const fetcher = vi.fn(async (url: string, options?: RequestInit) => new Response(JSON.stringify(url === '/api/evals'
    ? { evals, retrieval_methods: ['opinion_chunks', 'head_matter'], judge_available: false }
    : { run_id: 'test', eval_id: 'E06', status: 'completed', runs: [makeRun('opinion_chunks', ['1', '2', '3']), makeRun('head_matter', ['2', '3', '4'])],
      comparison: { shared_case_ids: ['2', '3'], overlap_count: 2 } })));
  vi.stubGlobal('fetch', fetcher);
  try {
    new Function(viewerScript)();
    await vi.waitFor(() => expect(document.querySelector('select[aria-label="Evaluatie kiezen"]')).not.toBeNull());
    const scenarioSelector = document.querySelector<HTMLSelectElement>('select[aria-label="Evaluatie kiezen"]')!;
    expect(scenarioSelector.options.length).toBe(26);
    scenarioSelector.value = 'E01';
    scenarioSelector.dispatchEvent(new Event('change', {bubbles: true}));
    expect(document.querySelector('#run-E01')!.textContent).toContain('Alleen document');
    expect(document.querySelector('#run-E01 .run-query')).toBeNull();
    scenarioSelector.value = 'E11';
    scenarioSelector.dispatchEvent(new Event('change', {bubbles: true}));
    expect(document.querySelector('#run-E11')!.textContent).toContain('Document + vraag');
    scenarioSelector.value = 'E06';
    scenarioSelector.dispatchEvent(new Event('change', {bubbles: true}));
    expect(document.querySelector('select[aria-label="Zoekmethode voor E06"]')).not.toBeNull();
    const select = document.querySelector<HTMLSelectElement>('select[aria-label="Zoekmethode voor E06"]')!;
    select.value = 'both';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    const judge = document.querySelector<HTMLInputElement>('#run-E06 input[type="checkbox"]')!;
    expect(judge.checked).toBe(false);
    expect(judge.disabled).toBe(true);
    document.querySelector<HTMLButtonElement>('[data-eval-id="E06"]')!.click();
    await vi.waitFor(() => expect(document.querySelectorAll('#run-E06 .method-result').length).toBe(2));
    expect(JSON.parse(String(fetcher.mock.calls[1][1]!.body))).toEqual({ retrieval_methods: ['opinion_chunks', 'head_matter'], judge: false });
    expect(document.querySelector('#run-E06 .comparison-summary')!.textContent).toContain('2 van de 3');
    expect(document.querySelector('#run-E06 .run-results')!.textContent).toContain('Letterlijke bronpassage 4.');
    expect(document.querySelector('#run-E06 .run-results')!.textContent).toContain('Head matter (A)');
    expect(document.querySelector('#run-E06 .run-results')!.textContent).toContain('Oordeelpassages (B)');
  } finally { vi.unstubAllGlobals(); }
});
