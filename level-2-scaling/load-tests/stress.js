// Стресс-тест с 3 инстансами бэкенда — сравниваем с уровнем 1
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '30s', target: 50 },
    { duration: '1m',  target: 100 },
    { duration: '30s', target: 150 },
    { duration: '30s', target: 0 },
  ],
};

export default function () {
  const res = http.get('http://localhost/api/ads');
  errorRate.add(res.status !== 200);
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}
