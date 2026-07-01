/**
 * class-c.js — Beban untuk skenario Kelas C (tekanan memori bertahap + kaskade).
 * Digunakan bersama fault injection C1 (gradual mem) dan C2 (cascade).
 *
 * Jalankan:
 *   SCENARIO=C1 CONDITION=treatment RUN=1 ACCESS_TOKEN=<token> \
 *     k6 run experiments/k6/class-c.js \
 *     --out json=experiments/data/raw/C1/treatment/run1/k6-result.json
 */

import { sleep } from 'k6';
import { infer, ENV } from './common.js';
import { payloadForMode } from './payloads.js';

const MAX_VU = parseInt(__ENV.K6_MAX_VU || '5');

export const options = {
  stages: [
    { duration: '2m',  target: Math.min(10, MAX_VU) },
    { duration: '5m',  target: Math.min(20, MAX_VU) },
    { duration: '3m',  target: MAX_VU },
    { duration: '3m',  target: MAX_VU },
    { duration: '3m',  target: Math.min(10, MAX_VU) },
    { duration: '1m',  target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<60000'],
    http_req_failed:   ['rate<0.70'],
  },
};

export default function () {
  infer(payloadForMode('multimodal'));
  sleep(1);
}
