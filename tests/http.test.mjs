import assert from 'node:assert/strict';
import { test } from 'node:test';
import { api, decode, downloadPdf } from '../static/http.mjs';
test('decode workbench handles reversed formulas and Base64 manifests', () => {
  assert.equal(decode(')91A:2A(MUS=', 'reverse'), '=SUM(A2:A19)');
  assert.equal(decode(btoa('SHA256: abc123'), 'base64'), 'SHA256: abc123');
  assert.throws(() => decode('invalid base64!', 'base64'));
  assert.equal(decode('🛰abc', 'reverse'), 'cba🛰');
});

test('PDF download keeps credentials same-origin and returns a PDF blob', async (context) => {
  context.mock.method(globalThis, 'fetch', async (path, options) => {
    assert.equal(path, '/api/export');
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.cache, 'no-store');
    return new Response('%PDF-1.4 sample', { headers: { 'Content-Type': 'application/pdf' } });
  });
  const blob = await downloadPdf('/api/export');
  assert.equal(await blob.text(), '%PDF-1.4 sample');
});
test('PDF download rejects expired sessions and mislabeled success responses', async (context) => {
  const fetchMock = context.mock.method(globalThis, 'fetch', async () =>
    Response.json({ detail: 'Session expired' }, { status: 401 }),
  );
  await assert.rejects(downloadPdf('/api/export'), /Session expired/);
  fetchMock.mock.mockImplementation(async () => Response.json({ detail: 'Unexpected JSON' }));
  await assert.rejects(downloadPdf('/api/export'), /invalid PDF/);
});

test('API retains HTTP status when an expired-session response is not JSON', async (context) => {
  context.mock.method(
    globalThis,
    'fetch',
    async () => new Response('proxy error', { status: 401 }),
  );
  await assert.rejects(
    api('/api/state'),
    (error) => error.status === 401 && /unreadable/.test(error.message),
  );
});
test('network failure gives recovery guidance without retrying the action', async (context) => {
  let count = 0;
  context.mock.method(globalThis, 'fetch', async () => {
    count++;
    throw new TypeError('Failed to fetch');
  });
  await assert.rejects(api('/api/chat', { message: 'Draft' }), /Reload to check/);
  assert.equal(count, 1);
});

test('null JSON errors preserve a readable message and status', async (context) => {
  context.mock.method(globalThis, 'fetch', async () => Response.json(null, { status: 500 }));
  await assert.rejects(
    api('/api/state'),
    (error) => error.status === 500 && /could not be completed/.test(error.message),
  );
});
