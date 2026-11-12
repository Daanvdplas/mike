import { expect, it } from 'vitest';
import { createSearchRuntime } from './runtime';
import fixtureResponse from '../../fixtures/api/search-response.json';

it('kiest zonder modus de echte API en verstuurt de eigen vraag naar die backend', async () => {
  let requestedUrl = '';
  let submittedQuery: FormDataEntryValue | null = null;
  const runtime = createSearchRuntime(undefined, 'http://127.0.0.1:8000', async (url, init) => {
    requestedUrl = String(url);
    submittedQuery = (init?.body as FormData).get('query');
    return new Response(JSON.stringify(fixtureResponse));
  });
  expect(runtime.isMock).toBe(false);
  await runtime.client.search({ query: 'My own question' });
  expect(requestedUrl).toBe('http://127.0.0.1:8000/api/search');
  expect(submittedQuery).toBe('My own question');
});

it('gebruikt fixtures uitsluitend bij de expliciete modus mock', () => {
  expect(createSearchRuntime('mock').isMock).toBe(true);
  expect(createSearchRuntime('api').isMock).toBe(false);
  expect(createSearchRuntime('onbekend').isMock).toBe(false);
});

it('geeft een netwerk- of backendfout door zonder terug te vallen op fixtures', async () => {
  const disconnected = createSearchRuntime(undefined, undefined, async () => { throw new TypeError('Backend niet bereikbaar'); });
  await expect(disconnected.client.search({ query: 'My question' })).rejects.toThrow('Backend niet bereikbaar');
  const unavailable = createSearchRuntime(undefined, undefined, async () => new Response(JSON.stringify({ error: { message: 'Index niet gereed' } }), { status: 503 }));
  await expect(unavailable.client.search({ query: 'My question' })).rejects.toThrow('Index niet gereed');
});
