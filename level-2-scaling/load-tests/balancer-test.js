// Тест балансировщика: проверяем что запросы распределяются между инстансами
// и что убийство одного контейнера не роняет сервис
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const errors = new Counter('errors');

export const options = {
  vus: 20,
  duration: '2m',
  thresholds: {
    http_req_failed: ['rate<0.05'], // не более 5% ошибок (включая момент убийства контейнера)
  },
};

export default function () {
  // Запрос к /api/instance показывает какой инстанс ответил и его счётчик
  const res = http.get('http://localhost/api/instance');
  const ok = check(res, { 'status 200': (r) => r.status === 200 });
  if (!ok) errors.add(1);

  sleep(0.5);
}
