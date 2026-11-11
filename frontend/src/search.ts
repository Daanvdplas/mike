export type RetrievalMethod = 'opinion_chunks' | 'head_matter';
export interface SearchInput { query?: string; document?: File; retrieval_method?: RetrievalMethod }
export interface CaseMetadata {
  case_id: string; title: string; court: string; decision_date: string; citation: string; text_version: string;
}
export interface SearchResult extends CaseMetadata {
  score: number; case_url: string;
  passage: { passage_id: string; text: string; start_utf16: number; end_utf16: number;
    source_section?: 'majority' | 'head_matter'; text_version?: string };
  explanation?: {
    text: string;
    citations: { passage_id: string; quote: string }[];
    input_citations?: { quote: string; start_utf16: number; end_utf16: number }[];
    limitations: string[];
  };
}
export interface SearchResponse {
  mode: 'query' | 'document' | 'combined'; corpus_version: string; ranking_version: string; results: SearchResult[];
  explanation_status?: 'available' | 'unavailable';
  retrieval_method?: RetrievalMethod;
  input_context?: { text_version: string; utf16_length: number };
}
export interface CaseDetail extends CaseMetadata {
  corpus_version: string; text: string; head_matter?: string; head_matter_text_version?: string;
}
export function validateInput(input: SearchInput): SearchInput & { query: string; mode: SearchResponse['mode'] } {
  const query = input.query?.trim() ?? '';
  const document = input.document;
  if (document) {
    if (!/\.(pdf|txt)$/i.test(document.name)) throw new Error('Kies een PDF- of TXT-bestand.');
    if (document.size > 10 * 1024 * 1024) throw new Error('Het bestand mag maximaal 10 MiB zijn.');
    if (document.size === 0) throw new Error('Dit bestand is leeg. Kies een ander bestand.');
  }
  if (!query && !document) throw new Error('Typ of plak tekst, of voeg een document toe.');
  return { ...input, query, mode: document ? (query ? 'combined' : 'document') : 'query' };
}
export function getPassageParts(corpusVersion: string, result: SearchResult, detail: CaseDetail): { before: string; match: string; after: string } {
  if (corpusVersion !== detail.corpus_version || result.text_version !== detail.text_version) {
    throw new Error('De brontekst is gewijzigd. Verstuur je zoekopdracht opnieuw.');
  }
  const { start_utf16: start, end_utf16: end, text } = result.passage;
  const section = result.passage.source_section ?? 'majority';
  const source = section === 'head_matter' ? detail.head_matter : detail.text;
  const version = section === 'head_matter' ? detail.head_matter_text_version : detail.text_version;
  if ((section !== 'majority' && section !== 'head_matter') || source === undefined ||
      (section === 'head_matter' && !result.passage.text_version) ||
      (result.passage.text_version !== undefined && result.passage.text_version !== version)) {
    throw new Error('De brontekst is gewijzigd. Verstuur je zoekopdracht opnieuw.');
  }
  if (result.case_id !== detail.case_id || !Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > source.length || source.slice(start, end) !== text) {
    throw new Error('De gevonden passage past niet bij deze brontekst. Verstuur je zoekopdracht opnieuw.');
  }
  return { before: source.slice(0, start), match: source.slice(start, end), after: source.slice(end) };
}
