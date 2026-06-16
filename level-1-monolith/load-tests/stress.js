// Stress test — постепенно увеличиваем нагрузку до поломки
// Запускай параллельно с: docker stats
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

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

export default function () {
  // Имитируем реального пользователя: смотрим список, иногда создаём объявление
  const listRes = http.get('http://localhost/api/ads');
  errorRate.add(listRes.status !== 200);
  check(listRes, { 'list: status 200': (r) => r.status === 200 });

  // Каждый 5-й виртуальный пользователь создаёт объявление
  if (__VU % 5 === 0) {
    const payload = JSON.stringify({
      title: `Объявление от VU ${__VU}`,
      description: 'Тестовое объявление под нагрузкой',
      price: Math.floor(Math.random() * 10000),
      author: `user_${__VU}`,
    });
    const createRes = http.post('http://localhost/api/ads', payload, {
      headers: { 'Content-Type': 'application/json' },
    });
    errorRate.add(createRes.status !== 201);
    check(createRes, { 'create: status 201': (r) => r.status === 201 });
  }

  sleep(1);
}
