import { createApiClient, createMockClient } from './client';

export function createSearchRuntime(mode?: string, baseUrl = 'http://127.0.0.1:8000', fetcher: typeof fetch = fetch) {
  const isMock = mode === 'mock';
  return { isMock, client: isMock ? createMockClient() : createApiClient(baseUrl, fetcher) };
}
