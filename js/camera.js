// カメラ（インカメラ user ／ アウトカメラ environment）の起動と切りかえ
import { load, save } from './storage.js';

export function cameraErrorText(err) {
  if (!window.isSecureContext) return 'カメラは https のページでしか使えません。GitHub Pages のURLから開いてください。';
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return 'このブラウザではカメラを使えません。iPhone・iPad は Safari、Android は Chrome で開いてください。';
  if (err && err.name === 'NotAllowedError') return 'カメラの使用が許可されていません。ブラウザの設定でカメラを許可してから、もう一度ためしてください。';
  if (err && err.name === 'NotFoundError') return 'カメラが見つかりませんでした。';
  return `カメラを起動できませんでした（${err && err.message ? err.message : err}）。`;
}

// 優先順位：URLの ?camera=user|environment → 前回の選択 → インカメラ
export function initialFacing() {
  const q = new URLSearchParams(location.search).get('camera');
  if (q === 'user' || q === 'environment') return q;
  const saved = load('camera');
  return saved === 'environment' ? 'environment' : 'user';
}

export function rememberFacing(facing) {
  save('camera', facing);
}

let stream = null;

export async function startCamera(video, facing) {
  stopCamera(video);
  stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: { ideal: facing }, width: { ideal: 1920 }, height: { ideal: 1080 } },
  });
  video.srcObject = stream;
  await video.play();
  if (!video.videoWidth) await new Promise((r) => video.addEventListener('loadedmetadata', r, { once: true }));
}

export function stopCamera(video) {
  if (stream) stream.getTracks().forEach((t) => t.stop());
  stream = null;
  video.srcObject = null;
}
