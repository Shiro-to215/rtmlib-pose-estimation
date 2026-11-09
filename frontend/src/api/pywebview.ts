import { BackendApi } from '../types/pywebview';

export function getBackendApi(): BackendApi | null {
  if (typeof window !== 'undefined' && window.pywebview && window.pywebview.api) {
    return window.pywebview.api;
  }
  return null;
}

export async function callApi<T>(fn: (api: BackendApi) => Promise<T>, fallback: T): Promise<T> {
  const api = getBackendApi();
  if (!api) {
    console.warn('[PyWebView] Backend API not available (browser mock fallback)');
    return fallback;
  }
  try {
    return await fn(api);
  } catch (err) {
    console.error('[PyWebView] Bridge call error:', err);
    throw err;
  }
}
