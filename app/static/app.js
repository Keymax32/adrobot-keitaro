const $ = id => document.getElementById(id);
const statusLine = $('status');
let campaign = null;
let streams = [];
let busy = false;

function node(tag, text, css) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (css) el.className = css;
  return el;
}

function notify(message, error = false) {
  statusLine.textContent = message;
  statusLine.className = error ? 'error' : '';
}

async function api(path, method = 'GET', payload) {
  const res = await fetch('/api/' + path, {
    method, headers: {'Content-Type': 'application/json'},
    body: payload === undefined ? undefined : JSON.stringify(payload)
  });
  const data = await res.json();
  if (!res.ok) throw Error(Array.isArray(data.detail)
    ? data.detail.map(x => x.msg).join('. ') : data.detail || 'Ошибка запроса');
  return data;
}

async function run(task) {
  if (busy) return;
  busy = true;
  document.querySelector('main').inert = true;
  notify('Выполняется запрос…');
  try { notify(await task() || ''); }
  catch (e) { notify(e.message, true); }
  finally { busy = false; document.querySelector('main').inert = false; }
}

function mode(create) {
  $('editor').hidden = create;
  $('creator').hidden = !create;
  $('tab-edit').setAttribute('aria-pressed', !create);
  $('tab-create').setAttribute('aria-pressed', create);
}

$('tab-edit').onclick = () => { mode(false); notify(''); };
$('tab-create').onclick = () => run(async () => {
  mode(true);
  const settings = await api('settings');
  for (const [field, key] of Object.entries({domain_id:'domains', group_id:'groups', traffic_source_id:'sources'})) {
    $('create-form').elements[field].replaceChildren(new Option('Выберите…', ''),
      ...settings[key].map(x => new Option(x.name + ' · #' + x.id, x.id)));
  }
});

async function openCampaign(cid) {
  let rows = await api('campaigns/' + cid + '/streams');
  if (!rows.length) rows = await api('campaigns/' + cid + '/fetch', 'POST');
  campaign = cid;
  streams = rows;
  sessionStorage.setItem('campaign', cid);
  $('open-form').elements.cid.value = cid;
  $('workspace').hidden = false;
  $('campaign-title').textContent = 'Кампания #' + cid;
  render();
}

$('open-form').onsubmit = event => {
  event.preventDefault();
  run(() => openCampaign(Number(event.target.elements.cid.value)));
};
$('fetch').onclick = () => run(async () => {
  streams = await api('campaigns/' + campaign + '/fetch', 'POST');
  render();
  return 'Потоки загружены.';
});
$('create-form').onsubmit = event => {
  event.preventDefault();
  run(async () => {
    const data = Object.fromEntries(new FormData(event.target));
    const result = await api('campaigns', 'POST', data);
    mode(false);
    $('open-form').elements.cid.value = result.id;
    try { await openCampaign(result.id); }
    catch (e) { throw Error('Создана кампания #' + result.id + '. ' + e.message); }
    return 'Создана кампания ' + result.name + ' · #' + result.id;
  });
};

function button(text, fn) {
  const el = node('button', text);
  el.type = 'button';
  el.onclick = () => run(fn);
  return el;
}

async function change(stream, action, offer_id) {
  const result = await api('streams/' + stream.id, 'POST', {version: stream.version, action, offer_id});
  streams = streams.map(s => s.id === stream.id ? result : s);
  render();
  return action === 'push' ? 'Изменения опубликованы.' : '';
}

function lookup(stream) {
  const wrap = node('div', undefined, 'lookup');
  const input = node('input');
  input.placeholder = 'ID или название оффера';
  input.setAttribute('aria-label', 'Поиск оффера');
  const select = node('select');
  select.setAttribute('aria-label', 'Найденные офферы');
  const add = button('Добавить', () => change(stream, 'add', Number(select.value)));
  select.hidden = add.hidden = true;
  const search = button('Найти', async () => {
    const rows = await api('offers?q=' + encodeURIComponent(input.value));
    const matches = rows.filter(x => !stream.offers.some(r => r.id === x.id));
    select.replaceChildren(...matches.map(x => new Option(x.name + ' · #' + x.id, x.id)));
    select.hidden = add.hidden = !matches.length;
    return matches.length ? '' : 'Нет подходящих офферов.';
  });
  input.oninput = () => { select.hidden = add.hidden = true; };
  input.onkeydown = e => { if (e.key === 'Enter') search.click(); };
  wrap.append(input, search, select, add);
  return wrap;
}

function render() {
  const list = $('streams');
  list.replaceChildren();
  if (!streams.length) list.append(node('p', 'В кампании нет потоков.'));
  for (const s of streams) {
    const card = node('article', undefined, s.dirty ? 'stream dirty' : 'stream');
    const heading = node('div', undefined, 'heading');
    heading.append(node('h3', s.name + ' · #' + s.id));
    if (s.dirty) heading.append(node('span', 'Черновик', 'badge'));
    card.append(heading);
    if (s.editable) {
      for (const r of s.offers) {
        const row = node('div', undefined, r.removed ? 'offer removed' : 'offer');
        const state = r.removed ? ' · архив' : r.state === 'disabled' ? ' · отключён' : '';
        row.append(node('span', r.name + ' · #' + r.id + state), node('strong', r.share + '%'));
        if (!r.removed && r.state === 'active') row.append(button(r.pinned ? 'Открепить' : 'Закрепить',
          () => change(s, 'pin', r.id)));
        row.append(button(r.removed ? 'Вернуть' : 'Удалить', () => change(s, r.removed ? 'restore' : 'remove', r.id)));
        card.append(row);
      }
      card.append(lookup(s));
    }
    if (s.dirty) {
      const actions = node('div', undefined, 'actions');
      const publish = button('Опубликовать', () => change(s, 'push'));
      publish.className = 'primary';
      actions.append(publish, button('Отменить', () => change(s, 'cancel')));
      card.append(actions);
    }
    list.append(card);
  }
}

const saved = Number(sessionStorage.getItem('campaign'));
if (saved > 0) run(() => openCampaign(saved));

