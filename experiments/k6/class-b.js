/**
 * class-b.js — Beban untuk skenario Kelas B (worker dihentikan).
 * Digunakan bersama fault injection B1, B2, B3.
 *
 * Jalankan:
 *   SCENARIO=B1 CONDITION=treatment RUN=1 ACCESS_TOKEN=<token> \
 *     k6 run experiments/k6/class-b.js \
 *     --out json=experiments/data/raw/B1/treatment/run1/k6-result.json
 */

import { sleep } from 'k6';
import { infer, ENV } from './common.js';
import { payloadForMode } from './payloads.js';

// VU override untuk local testing — set K6_MAX_VU=5 di env untuk laptop
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
    http_req_failed:   ['rate<0.60'],   // lebih permisif karena worker dihentikan
  },
};

export default function () {
  // B1/B2/B3 semua memakai multimodal agar semua worker terpengaruh
  const mode = __ENV.MODE || 'multimodal';
  infer(payloadForMode(mode));
  sleep(1);
}
