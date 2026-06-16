const API = '/api';

async function loadAds() {
  const res = await fetch(`${API}/ads`);
  const ads = await res.json();
  const container = document.getElementById('adsList');

  if (ads.length === 0) {
    container.innerHTML = '<p class="empty">Объявлений пока нет. Будьте первым!</p>';
    return;
  }

  container.innerHTML = ads.map(ad => `
    <div class="ad-card">
      <div class="ad-info">
        <div class="ad-title">${escHtml(ad.title)}</div>
        <div class="ad-desc">${escHtml(ad.description)}</div>
        <div class="ad-meta">Автор: ${escHtml(ad.author)} · ${new Date(ad.created_at).toLocaleDateString('ru-RU')}</div>
      </div>
      <div style="display:flex;align-items:center">
        <div class="ad-price">${Number(ad.price).toLocaleString('ru-RU')} ₽</div>
        <button class="delete-btn" onclick="deleteAd(${ad.id})">Удалить</button>
      </div>
    </div>
  `).join('');
}

async function deleteAd(id) {
  if (!confirm('Удалить объявление?')) return;
  await fetch(`${API}/ads/${id}`, { method: 'DELETE' });
  loadAds();
}

document.getElementById('adForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    title: document.getElementById('title').value,
    description: document.getElementById('description').value,
    price: parseInt(document.getElementById('price').value),
    author: document.getElementById('author').value,
  };
  await fetch(`${API}/ads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  e.target.reset();
  loadAds();
});

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

loadAds();
