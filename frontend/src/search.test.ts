import { describe, expect, it } from 'vitest';
import { getPassageParts, validateInput } from './search';
import { createMockClient, createApiClient } from './client';
import cases from '../../docs/examples/cases.json';
import response from '../../docs/examples/search-response.json';

const txt = new File(['eigen inhoud'], 'mijn zaak.txt', { type: 'text/plain' });

describe('invoer', () => {
  it('vereist tekst of een document', () => {
    expect(() => validateInput({ query: '  ' })).toThrow('Typ');
  });
  it('ondersteunt tekst, document en beide', () => {
    expect(validateInput({ query: ' vraag ' })).toEqual({ query: 'vraag', mode: 'query' });
    expect(validateInput({ query: '', document: txt }).mode).toBe('document');
    expect(validateInput({ query: 'vraag', document: txt }).mode).toBe('combined');
  });
  it('weigert een ongeldig bestand ook met geldige tekst', () => {
    expect(() => validateInput({ query: 'vraag', document: new File(['x'], 'bestand.exe') })).toThrow('PDF');
  });
  it('weigert lege en te grote bestanden', () => {
    expect(() => validateInput({ document: new File([], 'leeg.txt') })).toThrow('leeg');
    expect(() => validateInput({ document: new File([new Uint8Array(10485761)], 'groot.pdf') })).toThrow('10 MiB');
  });
});

describe('bronmarkering', () => {
  it('markeert head matter met zijn eigen tekstversie en laat de meerderheidstekst apart', () => {
    const text = 'Redactioneel voorwerk: getuigenverklaring.';
    const result = { ...response.results[0], passage: {
      passage_id: 'head-1', text, start_utf16: 0, end_utf16: text.length,
      source_section: 'head_matter' as const, text_version: 'head-version',
    } };
    const detail = { ...cases[0], head_matter: text, head_matter_text_version: 'head-version' };
    expect(getPassageParts(response.corpus_version, result, detail)).toEqual({ before: '', match: text, after: '' });
    expect(() => getPassageParts(response.corpus_version, result, { ...detail, head_matter_text_version: 'oud' })).toThrow('opnieuw');
    expect(() => getPassageParts(response.corpus_version, result, cases[0])).toThrow('opnieuw');
  });
  it('markeert de exacte UTF-16-passage na Unicode in alle drie documenten', () => {
    for (const result of response.results) {
      const detail = cases.find((item) => item.case_id === result.case_id)!;
      const parts = getPassageParts(response.corpus_version, result, detail);
      expect(parts.match).toBe(result.passage.text);
      expect(parts.before + parts.match + parts.after).toBe(detail.text);
    }
  });
  it('weigert oude corpus- en tekstversies en onjuiste posities', () => {
    const result = response.results[0];
    expect(() => getPassageParts('oud', result, cases[0])).toThrow('opnieuw');
    expect(() => getPassageParts(response.corpus_version, result, { ...cases[0], text_version: 'oud' })).toThrow('opnieuw');
    expect(() => getPassageParts(response.corpus_version, { ...result, passage: { ...result.passage, start_utf16: 0 } }, cases[0])).toThrow('passage');
  });
});

describe('lokale simulatie en API-grens', () => {
  it('houdt de gewone zoekbackend zonder modelcatalogus ondersteund', async () => {
    const client = createApiClient('http://127.0.0.1:8000', async () => new Response('{}', { status: 404 }));
    expect(await client.getModels!()).toBeNull();
  });

  it('gebruikt de optionele B-default op de bestaande proxy en behoudt upload en modelheader', async () => {
    let request: RequestInit | undefined;
    const client = createApiClient('http://127.0.0.1:18000', async (_url, init) => {
      request = init;
      if ((init?.body as FormData).has('retrieval_method')) return new Response(JSON.stringify({error: {message: 'Onbekend veld'}}), {status: 400});
      return new Response(JSON.stringify(response), { status: 200 });
    });
    await client.search({ query: 'vraag', document: txt, model: 'catalog/test-model' });
    expect(request?.headers).toEqual({ 'X-Orq-Model': 'catalog/test-model' });
    expect([...(request?.body as FormData).keys()]).toEqual(['query', 'document']);
    expect((request?.body as FormData).get('document')).toBeInstanceOf(File);
    await expect(client.search({query: 'vraag', retrieval_method: 'opinion_chunks'})).resolves.toMatchObject({results: response.results});
  });

  it('stuurt de gekozen zoekmethode mee en weigert een stille terugval naar oordeelpassages', async () => {
    const bodies: FormData[] = [];
    const headers: (HeadersInit | undefined)[] = [];
    let returnedMethod = 'head_matter';
    const client = createApiClient('http://127.0.0.1:8000', async (_url, init) => {
      bodies.push(init!.body as FormData);
      headers.push(init!.headers);
      return new Response(JSON.stringify({ ...response, retrieval_method: returnedMethod }));
    });
    const actual = await client.search({ query: 'vraag', retrieval_method: 'head_matter', model: 'catalog/selected-model' });
    expect(bodies[0].get('retrieval_method')).toBe('head_matter');
    expect(actual.retrieval_method).toBe('head_matter');
    expect(headers[0]).toEqual({ 'X-Orq-Model': 'catalog/selected-model' });
    expect(bodies[0].get('model')).toBeNull();
    returnedMethod = 'opinion_chunks';
    await expect(client.search({ query: 'vraag', retrieval_method: 'head_matter' })).rejects.toThrow('zoekmethode');
  });

  it('doet in de expliciete mockmodus geen alsof-headmatterzoekactie', async () => {
    await expect(createMockClient(0).search({ query: 'vraag', retrieval_method: 'head_matter' })).rejects.toThrow('voorbeeldmodus');
  });
  it('geeft in elke invoermodus exact drie unieke fixturezaken en passende details', async () => {
    const client = createMockClient(0);
    for (const input of [{ query: 'vraag' }, { document: txt }, { query: 'vraag', document: txt }]) {
      const actual = await client.search(input);
      expect(actual.mode).toBe(validateInput(input).mode);
      expect(new Set(actual.results.map((result) => result.case_id)).size).toBe(3);
      for (const result of actual.results) {
        const detail = await client.getCase(result.case_url);
        expect(getPassageParts(actual.corpus_version, result, detail).match).toBe(result.passage.text);
      }
    }
  });
  it('verstuurd multipart zonder eigen Content-Type naar configureerbare API', async () => {
    const requests: { url: string; init?: RequestInit }[] = [];
    const fetcher: typeof fetch = async (url, init) => {
      requests.push({ url: String(url), init });
      return new Response(JSON.stringify(response), { status: 200 });
    };
    const client = createApiClient('http://127.0.0.1:8000/', fetcher);
    await client.search({ query: ' vraag ', document: txt });
    expect(requests[0].url).toBe('http://127.0.0.1:8000/api/search');
    expect(requests[0].init?.headers).toBeUndefined();
    const form = requests[0].init?.body as FormData;
    expect(form.get('query')).toBe('vraag');
    expect(form.get('document')).toBeInstanceOf(File);
  });
  it('toont de backendfout en gebruikt de case_url voor volledige tekst', async () => {
    let requested = '';
    const client = createApiClient('http://127.0.0.1:8000', async (url) => {
      requested = String(url);
      return new Response(JSON.stringify({ error: { message: 'Index nog niet gereed.' } }), { status: 503 });
    });
    await expect(client.getCase('/api/cases/abc')).rejects.toThrow('Index nog niet gereed.');
    expect(requested).toBe('http://127.0.0.1:8000/api/cases/abc');
  });
});
