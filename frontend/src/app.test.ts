// @vitest-environment happy-dom
import { beforeEach, expect, it, vi } from 'vitest';
import { App } from './app';
import { createRoot } from 'react-dom/client';
import { createElement, act } from 'react';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
async function mountApp(root: HTMLElement, client: ReturnType<typeof createMockClient>, isMock: boolean) {
  await act(async () => { createRoot(root).render(createElement(App, { client, isMock })); });
}
import { createMockClient } from './client';

beforeEach(() => { document.body.innerHTML = '<div id="app"></div>'; });

it('kiest een catalogusmodel en toont het werkelijk teruggegeven model', async () => {
  const mock = createMockClient(0);
  const search = vi.fn(async (input) => ({ ...await mock.search(input), explanation_requested_model: input.model, explanation_model: 'provider/actual-model' }));
  await mountApp(document.querySelector('#app')!, {
    ...mock,
    getModels: async () => ({ models: [{ id: 'catalog/first', label: 'Eerste model' }, { id: 'catalog/second', label: 'Tweede model' }], default_model: 'catalog/first' }),
    search,
  }, false);
  const select = document.querySelector<HTMLSelectElement>('#explanation-model');
  expect(select).not.toBeNull();
  await act(async () => {
    select!.value = 'catalog/second'; select!.dispatchEvent(new Event('change', { bubbles: true }));
    const textarea = document.querySelector('textarea')!;
    textarea.value = 'Mijn vraag'; textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => { document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
  await vi.waitFor(() => expect(search).toHaveBeenCalledWith(expect.objectContaining({ model: 'catalog/second' })));
  await vi.waitFor(() => expect(document.querySelector('.answer-model')?.textContent).toContain('provider/actual-model'));
});

it('verstuurt eigen tekst, toont drie uitspraken en opent de volledige gemarkeerde bron', async () => {
  await mountApp(document.querySelector('#app')!, createMockClient(0), true);
  const textarea = document.querySelector('textarea')!;
  expect(textarea).not.toBeNull();
  await act(async () => {
    textarea.value = 'Mijn eigen vraag over bewijs';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => { document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); await new Promise(resolve => setTimeout(resolve, 10)); });
  await vi.waitFor(() => expect(document.querySelectorAll('.case-button')).toHaveLength(3));
  const results = document.querySelector('.answer')!;
  expect(document.querySelector('form')!.compareDocumentPosition(results) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  await act(async () => { (document.querySelector('.case-button') as HTMLButtonElement).click(); });
  await vi.waitFor(() => expect(document.querySelector('mark')?.textContent).toContain('Witness testimony'));
  expect(document.querySelector('.opinion')?.textContent).toContain('This invented ending');
  expect(document.querySelector('.reader')).not.toBeNull();
  expect(document.querySelector('.why-passage')).toBeNull();
  await act(async () => { document.querySelector<HTMLButtonElement>('.reader-back')!.click(); });
  expect(document.querySelector('.reader')).toBeNull();
  expect(document.activeElement).toBe(document.querySelector('.case-button'));
  expect(document.querySelector('textarea')?.value).toBe('');
});

it('houdt de invoer beschikbaar bij lege invoer en een mislukte zoekopdracht', async () => {
  await mountApp(document.querySelector('#app')!, { ...createMockClient(0), search: async () => { throw new Error('Tijdelijk niet bereikbaar.'); } }, true);
  const form = document.querySelector('form')!;
  expect(form).not.toBeNull();
  await act(async () => { form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('Typ');
  const textarea = document.querySelector('textarea')!;
  await act(async () => { textarea.value = 'Opnieuw proberen'; textarea.dispatchEvent(new Event('input', { bubbles: true })); });
  await act(async () => { form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('Tijdelijk niet bereikbaar.'));
  expect(textarea.value).toBe('Opnieuw proberen');
  expect((document.querySelector('[type="submit"]') as HTMLButtonElement).disabled).toBe(false);
});

it('herstelt na Enter-versturen de invoerfocus als de browser die tijdens laden verliest', async () => {
  await mountApp(document.querySelector('#app')!, createMockClient(20), true);
  const textarea = document.querySelector('textarea')!;
  await act(async () => {
    textarea.focus();
    textarea.value = 'Een vraag';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => { document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
  document.body.tabIndex = -1;
  document.body.focus(); // Simuleer browserfocusverlies bij disabled textarea.
  expect(document.activeElement).toBe(document.body);
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
  expect(document.activeElement).toBe(textarea);
});

it('steelt na laden geen focus van een andere leesinteractie', async () => {
  await mountApp(document.querySelector('#app')!, createMockClient(20), true);
  const textarea = document.querySelector('textarea')!;
  await act(async () => {
    textarea.focus(); textarea.value = 'Een vraag';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => { document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
  await act(async () => {
    textarea.focus(); textarea.value = 'Een volgende vraag';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => { document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
  const readingButton = document.querySelector<HTMLButtonElement>('.case-button')!;
  readingButton.focus();
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
  expect(document.activeElement).toBe(readingButton);
});


it('vervangt de vorige resultaten bij een nieuwe zoekopdracht', async () => {
  await mountApp(document.querySelector('#app')!, createMockClient(0), true);
  for (const query of ['Eerste vraag', 'Tweede vraag']) {
    await act(async () => {
      const textarea = document.querySelector('textarea')!;
      textarea.value = query; textarea.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => { document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); await new Promise(resolve => setTimeout(resolve, 10)); });
  }
  expect(document.querySelectorAll('.case-button')).toHaveLength(3);
  expect(document.querySelectorAll('.answer')).toHaveLength(1);
});

it('toont de gehele lange brontekst veilig en weigert markeringen bij versieverschillen', async () => {
  const mock = createMockClient(0);
  const source = await mock.getCase('/api/cases/fixture-case-001');
  const fullText = source.text + '\n\n' + 'Volledige extra alinea. '.repeat(500) + '<script>ongewenst()</script>';
  let stale = true;
  await mountApp(document.querySelector('#app')!, {
    ...mock,
    getCase: async () => ({ ...source, text: fullText, text_version: stale ? 'oude-versie' : source.text_version }),
  }, true);
  await act(async () => {
    const textarea = document.querySelector('textarea')!;
    textarea.value = 'Een vraag'; textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => { document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); await new Promise(resolve => setTimeout(resolve, 10)); });
  await act(async () => { document.querySelector<HTMLButtonElement>('.case-button')!.click(); });
  expect(document.querySelector('.reader [role="alert"]')?.textContent).toContain('opnieuw');
  expect(document.querySelector('.opinion')).toBeNull();
  await act(async () => { document.querySelector<HTMLButtonElement>('.reader-back')!.click(); });
  stale = false;
  await act(async () => { document.querySelector<HTMLButtonElement>('.case-button')!.click(); });
  expect(document.querySelector('.opinion')?.textContent).toBe(fullText);
  expect(document.querySelector('.opinion script')).toBeNull();
});

it('toont één compacte uitleg boven de volledige bron zonder dubbele quote of spronglink', async () => {
  const mock = createMockClient(0);
  await mountApp(document.querySelector('#app')!, {
    ...mock,
    search: async (input) => {
      const response = await mock.search(input);
      return {
        ...response,
        explanation_status: 'available' as const,
        results: response.results.map((result) => ({
          ...result,
          explanation: {
            text: 'Deze uitspraak bespreekt getuigenbewijs. <script>ongewenst()</script>',
            citations: [{ passage_id: result.passage.passage_id, quote: result.passage.text }],
            limitations: ['De passage bewijst niet dat de feiten van beide zaken gelijk zijn.', 'De inhoud van je upload is niet aan het taalmodel getoond.'],
          },
        })),
      };
    },
  }, false);
  await act(async () => {
    const textarea = document.querySelector('textarea')!;
    textarea.value = 'Hoe betrouwbaar is getuigenbewijs?';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => {
    document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await new Promise(resolve => setTimeout(resolve, 10));
  });
  await act(async () => { document.querySelector<HTMLButtonElement>('.case-button')!.click(); });
  expect(document.querySelector('.model-explanation')?.textContent).toContain('Deze uitspraak bespreekt getuigenbewijs.');
  expect(document.querySelector('.why-passage')).toBeNull();
  expect(document.querySelector('a[href="#source-passage"]')).toBeNull();
  expect(document.querySelector('#source-passage')?.textContent).toContain('Witness testimony');
  const reason = document.querySelector('.document-reason')!;
  expect(reason.querySelectorAll('p')).toHaveLength(1);
  expect(reason.querySelector('ul')).toBeNull();
  expect(reason.textContent).toContain('De passage bewijst niet');
  expect(reason.textContent).toContain('De inhoud van je upload is niet aan het taalmodel getoond.');
  expect(reason.textContent).not.toContain('Witness testimony');
  expect(reason.textContent).not.toContain('Overeenkomstscore');
  const source = await mock.getCase('/api/cases/fixture-case-001');
  expect(document.querySelector('.opinion')?.textContent).toBe(source.text);
  expect(reason.compareDocumentPosition(document.querySelector('.opinion')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(document.querySelector('.document-reason script')).toBeNull();
});

it('houdt echte zoekresultaten leesbaar en meldt het als modeluitleg niet beschikbaar is', async () => {
  const mock = createMockClient(0);
  await mountApp(document.querySelector('#app')!, {
    ...mock,
    search: async (input) => ({ ...await mock.search(input), explanation_status: 'unavailable' as const }),
  }, false);
  await act(async () => {
    const textarea = document.querySelector('textarea')!;
    textarea.value = 'Een vraag';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => {
    document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await new Promise(resolve => setTimeout(resolve, 10));
  });
  expect(document.querySelectorAll('.case-button')).toHaveLength(3);
  await act(async () => { document.querySelector<HTMLButtonElement>('.case-button')!.click(); });
  expect(document.querySelector('.explanation-status')?.textContent).toContain('De toelichting is tijdelijk niet beschikbaar.');
  expect(document.querySelector('.model-explanation')).toBeNull();
  expect(document.querySelector('.opinion')?.textContent).toContain('This invented ending');
  expect(document.querySelector('mark')?.textContent).toContain('Witness testimony');
});

it('toont gevalideerde uploadonderbouwing compact naast de uitleg zonder de corpuspassage te herhalen', async () => {
  const mock = createMockClient(0);
  const uploadQuote = 'The witness could not identify the defendant. <script>ongewenst()</script>';
  const uploadText = `Fictional upload 🧪. ${uploadQuote}`;
  await mountApp(document.querySelector('#app')!, {
    ...mock,
    search: async (input) => {
      const response = await mock.search(input);
      return {
        ...response,
        explanation_status: 'available' as const,
        input_context: { text_version: `sha256:${'a'.repeat(64)}`, utf16_length: uploadText.length },
        results: response.results.map((result) => ({
          ...result,
          explanation: {
            text: 'Je document en deze uitspraak bespreken de betrouwbaarheid van getuigenbewijs.',
            citations: [{ passage_id: result.passage.passage_id, quote: result.passage.text }],
            input_citations: [{ quote: uploadQuote, start_utf16: uploadText.indexOf(uploadQuote), end_utf16: uploadText.length }],
            limitations: ['De feiten van beide zaken kunnen verschillen.'],
          },
        })),
      };
    },
  }, false);
  await act(async () => {
    const textarea = document.querySelector('textarea')!;
    textarea.value = 'Hoe betrouwbaar is dit getuigenbewijs?';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    const upload = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    Object.defineProperty(upload, 'files', { value: [new File([uploadText], 'mijn-document.txt', { type: 'text/plain' })] });
    upload.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await act(async () => {
    document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await new Promise(resolve => setTimeout(resolve, 10));
  });
  await act(async () => { document.querySelector<HTMLButtonElement>('.case-button')!.click(); });
  const evidence = document.querySelector<HTMLDetailsElement>('.input-evidence');
  expect(evidence).not.toBeNull();
  expect(evidence?.open).toBe(false);
  expect(evidence?.querySelector('summary')?.textContent).toBe('Uit je document');
  expect(evidence?.querySelector('blockquote')?.textContent).toBe(uploadQuote);
  expect(evidence?.querySelector('script')).toBeNull();
  expect(document.querySelector('.model-explanation')?.textContent).toContain('De feiten van beide zaken kunnen verschillen.');
  expect(document.querySelector('.document-reason')?.textContent).not.toContain('Witness testimony');
  expect(document.querySelector('.document-reason')?.textContent).not.toContain('niet aan het taalmodel getoond');
  expect(document.querySelector('mark')?.textContent).toContain('Witness testimony');
  expect(document.querySelector('.opinion')?.textContent).toContain('This invented ending');
});

it('toont geen uploadonderbouwing wanneer de API geen verwerkte documentcontext levert', async () => {
  const mock = createMockClient(0);
  await mountApp(document.querySelector('#app')!, {
    ...mock,
    search: async (input) => {
      const response = await mock.search(input);
      return {
        ...response,
        explanation_status: 'available' as const,
        results: response.results.map((result) => ({
          ...result,
          explanation: {
            text: 'Deze uitspraak bespreekt getuigenbewijs.',
            citations: [{ passage_id: result.passage.passage_id, quote: result.passage.text }],
            input_citations: [{ quote: 'Geen verwerkte bron.', start_utf16: 0, end_utf16: 19 }],
            limitations: [],
          },
        })),
      };
    },
  }, false);
  await act(async () => {
    const textarea = document.querySelector('textarea')!;
    textarea.value = 'Getuigenbewijs';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => {
    document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await new Promise(resolve => setTimeout(resolve, 10));
  });
  await act(async () => { document.querySelector<HTMLButtonElement>('.case-button')!.click(); });
  expect(document.querySelector('.input-evidence')).toBeNull();
  expect(document.querySelector('.model-explanation')?.textContent).toBe('Deze uitspraak bespreekt getuigenbewijs.');
  expect(document.querySelector('.opinion')?.textContent).toContain('This invented ending');
});
