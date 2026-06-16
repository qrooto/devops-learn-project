// Тест кэша: сравниваем время ответа с кэшем и без
// Сначала запусти с кэшем (штатно), потом сбрось кэш и запусти снова
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const listDuration = new Trend('list_duration');

export const options = {
  vus: 50,
  duration: '1m',
};

export default function () {
  const res = http.get('http://localhost/api/ads');
  check(res, { 'status 200': (r) => r.status === 200 });
  listDuration.add(res.timings.duration);
  sleep(0.5);
}
