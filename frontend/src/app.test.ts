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
  expect(document.querySelector('.user-message')?.textContent).toContain('Mijn eigen vraag over bewijs');
  await act(async () => { (document.querySelector('.case-button') as HTMLButtonElement).click(); });
  await vi.waitFor(() => expect(document.querySelector('mark')?.textContent).toContain('Witness testimony'));
  expect(document.querySelector('.opinion')?.textContent).toContain('This invented ending');
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
