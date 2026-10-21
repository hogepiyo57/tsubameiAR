"""つばめいの3Dモデルを、正面のイラスト（つばめい/つばめい (2).PNG）から作る。

やり方（イラストに忠実にするため、形も模様も元の絵から取る）
  1. 絵をベタ塗りの色ごとの領域に分け、部品（頭・とさか・くちばし・羽・胴・ズボン・足）に振り分ける
  2. 部品の輪郭をそのまま使い、内側ほど厚くなるようにふくらませて立体にする
     （正面から見ると元の絵と同じ形になる）
  3. 正面には元の絵をそのまま貼る。ほかの部品に隠れていた所は、その部品の色でうめる
  4. 背面は部品の色でぬる。ふちの線は絵から消し、表示のときに立体の輪郭線として描く
色は、5枚のうち4枚（1・3・4・5）で使われている濃いめの配色にそろえる。

出力：assets/tsubamei/model.json（部品の配置）, model.bin（頂点）, front.png, back.png（模様）
実行：.venv の Python（numpy, pillow, scipy）で `python tools/build_tsubamei.py`
"""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'つばめい' / 'つばめい (2).PNG'
SRC_SPREAD = ROOT / 'つばめい' / 'つばめい (1).png'  # 羽を広げた絵（ばんざい）。広げた羽の部品をここから作る
SPREAD_ROOT_IN = 40  # 広げた羽の根もとを、肩から体の内側へ入れる量（絵 1 の px）
OUT = ROOT / 'assets' / 'tsubamei'
MODEL_VERSION = 2  # モデルの版。形を変えたら上げる（git のタグ tsubamei-v<番号> で戻せる）
HEIGHT_M = 1.2   # とさかの先〜足の裏
GRID = 6         # 頂点の間隔（px）

# 元の絵のベタ色 → 濃いめの配色
FILLS = {
    'purple': ((176, 136, 184), (144, 104, 160)),
    'hl':     ((200, 184, 208), (200, 182, 212)),
    'green':  ((224, 248, 176), (200, 240, 144)),
    'pink':   ((248, 168, 168), (248, 144, 144)),
    'shorts': ((192, 216, 152), (136, 160, 80)),
    'yellow': ((248, 248, 176), (248, 248, 128)),
    'white':  ((248, 248, 248), (250, 244, 250)),
}
LINE_SRC = np.array((72, 20, 52), np.float32)
LINE = np.array((24, 14, 24), np.float32)

# 前にある部品から順に（重なった線は前の部品のもの）
ORDER = ['crest', 'beak', 'head', 'shorts', 'wingL', 'wingR', 'footL', 'footR', 'torso']
PARENT = {'body': None, 'torso': 'body', 'shorts': 'body', 'wingL': 'body', 'wingR': 'body',
          'footL': 'body', 'footR': 'body', 'tailL': 'body', 'tailR': 'body', 'head': 'body',
          'crest': 'head', 'beak': 'head', 'tuft': 'head', 'spreadL': 'body', 'spreadR': 'body'}
BACK_COLOR = {'head': 'purple', 'crest': 'green', 'beak': 'yellow', 'wingL': 'purple', 'wingR': 'purple',
              'footL': 'yellow', 'footR': 'yellow', 'torso': 'white', 'shorts': 'shorts', 'tailL': 'purple', 'tailR': 'purple', 'tuft': 'purple',
              'spreadL': 'purple', 'spreadR': 'purple'}
# 厚み（前・後ろ）
#   ROUND の部品：横から見た奥行きを、その高さでの横幅の半分に対する割合で決める（横向きの絵 3・4 に合わせて、
#                 頭・胴・ズボンは幅と同じくらいの奥行きがある丸い体型）。ふちは半径 ROUND[p] px で丸める
#   それ以外：輪郭の内接円が球になる厚さを 1 として、内側ほど厚くふくらませる（羽・とさかなど平たいもの）
DEPTH = {'head': (0.8, 0.78), 'crest': (1.3, 1.3), 'beak': (2.6, 1.6), 'wingL': (1.3, 1.3), 'wingR': (1.3, 1.3),
         'footL': (0.75, 0.75), 'footR': (0.75, 0.75), 'torso': (0.85, 0.8), 'shorts': (0.85, 0.8),
         'tailL': (0.35, 0.35), 'tailR': (0.35, 0.35), 'tuft': (0.4, 0.4),
         'spreadL': (0.3, 0.3), 'spreadR': (0.3, 0.3)}
# 羽も、横から見ると幅の広いへら形（絵 3・4）なので、正面の幅より奥行きを大きくする
ROUND = {'head': 34, 'torso': 75, 'shorts': 34, 'footL': 14, 'footR': 14, 'wingL': 22, 'wingR': 22}
# 横を向いた面に絵を貼ると、ふち近くの模様（ほおの E など）が横に長くのびる。
# 中心から幅の WRAP_START 倍より外は、正面から見た位置ではなく回りこんだ角度で絵を割りあてる
WRAP_START = 0.75
# 頭はほおの高さ（E のある所）だけ回りこませる。上の方は元の絵の位置のまま（頭のつやを小さくしない）
WRAP_ROWS = {'head': (500, 560)}
PAD = 16  # アトラスで部品のまわりに色をのばす幅（px）
RIM = 13  # 部品のふちから RIM px は、内側の色をのばして模様を置かない（横から見ると引きのばされるため）
# 胴とズボンのつなぎめ（腰）は丸めない（丸めると腰がくびれて見える）
ROUND_OPEN = {'torso': 'bottom', 'shorts': 'top'}
CREST_TILT = 16  # とさかを後ろへ傾ける角度（横からの線画では、ほぼまっすぐ立った幅の広い葉の形）
# しっぽ：左右のズボンのすそ（後ろ側）を底辺とする三角形が、下・後ろへとがる（後ろからの線画）
TAIL_BASE = 150   # 底辺の長さ（px）。片足のすその幅くらい
TAIL_LEN = 175    # 底辺から先までの長さ（px、約 0.25m）
TAIL_ROOT = 40    # 底辺からズボンの中へうめる長さ（px）
TAIL_BEND = 65    # 底辺の両はしを、ズボンのすその丸みに沿って体の側へ曲げる量（px）。まっすぐだと両はしにすき間ができる
TAIL_GROUND = 0.01  # しっぽの先と地面のすき間（m。立ちポーズの体の上下ゆれ 6mm で地面にめりこまない分）。傾きは、先がここまで下がるように付け根の高さから決める
TAIL_SPLAY = 8    # 外へ開く角度
FOOT_FORWARD = 110  # 足を前へ出す量（px）


def main():
    img = np.array(Image.open(SRC).convert('RGBA')).astype(np.float32)
    H, W = img.shape[:2]
    rgb, alpha = img[..., :3], img[..., 3]
    inside = alpha > 127
    ys, xs = np.where(inside)
    top, bottom = ys.min(), ys.max()
    scale = HEIGHT_M / (bottom - top)  # m/px
    cx = 640.0

    # ---- 色の分類と配色の置きかえ ----
    names = list(FILLS)
    src = np.array([FILLS[n][0] for n in names], np.float32)
    dst = np.array([FILLS[n][1] for n in names], np.float32)
    dist = np.linalg.norm(rgb[:, :, None, :] - src[None, None], axis=-1)
    cls = dist.argmin(-1)
    fill = inside & (dist.min(-1) < 30)
    # 線と塗りの中間の色（アンチエイリアス）は、線→塗りの割合を保って色を置きかえる
    f = src[cls]
    t = np.clip(((rgb - LINE_SRC) * (f - LINE_SRC)).sum(-1) / ((f - LINE_SRC) ** 2).sum(-1), 0, 1)[..., None]
    color = LINE + t * (dst[cls] - LINE)

    # ---- 塗りの領域 → 部品 ----
    part_fill = {p: np.zeros((H, W), bool) for p in ORDER}
    for i, n in enumerate(names):
        lab, k = ndi.label(fill & (cls == i))
        for j in range(1, k + 1):
            m = lab == j
            yy, xx = np.where(m)
            if len(yy) < 20:
                continue
            mx, my = xx.mean(), yy.mean()
            if n == 'pink':  # ほお〜胸のピンクは1つながり。頭の下の線で分ける
                cut = np.zeros_like(m)
                cut[:652] = True
                part_fill['head'] |= m & cut
                part_fill['torso'] |= m & ~cut
                continue
            part_fill[assign(n, mx, my)] |= m

    # ---- 線を部品に振り分ける（近くにある、いちばん前の部品のもの） ----
    lines = inside & ~fill
    near = {p: ndi.distance_transform_edt(~part_fill[p]) <= 5 for p in ORDER}
    taken = np.zeros((H, W), bool)
    part_px = {}
    for p in ORDER:
        own = lines & near[p] & ~taken
        taken |= own
        part_px[p] = part_fill[p] | own

    # ---- 隠れていた所をおぎなった輪郭 ----
    masks = {}
    for p in ORDER:
        m = part_px[p]
        if p == 'head':
            m = hull(m) | ellipse(H, W, 640, 478, 256, 180)
        elif p in ('wingL', 'wingR'):
            m = hull(m)
        elif p == 'torso':
            # 羽の後ろには広げない（胴のふちが羽を突きぬけないように）
            wings = ndi.binary_erosion(masks['wingL'] | masks['wingR'], iterations=6)
            m = hull(m | ellipse(H, W, 638, 700, 150, 80)) & ~wings
        elif p in ('footL', 'footR'):
            yy, xx = np.where(m)
            m = hull(m | ellipse(H, W, xx.mean(), 990, (xx.max() - xx.min()) * 0.42, 22))
        m = ndi.binary_fill_holes(m)
        m = ndi.gaussian_filter(m.astype(np.float32), 1.5) > 0.5  # ふちのギザギザをならす
        masks[p] = m

    # ---- 部品ごとの絵（正面）と背面 ----
    tiles = {}
    for p in ORDER:
        m = masks[p]
        known = part_fill[p]
        tex = color.copy()
        # 隠れていた所は、その部品のいちばん近い塗りの色でうめる
        _, (iy, ix) = ndi.distance_transform_edt(~known, return_indices=True)
        hidden = m & ~part_px[p]
        tex[hidden] = color[iy[hidden], ix[hidden]]
        # 部品のふちの線は消す（横から見ると側面に引きのばされて黒いすじになるため）。
        # ふちの線は、表示するときに立体の輪郭線として描く
        edge = m & (ndi.distance_transform_edt(m) <= 7) & ~known
        tex[edge] = color[iy[edge], ix[edge]]
        # ふちのすぐ内側（線のにじみが残る所）は、少し内側の塗りの色（線は使わない）をのばす
        dm = ndi.distance_transform_edt(m)
        _, (jy, jx) = ndi.distance_transform_edt(~((dm > RIM) & known), return_indices=True)
        rim = m & (dm <= RIM)
        tex[rim] = tex[jy[rim], jx[rim]]
        back = np.empty_like(tex)
        back[:] = dst[names.index(BACK_COLOR[p])]
        paint_back(p, back, m, dst[names.index('green')], dst[names.index('shorts')])
        if p == 'head':
            redraw_highlight(tex, m, part_fill['head'] & (cls == names.index('hl')), dst[names.index('purple')], dst[names.index('hl')])
        tiles[p] = (m, tex, back)

    # 本体の絵にないもの：しっぽ、後頭部のはね（横向きの絵 3・5 に描かれている）
    # しっぽは、底辺がズボンのすそになる三角形。左右で同じ形
    # 底辺（x=TAIL_ROOT）の手前に、ズボンの中にうまる根もとをつける
    tail = synth_part([(0, 0), (TAIL_ROOT, 0), (TAIL_ROOT + TAIL_LEN, TAIL_BASE / 2), (TAIL_ROOT, TAIL_BASE), (0, TAIL_BASE)], 'purple', dst, names)
    synth = {
        'tailL': tail,
        'tailR': tail,
        'tuft': synth_part([(0, 0), (40, 6), (82, 30), (36, 34), (0, 34)], 'purple', dst, names),
    }

    # ---- ふくらませた高さ ----
    def height_field(m, p):
        d = ndi.distance_transform_edt(m)
        R = d.max()
        if p in ROUND:
            # 行ごとに、横幅を直径とするだ円の断面にする
            H_, W_ = m.shape
            x = np.arange(W_)[None, :]
            any_ = m.any(1)
            left = np.where(any_, m.argmax(1), 0)[:, None]
            right = np.where(any_, W_ - 1 - m[:, ::-1].argmax(1), 0)[:, None]
            half = np.maximum((right - left + 1) / 2, 1)
            u = (x - (left + right) / 2) / half
            h = half * np.sqrt(np.clip(1 - u * u, 0, None))
            r = ROUND[p]
            if p in ROUND_OPEN:
                # 開いている側にふちが無いものとして、ふちからの距離を測りなおす
                ext = np.maximum.accumulate(m, axis=0) if ROUND_OPEN[p] == 'bottom' else np.maximum.accumulate(m[::-1], axis=0)[::-1]
                d = ndi.distance_transform_edt(ext)
            h *= np.where(d < r, np.sqrt(np.clip(d * (2 * r - d), 0, None)) / r, 1)
            rows[p] = ((left + right)[:, 0] / 2, half[:, 0])
            return ndi.gaussian_filter(h, 3) * m
        if p == 'beak':
            h = d * 1.0  # くちばしはとがらせる
        else:
            h = np.sqrt(np.clip(d * (2 * R - d), 0, None))
        h = ndi.gaussian_filter(h, max(1.5, R * 0.1)) * m
        return h

    rows = {}
    hf = {p: height_field(masks[p], p) for p in ORDER}
    z0 = {}
    front = lambda p: z0[p] + DEPTH[p][0] * hf[p]

    inner = {p: ndi.distance_transform_edt(masks[p]) >= 12 for p in ORDER}

    def above(p, others, base):
        # p が q より前に見えるように（p のふちぎりぎりは輪郭線なので見ない）
        z = base
        for q in others:
            ov = inner[p] & masks[q]
            if ov.any():
                z = max(z, float((front(q) - DEPTH[p][0] * hf[p] + 3)[ov].max()))
        return z

    z0['torso'] = 0.0
    z0['wingL'] = above('wingL', ['torso'], 0.0)
    z0['wingR'] = above('wingR', ['torso'], 0.0)
    z0['shorts'] = above('shorts', ['torso', 'wingL', 'wingR'], 0.0)
    for p in ('footL', 'footR'):
        z0[p] = 0.0
        ov = masks[p] & inner['shorts']  # ズボンのすその線のところは見ない
        z0[p] = min(FOOT_FORWARD, float((front('shorts') - DEPTH[p][0] * hf[p] - 3)[ov].min())) if ov.any() else FOOT_FORWARD
    z0['head'] = above('head', ['torso', 'wingL', 'wingR'], 10.0)
    z0['beak'] = above('beak', ['head'], 0.0)

    # とさか：根もと（いちばん下）は額の表面、上へいくほど後ろへ傾ける（正面の形は変えずにずらす）
    cm = masks['crest']
    cy_, cx_ = np.where(cm)
    root_y = cy_.max()
    root_x = cx_[cy_ == root_y].mean()
    tilt = math.tan(math.radians(CREST_TILT))
    shear = np.zeros((H, W), np.float32)
    shear[:] = -(root_y - np.arange(H))[:, None] * tilt
    ov = cm & masks['head']
    z0['crest'] = float((front('head') - DEPTH['crest'][0] * hf['crest'] - shear + 4)[ov].max())
    crest_shear = shear

    # ---- 部品の回転の中心（px、z も px） ----
    def px(x, y, z=0.0):
        return [x, y, z]

    wl = np.where(masks['wingL']); wr = np.where(masks['wingR'])
    pivots = {
        'body': px(cx, 845),
        'torso': px(cx, 845),
        'shorts': px(cx, 845),
        'head': px(cx, 650),
        'crest': px(root_x, root_y, 0),
        'beak': px(cx, 560),
        'wingL': px(wl[1][wl[0] < wl[0].min() + 15].mean() + 6, wl[0].min() + 18),
        'wingR': px(wr[1][wr[0] < wr[0].min() + 15].mean() - 6, wr[0].min() + 18),
        'footL': px(558, 985),
        'footR': px(722, 985),
    }

    # 広げた羽（絵 1 から）。回転の中心はたたんだ羽と同じ肩
    spread, spread_scale = build_spread_wings(dst, names, pivots, cx, top, scale)

    # ---- アトラスに並べる ----
    items = {}
    for p in ORDER:
        m, tex, back = tiles[p]
        yy, xx = np.where(m)
        items[p] = (m, tex, back, xx.min() - PAD, yy.min() - PAD, xx.max() + PAD + 1, yy.max() + PAD + 1)
    for p, (m, tex, back) in synth.items():
        h, w = m.shape
        items[p] = (m, tex, back, -PAD, -PAD, w + PAD, h + PAD)
    for p, (m, tex, back, _pivot) in spread.items():
        yy, xx = np.where(m)
        items[p] = (m, tex, back, xx.min() - PAD, yy.min() - PAD, xx.max() + PAD + 1, yy.max() + PAD + 1)
    place, AW, AH = pack({p: (v[5] - v[3], v[6] - v[4]) for p, v in items.items()})
    # すき間は黒にしない（遠くから見たとき、縮小した模様に黒がにじんで継ぎ目に点線が出るため）
    atlas_f = np.empty((AH, AW, 3), np.float32)
    atlas_f[:] = dst[names.index('purple')]
    atlas_b = atlas_f.copy()
    for p, (m, tex, back, x0, y0, x1, y1) in items.items():
        ax, ay = place[p]
        for atlas, src_img in ((atlas_f, tex), (atlas_b, back)):
            crop = crop_pad(src_img, m, x0, y0, x1, y1)
            atlas[ay:ay + crop.shape[0], ax:ax + crop.shape[1]] = crop

    # ---- メッシュ ----
    OUT.mkdir(parents=True, exist_ok=True)
    blob = bytearray()
    parts_json = []

    def add_part(name, m, h, zfun, pivot, x0, y0, extra=None, s=scale, warp=None):
        ax, ay = place[name]
        pos, uv, idx, nfront = build_mesh(m, h, zfun, DEPTH[name])
        uvpos = pos.copy()  # 絵の位置は曲げる前の形で決める
        if warp:
            pos = warp(pos)
        # px → m（y は上向き、回転の中心からの位置）。s は元の絵の 1px の長さ
        P = np.stack([(pos[:, 0] - pivot[0]) * s, -(pos[:, 1] - pivot[1]) * s, (pos[:, 2] - pivot[2]) * s], 1)
        ux = uvpos[:, 0].copy()
        if name in rows:
            ux = wrap_u(ux, uvpos[:, 1], *rows[name], WRAP_ROWS.get(name))
        UV = np.stack([(ux - x0 + ax) / AW, 1 - (uvpos[:, 1] - y0 + ay) / AH], 1)
        rec = {'name': name, 'parent': PARENT[name], 'vertexCount': len(P), 'frontIndexCount': nfront, 'indexCount': len(idx)}
        for key, arr, typ in (('position', P, np.float32), ('uv', UV, np.float32), ('index', idx, np.uint16)):
            while len(blob) % 4:
                blob.append(0)
            rec[key] = len(blob)
            blob.extend(arr.astype(typ).tobytes())
        rec.update(extra or {})
        parts_json.append(rec)

    def offset(child, parent):
        a, b = pivots[child], pivots[parent]
        return [(a[0] - b[0]) * scale, -(a[1] - b[1]) * scale, (a[2] - b[2]) * scale]

    for p in ORDER:
        m, *_ , x0, y0, _x1, _y1 = items[p]
        base = z0[p] + (crest_shear if p == 'crest' else 0)
        add_part(p, m, hf[p], base, pivots[p], x0, y0, {'position0': offset(p, PARENT[p]) if PARENT[p] else [0, 0, 0]})

    # しっぽ：左右のズボンのすその後ろから、後ろ下へ。後頭部のはね：頭の上の後ろから、後ろ上へ
    shorts_backz = z0['shorts'] - DEPTH['shorts'][1] * hf['shorts']
    synth_place = []
    for name, side, fx in (('tailL', -1, pivots['footL'][0]), ('tailR', 1, pivots['footR'][0])):
        col = int(fx)
        hem = int(np.where(masks['shorts'][:, col])[0].max())
        y = hem - 8
        z = float(shorts_backz[hem - 25, col]) + 14  # すその後ろの面に、底辺を少しうめる
        base_h = (bottom - y) * scale  # 付け根（すそ）の地面からの高さ
        synth_place.append((name, [(fx - cx) * scale, -(y - 845) * scale, z * scale], tail_rotation(side, base_h, TAIL_LEN * scale)))
    head_back = float((z0['head'] - DEPTH['head'][1] * hf['head'])[340, int(cx)])
    synth_place.append(('tuft', [0, -(330 - 650) * scale, (head_back + 14) * scale], [0, math.pi / 2, 0.5]))
    for name, pos0, rot in synth_place:
        m, tex, back = synth[name]
        hh = height_field_simple(m)
        is_tail = name.startswith('tail')
        root_x = TAIL_ROOT if is_tail else 0  # しっぽは底辺が回転の中心
        add_part(name, m, hh, 0.0, [root_x, m.shape[0] / 2, 0], -PAD, -PAD, {'position0': pos0, 'rotation0': rot},
                 warp=bend_tail if is_tail else None)

    # 広げた羽：ふだんは隠しておき、羽を広げるポーズのときにたたんだ羽と入れかえる
    for name, hang in (('spreadL', 'wingL'), ('spreadR', 'wingR')):
        m, tex, back, pivot1 = spread[name]
        x0, y0 = items[name][3], items[name][4]
        pos0 = offset(hang, 'body')
        pos0[2] -= 0.012  # 胴より少し後ろ（絵 1 でも羽は頭と胴の後ろから出ている）
        add_part(name, m, height_field_simple(m), 0.0, pivot1, x0, y0, {'position0': pos0, 'spreadOf': hang}, s=spread_scale)

    # 表情の切りかえ用：目の位置（アトラス上の px）
    eyes = []
    hx0, hy0 = items['head'][3], items['head'][4]
    hax, hay = place['head']
    lab, k = ndi.label(part_fill['head'] & (cls == names.index('white')))
    for j in range(1, k + 1):
        yy, xx = np.where(lab == j)
        if len(yy) > 500:
            eyes.append([float(xx.mean() - hx0 + hax), float(yy.mean() - hy0 + hay), float(xx.max() - xx.min()), float(yy.max() - yy.min())])

    meta = {
        'version': MODEL_VERSION, 'source': SRC.name, 'height': HEIGHT_M, 'atlas': [AW, AH],
        'colors': {'purple': rgb_hex(dst[names.index('purple')]), 'line': rgb_hex(LINE)},
        'eyes': sorted(eyes), 'parts': parts_json,
        'pivotHeight': {'body': (bottom - pivots['body'][1]) * scale},
    }
    (OUT / 'model.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'model.bin').write_bytes(bytes(blob))
    Image.fromarray(np.clip(atlas_f, 0, 255).astype(np.uint8)).save(OUT / 'front.png', optimize=True)
    Image.fromarray(np.clip(atlas_b, 0, 255).astype(np.uint8)).save(OUT / 'back.png', optimize=True)
    print('atlas', AW, AH, 'bin', len(blob), 'parts', [(p['name'], p['vertexCount']) for p in parts_json])
    print('z0', {k: round(v, 1) for k, v in z0.items()}, 'scale', scale)


def assign(n, x, y):
    if n == 'green':
        return 'crest' if y < 440 else 'torso'
    if n in ('purple', 'hl'):
        if y < 640:
            return 'head'
        return 'wingL' if x < 640 else 'wingR'
    if n == 'yellow':
        if y < 700:
            return 'beak'
        return 'footL' if x < 640 else 'footR'
    if n == 'white':
        if y < 520:
            return 'head'  # 目
        if x < 500:
            return 'wingL'
        if x > 815:
            return 'wingR'  # 羽のつや
        return 'torso'
    if n == 'shorts':
        return 'shorts'
    raise ValueError(n)


def bend_tail(pos):
    """しっぽの底辺を、ズボンのすその丸みに合わせて弓なりに曲げる（両はしほど体の側＝根もと側へ寄せる）。
    先へいくほど曲げを弱め、先は曲げない"""
    pos = pos.copy()
    hb = TAIL_BASE / 2
    across = (pos[:, 1] - hb) / hb                                   # 底辺に沿った位置（-1〜1）
    along = np.clip((pos[:, 0] - TAIL_ROOT) / TAIL_LEN, 0, 1)        # 底辺 0 → 先 1
    pos[:, 0] -= TAIL_BEND * across ** 2 * (1 - along) ** 2
    return pos


def tail_rotation(side, base_h, length):
    """しっぽの向き：三角形の先を下・後ろ（少し外）へ、底辺を左右（すそに沿う向き）へ"""
    b = math.radians(TAIL_SPLAY)
    # 先の高さ＝付け根の高さ − 長さ×（下向きの成分）が TAIL_GROUND になる、真下からの傾き a
    drop = (base_h - TAIL_GROUND) / length * math.sqrt(1 + math.sin(b) ** 2)
    a = math.acos(max(-1.0, min(1.0, drop)))
    X = np.array([side * math.sin(b), -math.cos(a), -math.sin(a)])  # 底辺→先
    X /= np.linalg.norm(X)
    Y = np.array([1.0, 0, 0]) - X[0] * X  # 底辺の向き
    Y /= np.linalg.norm(Y)
    Z = np.cross(X, Y)
    R = np.stack([X, Y, Z], 1)
    # three.js の Euler（XYZ 順）に直す
    y = math.asin(max(-1, min(1, R[0, 2])))
    x = math.atan2(-R[1, 2], R[2, 2])
    z = math.atan2(-R[0, 1], R[0, 0])
    return [x, y, z]


def paint_back(p, back, m, green, shorts):
    """背中側の模様（後ろからの線画）：胴にはサスペンダーが2本まっすぐ下りる。ズボンは上に腰ひもの線"""
    if p == 'torso':
        for cx in (506, 768):  # 正面のサスペンダーと同じ位置
            band = m.copy()
            band[:, :cx - 24] = False
            band[:, cx + 24:] = False
            back[band] = LINE
            band[:, :cx - 20] = False
            band[:, cx + 20:] = False
            back[band] = green
    if p == 'shorts':
        # 上のふちに沿って、28〜32px 下に線を引く
        top = m.argmax(0)
        Y = np.arange(m.shape[0])[:, None]
        band = m & (Y >= top[None, :] + 28) & (Y < top[None, :] + 32)
        back[band] = LINE


def redraw_highlight(tex, head, hl, purple, color, margin=16):
    """頭のつやは絵では頭のふちで切れている。立体にすると横で切れて見えるので、
    同じ大きさのまま少し内側へずらし、ふちから margin px 内側に収まるまるごとのだ円に描きなおす"""
    lab, k = ndi.label(hl)
    if not k:
        return
    sizes = ndi.sum(hl, lab, range(1, k + 1))
    big = lab == (int(np.argmax(sizes)) + 1)
    tex[ndi.binary_dilation(big, iterations=7)] = purple  # にじんだふちも消す
    yy, xx = np.where(big)
    x0, x1, y0, y1 = xx.min(), xx.max(), yy.min(), yy.max()
    inner = ndi.binary_erosion(head, iterations=margin)
    H, W = head.shape
    Y, X = np.mgrid[:H, :W]
    cx0, cy0 = (x0 + x1) / 2, (y0 + y1) / 2
    a, b = (x1 - x0) / 2 + 2, (y1 - y0) / 2 + 2
    # 頭の中心の方へ少しずつずらす
    hy, hx = np.where(head)
    d = np.array([hx.mean() - cx0, hy.mean() - cy0])
    d /= np.linalg.norm(d)
    for i in range(80):
        cx, cy = cx0 + d[0] * i, cy0 + d[1] * i
        e = ((X - cx) / a) ** 2 + ((Y - cy) / b) ** 2
        if not (e <= 1.05)[~inner].any():
            break
    # ふちをなめらかに（だ円の境目を 1.5px ぼかして塗る）
    edge = np.clip((1 - np.sqrt(e)) * min(a, b) / 1.5 + 0.5, 0, 1)[..., None]
    tex[:] = tex * (1 - edge) + np.asarray(color, np.float32) * edge


def wrap_u(x, y, center, half, rows=None):
    """ふち近くの頂点の絵の位置を、回りこんだ角度に合わせて内側へ寄せる（ふちで元の絵のふちに戻る）
    rows=(y0, y1)：y0 より上は回りこませず、y1 までに少しずつ回りこませる"""
    yi = np.clip(np.round(y).astype(int), 0, len(center) - 1)
    c, hw = center[yi], half[yi]
    s = np.clip((x - c) / hw, -1, 1)
    th = np.arcsin(np.abs(s))
    th0 = math.asin(WRAP_START)
    # th0 より外側は、絵の WRAP_START〜1 の範囲を角度に比例して割りあてる（真横で絵のふちになる）
    s2 = np.where(th > th0, WRAP_START + (1 - WRAP_START) * (th - th0) / (math.pi / 2 - th0), np.abs(s))
    if rows:
        w = np.clip((y - rows[0]) / (rows[1] - rows[0]), 0, 1)
        s2 = np.abs(s) + (s2 - np.abs(s)) * w * w * (3 - 2 * w)
    return c + np.sign(s) * s2 * hw


def hull(m):
    yy, xx = np.where(m)
    pts = np.stack([xx, yy], 1)
    hpts = pts[ConvexHull(pts).vertices]
    im = Image.new('L', (m.shape[1], m.shape[0]), 0)
    ImageDraw.Draw(im).polygon([tuple(map(float, p)) for p in hpts], fill=1)
    return np.array(im, bool) | m


def ellipse(H, W, cx, cy, a, b):
    y, x = np.mgrid[:H, :W]
    return ((x - cx) / a) ** 2 + ((y - cy) / b) ** 2 <= 1


def build_spread_wings(dst, names, pivots, cx2, top2, scale2):
    """羽を広げた絵（1）から、左右の広げた羽（上が紫、下に白い羽根）を切り出す。
    絵 1 は絵 2 と大きさがちがうので、全体の高さで合わせ、肩（たたんだ羽の回転の中心）の位置を対応させる"""
    img = np.array(Image.open(SRC_SPREAD).convert('RGBA')).astype(np.float32)
    H, W = img.shape[:2]
    rgb, inside = img[..., :3], img[..., 3] > 127
    ys, _ = np.where(inside)
    top1, bottom1 = ys.min(), ys.max()
    scale1 = HEIGHT_M / (bottom1 - top1)
    k = scale1 / scale2  # 絵 1 の 1px が絵 2 の何 px か
    cols = np.array([FILLS[n][1] for n in names], np.float32)  # 絵 1 はもともと濃いめの配色
    dist = np.linalg.norm(rgb[:, :, None, :] - cols[None, None], axis=-1)
    cls = dist.argmin(-1)
    fill = inside & (dist.min(-1) < 30)
    lab_s, _ = ndi.label(fill & (cls == names.index('shorts')))
    cx1 = np.where(lab_s > 0)[1].mean()  # 体のまん中
    out = {}
    for name, hang, side in (('spreadL', 'wingL', -1), ('spreadR', 'wingR', 1)):
        wf = np.zeros((H, W), bool)
        for cname in ('purple', 'white'):
            lab, n = ndi.label(fill & (cls == names.index(cname)))
            for j in range(1, n + 1):
                c = lab == j
                yy, xx = np.where(c)
                if len(yy) > 5000 and (xx.mean() - cx1) * side > 120:
                    wf |= c
        others = fill & ~wf
        lines = inside & ~fill & (ndi.distance_transform_edt(~wf) <= 5) & (ndi.distance_transform_edt(~others) > 4)
        own = wf | lines
        hx, hy = pivots[hang][0], pivots[hang][1]
        px1, py1 = cx1 + (hx - cx2) / k, top1 + (hy - top2) / k  # 肩の位置（絵 1 の座標）
        # 頭と胴に隠れている羽の根もとを、肩の中までおぎなう（羽を上げたとき体から離れて見えないように、
        # 根もとは大きく、肩より体の内側まで入れる）
        X = np.arange(W)[None, :]
        root = ellipse(H, W, px1 - side * SPREAD_ROOT_IN, py1, 55, 75) | (own & (np.abs(X - px1) < 90))
        m = own | hull(root)
        m = ndi.binary_fill_holes(m)
        m = ndi.gaussian_filter(m.astype(np.float32), 1.5) > 0.5
        tex = rgb.copy()
        core = ndi.binary_erosion(wf, iterations=2)
        _, (iy, ix) = ndi.distance_transform_edt(~core, return_indices=True)
        hidden = m & ~own
        tex[hidden] = rgb[iy[hidden], ix[hidden]]
        dm = ndi.distance_transform_edt(m)
        rim = m & (dm <= RIM)
        _, (jy, jx) = ndi.distance_transform_edt(~((dm > RIM) & core), return_indices=True)
        tex[rim] = tex[jy[rim], jx[rim]]
        back = tex.copy()  # 後ろから見ても前と同じ色（上が紫、下に白い羽根）
        out[name] = (m, tex, back, [px1, py1, 0.0])
    return out, scale1


def synth_part(poly, cname, dst, names, ss=4):
    """多角形をなめらかにして、色と輪郭線をつけた部品を作る"""
    pts = np.array(poly, np.float32)
    w, h = int(pts[:, 0].max()) + 2, int(pts[:, 1].max()) + 2
    im = Image.new('L', (w * ss, h * ss), 0)
    ImageDraw.Draw(im).polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    m = np.array(im.resize((w, h), Image.LANCZOS)) > 127
    m = ndi.gaussian_filter(m.astype(np.float32), 2) > 0.5
    tex = np.empty((h, w, 3), np.float32)
    tex[:] = dst[names.index(cname)]
    back = tex.copy()
    return m, tex, back


def height_field_simple(m):
    d = ndi.distance_transform_edt(m)
    R = d.max()
    return ndi.gaussian_filter(np.sqrt(np.clip(d * (2 * R - d), 0, None)), 1.5) * m


def crop_pad(img, m, x0, y0, x1, y1):
    """部品の範囲を切り出し、外側に色をのばして（にじみ防止）返す"""
    H, W = m.shape
    out = np.zeros((y1 - y0, x1 - x0, 3), np.float32)
    mm = np.zeros((y1 - y0, x1 - x0), bool)
    sx0, sy0, sx1, sy1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    out[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = img[sy0:sy1, sx0:sx1]
    mm[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = m[sy0:sy1, sx0:sx1]
    _, (iy, ix) = ndi.distance_transform_edt(~mm, return_indices=True)
    return out[iy, ix]


def pack(sizes):
    """縦に高い順に棚へ並べる"""
    AW = 1024
    order = sorted(sizes, key=lambda p: -sizes[p][1])
    place, x, y, row = {}, 0, 0, 0
    for p in order:
        w, h = sizes[p]
        if x + w > AW:
            x, y, row = 0, y + row, 0
        place[p] = (x, y)
        x += w
        row = max(row, h)
    AH = 1 << math.ceil(math.log2(y + row))
    return place, AW, AH


def sample(a, x, y):
    """配列 a を (x, y) で双一次補間"""
    H, W = a.shape
    x = np.clip(x, 0, W - 1.001); y = np.clip(y, 0, H - 1.001)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = x - x0; fy = y - y0
    return (a[y0, x0] * (1 - fx) * (1 - fy) + a[y0, x0 + 1] * fx * (1 - fy)
            + a[y0 + 1, x0] * (1 - fx) * fy + a[y0 + 1, x0 + 1] * fx * fy)


def build_mesh(m, h, zbase, depth):
    """輪郭 m・高さ h から、表と裏がふちでつながった閉じたメッシュを作る（座標は px）"""
    H, W = m.shape
    # 符号つき距離（内側が正）。ふちの頂点をこれが 0 になる所へ寄せる
    sdf = ndi.distance_transform_edt(m) - ndi.distance_transform_edt(~m)
    sdf = ndi.gaussian_filter(sdf.astype(np.float32), 1.0)
    gy, gx = np.gradient(sdf)
    g = GRID
    nx, ny = W // g + 2, H // g + 2
    X, Y = np.meshgrid(np.arange(nx) * g, np.arange(ny) * g)
    cell_in = sample(sdf, X[:-1, :-1] + g / 2, Y[:-1, :-1] + g / 2) > 0
    used = np.zeros((ny, nx), bool)
    used[:-1, :-1] |= cell_in; used[1:, :-1] |= cell_in; used[:-1, 1:] |= cell_in; used[1:, 1:] |= cell_in
    # ふち＝使われているセルとそうでないセルの両方に接する頂点
    pad = np.pad(cell_in, 1)
    touch_out = ~(pad[:-1, :-1] & pad[1:, :-1] & pad[:-1, 1:] & pad[1:, 1:])
    edge = used & touch_out
    vid = -np.ones((ny, nx), int)
    vid[used] = np.arange(used.sum())
    px_ = X[used].astype(np.float32); py_ = Y[used].astype(np.float32)
    is_edge = edge[used]
    for _ in range(4):
        e = is_edge
        s = sample(sdf, px_[e], py_[e])
        dx = sample(gx, px_[e], py_[e]); dy = sample(gy, px_[e], py_[e])
        n = np.sqrt(dx * dx + dy * dy) + 1e-6
        px_[e] -= s * dx / n; py_[e] -= s * dy / n
    hh = sample(h.astype(np.float32), px_, py_)
    hh[is_edge] = 0
    zb = zbase if np.isscalar(zbase) else sample(zbase.astype(np.float32), px_, py_)
    nv = len(px_)
    front = np.stack([px_, py_, zb + depth[0] * hh], 1)
    # 裏：ふち以外の頂点を複製
    back_ids = -np.ones(nv, int)
    inner = np.where(~is_edge)[0]
    back_ids[inner] = nv + np.arange(len(inner))
    back_ids[is_edge] = np.where(is_edge)[0]
    back = np.stack([px_[inner], py_[inner], (zb if np.isscalar(zb) else zb[inner]) - depth[1] * hh[inner]], 1)
    pos = np.concatenate([front, back])
    tf, tb = [], []
    for j in range(ny - 1):
        for i in range(nx - 1):
            if not cell_in[j, i]:
                continue
            a, b, c, d = vid[j, i], vid[j, i + 1], vid[j + 1, i], vid[j + 1, i + 1]
            # 画像の y は下向き。表（+z）から見て反時計回り
            tf += [a, c, b, b, c, d]
            A, B, C, D = back_ids[[a, b, c, d]]
            tb += [A, B, C, B, D, C]
    idx = np.array(tf + tb, np.int64)
    assert pos.shape[0] < 65536
    return pos, pos[:, :2], idx, len(tf)


def rgb_hex(c):
    return '#%02x%02x%02x' % tuple(int(v) for v in c)


if __name__ == '__main__':
    main()
