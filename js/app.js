// カメラ画面：カメラの映像の上に3Dのつばめいを重ねて、いっしょに写真をとる
//   つばめいの位置・大きさは画面の割合で持つ（x＝左右、y＝足もとの高さ、size＝高さ。どれも画面の幅・高さに対する割合）
//   1本指のドラッグで移動、2本指のピンチで拡大縮小。調整パネルのスライダーでも変えられる
import * as THREE from 'three';
import { createTsubamei, TSUBAMEI_HEIGHT } from './models/tsubamei.js';
import { cameraErrorText, initialFacing, rememberFacing, startCamera } from './camera.js';
import { countdown, flash, showResult } from './capture.js';
import { load, save, loadJSON, saveJSON } from './storage.js';
import { VERSION, RELEASED } from './version.js';

const $ = (id) => document.getElementById(id);
const stage = $('stage'), video = $('video'), glCanvas = $('gl');

// ---------- 位置と大きさ ----------
const DEFAULT_PLACE = { x: 0.7, y: 0.92, size: 0.5, turn: -15 };
const LIMIT = { x: [0, 1], y: [0.1, 1.5], size: [0.1, 1.5], turn: [-90, 90] };
const clamp = (v, [a, b]) => Math.min(b, Math.max(a, v));
const place = { ...DEFAULT_PLACE, ...(loadJSON('place') || {}) };
for (const k of Object.keys(LIMIT)) place[k] = clamp(Number.isFinite(place[k]) ? place[k] : DEFAULT_PLACE[k], LIMIT[k]);

let saveTimer = 0;
function placeChanged() {
  for (const k of Object.keys(LIMIT)) place[k] = clamp(place[k], LIMIT[k]);
  paintSliders();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saveJSON('place', place), 300);
}

// ---------- 3D ----------
const renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0x000000, 0);

const scene = new THREE.Scene();
const FOV = 35, DEPTH = 4; // つばめいを置く奥行き（m）
const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 50);
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a7a90, 1.2));
const sun = new THREE.DirectionalLight(0xffffff, 1.3);
sun.position.set(-1, 2, 3);
scene.add(sun);

const chara = createTsubamei();
chara.rotation.order = 'XYZ';
scene.add(chara);
chara.userData.ready.then(() => chara.userData.appear());

// 画面の割合 → 奥行き DEPTH の位置。少し上から見おろす向きにかたむけて、足もとの影が見えるようにする
function placeChara() {
  const viewH = 2 * DEPTH * Math.tan(THREE.MathUtils.degToRad(FOV / 2));
  chara.position.set((place.x - 0.5) * viewH * camera.aspect, (0.5 - place.y) * viewH, -DEPTH);
  chara.scale.setScalar(place.size * viewH / TSUBAMEI_HEIGHT);
  chara.rotation.set(0.15, THREE.MathUtils.degToRad(place.turn), 0);
}

function resize() {
  const w = stage.clientWidth, h = stage.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

const clock = new THREE.Clock();
function loop() {
  chara.userData.update(Math.min(0.1, clock.getDelta()));
  placeChara();
  renderer.render(scene, camera);
}
renderer.setAnimationLoop(loop);

// ---------- 指での操作 ----------
const pointers = new Map();
let gesture = null; // 2本指：{ dist, mx, my }

function twoFinger() {
  const [a, b] = [...pointers.values()];
  return { dist: Math.hypot(a.x - b.x, a.y - b.y), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
}

stage.addEventListener('pointerdown', (e) => {
  try { stage.setPointerCapture(e.pointerId); } catch { /* 指が画面外へ出ても追えないだけ */ }
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size === 2) gesture = twoFinger();
  hideHint();
});
stage.addEventListener('pointermove', (e) => {
  const p = pointers.get(e.pointerId);
  if (!p) return;
  const W = stage.clientWidth, H = stage.clientHeight;
  if (pointers.size === 1) {
    place.x += (e.clientX - p.x) / W;
    place.y += (e.clientY - p.y) / H;
    p.x = e.clientX;
    p.y = e.clientY;
  } else if (pointers.size === 2) {
    p.x = e.clientX;
    p.y = e.clientY;
    const g = twoFinger();
    if (gesture.dist > 10) place.size *= g.dist / gesture.dist;
    place.x += (g.mx - gesture.mx) / W;
    place.y += (g.my - gesture.my) / H;
    gesture = g;
  }
  placeChanged();
});
const release = (e) => {
  pointers.delete(e.pointerId);
  gesture = pointers.size === 2 ? twoFinger() : null;
};
stage.addEventListener('pointerup', release);
stage.addEventListener('pointercancel', release);
// iPhone の Safari：2本指でページごと拡大されないようにする
document.addEventListener('gesturestart', (e) => e.preventDefault());
// パソコンで確認するとき：ホイールで拡大縮小
stage.addEventListener('wheel', (e) => {
  e.preventDefault();
  place.size *= Math.exp(-e.deltaY * 0.001);
  placeChanged();
}, { passive: false });

const hint = $('hint');
function hideHint() { hint.classList.add('gone'); }
setTimeout(hideHint, 6000);

// ---------- 調整パネル ----------
const SLIDERS = {
  size: { scale: 100, text: (v) => `${Math.round(v * 100)}%` },
  x: { scale: 100, text: (v) => `${Math.round(v * 100)}` },
  y: { scale: 100, text: (v) => `${Math.round(v * 100)}` },
  turn: { scale: 1, text: (v) => (Math.round(v) === 0 ? 'しょうめん' : `${Math.abs(Math.round(v))}° ${v < 0 ? '左' : '右'}`) },
};
function paintSliders() {
  for (const [k, s] of Object.entries(SLIDERS)) {
    $(k).value = place[k] * s.scale;
    $(`${k}Out`).textContent = s.text(place[k]);
  }
}
for (const [k, s] of Object.entries(SLIDERS)) {
  $(k).addEventListener('input', () => {
    place[k] = Number($(k).value) / s.scale;
    placeChanged();
  });
}
paintSliders();

$('resetPlace').addEventListener('click', () => {
  Object.assign(place, DEFAULT_PLACE);
  placeChanged();
});

const panel = $('panel'), toggle = $('togglePanel');
toggle.addEventListener('click', () => {
  panel.hidden = !panel.hidden;
  hideHint();
  toggle.setAttribute('aria-expanded', String(!panel.hidden));
});

// 選択式のボタン（ポーズ・タイマー）
function chips(root, attr, current, onPick) {
  const buttons = [...root.querySelectorAll('button')];
  const paint = (v) => buttons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset[attr] === v)));
  paint(current);
  root.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    paint(b.dataset[attr]);
    onPick(b.dataset[attr]);
  });
}
chips($('poses'), 'pose', 'auto', (pose) => {
  if (pose === 'auto') chara.userData.setAuto();
  else chara.userData.holdPose(pose);
});
let timerSec = load('timer') ?? '3';
chips($('timer'), 'sec', timerSec, (sec) => { timerSec = sec; save('timer', sec); });

$('ver').textContent = `ver ${VERSION}（${RELEASED.replaceAll('-', '.')}）`;

// ---------- カメラ ----------
const overlay = $('overlay'), overlayMsg = $('overlayMsg'), retry = $('retry');
let facing = initialFacing();

function paintFacing() {
  stage.classList.toggle('mirror', facing === 'user');
  $('camLabel').textContent = facing === 'user' ? 'イン' : 'アウト';
}

async function openCamera() {
  overlay.hidden = false;
  overlayMsg.textContent = 'カメラを じゅんびしています…';
  retry.hidden = true;
  try {
    await startCamera(video, facing);
    paintFacing();
    overlay.hidden = true;
  } catch (err) {
    overlayMsg.textContent = cameraErrorText(err);
    retry.hidden = false;
  }
}
retry.addEventListener('click', openCamera);

let switching = false;
async function switchCamera() {
  if (switching) return;
  switching = true;
  facing = facing === 'user' ? 'environment' : 'user';
  rememberFacing(facing);
  await openCamera();
  switching = false;
}
$('switchCam').addEventListener('click', switchCamera);
paintFacing();
openCamera();

// ---------- 撮影 ----------
// 画面に見えている範囲（video の object-fit: cover と同じ切り抜き）を、カメラの解像度のまま写真にする
function compose() {
  const vw = video.videoWidth, vh = video.videoHeight;
  const aspect = stage.clientWidth / stage.clientHeight;
  let cw = vw, ch = vw / aspect;
  if (ch > vh) { ch = vh; cw = vh * aspect; }
  const W = Math.round(cw), H = Math.round(ch);
  const out = document.createElement('canvas');
  out.width = W;
  out.height = H;
  const g = out.getContext('2d');
  g.save();
  if (facing === 'user') { g.translate(W, 0); g.scale(-1, 1); } // インカメラは画面と同じく鏡うつし
  g.drawImage(video, (vw - cw) / 2, (vh - ch) / 2, cw, ch, 0, 0, W, H);
  g.restore();
  // つばめいを写真と同じ大きさで描いて重ねる
  const pr = renderer.getPixelRatio();
  renderer.setPixelRatio(1);
  renderer.setSize(W, H, false);
  renderer.render(scene, camera);
  g.drawImage(glCanvas, 0, 0, W, H);
  renderer.setPixelRatio(pr);
  resize();
  return out;
}

const shutter = $('shutter');
shutter.addEventListener('click', async () => {
  if (!video.videoWidth) return;
  shutter.disabled = true;
  panel.hidden = true;
  toggle.setAttribute('aria-expanded', 'false');
  await countdown($('countdown'), Number(timerSec));
  const photo = compose();
  flash($('flash'));
  // 結果を見ている間は描画を止めて、電池と発熱をおさえる
  renderer.setAnimationLoop(null);
  video.pause();
  await showResult($('result'), photo);
  video.play();
  clock.getDelta();
  renderer.setAnimationLoop(loop);
  shutter.disabled = false;
});
