const rows = document.getElementById('rows');
const message = document.getElementById('message');
const form = document.getElementById('create-form');

function showMessage(text, isError) {
  message.textContent = text;
  message.className = isError ? 'error' : '';
}

async function request(path, options) {
  const response = await fetch('/api' + path, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : response.statusText;
    const text = typeof detail === 'string' ? detail : JSON.stringify(detail);
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return body;
}

function makeButton(label, onClick) {
  const button = document.createElement('button');
  button.textContent = label;
  button.addEventListener('click', onClick);
  return button;
}

async function runCommand(id, command) {
  try {
    await request(`/reservations/${id}/${command}`, { method: 'POST' });
    await loadReservations();
  } catch (error) {
    showMessage(error.message, true);
  }
}

function renderRow(item) {
  const tr = document.createElement('tr');
  [item.id, item.event_id, item.seat, item.customer_id, item.status].forEach((value) => {
    const td = document.createElement('td');
    td.textContent = value;
    tr.appendChild(td);
  });
  const actions = document.createElement('td');
  if (item.status === 'held') {
    actions.appendChild(makeButton('Подтвердить', () => runCommand(item.id, 'confirm')));
  }
  if (item.status !== 'cancelled') {
    actions.appendChild(makeButton('Отменить', () => runCommand(item.id, 'cancel')));
  }
  tr.appendChild(actions);
  return tr;
}

async function loadReservations() {
  showMessage('Загрузка...', false);
  try {
    const items = await request('/reservations');
    rows.replaceChildren(...items.map(renderRow));
    showMessage(items.length === 0 ? 'Список пуст' : '', false);
  } catch (error) {
    showMessage(error.message, true);
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(form));
  try {
    await request('/reservations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    form.reset();
    await loadReservations();
  } catch (error) {
    showMessage(error.message, true);
  }
});

loadReservations();
