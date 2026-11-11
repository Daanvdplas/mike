import fixtureResponse from '../../docs/examples/search-response.json';
import fixtureCases from '../../docs/examples/cases.json';
import { validateInput, type CaseDetail, type ModelCatalog, type SearchInput, type SearchResponse } from './search';

export interface SearchClient {
  search(input: SearchInput): Promise<SearchResponse>;
  getCase(caseUrl: string): Promise<CaseDetail>;
  getModels?(): Promise<ModelCatalog | null>;
}

export function createMockClient(delay = 650): SearchClient {
  return {
    async search(input) {
      const { mode } = validateInput(input);
      await new Promise((resolve) => setTimeout(resolve, delay));
      return { ...structuredClone(fixtureResponse), mode };
    },
    async getCase(caseUrl) {
      const detail = fixtureCases.find((item) => caseUrl === `/api/cases/${encodeURIComponent(item.case_id)}`);
      if (!detail) throw new Error('Deze uitspraak is niet gevonden.');
      return structuredClone(detail);
    },
  };
}

export function createApiClient(baseUrl: string, fetcher: typeof fetch = fetch): SearchClient {
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetcher(`${baseUrl.replace(/\/$/, '')}${path}`, init);
    const body = await response.json();
    if (!response.ok) throw new Error(body.error?.message || 'Het verzoek is mislukt. Probeer het opnieuw.');
    return body as T;
  }
  return {
    async search(input) {
      const { query, document } = validateInput(input);
      const form = new FormData();
      if (query) form.append('query', query);
      if (document) form.append('document', document);
      return request<SearchResponse>('/api/search', {
        method: 'POST', body: form,
        ...(input.model ? { headers: { 'X-Orq-Model': input.model } } : {}),
      });
    },
    getCase: (caseUrl) => request<CaseDetail>(caseUrl),
    async getModels() {
      const response = await fetcher(`${baseUrl.replace(/\/$/, '')}/api/models`);
      if (response.status === 404) return null;
      if (!response.ok) throw new Error('Modelkeuze is niet beschikbaar. Zoeken gebruikt de serverinstelling.');
      const catalog = await response.json() as ModelCatalog;
      if (!Array.isArray(catalog.models) || (catalog.models.length && !catalog.models.some(model => model.id === catalog.default_model))) {
        throw new Error('De server geeft geen geldige modelkeuze.');
      }
      return catalog;
    },
  };
}
