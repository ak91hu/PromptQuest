export async function api(path, data, { signal } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method: data === undefined ? 'GET' : 'POST',
      headers: data === undefined ? {} : { 'Content-Type': 'application/json' },
      body: data === undefined ? undefined : JSON.stringify(data),
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
    });
  } catch (cause) {
    if (cause.name === 'AbortError') throw cause;
    throw new Error(
      'Connection interrupted. Your text is kept. Reload to check whether the action completed before retrying.',
    );
  }
  let result;
  try {
    result = await response.json();
  } catch {
    const error = new Error(
      'The server returned an unreadable response. Reload to check your mission before retrying.',
    );
    error.status = response.status;
    throw error;
  }
  if (!response.ok) {
    const error = new Error(
      typeof result?.detail === 'string' ? result.detail : 'The request could not be completed.',
    );
    error.status = response.status;
    throw error;
  }
  return result;
}
export function decode(value, method) {
  if (method === 'reverse') return Array.from(value).reverse().join('');
  const bytes = Uint8Array.from(atob(value.trim()), (c) => c.charCodeAt(0));
  return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
}
export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

export async function downloadPdf(path) {
  let response;
  try {
    response = await fetch(path, { credentials: 'same-origin', cache: 'no-store' });
  } catch {
    throw new Error(
      'Connection interrupted. Your mission is kept. Retry the download when connected.',
    );
  }
  if (!response.ok) {
    let result;
    try {
      result = await response.json();
    } catch {
      /* Use the generic error below. */
    }
    const error = new Error(
      typeof result?.detail === 'string' ? result.detail : 'The PDF could not be downloaded.',
    );
    error.status = response.status;
    throw error;
  }
  if (!response.headers.get('content-type')?.includes('application/pdf'))
    throw new Error('The server returned an invalid PDF. Retry your download.');
  return response.blob();
}
