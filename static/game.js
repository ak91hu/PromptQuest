import { api, decode, element, downloadPdf } from './http.mjs';
const $ = (id) => document.getElementById(id);
let state,
  busy = false,
  lastStation = -1,
  notesDirty = false,
  initializing = true,
  changingStation = false,
  hintUntil = 0;
let decoded = '',
  launchTimer,
  shownLaunch = false,
  elapsedAt = Date.now();
let missionStartsRemaining = null;
let renderedMessages = [];
const actionButtons = [
  'start-button',
  'send-button',
  'ask-button',
  'code-button',
  'hint-button',
  'next-button',
  'save-note',
  'guided-button',
  'confirm-reset',
  'reset-button',
  'result-reset',
  'end-exhausted',
  'defense-button',
];
function status(text) {
  $('connection-text').textContent = text;
}
function showView(id) {
  for (const view of ['landing', 'mission', 'results']) $(view).hidden = view !== id;
}
function refreshButtons() {
  for (const id of actionButtons) $(id).disabled = busy;
  $('start-button').disabled =
    busy || initializing || missionStartsRemaining === null || missionStartsRemaining === 0;
  $('notes-input').disabled = changingStation;
  $('mission-allowance').textContent =
    missionStartsRemaining === null
      ? 'Checking this network’s mission allowance…'
      : `${missionStartsRemaining} / 3 mission starts remain for this network. Three starts total, shared by this IP, with no daily reset. Continuing uses no new start.`;
  if (state) {
    const stopped = state.room.solved || state.game_over;
    for (const id of ['send-button', 'ask-button', 'code-button', 'guided-button'])
      $(id).disabled = busy || stopped;
    const wait = Math.max(0, Math.ceil((hintUntil - Date.now()) / 1000));
    $('hint-button').disabled = busy || stopped || !state.room.hint_token || wait > 0;
    $('hint-button').textContent = wait ? `Request hint (${wait}s)` : 'Request hint';
  }
}
async function saveNotes() {
  if (!state || !notesDirty) return;
  const note = $('notes-input').value;
  const station = state.current;
  const mission = state.mission_number;
  await api('/api/note', { note, station });
  if (state?.current === station && state.mission_number === mission) {
    state.room.note = note;
    notesDirty = $('notes-input').value !== note;
    $('note-status').textContent = notesDirty
      ? 'New changes are not saved yet.'
      : 'Observation saved.';
  }
}
async function action(path, data, errorId, { save = false } = {}) {
  if (busy) return;
  busy = true;
  changingStation = path === '/api/next';
  $('request-status').textContent =
    path === '/api/chat' ? 'Waiting for the guard’s response…' : 'Saving your action…';
  $('chat-log').setAttribute('aria-busy', String(path === '/api/chat'));
  refreshButtons();
  if (errorId) $(errorId).textContent = '';
  try {
    if (save) await saveNotes();
    if (state && ['/api/chat', '/api/code', '/api/hint', '/api/next'].includes(path))
      data = { ...data, station: state.current };
    const result = path ? await api(path, data) : { saved: true };
    if (result.room) render(result);
    return result;
  } catch (error) {
    if (errorId) $(errorId).textContent = error.message;
    if (error.status === 401 && state) {
      state = undefined;
      lastStation = -1;
      showView('landing');
      $('start-error').textContent = error.message;
    }
    if (error.status === 401 || (path === '/api/start' && error.status === 429)) {
      try {
        const config = await api('/api/config');
        missionStartsRemaining = config.mission_starts_remaining;
      } catch {
        /* Keep the original failure visible. */
      }
    }
  } finally {
    busy = false;
    changingStation = false;
    $('request-status').textContent = '';
    $('chat-log').setAttribute('aria-busy', 'false');
    refreshButtons();
  }
}
function render(next) {
  const previous = state;
  state = next;
  missionStartsRemaining = state.mission_starts_remaining;
  elapsedAt = Date.now();
  const changed = lastStation !== state.current;
  lastStation = state.current;
  const room = state.room;
  showView(state.finished ? 'results' : 'mission');
  $('mission-callsign').textContent =
    `OPERATOR / ${state.team} · MISSION ${state.mission_number} / ${state.mission_limit}`;
  $('mission-score').replaceChildren(
    document.createTextNode(`${state.score} `),
    element('small', `/ ${state.max_score}`),
  );
  $('mission-fragments').textContent =
    state.levels
      .filter((l) => l.solved)
      .map((l) => l.fragment)
      .join(' ') || 'Awaiting recovery';
  $('sector-list').replaceChildren(
    ...state.levels.map((level, i) => {
      const li = element(
        'li',
        undefined,
        `${level.solved ? 'solved' : ''} ${i === state.current ? 'current' : ''} ${level.unlocked ? '' : 'locked'}`,
      );
      li.append(
        element('span', level.solved ? '✓' : String(i + 1).padStart(2, '0'), 'sector-num'),
        element('span', level.name),
      );
      if (i === state.current) li.setAttribute('aria-current', 'step');
      if (!level.unlocked) li.setAttribute('aria-label', `${i + 1}. ${level.name}, locked`);
      return li;
    }),
  );
  if (changed && matchMedia('(max-width: 900px)').matches)
    $('sector-list').children[state.current].scrollIntoView({ block: 'nearest', inline: 'center' });
  $('sector-label').textContent =
    `SECTOR ${String(state.current + 1).padStart(2, '0')} / ${state.levels.length} — ${room.topic.toUpperCase()}`;
  $('room-title').textContent = room.name;
  $('room-story').textContent = room.story;
  $('room-subject').textContent = room.subject;
  $('attempts-left').textContent = `${room.remaining} / ${room.budget} prompts left`;
  $('attempts-left').classList.toggle('low-budget', room.remaining <= 5 && !room.solved);
  $('hint-count').textContent = `${room.hints.length} / ${room.hint_total} hints used`;
  $('room-objective').textContent = room.mission;
  $('guard-defense').textContent = room.defense;
  $('agent-name').textContent = room.agent.toUpperCase();
  $('guard-status').textContent = room.solved
    ? 'RECOVERED'
    : state.game_over
      ? 'MISSION ENDED'
      : 'CHANNEL OPEN';
  const messages = [{ role: 'assistant', content: room.intro }, ...room.history];
  const samePrefix =
    !changed &&
    renderedMessages.every(
      (m, i) => messages[i]?.role === m.role && messages[i]?.content === m.content,
    );
  const count = samePrefix ? renderedMessages.length : 0;
  if (!samePrefix) $('chat-log').replaceChildren();
  for (const m of messages.slice(count)) {
    const block = element('div', undefined, `message ${m.role === 'user' ? 'user' : 'assistant'}`);
    block.append(
      element(
        'span',
        m.role === 'user' ? 'OPERATOR / TRANSMISSION' : room.agent.toUpperCase(),
        'message-label',
      ),
      element('p', m.content),
    );
    $('chat-log').append(block);
  }
  if (count !== messages.length) $('chat-log').scrollTop = $('chat-log').scrollHeight;
  renderedMessages = messages;
  $('tool-traces').hidden = !room.traces.length;
  $('tool-traces').replaceChildren(
    ...room.traces.map((trace) => {
      const block = element('div');
      block.append(element('strong', `${trace.name}: `), document.createTextNode(trace.result));
      return block;
    }),
  );
  $('document-area').hidden = !room.document;
  $('message-area').hidden = false;
  $('ask-button').hidden = !room.document;
  $('send-button').textContent = room.document ? 'Transmit document ↗' : 'Transmit ↗';
  $('chat-form').hidden = room.solved || state.game_over;
  $('hint-list').replaceChildren(...room.hints.map((h) => element('li', h)));
  hintUntil = Date.now() + room.hint_wait_seconds * 1000;
  $('guided-button').hidden = !room.guided_prompt;
  $('recovery').hidden = !room.solved;
  if (room.solved) {
    $('recovery-lesson').textContent = room.lesson;
    $('recovered-secret').textContent = room.discovery.secret;
    $('recovery-question').textContent = room.discovery.question;
    $('recovery-explanation').textContent = room.discovery.explanation;
    $('code-correction').textContent = room.code_correction;
    $('next-button').textContent =
      state.current === state.levels.length - 1
        ? 'Authorize departure →'
        : 'Proceed to next system →';
  }
  $('game-over').hidden = !state.game_over;
  if (state.game_over && !previous?.game_over) $('game-over-title').focus();
  if (changed) {
    $('message-input').value = '';
    $('document-input').value = room.document;
    $('notes-input').value = room.note;
    $('note-status').textContent = room.note ? 'Observation saved.' : '';
    notesDirty = false;
    $('code-input').value = '';
    $('decode-input').value = '';
    $('decode-output').textContent = '';
    $('use-decoded').hidden = true;
    $('decode-input').closest('details').open = false;
    for (const id of ['chat-error', 'hint-error', 'code-error']) $(id).textContent = '';
    if (!state.finished) $('room-title').focus({ preventScroll: true });
  }
  if (state.finished) {
    results();
    if (previous && !previous.finished && !shownLaunch) launch();
    else $('results-title').focus({ preventScroll: true });
  }
  refreshButtons();
}
function results() {
  $('result-reset').textContent = missionStartsRemaining
    ? 'Start another mission ↗'
    : 'Return to deployment';
  if (state.defense_passed) {
    for (const input of $('defense-options').querySelectorAll('input'))
      input.checked = ['outside', 'permissions', 'documents'].includes(input.value);
    $('defense-result').textContent =
      'Defense plan validated. The model assists; the server enforces permission.';
  }
  $('result-name').textContent = state.team;
  $('result-score').textContent = `${state.score} / ${state.max_score}`;
  $('result-fragments').textContent = `${state.levels.map((l) => l.fragment).join(' ')}.`;
  $('result-stations').replaceChildren(
    ...state.levels.map((level, i) => {
      const article = element('article', undefined, 'result-station');
      article.append(
        element(
          'p',
          `SYSTEM ${String(i + 1).padStart(2, '0')} / ${level.points} POINTS`,
          'eyebrow',
        ),
        element('h3', level.name),
        element('p', level.discovery.question),
        element('code', level.discovery.secret),
        element('p', level.discovery.explanation),
      );
      return article;
    }),
  );
}
function launch() {
  shownLaunch = true;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    $('results-title').focus();
    return;
  }
  $('launch-dialog').showModal();
  launchTimer = setTimeout(closeLaunch, 7000);
}
function closeLaunch() {
  clearTimeout(launchTimer);
  $('launch-dialog').close();
  $('results-title').focus();
  window.scrollTo({ top: 0 });
}
$('skip-launch').addEventListener('click', closeLaunch);
$('launch-dialog').addEventListener('cancel', (event) => {
  event.preventDefault();
  closeLaunch();
});
$('start-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  await action('/api/start', { team: $('operator').value.trim() }, 'start-error');
});
$('chat-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const sourceInput = state.room.document ? $('document-input') : $('message-input');
  if (!sourceInput.value.trim()) {
    $('chat-error').textContent = state.room.document
      ? 'Edit the document before transmitting it.'
      : 'Enter an experiment or question.';
    sourceInput.focus();
    return;
  }
  const data = state.room.document
    ? { document: $('document-input').value }
    : { message: $('message-input').value };
  const result = await action('/api/chat', data, 'chat-error');
  if (result && !result.room.document && $('message-input').value === data.message)
    $('message-input').value = '';
});
$('ask-button').addEventListener('click', async () => {
  const message = $('message-input').value;
  if (!message.trim()) {
    $('chat-error').textContent = 'Enter a question for the guard.';
    $('message-input').focus();
    return;
  }
  const result = await action('/api/chat', { message }, 'chat-error');
  if (result && $('message-input').value === message) $('message-input').value = '';
});
for (const id of ['message-input', 'document-input'])
  $(id).addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !busy) {
      event.preventDefault();
      if (id === 'message-input' && state.room.document) $('ask-button').click();
      else $('chat-form').requestSubmit();
    }
  });
$('code-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const result = await action('/api/code', { code: $('code-input').value }, 'code-error');
  if (result?.room.solved && !result.finished) $('next-button').focus();
});
$('hint-button').addEventListener('click', () =>
  action('/api/hint', { token: state.room.hint_token }, 'hint-error'),
);
$('guided-button').addEventListener('click', () => {
  const target = state.room.document ? $('document-input') : $('message-input');
  target.value = state.room.document
    ? state.room.document + state.room.guided_prompt
    : state.room.guided_prompt;
  target.focus();
});
$('next-button').addEventListener('click', () =>
  action('/api/next', {}, 'chat-error', { save: true }),
);
$('notes-input').addEventListener('input', () => {
  notesDirty = true;
  $('note-status').textContent = 'Unsaved observation.';
});
$('save-note').addEventListener('click', () => action(null, null, 'note-status', { save: true }));
window.addEventListener('beforeunload', (event) => {
  if (notesDirty) {
    event.preventDefault();
    event.returnValue = '';
  }
});

for (const [id, method] of [
  ['reverse-button', 'reverse'],
  ['base64-button', 'base64'],
])
  $(id).addEventListener('click', () => {
    try {
      decoded = decode($('decode-input').value, method);
      $('decode-output').textContent = decoded;
      $('use-decoded').hidden = !decoded;
    } catch {
      $('decode-output').textContent =
        'Invalid Base64. Paste only the encoded value, without the response label.';
      $('use-decoded').hidden = true;
    }
  });
$('use-decoded').addEventListener('click', () => {
  $('code-input').value = decoded;
  $('code-input').focus();
});
for (const id of ['reset-button', 'result-reset', 'end-exhausted'])
  $(id).addEventListener('click', () => {
    $('reset-error').textContent = '';
    $('reset-allowance').textContent = missionStartsRemaining
      ? `${missionStartsRemaining} / 3 starts remain. Ending this mission does not restore an allowance or start the next mission automatically.`
      : 'No mission starts remain for this network. Ending this mission clears the results; the unlimited training lab remains available.';
    $('restart-dialog').showModal();
  });
$('cancel-reset').addEventListener('click', () => $('restart-dialog').close());
$('confirm-reset').addEventListener('click', async () => {
  const result = await action('/api/reset', {}, 'reset-error');
  if (!result) return;
  missionStartsRemaining = result.mission_starts_remaining;
  state = undefined;
  lastStation = -1;
  shownLaunch = false;
  notesDirty = false;
  $('restart-dialog').close();
  showView('landing');
  refreshButtons();
  $('operator').focus();
});
$('defense-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const choices = [...$('defense-options').querySelectorAll('input:checked')].map(
    (input) => input.value,
  );
  const result = await action('/api/defense', { choices }, 'defense-result');
  if (!result) return;
  state.defense_passed = result.passed;
  $('defense-result').replaceChildren(
    element('p', result.message),
    ...result.tests.map((test) =>
      element('p', `${test.passed ? '✓' : '○'} ${test.name}: ${test.explanation}`),
    ),
  );
});
setInterval(() => {
  refreshButtons();
  if (!state) return;
  const seconds =
    state.elapsed + (state.finished ? 0 : Math.floor((Date.now() - elapsedAt) / 1000));
  $('elapsed').textContent =
    `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')} elapsed`;
}, 1000);
async function initialize() {
  if (busy) return;
  initializing = true;
  refreshButtons();
  $('retry-connection').hidden = true;
  $('start-error').textContent = '';
  try {
    const config = await api('/api/config');
    missionStartsRemaining = config.mission_starts_remaining;
    refreshButtons();
    status(config.mode === 'live' ? 'LIVE AI ONLINE' : 'TRAINING CHANNEL ONLINE');
    $('mode-label').textContent =
      config.mode === 'live' ? 'Live AI' : 'Deterministic training mode / No live model calls';
    $('station-grid').replaceChildren(
      ...config.stations.map((station, i) => {
        const button = element('button', undefined, 'station-card');
        button.type = 'button';
        button.setAttribute('aria-pressed', 'false');
        button.append(
          element('span', String(i + 1).padStart(2, '0'), 'station-index'),
          element('strong', station.name),
          element('small', station.subject),
        );
        button.addEventListener('click', () => {
          for (const card of $('station-grid').children)
            card.setAttribute('aria-pressed', String(card === button));
          $('preview').replaceChildren(
            element('p', `SYSTEM ${String(i + 1).padStart(2, '0')} / ${station.topic}`, 'eyebrow'),
            element('h3', station.name),
            element('p', station.story),
          );
        });
        return button;
      }),
    );
    $('station-grid').firstElementChild?.click();
    $('defense-options').replaceChildren(
      ...config.defenses.map((defense) => {
        const label = element('label');
        const input = element('input');
        input.type = 'checkbox';
        input.value = defense.id;
        label.append(input, document.createTextNode(defense.label));
        return label;
      }),
    );
    try {
      render(await api('/api/state'));
    } catch (error) {
      if (error.status !== 401) throw error;
    }
  } catch (error) {
    status('LINK UNAVAILABLE');
    $('start-error').textContent = error.message;
    $('retry-connection').hidden = false;
  } finally {
    initializing = false;
    refreshButtons();
  }
}
$('retry-connection').addEventListener('click', initialize);
for (const link of document.querySelectorAll('a[download]')) {
  link.addEventListener('click', async (event) => {
    event.preventDefault();
    if (busy) return;
    const path = new URL(link.href).pathname;
    const errorTarget = state?.finished ? $('download-error') : $('chat-error');
    errorTarget.textContent = '';
    busy = true;
    refreshButtons();
    $('request-status').textContent = 'Preparing your download…';
    link.setAttribute('aria-busy', 'true');
    try {
      await saveNotes();
      const blob = await downloadPdf(path);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download =
        path === '/api/certificate' ? 'hacktheai-certificate.pdf' : 'hacktheai-mission-log.pdf';
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      errorTarget.textContent = error.message;
    } finally {
      link.removeAttribute('aria-busy');
      busy = false;
      $('request-status').textContent = '';
      refreshButtons();
    }
  });
}
initialize();
