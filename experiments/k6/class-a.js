/**
 * class-a.js — Beban untuk skenario Kelas A (CPU/Memory pressure).
 * Digunakan bersama fault injection A1, A2, A3.
 *
 * Jalankan:
 *   SCENARIO=A1 CONDITION=treatment RUN=1 ACCESS_TOKEN=<token> \
 *     k6 run experiments/k6/class-a.js \
 *     --out json=experiments/data/raw/A1/treatment/run1/k6-result.json
 */

import { sleep } from 'k6';
import { infer, ENV } from './common.js';
import { payloadForMode } from './payloads.js';

const MAX_VU = parseInt(__ENV.K6_MAX_VU || '5');

export const options = {
  stages: [
    { duration: '2m',  target: Math.min(10, MAX_VU) },
    { duration: '3m',  target: MAX_VU },
    { duration: '3m',  target: MAX_VU },
    { duration: '2m',  target: Math.min(10, MAX_VU) },
    { duration: '1m',  target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<60000'],
    http_req_failed:   ['rate<0.50'],
  },
};

export default function () {
  // A3 bisa memakai multimodal; A1/A2 bisa vision/asr saja
  const mode = __ENV.MODE || 'multimodal';
  infer(payloadForMode(mode));
  sleep(1);
}
