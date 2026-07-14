// Stress test — постепенно увеличиваем нагрузку до поломки
// Запускай параллельно с: docker stats
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

const BASE_URL = 'http://localhost';
const JSON_HEADERS = { 'Content-Type': 'application/json' };

// Тестовый пользователь: логин строго по username (не по email!) —
// см. login endpoint в backend/main.py
const TEST_USER = { username: 'Test', password: 'test123', email: 'test@test.com' };

export const options = {
  stages: [
    { duration: '30s', target: 10 },   // разгон до 10 пользователей
    { duration: '30s', target: 30 },   // разгон до 30
    { duration: '1m',  target: 50 },   // держим 50 — здесь должна начаться деградация
    { duration: '30s', target: 100 },  // пробуем 100 — явная перегрузка
    { duration: '30s', target: 0 },    // остановка
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% запросов должны укладываться в 2 сек
    errors: ['rate<0.1'],              // меньше 10% ошибок
  },
};

// setup() выполняется один раз до нагрузки; что вернёт — попадёт
// аргументом data в default function
export function setup() {
  // POST /api/ads требует JWT — логинимся заранее
  let res = http.post(
    `${BASE_URL}/api/auth/login`,
    JSON.stringify({ username: TEST_USER.username, password: TEST_USER.password }),
    { headers: JSON_HEADERS }
  );

  // Пользователя ещё нет — регистрируем (register тоже возвращает access_token)
  if (res.status !== 200) {
    res = http.post(`${BASE_URL}/api/auth/register`, JSON.stringify(TEST_USER), {
      headers: JSON_HEADERS,
    });
  }

  const token = res.json('access_token');
  if (!token) {
    throw new Error(`setup: не удалось получить токен (status ${res.status}): ${res.body}`);
  }
  return { token };
}

export default function (data) {
  // Имитируем реального пользователя: смотрим список, иногда создаём объявление
  const listRes = http.get(`${BASE_URL}/api/ads`);
  errorRate.add(listRes.status !== 200);
  check(listRes, { 'list: status 200': (r) => r.status === 200 });

  // Каждый 5-й виртуальный пользователь создаёт объявление
  if (__VU % 5 === 0) {
    const payload = JSON.stringify({
      title: `Объявление от VU ${__VU}`,
      description: 'Тестовое объявление под нагрузкой',
      price: Math.floor(Math.random() * 10000),
    });
    const createRes = http.post(`${BASE_URL}/api/ads`, payload, {
      headers: { ...JSON_HEADERS, Authorization: `Bearer ${data.token}` },
    });
    errorRate.add(createRes.status !== 201);
    check(createRes, { 'create: status 201': (r) => r.status === 201 });
  }

  sleep(1);
}
