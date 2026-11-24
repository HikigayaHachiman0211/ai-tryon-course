import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ catalog: vi.fn(), translate: (key: string) => key, locale: 'en' }));
vi.mock('./api', () => ({ getCatalogProducts: mocks.catalog, analyzeStyleLab: vi.fn(), buildImageURL: vi.fn(), getHistoryDetail: vi.fn(), getRecommend: vi.fn() }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mocks.translate }) }));
vi.mock('./i18n', () => ({ default: { get resolvedLanguage() { return mocks.locale; } }, setAppLocale: vi.fn() }));
vi.mock('./i18n/LanguageSwitcher', () => ({ LanguageSwitcher: () => null }));
vi.mock('./views/RecommendView', () => ({ RecommendView: () => null }));
vi.mock('./views/StyleLabView', () => ({ StyleLabView: (props: {
  catalogQuery: string; onCatalogQueryChange: (value: string) => void; catalogItems: { title: string }[];
  catalogLoading: boolean; catalogError: string | null; onLoadMoreCatalog: () => void;
}) => <div>
  <input aria-label="query" value={props.catalogQuery} onChange={event => props.onCatalogQueryChange(event.target.value)} />
  <div data-testid="items">{props.catalogItems.map(item => item.title).join(',')}</div>
  <div data-testid="loading">{String(props.catalogLoading)}</div>
  <div data-testid="error">{props.catalogError}</div>
  <button onClick={props.onLoadMoreCatalog}>more</button>
</div> }));
vi.mock('./components/DebugDrawer', () => ({ DebugDrawer: () => null }));
vi.mock('./components/HistoryDrawer', () => ({ HistoryDrawer: () => null }));
vi.mock('./assistant/components/FloatingAssistant', () => ({ FloatingAssistant: () => null }));
vi.mock('framer-motion', () => ({ AnimatePresence: ({ children }: { children: React.ReactNode }) => children, motion: { div: ({ children }: { children: React.ReactNode }) => <div>{children}</div> } }));

import App from './App';

function deferred() {
  let resolve!: (value: unknown) => void; let reject!: (error: Error) => void;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const response = (title: string) => ({ items: [{ id: title, title }], total: 2, gender_fallback: false });

beforeEach(() => { mocks.catalog.mockReset(); mocks.locale = 'en'; window.location.hash = '#style-lab'; });

it('keeps the newest query, loading state, and page results when requests finish out of order', async () => {
  const a = deferred(); const b = deferred(); const page = deferred(); const c = deferred(); const d = deferred();
  mocks.catalog.mockImplementation(({ query, offset }: { query?: string; offset: number }) => {
    if (query === 'A') return a.promise;
    if (query === 'B') return offset ? page.promise : b.promise;
    if (query === 'C') return c.promise;
    if (query === 'D') return d.promise;
    return Promise.resolve({ items: [], total: 0 });
  });
  render(<App />);
  const input = screen.getByLabelText('query');
  fireEvent.change(input, { target: { value: 'A' } });
  await waitFor(() => expect(mocks.catalog).toHaveBeenCalledWith(expect.objectContaining({ query: 'A' })));
  fireEvent.change(input, { target: { value: 'B' } });
  await waitFor(() => expect(mocks.catalog).toHaveBeenCalledWith(expect.objectContaining({ query: 'B', offset: 0 })));
  await act(async () => { a.resolve(response('old A')); await a.promise; });
  expect(screen.getByTestId('items')).not.toHaveTextContent('old A');
  expect(screen.getByTestId('loading')).toHaveTextContent('true');
  await act(async () => { b.resolve(response('B')); await b.promise; });
  expect(screen.getByTestId('items')).toHaveTextContent('B');
  fireEvent.click(screen.getByText('more'));
  await waitFor(() => expect(mocks.catalog).toHaveBeenCalledWith(expect.objectContaining({ query: 'B', offset: 1 })));
  fireEvent.change(input, { target: { value: 'C' } });
  await waitFor(() => expect(mocks.catalog).toHaveBeenCalledWith(expect.objectContaining({ query: 'C' })));
  await act(async () => { page.resolve(response('old page')); await page.promise; });
  expect(screen.getByTestId('items')).not.toHaveTextContent('old page');
  fireEvent.change(input, { target: { value: 'D' } });
  await waitFor(() => expect(mocks.catalog).toHaveBeenCalledWith(expect.objectContaining({ query: 'D' })));
  await act(async () => { d.resolve(response('D')); await d.promise; });
  await act(async () => { c.reject(new Error('old error')); await c.promise.catch(() => {}); });
  expect(screen.getByTestId('items')).toHaveTextContent('D');
  expect(screen.getByTestId('error')).toBeEmptyDOMElement();
});

it('invalidates an older request when the language changes', async () => {
  const oldRequest = deferred(); const newRequest = deferred();
  mocks.catalog.mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise);
  const view = render(<App />);
  await waitFor(() => expect(mocks.catalog).toHaveBeenCalledTimes(1));
  mocks.locale = 'ja';
  view.rerender(<App />);
  await waitFor(() => expect(mocks.catalog).toHaveBeenCalledTimes(2));
  await act(async () => { newRequest.resolve(response('new language')); await newRequest.promise; });
  await act(async () => { oldRequest.resolve(response('old language')); await oldRequest.promise; });
  expect(screen.getByTestId('items')).toHaveTextContent('new language');
});
