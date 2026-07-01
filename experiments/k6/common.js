import http from 'k6/http';
import { check } from 'k6';

export const ENV = {
  BASE_URL:     __ENV.BASE_URL     || 'http://localhost:8080',
  ACCESS_TOKEN: __ENV.ACCESS_TOKEN || '',
  SCENARIO:     __ENV.SCENARIO     || 'SS',
  CONDITION:    __ENV.CONDITION    || 'treatment',
  RUN:          Number(__ENV.RUN   || 1),
  REQUEST_TIMEOUT_MS: Number(__ENV.REQUEST_TIMEOUT_MS || 90000),
};

if (!ENV.ACCESS_TOKEN.trim()) {
  throw new Error('ACCESS_TOKEN is required for k6 experiment runs');
}

export function newRequestID() {
  const rand = Math.random().toString(36).slice(2, 10);
  return `req-${ENV.SCENARIO}-${ENV.CONDITION}-run${ENV.RUN}-${__VU}-${__ITER}-${Date.now()}-${rand}`;
}

export function authHeaders(requestID = newRequestID()) {
  return {
    'Content-Type':  'application/json',
    'Authorization': `Bearer ${ENV.ACCESS_TOKEN}`,
    'X-Request-ID':  requestID,
  };
}

/**
 * Bangun payload JSON untuk POST /api/v1/infer.
 * @param {Object} opts - { imageBase64, audioBase64, mode, enableVision, enableOCR, enableASR }
 */
export function buildPayload(opts = {}) {
  const requestID = opts.requestId || newRequestID();
  return JSON.stringify({
    request_id: requestID,
    scenario:   ENV.SCENARIO,
    condition:  ENV.CONDITION,
    run:        ENV.RUN,
    mode:       opts.mode || 'multimodal',
    inputs: {
      image_base64: opts.imageBase64 || '',
      audio_base64: opts.audioBase64 || '',
    },
    options: {
      enable_vision: opts.enableVision !== undefined ? opts.enableVision : true,
      enable_ocr:    opts.enableOCR   !== undefined ? opts.enableOCR   : true,
      enable_asr:    opts.enableASR   !== undefined ? opts.enableASR   : true,
      timeout_ms:    opts.timeoutMs   || ENV.REQUEST_TIMEOUT_MS,
    },
  });
}

export function defaultChecks(res) {
  return check(res, {
    'status valid (200/502/504)':  (r) => [200, 502, 504].includes(r.status),
    'has response_category':       (r) => {
      try {
        const body = JSON.parse(r.body);
        return ['full', 'partial', 'failure'].includes(body.response_category);
      } catch { return false; }
    },
    'has request_id':              (r) => {
      try { return !!JSON.parse(r.body).request_id; }
      catch { return false; }
    },
  });
}

export function infer(opts = {}) {
  const requestID = opts.requestId || newRequestID();
  const timeoutMs = opts.timeoutMs || ENV.REQUEST_TIMEOUT_MS;
  const httpTimeout = `${Math.ceil(timeoutMs / 1000) + 10}s`;
  const res = http.post(
    `${ENV.BASE_URL}/api/v1/infer`,
    buildPayload(Object.assign({}, opts, { requestId: requestID })),
    { headers: authHeaders(requestID), timeout: httpTimeout }
  );
  defaultChecks(res);
  return res;
}
