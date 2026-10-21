// つばめい（清明高校のマスコット）の3Dモデル
//   形と模様は、正面のイラスト（つばめい/つばめい (2).PNG）から tools/build_tsubamei.py で作ったもの
//   （assets/tsubamei/）。正面から見ると元の絵と同じ見た目になる
//   ・高さ 1.2m（足元が y=0、単位はメートル）。正面は +z
//   ・部品（頭・羽・足など）を動かして、一定の間隔でポーズを変える
//     立つ → 手をふる → ばんざい → てれる → とぶ（イラスト1〜5のポーズ）
import * as THREE from 'three';

export const TSUBAMEI_HEIGHT = 1.2;
const BASE = new URL('../../assets/tsubamei/', import.meta.url);
const POSE_HOLD = 3.6;  // 1つのポーズを続ける秒数
const POSE_BLEND = 0.7; // 次のポーズへ移り変わる秒数
const POSE_ORDER = ['stand', 'wave', 'banzai', 'shy', 'fly'];
const SPREAD_FOLD = 1.4; // 広げた羽を、たたんだ羽と入れかえるときにたたむ角度

// ---------- 読み込み（ページ内で1回だけ） ----------
let assetsPromise = null;
function loadAssets() {
  if (!assetsPromise) {
    const tex = (name) => new Promise((resolve, reject) => {
      new THREE.TextureLoader().load(new URL(name, BASE).href, (t) => {
        t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = 4;
        resolve(t);
      }, undefined, reject);
    });
    assetsPromise = Promise.all([
      fetch(new URL('model.json', BASE)).then((r) => r.json()),
      fetch(new URL('model.bin', BASE)).then((r) => r.arrayBuffer()),
      tex('front.png'),
      tex('back.png'),
    ]).then(([meta, bin, front, back]) => ({ meta, bin, front, back }));
  }
  return assetsPromise;
}

function geometryOf(part, bin) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(bin, part.position, part.vertexCount * 3), 3));
  g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(bin, part.uv, part.vertexCount * 2), 2));
  g.setIndex(new THREE.BufferAttribute(new Uint16Array(bin, part.index, part.indexCount), 1));
  g.addGroup(0, part.frontIndexCount, 0);                                      // 表：元の絵
  g.addGroup(part.frontIndexCount, part.indexCount - part.frontIndexCount, 1); // 裏：部品の色
  g.computeVertexNormals();
  return g;
}

// 照明が暗くても絵の色が残るよう、半分ほど自己発光させる
function paintMaterial(map) {
  return new THREE.MeshLambertMaterial({ map, emissive: 0xffffff, emissiveMap: map, emissiveIntensity: 0.68, color: 0x8c8c8c });
}

// 輪郭線：面を法線方向に少しふくらませた裏面を黒で描く
let outlineMaterial = null;
function outline(geo, color) {
  if (!outlineMaterial) {
    outlineMaterial = new THREE.ShaderMaterial({
      uniforms: { thickness: { value: 0.004 }, color: { value: new THREE.Color(color) } },
      // 線の面をカメラから少し遠ざけて、表と裏のつなぎめで線が表面に点線のように出ないようにする
      // （モデルの拡大率に合わせた距離なので、ポスターARの単位でも同じ見え方になる）
      vertexShader: `uniform float thickness;
        void main() {
          vec4 mv = modelViewMatrix * vec4(position + normal * thickness, 1.0);
          mv.xyz += normalize(mv.xyz) * thickness * 2.5 * length(modelViewMatrix[0].xyz);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: 'uniform vec3 color; void main() { gl_FragColor = vec4(color, 1.0); }',
      side: THREE.BackSide,
    });
  }
  return new THREE.Mesh(geo, outlineMaterial);
}

// 表情：目を閉じた絵（うれしい顔の「∩」と、まばたき）を、元の絵の目の上に描いて作る
function faceTextures(front, meta) {
  const img = front.image;
  const make = (draw) => {
    const c = document.createElement('canvas');
    c.width = img.width;
    c.height = img.height;
    const g = c.getContext('2d');
    g.drawImage(img, 0, 0);
    for (const [x, y, w, h] of meta.eyes) {
      // 目（白目＋黒いふち）を頭の色でうめてから、閉じた目を描く
      g.fillStyle = meta.colors.purple;
      g.beginPath();
      g.ellipse(x, y, w / 2 + 9, h / 2 + 9, 0, 0, Math.PI * 2);
      g.fill();
      g.strokeStyle = meta.colors.line;
      g.lineCap = 'round';
      g.lineWidth = Math.max(6, w * 0.17);
      g.beginPath();
      draw(g, x, y, w, h);
      g.stroke();
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 4;
    t.flipY = front.flipY;
    return t;
  };
  return {
    open: front,
    happy: make((g, x, y, w) => g.arc(x, y + w * 0.35, w * 0.62, Math.PI * 1.1, Math.PI * 1.9)),
    blink: make((g, x, y, w) => { g.moveTo(x - w * 0.55, y + 2); g.quadraticCurveTo(x, y + w * 0.3, x + w * 0.55, y + 2); }),
  };
}

// ---------- 本体 ----------
export function createTsubamei({ shadow = true } = {}) {
  const root = new THREE.Group();
  const model = new THREE.Group(); // 登場のアニメで拡大縮小する
  root.add(model);
  const nodes = {};
  let faces = null, headMat = null;

  root.userData.ready = loadAssets().then(({ meta, bin, front, back }) => {
    const backMat = paintMaterial(back);
    const frontMat = paintMaterial(front);
    faces = faceTextures(front, meta);
    headMat = paintMaterial(faces.open);
    // 体の中心（腰）
    const body = new THREE.Group();
    body.rotation.order = 'YXZ'; // 向きを変えてから、その向きで前かがみ
    body.position.y = meta.pivotHeight.body;
    body.userData.baseY = body.position.y;
    nodes.body = body;
    model.add(body);
    for (const part of meta.parts) {
      const geo = geometryOf(part, bin);
      const node = new THREE.Group();
      node.position.fromArray(part.position0);
      if (part.rotation0) node.rotation.fromArray(part.rotation0);
      const mesh = new THREE.Mesh(geo, [part.name === 'head' ? headMat : frontMat, backMat]);
      node.add(mesh, outline(geo, meta.colors.line));
      nodes[part.name] = node;
    }
    for (const part of meta.parts) nodes[part.parent].add(nodes[part.name]);
    // 広げた羽（絵 1 から作った部品）は、羽を広げるポーズのときだけ出す
    nodes.spreadL.visible = nodes.spreadR.visible = false;
    root.userData.version = meta.version;
    root.userData.update(0);
  });

  // 足元の影（とんでも地面に残る）
  let shadowMesh = null;
  if (shadow) {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const g = c.getContext('2d');
    const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, 'rgba(0,0,0,0.5)');
    gr.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = gr;
    g.fillRect(0, 0, 64, 64);
    shadowMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(0.8, 0.55),
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false })
    );
    shadowMesh.rotation.x = -Math.PI / 2;
    shadowMesh.position.y = 0.003;
    root.add(shadowMesh);
  }

  // ---------- ポーズ ----------
  // 羽：raise＝外へひろげる（上へ）、fwd＝前へ出す、twist＝後ろへ引く
  const POSES = {
    stand: (t) => ({
      by: Math.sin(t * 2.2) * 0.006, headY: Math.sin(t * 0.6) * 0.1, headZ: Math.sin(t * 0.9) * 0.04,
      lRaise: Math.sin(t * 2.2) * 0.03, rRaise: Math.sin(t * 2.2) * 0.03,
    }),
    // 羽を広げるポーズ（手をふる・ばんざい・とぶ）は、絵 1 の広げた羽に入れかえる（spread＝1）。flap＝広げた羽の上下
    wave: (t) => ({
      by: Math.sin(t * 2.2) * 0.006, headZ: -0.1, headY: 0.08,
      rRaise: 2.5, rFwd: 0.2, rSpread: 1, rFlap: 0.05 + Math.sin(t * 9) * 0.25,
    }),
    banzai: (t) => ({
      by: Math.abs(Math.sin(t * 5)) * 0.045, headX: -0.08, happy: 1,
      lRaise: 2.2, rRaise: 2.2, lSpread: 1, rSpread: 1,
      lFlap: Math.sin(t * 10) * 0.1, rFlap: Math.sin(t * 10) * 0.1,
    }),
    shy: (t) => ({
      by: Math.sin(t * 2) * 0.005, roll: 0.05 + Math.sin(t * 2) * 0.04, headZ: 0.2, headY: 0.2, headX: 0.08,
      lRaise: -0.55, rRaise: -0.5, lFwd: 1.25, rFwd: 1.35,
    }),
    fly: (t, dir) => ({
      by: 0.14 + Math.sin(t * 4.5) * 0.03, yaw: dir * 1.2, pitch: 0.3, headX: -0.22, legs: 0.7,
      lRaise: 1.45, rRaise: 1.45, lTwist: 1.0, rTwist: 1.0,
      lSpread: 1, rSpread: 1, lFlap: Math.sin(t * 11) * 0.45, rFlap: Math.sin(t * 11) * 0.45,
    }),
  };
  const KEYS = ['by', 'yaw', 'pitch', 'roll', 'headX', 'headY', 'headZ', 'lRaise', 'lFwd', 'lTwist', 'rRaise', 'rFwd', 'rTwist',
    'lSpread', 'rSpread', 'lFlap', 'rFlap', 'legs', 'happy'];
  const evalPose = (p, t) => {
    const v = POSES[p.name](t, p.dir);
    for (const k of KEYS) v[k] = v[k] || 0;
    return v;
  };

  const state = {
    t: 0, appear: 1, order: 0, flyDir: 1, auto: true,
    from: { name: 'stand', dir: 1 }, to: { name: 'stand', dir: 1 }, blend: 1, hold: 0,
    blinkAt: 2, blink: 0, face: 'open',
  };

  function setPose(name) {
    state.from = state.to;
    if (name === 'fly') state.flyDir = -state.flyDir; // とぶ向きは毎回入れかえる
    state.to = { name, dir: state.flyDir };
    state.blend = 0;
    state.hold = 0;
  }

  root.userData.appear = () => { state.appear = 0; state.order = 0; setPose('stand'); state.blend = 1; };
  root.userData.nextPose = () => {
    state.order = (state.order + 1) % POSE_ORDER.length;
    setPose(POSE_ORDER[state.order]);
    return POSE_ORDER[state.order];
  };
  root.userData.poseName = () => state.to.name;
  // 確認用：指定したポーズで止める／一定間隔の切りかえに戻す
  root.userData.holdPose = (name) => {
    state.auto = false;
    state.order = POSE_ORDER.indexOf(name);
    setPose(name);
  };
  root.userData.setAuto = () => { state.auto = true; state.hold = 0; };

  root.userData.update = (dt) => {
    state.t += dt;
    const t = state.t;

    // 一定の間隔で次のポーズへ
    state.hold += dt;
    if (state.auto && state.blend >= 1 && state.hold > POSE_HOLD) root.userData.nextPose();
    state.blend = Math.min(1, state.blend + dt / POSE_BLEND);
    const k = state.blend * state.blend * (3 - 2 * state.blend);
    const a = evalPose(state.from, t), b = evalPose(state.to, t);
    const v = {};
    for (const key of KEYS) v[key] = a[key] + (b[key] - a[key]) * k;

    // 登場：ぽんと出てきて小さくはねる
    if (state.appear < 1) state.appear = Math.min(1, state.appear + dt / 0.8);
    const s = Math.max(0.001, easeOutBack(state.appear));
    model.scale.setScalar(s);
    const jump = state.appear < 1 ? Math.sin(state.appear * Math.PI) * 0.15 : 0;

    if (shadowMesh) {
      const lift = Math.max(0, v.by + jump);
      shadowMesh.scale.setScalar(s * (1 - lift * 1.6));
      shadowMesh.material.opacity = 1 - lift * 2;
    }
    if (!nodes.head) return; // まだ読み込み中

    const { body, head, wingL, wingR, footL, footR } = nodes;
    body.position.y = body.userData.baseY + v.by + jump;
    body.rotation.set(v.pitch, v.yaw, v.roll);
    head.rotation.set(v.headX, v.headY, v.headZ);
    wingL.rotation.set(-v.lFwd, -v.lTwist, -v.lRaise);
    wingR.rotation.set(-v.rFwd, v.rTwist, v.rRaise);
    // たたんだ羽が半分まで上がったら、広げた羽に入れかえる。広げた羽は肩を中心に、たたんだ角度から開く
    for (const [side, hang, spread, s, flap, twist] of [
      [-1, wingL, nodes.spreadL, v.lSpread, v.lFlap, v.lTwist],
      [1, wingR, nodes.spreadR, v.rSpread, v.rFlap, v.rTwist],
    ]) {
      const open = s >= 0.5;
      hang.visible = !open;
      spread.visible = open;
      spread.rotation.set(0, side * twist, side * (flap - (1 - s) * SPREAD_FOLD));
      spread.scale.setScalar(0.75 + 0.25 * s);
    }
    footL.rotation.x = footR.rotation.x = v.legs;

    // 目：うれしい顔と、ときどきまばたき
    if (t > state.blinkAt) { state.blink = 0.13; state.blinkAt = t + 2 + Math.random() * 2.5; }
    state.blink = Math.max(0, state.blink - dt);
    const face = v.happy > 0.5 ? 'happy' : state.blink > 0 ? 'blink' : 'open';
    if (face !== state.face) {
      state.face = face;
      headMat.map = headMat.emissiveMap = faces[face];
      headMat.needsUpdate = true;
    }
  };

  return root;
}

function easeOutBack(x) {
  const c1 = 1.70158, c3 = c1 + 1;
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
}
