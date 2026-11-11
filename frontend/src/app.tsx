import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { SearchClient } from './client';
import { getPassageParts, validateInput, type CaseDetail, type SearchResponse, type SearchResult } from './search';

interface SelectedDocument { result: SearchResult; corpusVersion: string }

export function App({ client, isMock }: { client: SearchClient; isMock: boolean }) {
  const [query, setQuery] = useState('');
  const [document, setDocument] = useState<File>();
  const [response, setResponse] = useState<SearchResponse>();
  const [selected, setSelected] = useState<SelectedDocument | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadButton = useRef<HTMLButtonElement>(null);
  const pending = useRef(false);
  const restoreInputFocus = useRef(false);
  const readerOpener = useRef<HTMLButtonElement | null>(null);
  const resultsScroll = useRef(0);

  useEffect(() => {
    if (busy || !restoreInputFocus.current) return;
    if (window.document.activeElement === window.document.body) textarea.current?.focus();
    restoreInputFocus.current = false;
  }, [busy]);
  useEffect(() => {
    if (!selected && readerOpener.current) {
      readerOpener.current.focus({ preventScroll: true });
      window.scrollTo(0, resultsScroll.current);
      readerOpener.current = null;
    }
  }, [selected]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current) return;
    const input = { query, document };
    try { validateInput(input); }
    catch (cause) { setError(message(cause)); textarea.current?.focus(); return; }
    restoreInputFocus.current = event.currentTarget.contains(window.document.activeElement);
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      setResponse(await client.search(input));
      setQuery('');
      setDocument(undefined);
      if (fileInput.current) fileInput.current.value = '';
      if (textarea.current) textarea.current.style.height = '';
    } catch (cause) {
      setError(message(cause));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <>
    <header className="app-header"><img className="app-logo" src="/mike-wordmark.svg" alt="Mike" /></header>
    <main className="workspace" hidden={Boolean(selected)}>
      <section className="intro" aria-labelledby="intro-title">
        <h1 id="intro-title">Welke uitspraken zoek je?</h1>
      </section>
      <div className="composer-area">
        <p className="status" role="status" aria-live="polite">{busy ? (isMock ? 'Voorbeeldzaken ophalen…' : 'Uitspraken zoeken…') : response ? (isMock ? 'Drie voorbeeldzaken beschikbaar.' : 'Drie uitspraken beschikbaar.') : ''}</p>
        <p className="error" role="alert" hidden={!error}>{error}</p>
        <form className="composer" noValidate onSubmit={submit} aria-busy={busy}>
          <label className="visually-hidden" htmlFor="query">Vraag of tekst</label>
          <textarea id="query" ref={textarea} rows={3} value={query} disabled={busy} placeholder="Typ je vraag of plak hier tekst…" aria-invalid={Boolean(error)}
            onInput={(event) => {
              setQuery(event.currentTarget.value);
              if (!document) setError('');
              event.currentTarget.style.height = 'auto';
              event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 220)}px`;
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }} />
          {document ? <div className="attachment"><span className="attachment-name">{document.name}</span><button className="remove-file" type="button" disabled={busy} aria-label="Bijlage verwijderen" onClick={() => {
            setDocument(undefined); setError('');
            if (fileInput.current) fileInput.current.value = '';
            uploadButton.current?.focus();
          }}>×</button></div> : null}
          <div className="composer-actions">
            <button className="upload-button" ref={uploadButton} disabled={busy} type="button" onClick={() => fileInput.current?.click()}><span aria-hidden="true">＋</span> Document toevoegen</button>
            <input id="document" ref={fileInput} className="visually-hidden" type="file" accept=".pdf,.txt,application/pdf,text/plain" tabIndex={-1} aria-label="Document kiezen" disabled={busy} onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              setDocument(file); setError('');
              if (file) { try { validateInput({ document: file }); } catch (cause) { setError(message(cause)); } }
            }} />
            <button className="send-button" type="submit" disabled={busy}>{busy ? 'Even geduld' : 'Versturen'} <span aria-hidden="true">↑</span></button>
          </div>
        </form>
      </div>
      {response ? <section className="answer" aria-labelledby="results-title">
        <h2 id="results-title" className="answer-title">Drie uitspraken</h2>
        {isMock ? <p className="answer-note">Voorbeeldresultaten, geen analyse van je invoer.</p> : null}
        <ol className="case-list">
          {response.results.map((result, index) => <li key={result.case_id} className="case-item">
            <button className="case-button" type="button" aria-label={`${result.title} — volledig document bekijken`} onClick={(event) => {
              readerOpener.current = event.currentTarget;
              resultsScroll.current = window.scrollY;
              setSelected({ result, corpusVersion: response.corpus_version });
            }}>
              <span className="page-heading"><DocumentEmblem /><span>Uitspraak {index + 1}</span></span>
              <span className="case-title">{result.title}</span>
              <span className="case-meta">{formatDate(result.decision_date)}<br />{result.citation}</span>
              <span className="preview-label">Gevonden passage</span>
              <span className="preview-passage">{result.passage.text}</span>
              <span className="case-open">Volledig document <span aria-hidden="true">↗</span></span>
            </button>
          </li>)}
        </ol>
      </section> : null}
    </main>
    {selected ? <DocumentReader key={selected.result.case_id} selected={selected} client={client} isMock={isMock} onClose={() => setSelected(null)} /> : null}
  </>;
}

function DocumentEmblem() {
  return <svg className="document-emblem" width="24" height="28" viewBox="0 0 24 28" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true"><path d="M4 1.5h10l6 6v19H4z" /><path d="M14 1.5v6h6M8 13h8M8 17h8M8 21h5" /></svg>;
}

function DocumentReader({ selected, client, isMock, onClose }: { selected: SelectedDocument; client: SearchClient; isMock: boolean; onClose: () => void }) {
  const [detail, setDetail] = useState<CaseDetail>();
  const [error, setError] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  const { result, corpusVersion } = selected;
  useEffect(() => {
    let cancelled = false;
    heading.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
    async function load() {
      try {
        const source = await client.getCase(result.case_url);
        getPassageParts(corpusVersion, result, source);
        if (!cancelled) setDetail(source);
      } catch (cause) { if (!cancelled) setError(message(cause)); }
    }
    void load();
    return () => { cancelled = true; };
  }, [client, corpusVersion, result]);
  const parts = detail ? getPassageParts(corpusVersion, result, detail) : undefined;
  return <main className="reader" aria-labelledby="reader-title">
    <nav className="reader-nav" aria-label="Document"><button className="reader-back" type="button" onClick={onClose}><span aria-hidden="true">←</span> Terug naar resultaten</button></nav>
    <div className="reader-heading"><DocumentEmblem /><div><h1 id="reader-title" ref={heading} tabIndex={-1}>{result.title}</h1><p className="source-meta">{result.court} · {formatDate(result.decision_date)} · {result.citation}</p></div></div>
    {error ? <p className="error" role="alert">{error}</p> : !detail ? <p role="status">Document ophalen…</p> : null}
    {detail && parts ? <>
      <section className="document-reason" aria-labelledby="reason-title">
        <h2 id="reason-title">Waarom dit document?</h2>
        <p>{isMock ? 'Dit voorbeeldresultaat verwijst naar de onderstaande bronpassage.' : 'De zoekmethode vond de beste tekstovereenkomst binnen deze uitspraak in de onderstaande passage.'}</p>
        <blockquote className="why-passage">{result.passage.text}</blockquote>
        <p className="source-meta">Overeenkomstscore: {result.score.toLocaleString('nl-NL', { maximumFractionDigits: 3 })}</p>
      </section>
      <article className="document-text" aria-labelledby="document-title"><h2 id="document-title">Volledige meerderheidstekst</h2><div className="opinion">{parts.before}<mark>{parts.match}</mark>{parts.after}</div></article>
    </> : null}
  </main>;
}

function message(cause: unknown) { return cause instanceof Error ? cause.message : 'Verbinding mislukt. Probeer het opnieuw.'; }
function formatDate(value: string) { return new Intl.DateTimeFormat('nl-NL', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`)); }
