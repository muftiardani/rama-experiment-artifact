/**
 * payloads.js — Sample media dalam base64 untuk k6.
 *
 * File ini tidak disertakan dalam artefak publik karena berisi
 * data biner (gambar dan audio) yang ter-encode base64 dan
 * berukuran besar (auto-generated dari media uji internal).
 *
 * Untuk replikasi: sediakan implementasi sendiri dengan
 * satu gambar JPEG dan satu audio WAV/MP3, lalu encode ke base64.
 *
 * Contoh struktur yang diharapkan:
 *
 *   const IMAGE_B64 = '<base64-encoded JPEG>';
 *   const AUDIO_B64 = '<base64-encoded WAV/MP3>';
 *
 *   export function payloadForMode(mode) {
 *     if (mode === 'vision')     return { imageBase64: IMAGE_B64 };
 *     if (mode === 'asr')        return { audioBase64: AUDIO_B64 };
 *     return { imageBase64: IMAGE_B64, audioBase64: AUDIO_B64 };  // multimodal
 *   }
 */

export function payloadForMode(mode) {
  throw new Error(
    'payloads.js: implementasi tidak disertakan dalam artefak publik. ' +
    'Lihat komentar di atas untuk panduan implementasi.'
  );
}
