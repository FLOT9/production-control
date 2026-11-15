"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const escape = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const icons = {
  chat: '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5A8.5 8.5 0 0 1 10.5 3h2A8.5 8.5 0 0 1 21 11.5Z"/><path d="M7 10h9M7 14h6"/>',
  dashboard: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
  box: '<path d="m12 3 9 5v9l-9 5-9-5V8l9-5Zm0 10v9M3 8l9 5 9-5M7.5 5.5l9 5"/>',
  factory: '<path d="M3 21V9l6 3V8l6 3V3h5v18H3Zm5-5v2m5-2v2m5-2v2"/>',
  file: '<path d="M14 2H5v20h14V7l-5-5Zm0 0v5h5M8 12h8M8 16h6"/>',
  refresh: '<path d="M20 7a8 8 0 1 0 1 9M20 3v5h-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.box}</svg>`;
document.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); });
const names = {overview:"Обзор",batches:"Партии",products:"Продукция",centers:"Рабочие центры",reports:"Отчёты и файлы",assistant:"Ассистент"};
const state = { page:"overview", version:0, offset:0, limit:10, filters:{}, batches:[], editing:null, polling:false };
const main = $('#main');
const modal = $('#modal');
let modalVersion = 0;
const number = value => value === null || value === undefined ? "—" : new Intl.NumberFormat('ru-RU').format(value);
const percent = value => value === null || value === undefined ? "—" : `${number(Math.round(value * 10) / 10)}%`;
const date = value => value ? new Date(`${value}T12:00:00`).toLocaleDateString('ru-RU') : "—";
const dateTime = value => value ? new Date(value).toLocaleString('ru-RU', {dateStyle:'short',timeStyle:'short'}) : "—";
const localDateTime = value => {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0,16);
};
const badge = closed => `<span class="badge ${closed ? 'closed' : ''}">${closed ? 'Закрыта' : 'В работе'}</span>`;
const empty = (title, description = "", symbol = "layers") => `<div class="empty">${icon(symbol)}<strong>${escape(title)}</strong>${escape(description)}</div>`;
const btn = (label, action, symbol = '', primary = false, extra = '') => `<button type="button" class="btn ${primary ? 'primary' : ''}" data-action="${action}" ${extra}>${symbol ? icon(symbol) : ''}${label}</button>`;
const input = (label, name, type = 'text', value = '', extra = '', full = false) => `<label class="${full ? 'full' : ''}">${label}<input name="${name}" type="${type}" value="${escape(value)}" ${extra}></label>`;
const positive = 'required min="1" max="2147483647" step="1"';
const heading = (title, subtitle, actions = '') => `<div class="page-heading"><div><p class="eyebrow">PRODUCTION CONTROL</p><h1>${title}</h1><p class="subtitle">${subtitle}</p></div><div class="actions">${actions}</div></div><div class="notice error" id="page-error" role="alert" hidden></div>`;

async function api(path, options = {}) {
  const response = await fetch(path.startsWith('/health') ? path : `/api/v1${path}`, {
    ...options, signal: AbortSignal.timeout(35000),
    headers: { ...(options.body && !(options.body instanceof FormData) ? {'Content-Type':'application/json'} : {}), ...options.headers },
  });
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!response.ok) {
    let detail = data?.detail ?? data?.error ?? `Ошибка запроса (${response.status})`;
    if (Array.isArray(detail)) detail = detail.map(item => `${item.loc?.filter(x => x !== 'body').join(' · ') || 'Данные'}: ${item.msg}`).join('\n');
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}
const send = (path, body, method = 'POST') => api(path, {method, body:JSON.stringify(body)});
function errorText(error) {
  return error.name === 'TimeoutError' ? 'API не ответил вовремя. Попробуйте обновить.' : error.message || 'Не удалось выполнить запрос';
}
function pageError(error) {
  const el = $('#page-error');
  if (!el) return;
  el.hidden = false;
  el.textContent = errorText(error);
}
let toastTimer;
function toast(text) {
  const el = $('#toast'); el.textContent = text; el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 4500);
}
async function connection() {
  const el = $('#connection');
  try { await api('/health'); el.className = 'connection online'; el.textContent = 'API подключён'; }
  catch { el.className = 'connection offline'; el.textContent = 'API недоступен'; }
}
function openModal(html) {
  modalVersion += 1;
  $('#modal-content').innerHTML = `${btn('', 'close-modal', 'close', false, 'aria-label="Закрыть" style="position:absolute;top:16px;right:16px"')}${html}`;
  if (!modal.open) modal.showModal();
}
function formEnd(label, symbol = 'check') {
  return `<p class="form-error" role="alert"></p><div class="form-actions"><button class="btn primary" type="submit">${icon(symbol)}${label}</button></div>`;
}
function batchTable(items, {loading = false, compact = false} = {}) {
  if (!items.length) return empty(loading ? 'Загружаем партии…' : 'Пока нет партий', loading ? 'Получаем данные из API' : 'Создайте партию или измените фильтры');
  return `<div class="table-wrap"><table><thead><tr><th>ПАРТИЯ / НОМЕНКЛАТУРА</th><th>РАБОЧИЙ ЦЕНТР</th><th>ДАТА</th><th>СМЕНА</th><th>СТАТУС</th><th></th></tr></thead><tbody>${items.map(b => `<tr><td><button class="batch-link" data-action="batch-detail" data-id="${b.id}">№ ${number(b.batch_number)}</button><span class="cell-sub">ID ${b.id} · ${escape(b.nomenclature)}</span></td><td>РЦ #${b.work_center_id}<span class="cell-sub">${escape(b.team)}</span></td><td>${date(b.batch_date)}</td><td>${escape(b.shift)}</td><td>${badge(b.is_closed)}</td><td><button class="icon-btn" data-action="batch-detail" data-id="${b.id}" aria-label="Открыть партию ${b.batch_number}">${icon('arrow')}</button></td></tr>`).join('')}</tbody></table></div>`;
}
function metric(label, value, foot, symbol, color = '') {
  return `<div class="card"><div class="card-label">${label}${icon(symbol)}</div><div class="card-value ${color}">${number(value)}</div><div class="card-foot">${foot}</div></div>`;
}
async function overview(version) {
  main.innerHTML = heading('Обзор производства', 'Состояние партий и продукции в реальном времени', btn('Обновить','refresh','refresh') + btn('Новая партия','new-batch','plus',true)) + '<div id="overview-data"></div>';
  const render = (s, list, loading = false) => {
    $('#overview-data').innerHTML = `<div class="cards">${metric('Всего партий',s?.total_batches,'За весь период','layers')}${metric('В работе',s?.open_batches,'<span class="dot"></span>Открытые партии','clock')}${metric('Агрегировано',s?.aggregated_products,'Единиц продукции','check','accent')}${metric('Ожидает агрегации',s?.pending_products,'Единиц продукции','box')}</div>
    <div class="overview-grid"><section class="panel"><div class="panel-head"><div><h2>Агрегация продукции</h2><p>Общий прогресс по всем партиям</p></div>${icon('box')}</div><div class="panel-body"><div class="progress-top"><span class="progress-value">${percent(s?.aggregation_percent)}</span><p>${number(s?.aggregated_products)} из ${number(s?.total_products)} единиц агрегировано</p></div><div class="progress-track"><div class="progress-fill" style="width:${s?.aggregation_percent || 0}%"></div></div><div class="progress-legend"><span><i class="legend-dot"></i>Агрегировано</span><span><i class="legend-dot pending"></i>Ожидает агрегации</span></div></div></section>
    <section class="panel"><div class="panel-head"><div><h2>Состояние партий</h2><p>Текущая загрузка производства</p></div>${icon('layers')}</div><div class="panel-body"><div class="status-row"><span><i class="legend-dot"></i>В работе</span><strong>${number(s?.open_batches)}</strong></div><div class="status-row"><span><i class="legend-dot closed"></i>Завершено</span><strong>${number(s?.closed_batches)}</strong></div><div class="status-row"><span>Всего продукции</span><strong>${number(s?.total_products)} ед.</strong></div></div></section></div>
    <section class="panel"><div class="panel-head"><div><h2>Последние партии</h2><p>Последние записи в списке производства</p></div><a class="link" href="#batches">Все партии →</a></div>${batchTable(list, {loading, compact:true})}<div class="table-footer"><span>Данные из Production Control API</span><span>${loading ? 'Подключение…' : 'Показано ' + list.length}</span></div></section>`;
  };
  render(null, [], true);
  const results = await Promise.allSettled([api('/dashboard/summary'), api('/batches?limit=5&offset=0')]);
  if (version !== state.version) return;
  render(results[0].status === 'fulfilled' ? results[0].value : null, results[1].status === 'fulfilled' ? results[1].value.items : []);
  const failed = results.find(r => r.status === 'rejected');
  if (failed) pageError(failed.reason);
}
function filterFields() {
  const f = state.filters;
  return `${input('Номер партии','batch_number','number',f.batch_number || '', 'min="1" max="2147483647" placeholder="Все партии"')}<label>Статус<select name="is_closed"><option value="">Все статусы</option><option value="false" ${f.is_closed === 'false' ? 'selected' : ''}>В работе</option><option value="true" ${f.is_closed === 'true' ? 'selected' : ''}>Закрыта</option></select></label>${input('Дата партии','batch_date','date',f.batch_date || '')}${input('ID рабочего центра','work_center_id','number',f.work_center_id || '', 'min="1" placeholder="Все центры"')}${input('Смена','shift','text',f.shift || '', 'maxlength="50" placeholder="Все смены"')}`;
}
async function batches(version) {
  main.innerHTML = heading('Производственные партии','Управляйте заданиями, сменами и статусами партий',btn('Обновить','refresh','refresh') + btn('Новая партия','new-batch','plus',true)) + `<section class="panel"><form class="filters" data-form="filters">${filterFields()}<button class="btn" type="submit">Применить</button>${btn('Сбросить','reset-filters')}</form><div id="batch-table">${batchTable([], {loading:true})}</div><div id="batch-pagination"></div></section>`;
  try {
    const params = new URLSearchParams({...state.filters,limit:state.limit,offset:state.offset});
    const data = await api(`/batches?${params}`);
    if (version !== state.version) return;
    state.batches = data.items;
    $('#batch-table').innerHTML = batchTable(data.items);
    $('#batch-pagination').innerHTML = `<div class="table-footer"><span>${data.total ? `${state.offset + 1}–${Math.min(state.offset + state.limit,data.total)} из ${number(data.total)} партий` : '0 партий'}</span><div class="pagination">${btn('←','previous','',false, state.offset === 0 ? 'disabled aria-label="Предыдущая страница"' : 'aria-label="Предыдущая страница"')}${btn('→','next','',false,state.offset + state.limit >= data.total ? 'disabled aria-label="Следующая страница"' : 'aria-label="Следующая страница"')}</div></div>`;
  } catch (e) { if (version === state.version) { pageError(e); $('#batch-table').innerHTML = empty('Данные не загружены','Проверьте подключение к API и нажмите «Обновить»'); } }
}
function batchForm(batch = null) {
  state.editing = batch;
  const defaults = {batch_number:'',batch_date:localDateTime(Date.now()).slice(0,10),shift:'1',team:'',nomenclature:'',ekn_code:'',task_description:'',shift_start:localDateTime(Date.now()),shift_end:localDateTime(Date.now()+8*3600000)};
  const b = batch || defaults;
  const fields = `${input('Номер партии','batch_number','number',b.batch_number,positive)}${input('Дата партии','batch_date','date',b.batch_date,'required')}${input('Номенклатура','nomenclature','text',b.nomenclature,'required maxlength="255"',true)}${input('Код ЕКН','ekn_code','text',b.ekn_code,'required maxlength="100"')}${input('Бригада','team','text',b.team,'required maxlength="255"')}${input('Смена','shift','text',b.shift,'required maxlength="50"')}${batch ? input('ID рабочего центра','work_center_id','number',b.work_center_id,positive) : input('Идентификатор РЦ','work_center_identifier','text','','required maxlength="100" placeholder="Например, LINE-01"')}${batch ? '' : input('Название рабочего центра','work_center_name','text','','required maxlength="255"',true)}${input('Начало смены','shift_start','datetime-local',batch ? localDateTime(b.shift_start) : b.shift_start,'required')}${input('Окончание смены','shift_end','datetime-local',batch ? localDateTime(b.shift_end) : b.shift_end,'required')}<label class="full">Задание на смену<textarea name="task_description" required>${escape(b.task_description)}</textarea></label>`;
  openModal(`<h2 id="modal-title">${batch ? 'Редактирование партии № ' + number(b.batch_number) : 'Новая партия'}</h2><p class="hint" style="margin:8px 0 20px">${batch ? 'Сохраняются только изменённые поля.' : 'Рабочий центр будет найден или создан по идентификатору.'}</p><form class="form-stack" data-form="${batch ? 'edit-batch' : 'create-batch'}"><div class="form-grid">${fields}</div>${formEnd('Сохранить партию')}</form>`);
}
async function batchDetail(id) {
  openModal(`<h2 id="modal-title">Партия #${Number(id)}</h2>${empty('Загружаем карточку…')}`);
  const requestVersion = modalVersion;
  try {
    const [b, s] = await Promise.all([api(`/batches/${id}`),api(`/batches/${id}/statistics`)]);
    if (!modal.open || modalVersion !== requestVersion) return;
    state.editing = b;
    openModal(`<div class="detail-header"><div><p class="eyebrow">ПРОИЗВОДСТВЕННАЯ ПАРТИЯ</p><h2 id="modal-title">Партия № ${number(b.batch_number)}</h2><p class="hint">${escape(b.nomenclature)}</p></div></div>${badge(b.is_closed)}<div class="detail-grid"><div><small>Рабочий центр</small>РЦ #${b.work_center_id}</div><div><small>Дата / смена</small>${date(b.batch_date)} / ${escape(b.shift)}</div><div><small>Бригада</small>${escape(b.team)}</div><div><small>Код ЕКН</small>${escape(b.ekn_code)}</div><div><small>Начало смены</small>${dateTime(b.shift_start)}</div><div><small>Окончание смены</small>${dateTime(b.shift_end)}</div><div class="full"><small>Задание</small>${escape(b.task_description)}</div></div><div class="detail-metrics"><div><strong>${number(s.total_products)}</strong><span>Всего единиц</span></div><div><strong class="accent">${number(s.aggregated_products)}</strong><span>Агрегировано</span></div><div><strong>${percent(s.aggregation_percent)}</strong><span>Прогресс</span></div></div><h3>Продукция</h3>${b.products.length ? `<div class="table-wrap"><table><thead><tr><th>УНИКАЛЬНЫЙ КОД</th><th>СТАТУС</th><th>АГРЕГАЦИЯ</th></tr></thead><tbody>${b.products.map(p => `<tr><td class="mono">${escape(p.unique_code)}</td><td><span class="badge ${p.is_aggregated ? '' : 'queued'}">${p.is_aggregated ? 'Агрегировано' : 'Ожидает'}</span></td><td>${dateTime(p.aggregated_at)}</td></tr>`).join('')}</tbody></table></div>` : empty('Продукции пока нет','Добавьте коды на странице «Продукция»','box')}<p class="form-error" id="detail-error" role="alert"></p><div class="actions">${btn('Редактировать','edit-batch')}${btn(b.is_closed ? 'Открыть партию' : 'Закрыть партию','toggle-batch')}${btn('Отчёт','batch-report','file')}${btn('Удалить','delete-batch','',false,'style="color:var(--red);margin-left:auto"')}</div>`);
  } catch(e) { if (modal.open && modalVersion === requestVersion) openModal(`<h2 id="modal-title">Партия #${Number(id)}</h2><p class="form-error" role="alert">${escape(errorText(e))}</p>`); }
}
function products() {
  main.innerHTML = heading('Продукция и агрегация','Регистрация кодов и привязка продукции к производственным партиям') + `<div class="two-col"><section class="panel form-panel"><div class="panel-head"><div><h2>Зарегистрировать продукцию</h2><p>Добавление одной единицы в открытую партию</p></div>${icon('box')}</div><div class="panel-body"><form class="form-stack" data-form="create-product">${input('ID партии','batch_id','number','',positive + ' placeholder="Например, 1"')}${input('Уникальный код','unique_code','text','','required maxlength="255" placeholder="Введите или отсканируйте код"')}${formEnd('Добавить продукцию','plus')}</form><div data-result="create-product"></div></div></section><section class="panel form-panel"><div class="panel-head"><div><h2>Агрегировать продукцию</h2><p>Подтвердите коды продукции в партии</p></div>${icon('check')}</div><div class="panel-body"><form class="form-stack" data-form="aggregate">${input('ID партии','batch_id','number','',positive)}<label>Уникальные коды<textarea name="unique_codes" required placeholder="Каждый код с новой строки"></textarea></label><label>Способ обработки<select name="mode"><option value="sync">Сразу — для небольшого списка</option><option value="async">В фоне — через Celery</option></select></label><p class="hint">Результат сохраняется отдельно для каждого кода. Ошибки отдельных единиц не отменяют успешную агрегацию.</p>${formEnd('Агрегировать')}</form><div data-result="aggregate"></div></div></section></div><section class="panel section-gap"><div class="panel-head"><h2>Посмотреть продукцию партии</h2></div><div class="panel-body"><form class="filters" style="padding:0;border:0" data-form="lookup-batch">${input('ID партии','batch_id','number','',positive)}<button class="btn" type="submit">Открыть карточку ${icon('arrow')}</button></form></div></section>`;
}
function centers() {
  main.innerHTML = heading('Рабочие центры','Создание центров и просмотр по идентификатору записи') + `<div class="two-col"><section class="panel form-panel"><div class="panel-head"><div><h2>Новый рабочий центр</h2><p>Линия, участок или производственная площадка</p></div>${icon('factory')}</div><div class="panel-body"><form class="form-stack" data-form="create-center">${input('Идентификатор','identifier','text','','required maxlength="100" placeholder="LINE-01"')}${input('Название','name','text','','required maxlength="255" placeholder="Линия упаковки № 1"')}${formEnd('Создать центр','plus')}</form><div data-result="create-center"></div></div></section><section class="panel form-panel"><div class="panel-head"><div><h2>Найти рабочий центр</h2><p>По ID из производственной партии</p></div>${icon('dashboard')}</div><div class="panel-body"><form class="form-stack" data-form="lookup-center">${input('ID рабочего центра','id','number','',positive)}${formEnd('Найти центр','arrow')}</form><div data-result="lookup-center"></div></div><div class="info-strip">В текущем API нет общего списка рабочих центров. ID центра отображается в таблице и карточке партии.</div></section></div>`;
}
function readTasks() {
  try { const value = JSON.parse(localStorage.getItem('kontur-tasks') || '[]'); return Array.isArray(value) ? value.filter(t => typeof t?.task_id === 'string' && typeof t?.title === 'string').slice(0,20) : []; }
  catch { return []; }
}
let tasks = readTasks();
function saveTasks() { try { localStorage.setItem('kontur-tasks',JSON.stringify(tasks)); } catch { /* Storage may be unavailable in private browsing. */ } }
function addTask(data, title, kind, meta = {}) {
  tasks.unshift({...data,title,kind,...meta,created:new Date().toISOString()}); tasks = tasks.slice(0,20); saveTasks();
  toast('Задача поставлена в очередь. Статус — в разделе «Отчёты и файлы».'); renderTasks();
}
function reports() {
  main.innerHTML = heading('Отчёты и файлы','Выгрузка данных, импорт партий и отслеживание фоновых задач',btn('Обновить статусы','refresh-tasks','refresh')) + `<div class="two-col"><section class="panel form-panel"><div class="panel-head"><div><h2>Отчёт по партии</h2><p>Продукция и результаты агрегации</p></div>${icon('file')}</div><div class="panel-body"><form class="form-stack" data-form="batch-report">${input('ID партии','batch_id','number','',positive)}<label>Формат<select name="format"><option value="excel">Excel (.xlsx)</option><option value="pdf">PDF (.pdf)</option></select></label>${formEnd('Сформировать отчёт','file')}</form></div></section><section class="panel form-panel"><div class="panel-head"><div><h2>Сводный отчёт</h2><p>Общая статистика производства в Excel</p></div>${icon('dashboard')}</div><div class="panel-body"><form class="form-stack" data-form="summary"><p class="hint">Выгрузка сводных показателей по производственным партиям и продукции за весь период.</p>${formEnd('Сформировать сводку','file')}</form></div></section><section class="panel form-panel"><div class="panel-head"><div><h2>Импорт партий</h2><p>Загрузите CSV или Excel по схеме API</p></div>${icon('layers')}</div><div class="panel-body"><form class="form-stack" data-form="import"><label>Файл с партиями<input type="file" name="file" accept=".csv,.xlsx" required></label><p class="hint">Строки обрабатываются независимо. Результат покажет ID созданных партий и ошибки по строкам.</p>${formEnd('Загрузить файл','plus')}</form></div></section><section class="panel form-panel"><div class="panel-head"><div><h2>Экспорт партий</h2><p>Выгрузите все партии или текущую выборку</p></div>${icon('download')}</div><div class="panel-body"><form class="form-stack" data-form="export"><label>Формат<select name="format"><option value="csv">CSV (.csv)</option><option value="excel">Excel (.xlsx)</option></select></label><label>Выборка<select name="selection"><option value="all">Все партии</option><option value="filters">Фильтры со страницы «Партии»</option></select></label><p class="hint" id="export-filters">Текущие фильтры: ${escape(Object.entries(state.filters).map(([k,v]) => `${k}: ${v}`).join(', ') || 'не заданы')}</p>${formEnd('Экспортировать','download')}</form></div></section></div><section class="panel section-gap"><div class="panel-head"><div><h2>Последние задачи</h2><p>Статусы обновляются каждые 4 секунды на этой странице</p></div>${btn('Убрать завершённые','clear-tasks')}</div><div id="task-list"></div></section><p class="footnote">Список задач хранится в этом браузере. Файл доступен после завершения задачи.</p>`;
  if (state.reportBatchId) $('[data-form="batch-report"] [name="batch_id"]').value = state.reportBatchId;
  renderTasks(); pollTasks();
}
const terminal = status => ['SUCCESS','FAILURE','REVOKED'].includes(status);
function downloadPath(t) {
  const id = t.result?.report_id;
  if (!id || !/^[0-9a-f-]{36}$/i.test(id)) return '';
  if (t.kind === 'summary') return `/api/v1/reports/${id}/download`;
  if (t.kind === 'export') return `/api/v1/batches/exports/${id}/download?format=${t.format === 'excel' ? 'excel' : 'csv'}`;
  if (t.kind === 'batch-report') return `/api/v1/batches/${Number(t.batch_id)}/reports/${id}/download?format=${t.format === 'pdf' ? 'pdf' : 'excel'}`;
  return '';
}
function renderTasks() {
  const el = $('#task-list'); if (!el) return;
  const labels = {queued:'В очереди',PENDING:'Ожидает',STARTED:'Выполняется',PROGRESS:'Выполняется',RETRY:'Повтор',SUCCESS:'Завершена',FAILURE:'Ошибка',REVOKED:'Отменена'};
  el.innerHTML = tasks.length ? `<div class="task-list">${tasks.map(t => {
    const download = t.status === 'SUCCESS' ? downloadPath(t) : '';
    let result = '';
    if (t.status === 'SUCCESS' && t.kind === 'import') result = `Создано: ${t.result?.processed?.length || 0}. Ошибок: ${t.result?.failed?.length || 0}.\n${JSON.stringify(t.result,null,2)}`;
    if (t.status === 'SUCCESS' && t.kind === 'aggregate') result = `Агрегировано: ${t.result?.aggregated || 0}. Ошибок: ${t.result?.failed || 0}.\n${JSON.stringify(t.result?.errors || [],null,2)}`;
    return `<article class="task-item"><div class="task-line"><strong>${escape(t.title)}</strong><span class="badge ${t.status === 'SUCCESS' ? '' : ['FAILURE','REVOKED'].includes(t.status) ? 'failure' : 'queued'}">${escape(labels[t.status] || t.status)}</span></div><div class="mono">${escape(t.task_id)} · ${escape(dateTime(t.created))}</div>${t.progress ? `<div class="progress-track microbar"><div class="progress-fill" style="width:${Math.max(0,Math.min(100,Number(t.progress.progress)||0))}%"></div></div><p class="hint">${number(t.progress.current)} из ${number(t.progress.total)}</p>` : ''}${t.error || t.pollError ? `<p class="form-error">${escape(t.error || t.pollError)}</p>` : ''}${result ? `<pre class="task-result">${escape(result)}</pre>` : ''}${download ? `<a class="btn" href="${download}">${icon('download')}Скачать ${t.format === 'pdf' ? 'PDF' : t.format === 'csv' ? 'CSV' : 'Excel'}</a>` : ''}</article>`;
  }).join('')}</div>` : empty('Задач пока нет','Сформируйте отчёт или загрузите файл','file');
}
async function pollTasks() {
  if (state.polling || state.page !== 'reports') return;
  state.polling = true;
  try {
    await Promise.all(tasks.filter(t => !terminal(t.status)).map(async t => {
      try { const data = await api(`/tasks/${encodeURIComponent(t.task_id)}`); Object.assign(t,data,{pollError:null}); }
      catch(e) { t.pollError = errorText(e); }
    }));
    saveTasks(); if (state.page === 'reports') renderTasks();
  } finally { state.polling = false; }
}
function renderResult(form, html) {
  const target = $(`[data-result="${form.dataset.form}"]`);
  if (target && form.isConnected) target.innerHTML = `<div class="result">${html}</div>`;
}
function centerResult(c) { return `<h3>${escape(c.name)}</h3><p>ID: <strong>${c.id}</strong> · <span class="mono">${escape(c.identifier)}</span></p><p class="hint">Создан: ${dateTime(c.created_at)}</p>`; }
async function submit(form) {
  const data = Object.fromEntries(new FormData(form));
  const type = form.dataset.form;
  const submitButton = $('button[type="submit"]',form);
  const errorEl = $('.form-error',form);
  if (errorEl) errorEl.textContent = '';
  const previousResult = $(`[data-result="${type}"]`);
  if (previousResult) previousResult.innerHTML = '';
  if (submitButton) submitButton.disabled = true;
  try {
    if (type === 'filters') {
      state.filters = Object.fromEntries(Object.entries(data).filter(([,v]) => v !== '')); state.offset = 0; await navigate();
    } else if (type === 'create-batch' || type === 'edit-batch') {
      for (const key of ['batch_number','work_center_id']) if (key in data) data[key] = Number(data[key]);
      if (new Date(data.shift_end) <= new Date(data.shift_start)) throw new Error('Окончание смены должно быть позже начала.');
      data.shift_start = new Date(data.shift_start).toISOString(); data.shift_end = new Date(data.shift_end).toISOString();
      if (type === 'create-batch') await send('/batches',[{...data,is_closed:false}]);
      else {
        const original = state.editing;
        const payload = Object.fromEntries(Object.entries(data).filter(([k,v]) => k.startsWith('shift_') ? form.elements[k].value !== localDateTime(original[k]) : v !== original[k]));
        if (Object.keys(payload).length) await send(`/batches/${original.id}`,payload,'PATCH');
      }
      modal.close(); toast('Партия сохранена'); if (['overview','batches'].includes(state.page)) await navigate();
    } else if (type === 'delete-batch') {
      await api(`/batches/${Number(data.id)}`,{method:'DELETE'}); modal.close(); toast('Партия удалена'); await navigate();
    } else if (type === 'create-product') {
      const p = await send('/products',{batch_id:Number(data.batch_id),unique_code:data.unique_code.trim()});
      renderResult(form,`<p class="green">Продукция зарегистрирована</p><p class="mono">${escape(p.unique_code)}</p><p>Партия #${p.batch_id} · ID продукции: ${p.id}</p>`); form.elements.unique_code.value = ''; toast('Продукция добавлена');
    } else if (type === 'aggregate') {
      const codes = data.unique_codes.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
      if (!codes.length) throw new Error('Введите хотя бы один код.');
      if (new Set(codes).size !== codes.length) throw new Error('В списке есть повторяющиеся коды. Уберите дубликаты.');
      const asyncMode = data.mode === 'async';
      const result = await send(`/batches/${Number(data.batch_id)}/${asyncMode ? 'aggregate-async' : 'aggregate'}`,{unique_codes:codes});
      if (asyncMode) { addTask(result,`Агрегация · партия #${Number(data.batch_id)}`,'aggregate'); renderResult(form,'<p>Задача в очереди. <a class="accent" href="#reports">Открыть статусы →</a></p>'); }
      else renderResult(form,`<p>Всего: ${result.total} · <span class="green">Агрегировано: ${result.aggregated}</span> · Ошибок: ${result.failed}</p>${result.errors?.length ? `<pre>${escape(result.errors.map(e => `${e.unique_code}: ${e.reason}`).join('\n'))}</pre>` : ''}`);
    } else if (type === 'lookup-batch') {
      await batchDetail(Number(data.batch_id));
    } else if (type === 'create-center' || type === 'lookup-center') {
      const c = type === 'create-center' ? await send('/work-centers',{identifier:data.identifier.trim(),name:data.name.trim()}) : await api(`/work-centers/${Number(data.id)}`);
      renderResult(form,centerResult(c)); if (type === 'create-center') toast('Рабочий центр создан');
    } else if (type === 'batch-report') {
      const id = Number(data.batch_id); const task = await send(`/batches/${id}/reports`,{format:data.format});
      addTask(task,`Отчёт · партия #${id}`,'batch-report',{batch_id:id,format:data.format});
    } else if (type === 'summary') {
      addTask(await api('/reports/production-summary',{method:'POST'}),'Сводка производства','summary',{format:'excel'});
    } else if (type === 'import') {
      if (!/\.(csv|xlsx)$/i.test(data.file.name)) throw new Error('Выберите CSV или XLSX файл.');
      if (!data.file.size) throw new Error('Файл пуст.');
      const payload = new FormData(); payload.append('file',data.file);
      addTask(await api('/batches/import',{method:'POST',body:payload}),`Импорт · ${data.file.name}`,'import'); form.reset();
    } else if (type === 'export') {
      const filters = data.selection === 'filters' ? {...state.filters} : {};
      for (const k of ['batch_number','work_center_id']) if (k in filters) filters[k] = Number(filters[k]);
      if ('is_closed' in filters) filters.is_closed = filters.is_closed === 'true';
      addTask(await send('/batches/export',{format:data.format,filters}),`Экспорт партий · ${data.format === 'csv' ? 'CSV' : 'Excel'}`,'export',{format:data.format});
    }
  } catch(e) {
    if (errorEl && form.isConnected) errorEl.textContent = errorText(e); else pageError(e);
  } finally { if (submitButton) submitButton.disabled = false; }
}
async function action(button) {
  const type = button.dataset.action;
  if (type === 'close-modal') return modal.close();
  if (type === 'new-batch') return batchForm();
  if (type === 'batch-detail') return batchDetail(Number(button.dataset.id));
  if (type === 'edit-batch') return batchForm(state.editing);
  if (type === 'delete-batch') {
    const b = state.editing;
    return openModal(`<h2 id="modal-title">Удалить партию № ${number(b.batch_number)}?</h2><p class="hint" style="margin:16px 0">Удаление нельзя отменить. API разрешает удалить только партию без продукции.</p><form class="form-stack" data-form="delete-batch"><input type="hidden" name="id" value="${b.id}">${formEnd('Удалить партию')}</form>`);
  }
  if (type === 'toggle-batch') {
    button.disabled = true;
    try { const b = state.editing; await send(`/batches/${b.id}`,{is_closed:!b.is_closed},'PATCH'); toast(b.is_closed ? 'Партия открыта' : 'Партия закрыта'); await batchDetail(b.id); if (['overview','batches'].includes(state.page)) await navigate(); }
    catch(e) { const el = $('#detail-error'); if (el) el.textContent = errorText(e); }
    finally { button.disabled = false; }
    return;
  }
  if (type === 'batch-report') {
    const id = state.editing.id;
    state.reportBatchId = id;
    modal.close();
    if (state.page !== 'reports') { location.hash = '#reports'; await navigate(); }
    const field = $('[data-form="batch-report"] [name="batch_id"]');
    if (field) { field.value = id; field.focus(); }
    return;
  }
  if (type === 'refresh-tasks') { button.disabled = true; await pollTasks(); await connection(); button.disabled = false; return; }
  if (type === 'clear-tasks') { tasks = tasks.filter(t => !terminal(t.status)); saveTasks(); renderTasks(); return; }
  if (type === 'reset-filters') { state.filters = {}; state.offset = 0; }
  if (type === 'previous') state.offset = Math.max(0,state.offset-state.limit);
  if (type === 'next') state.offset += state.limit;
  if (['refresh','reset-filters','previous','next'].includes(type)) { connection(); await navigate(); }
}
async function navigate() {
  const requested = location.hash.slice(1) || 'overview';
  state.page = names[requested] ? requested : 'overview';
  const version = ++state.version;
  $('#breadcrumb').textContent = names[state.page];
  document.title = `${names[state.page]} · Контур`;
  document.querySelectorAll('nav [data-page]').forEach(a => { a.classList.toggle('active',a.dataset.page === state.page); if (a.dataset.page === state.page) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current'); });
  if (state.page === 'overview') await overview(version);
  else if (state.page === 'batches') await batches(version);
  else if (state.page === 'products') products();
  else if (state.page === 'centers') centers();
  else if (state.page === 'assistant') window.renderAssistant(main);
  else reports();
}
document.addEventListener('submit',e => { const form = e.target.closest('[data-form]'); if (form) { e.preventDefault(); submit(form); } });
document.addEventListener('click',e => { const button = e.target.closest('[data-action]'); if (button && !button.disabled) action(button).catch(pageError); });
modal.addEventListener('click',e => { if (e.target === modal) { const r = modal.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) modal.close(); } });
window.addEventListener('hashchange',() => { modal.close(); navigate(); });
$('#today').textContent = new Date().toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric'});
setInterval(pollTasks,4000);
setInterval(connection,30000);
connection(); navigate();
