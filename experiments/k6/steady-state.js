/**
 * steady-state.js — Uji kondisi normal (Steady State / SS).
 *
 * Jalankan:
 *   SCENARIO=SS CONDITION=static_resilience RUN=1 ACCESS_TOKEN=<token> \
 *     k6 run experiments/k6/steady-state.js \
 *     --out json=experiments/data/raw/SS/static_resilience/run1/k6-result.json
 */

import { sleep } from 'k6';
import { infer } from './common.js';
import { payloadForMode } from './payloads.js';

const MAX_VU = parseInt(__ENV.K6_MAX_VU || '5');

export const options = {
  stages: [
    { duration: '1m',  target: Math.min(5, MAX_VU) },
    { duration: '5m',  target: MAX_VU },
    { duration: '1m',  target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<60000'],
    http_req_failed:   ['rate<0.20'],
  },
};

export default function () {
  infer(payloadForMode('multimodal'));
  sleep(1);
}
