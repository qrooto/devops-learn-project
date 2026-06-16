const API = '/api';

// ── Состояние ──────────────────────────────────────────────────────────────────
// JWT хранится в localStorage — переживает перезагрузку страницы.
// Альтернатива — httpOnly cookie (безопаснее против XSS, но сложнее в CORS).
let token = localStorage.getItem('token');
let currentUser = null;

// ── Утилиты ────────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function authHeaders() {
  return token ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
               : { 'Content-Type': 'application/json' };
}

async function apiFetch(path, options = {}) {
  const res = await fetch(API + path, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (res.status === 401) { logout(); return null; }
  return res;
}

// ── UI состояния ───────────────────────────────────────────────────────────────
function updateUI() {
  const authBlock   = document.getElementById('authBlock');
  const createBlock = document.getElementById('createBlock');
  const authStatus  = document.getElementById('authStatus');

  if (currentUser) {
    authBlock.style.display   = 'none';
    createBlock.style.display = 'block';
    authStatus.innerHTML = `
      <div class="user-badge">
        <span>👤 ${escHtml(currentUser.username)}</span>
        <button class="logout-btn" onclick="logout()">Выйти</button>
      </div>`;
  } else {
    authBlock.style.display   = 'block';
    createBlock.style.display = 'none';
    authStatus.innerHTML = '';
  }
}

// ── Авторизация ────────────────────────────────────────────────────────────────
async function fetchMe() {
  if (!token) return;
  const res = await apiFetch('/auth/me');
  if (res && res.ok) {
    currentUser = await res.json();
  } else {
    token = null;
    localStorage.removeItem('token');
  }
}

function logout() {
  token = null;
  currentUser = null;
  localStorage.removeItem('token');
  updateUI();
  loadAds();
}

function switchTab(tab) {
  document.getElementById('loginForm').style.display    = tab === 'login'    ? '' : 'none';
  document.getElementById('registerForm').style.display = tab === 'register' ? '' : 'none';
  document.querySelectorAll('.tab').forEach((el, i) =>
    el.classList.toggle('active', (i === 0) === (tab === 'login')));
  document.getElementById('authError').textContent = '';
}

document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const res = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: document.getElementById('loginUsername').value,
      password: document.getElementById('loginPassword').value,
    }),
  });
  if (!res.ok) {
    document.getElementById('authError').textContent = 'Неверный логин или пароль';
    return;
  }
  const data = await res.json();
  token = data.access_token;
  localStorage.setItem('token', token);
  await fetchMe();
  updateUI();
  loadAds();
});

document.getElementById('registerForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const res = await fetch(`${API}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: document.getElementById('regUsername').value,
      email:    document.getElementById('regEmail').value,
      password: document.getElementById('regPassword').value,
    }),
  });
  if (!res.ok) {
    const err = await res.json();
    document.getElementById('authError').textContent = err.detail || 'Ошибка регистрации';
    return;
  }
  const data = await res.json();
  token = data.access_token;
  localStorage.setItem('token', token);
  await fetchMe();
  updateUI();
  loadAds();
});

// ── Объявления ─────────────────────────────────────────────────────────────────
async function loadAds() {
  const res = await fetch(`${API}/ads`);
  const ads = await res.json();
  const container = document.getElementById('adsList');

  if (!ads.length) {
    container.innerHTML = '<p class="empty">Объявлений пока нет. Зарегистрируйтесь и будьте первым!</p>';
    return;
  }

  container.innerHTML = ads.map(ad => {
    const isOwn = currentUser && ad.author === currentUser.username;
    return `
      <div class="ad-card">
        <div class="ad-info">
          <div class="ad-title">${escHtml(ad.title)}</div>
          <div class="ad-desc">${escHtml(ad.description)}</div>
          <div class="ad-meta">
            Автор: <strong>${escHtml(ad.author)}</strong> ·
            ${new Date(ad.created_at).toLocaleDateString('ru-RU')}
          </div>
        </div>
        <div style="display:flex;align-items:center">
          <div class="ad-price">${Number(ad.price).toLocaleString('ru-RU')} ₽</div>
          ${isOwn ? `<button class="delete-btn" onclick="deleteAd(${ad.id})">Удалить</button>` : ''}
        </div>
      </div>`;
  }).join('');
}

async function deleteAd(id) {
  if (!confirm('Удалить объявление?')) return;
  await apiFetch(`/ads/${id}`, { method: 'DELETE' });
  loadAds();
}

document.getElementById('adForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  await apiFetch('/ads', {
    method: 'POST',
    body: JSON.stringify({
      title:       document.getElementById('title').value,
      description: document.getElementById('description').value,
      price:       parseInt(document.getElementById('price').value),
    }),
  });
  e.target.reset();
  loadAds();
});

// ── Инициализация ──────────────────────────────────────────────────────────────
(async () => {
  await fetchMe();
  updateUI();
  loadAds();
})();
