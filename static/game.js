import { api, decode, element, downloadPdf } from './http.mjs';
const $ = (id) => document.getElementById(id);
const stationIcons = [
  'M7 5 2 10l5 5m6-10 5 5-5 5M11 3 9 17',
  'M3 3h14v14H3zM3 8h14M8 3v14M3 13h14',
  'M3 5c0-4 14-4 14 0s-14 4-14 0v10c0 4 14 4 14 0V5M3 10c0 4 14 4 14 0',
  'M5 9h10v8H5zM7 9V6a3 3 0 0 1 6 0v3M10 12v2',
  'M3 4h5v4H3zM12 12h5v4h-5zM5 8v6h7M12 3h5v5h-5zM8 6h4',
  'M7 2 5 18M15 2l-2 16M2 7h16M2 13h16',
  'm10 2 8 4v8l-8 4-8-4V6l8-4Zm-8 4 8 4 8-4M10 10v8',
  'M2 17h16M4 13V8m4 5V3m4 10V6m4 7V2',
  'm10 2 7 3v6c0 3-4 6-7 7-3-1-7-4-7-7V5l7-3ZM6 10l3 3 5-6',
  'M2 10s3-6 8-6 8 6 8 6-3 6-8 6-8-6-8-6ZM10 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  'M12 3a5 5 0 0 0-5 6L2 14l4 4 5-5a5 5 0 0 0 6-5l-3 3-4-4 2-4Z',
  'M6 3a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Zm8 0a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3M3 8h3m8 4h3',
  'M2 5h13m-3-3 3 3-3 3M18 15H5m3-3-3 3 3 3',
  'M6 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm3 7 8 7m-4-4 2-2m0 4 2-2',
  'M2 4h16v12H2zM2 4l8 7 8-7',
  'M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16ZM2 10h16M10 2c-5 5-5 11 0 16 5-5 5-11 0-16',
  'M3 3h14v14H3zM6 7l3 3-3 3m5 0h3',
  'M5 2h7l4 4v12H5zM12 2v5h4M8 11h5m-5 3h5',
  'M3 3h5v5H3zM12 12h5v5h-5zM8 5h6v7M12 5l2 2 2-2',
  'M10 1l2 6 6 3-6 2-2 7-2-7-7-2 7-3 2-6Z',
];
function stationEmblem(index) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 20 20');
  svg.setAttribute('aria-hidden', 'true');
  svg.classList.add('station-emblem');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', stationIcons[index % stationIcons.length]);
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', 'currentColor');
  path.setAttribute('stroke-width', '1.25');
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  svg.append(path);
  return svg;
}
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
      : `${missionStartsRemaining} / 3 mission starts remain for this network. Three runs total for this network. Picking up an existing run doesn't use a start.`;
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
    $('note-status').textContent = notesDirty ? 'New changes are not saved yet.' : 'Note saved.';
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
  if (changed)
    $('sector-list').children[state.current].scrollIntoView({ block: 'nearest', inline: 'center' });
  $('sector-label').textContent =
    `SECTOR ${String(state.current + 1).padStart(2, '0')} / ${state.levels.length} — ${room.topic.toUpperCase()}`;
  const recovered = state.levels.filter((level) => level.solved).length;
  const progress = $('mission-progress-fill').parentElement;
  progress.setAttribute('aria-valuemax', String(state.levels.length));
  progress.setAttribute('aria-valuenow', String(recovered));
  $('mission-progress-fill').style.width = `${(recovered / state.levels.length) * 100}%`;
  $('result-recovery').textContent = `${recovered} / ${state.levels.length}`;
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
        m.role === 'user' ? 'YOU / MESSAGE' : room.agent.toUpperCase(),
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
  $('send-button').textContent = room.document ? 'Send edited source ↗' : 'Send message ↗';
  $('keyboard-send-help').textContent = room.document
    ? 'Message: Enter to send · Source: Ctrl / ⌘ + Enter to send'
    : 'Enter to send · Shift + Enter for a new line';
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
      state.current === state.levels.length - 1 ? 'Head home →' : 'Next challenge →';
  }
  $('game-over').hidden = !state.game_over;
  if (state.game_over && !previous?.game_over) $('game-over-title').focus();
  if (changed) {
    $('message-input').value = '';
    $('document-input').value = room.document;
    $('notes-input').value = room.note;
    $('note-status').textContent = room.note ? 'Note saved.' : '';
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
    : 'Back to mission start';
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
  focusAfterReply(result, sourceInput);
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
  focusAfterReply(result, $('message-input'));
});
function focusAfterReply(result, input) {
  if (!result || result.finished || result.game_over) return;
  if (result.room.solved) $('next-button').focus();
  else if ([document.body, $('send-button'), $('ask-button')].includes(document.activeElement))
    input.focus({ preventScroll: true });
}
for (const id of ['message-input', 'document-input'])
  $(id).addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || event.isComposing || event.keyCode === 229) return;
    const send =
      !event.shiftKey &&
      !event.altKey &&
      (id === 'message-input' || event.ctrlKey || event.metaKey);
    if (!send) return;
    event.preventDefault();
    if (busy || event.repeat || !state || state.room.solved || state.game_over) return;
    if (id === 'message-input' && state.room.document) $('ask-button').click();
    else $('chat-form').requestSubmit();
  });
$('keyboard-help').addEventListener('click', () => $('keyboard-dialog').showModal());
for (const dialog of document.querySelectorAll('dialog'))
  dialog.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab' || event.ctrlKey || event.metaKey || event.altKey) return;
    const controls = [
      ...dialog.querySelectorAll('button, a[href], input, textarea, select, [tabindex]'),
    ].filter(
      (control) => !control.disabled && control.tabIndex >= 0 && control.getClientRects().length,
    );
    const first = controls[0];
    const last = controls.at(-1);
    if (!first) return;
    if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
      event.preventDefault();
      last.focus();
    } else if (
      !event.shiftKey &&
      (document.activeElement === last || document.activeElement === dialog)
    ) {
      event.preventDefault();
      first.focus();
    }
  });
document.addEventListener('keydown', (event) => {
  if (
    event.defaultPrevented ||
    event.isComposing ||
    event.repeat ||
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    document.querySelector('dialog[open]')
  )
    return;
  if (
    event.target instanceof Element &&
    event.target.closest('input, textarea, select, [contenteditable="true"]')
  )
    return;
  if (event.key === '?') {
    event.preventDefault();
    $('keyboard-dialog').showModal();
  } else if (
    event.key === '/' &&
    state &&
    !state.finished &&
    !state.game_over &&
    !state.room.solved
  ) {
    event.preventDefault();
    $('message-input').focus();
  }
});
$('station-grid').addEventListener('keydown', (event) => {
  const cards = [...$('station-grid').children];
  const index = cards.indexOf(event.target);
  if (index < 0 || event.altKey || event.ctrlKey || event.metaKey) return;
  const columns = getComputedStyle($('station-grid')).gridTemplateColumns.split(' ').length;
  const targets = {
    ArrowLeft: index - 1,
    ArrowRight: index + 1,
    ArrowUp: index - columns,
    ArrowDown: index + columns,
    Home: 0,
    End: cards.length - 1,
  };
  if (!(event.key in targets)) return;
  event.preventDefault();
  const card = cards[Math.max(0, Math.min(cards.length - 1, targets[event.key]))];
  card.focus();
  card.click();
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
  $('note-status').textContent = 'Note not saved yet.';
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
        button.dataset.chapter = String(Math.floor(i / 5));
        button.setAttribute('aria-pressed', 'false');
        const heading = element('span', undefined, 'station-index');
        heading.append(stationEmblem(i), element('span', String(i + 1).padStart(2, '0')));
        button.append(heading, element('strong', station.name), element('small', station.subject));
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
