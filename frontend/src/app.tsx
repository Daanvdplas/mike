import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { SearchClient } from './client';
import { getPassageParts, validateInput, type CaseDetail, type SearchResponse, type SearchResult } from './search';

interface Turn { id: number; query: string; filename?: string; response?: SearchResponse }

export function App({ client, isMock }: { client: SearchClient; isMock: boolean }) {
  const [query, setQuery] = useState('');
  const [document, setDocument] = useState<File>();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadButton = useRef<HTMLButtonElement>(null);
  const pending = useRef(false);
  const nextId = useRef(0);
  const restoreInputFocus = useRef(false);
  useEffect(() => {
    if (busy || !restoreInputFocus.current) return;
    if (window.document.activeElement === window.document.body) textarea.current?.focus();
    restoreInputFocus.current = false;
  }, [busy]);

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
    const id = ++nextId.current;
    setTurns((previous) => [...previous, { id, query: query.trim(), filename: document?.name }]);
    try {
      const response = await client.search(input);
      setTurns((previous) => previous.map((turn) => turn.id === id ? { ...turn, response } : turn));
      setQuery('');
      setDocument(undefined);
      if (fileInput.current) fileInput.current.value = '';
      if (textarea.current) textarea.current.style.height = '';
    } catch (cause) {
      setTurns((previous) => previous.filter((turn) => turn.id !== id));
      setError(message(cause));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <>
    <header className="app-header">Mike</header>
    <main className="workspace">
      <section className="intro" aria-labelledby="intro-title" hidden={turns.length > 0}>
        <h1 id="intro-title">Welke uitspraken zoek je?</h1>
      </section>
      <section className="conversation" aria-label="Gesprek">
        {turns.map((turn) => <article key={turn.id} className="turn">
          <div className="user-message">
            <span className="visually-hidden">Jij: </span>
            {turn.filename ? <p className="user-file">Bijlage: {turn.filename}</p> : null}
            {turn.query ? <p className="user-text">{turn.query}</p> : null}
          </div>
          {turn.response ? <section className="answer">
            <h2 className="answer-title">{isMock ? 'Drie voorbeeldzaken' : 'Drie uitspraken'}</h2>
            {isMock ? <p className="answer-note">Vaste, verzonnen resultaten om de interface te proberen.</p> : null}
            <ol className="case-list">
              {turn.response.results.map((result) => <CaseResult key={result.case_id} id={`case-${turn.id}-${result.case_id}`} result={result} response={turn.response!} client={client} />)}
            </ol>
          </section> : null}
        </article>)}
      </section>
      <div className="composer-area">
        <p className="status" role="status" aria-live="polite">{busy ? (isMock ? 'Voorbeeldzaken ophalen…' : 'Uitspraken zoeken…') : turns.length ? (isMock ? 'Drie voorbeeldzaken beschikbaar.' : 'Drie uitspraken beschikbaar.') : ''}</p>
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
    </main>
  </>;
}

function CaseResult({ id, result, response, client }: { id: string; result: SearchResult; response: SearchResponse; client: SearchClient }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<CaseDetail>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function toggle() {
    setOpen(!open);
    if (open || detail || loading) return;
    setLoading(true); setError('');
    try {
      const source = await client.getCase(result.case_url);
      getPassageParts(response.corpus_version, result, source);
      setDetail(source);
    } catch (cause) { setError(message(cause)); }
    finally { setLoading(false); }
  }
  const parts = detail ? getPassageParts(response.corpus_version, result, detail) : undefined;
  return <li className="case-item">
    <button className="case-button" type="button" aria-expanded={open} aria-controls={id} onClick={toggle}>
      <span className="case-summary"><span className="case-title">{result.title}</span><span className="case-meta">{result.citation} · {formatDate(result.decision_date)}</span></span>
      <span className="case-open">{open ? 'Sluiten ↑' : 'Lezen →'}</span>
    </button>
    <section className="case-detail" id={id} hidden={!open}>
      {loading ? <p role="status">Document ophalen…</p> : null}
      {error ? <p className="error" role="alert">{error}</p> : null}
      {detail && parts ? <>
        <h3>Volledige meerderheidstekst</h3>
        <p className="source-meta">{detail.court} · {formatDate(detail.decision_date)} · {detail.citation}</p>
        <p className="source-meta">Overeenkomstscore: {result.score.toLocaleString('nl-NL', { maximumFractionDigits: 3 })} · geen juridische zekerheid</p>
        <div className="opinion">{parts.before}<mark>{parts.match}</mark>{parts.after}</div>
      </> : null}
    </section>
  </li>;
}

function message(cause: unknown) { return cause instanceof Error ? cause.message : 'Verbinding mislukt. Probeer het opnieuw.'; }
function formatDate(value: string) { return new Intl.DateTimeFormat('nl-NL', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`)); }
