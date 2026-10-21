// 端末への設定の記憶（プライベートブラウズなどで使えなくても動き続ける）
const PREFIX = 'tsubameiAR.';

export function load(key) {
  try { return localStorage.getItem(PREFIX + key); } catch { return null; }
}

export function save(key, value) {
  try { localStorage.setItem(PREFIX + key, value); } catch { /* 無視 */ }
}

export function loadJSON(key) {
  try { return JSON.parse(load(key)); } catch { return null; }
}

export function saveJSON(key, value) {
  save(key, JSON.stringify(value));
}
