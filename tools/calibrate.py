#!/usr/bin/env python3
"""Footage Logging — hiệu chỉnh ngưỡng máy đo theo mắt người dùng (chấm tay ~40 cảnh).

  python3 calibrate.py sample <dự án> [--n 40]
      Chọn ~40 cảnh trải đều các loại máy đoán (chân máy/gimbal/cầm tay, pan/tilt/tĩnh, các cỡ cảnh)
      → analysis/calib/sample.json (+ ảnh kf để đưa lên trang chấm)
  python3 calibrate.py page <dự án>
      Tạo trang chấm tự chứa (ảnh nhúng sẵn) → analysis/calib/cham.html. Mở bằng trình duyệt, chấm xong
      bấm "Tải answers.json" (hoặc đăng trang thành Artifact có db để Claude đọc thẳng kết quả).
  python3 calibrate.py fit <dự án> <answers.json>
      answers.json: {"<clip>#sNN": {"rig": "...", "move": "...", "size": "...", "stability": "...", "sharp": "..."}}
      (bỏ trống trường nào thì coi như máy đoán đúng). So với máy đoán, dò lại ngưỡng rung/chân máy/gimbal
      và ngưỡng cỡ cảnh → ghi tools/thresholds.json (shots.py tự đọc) + analysis/calib/report.md.
      Sau đó chạy lại shots.py --force để áp ngưỡng mới.
"""
import glob, itertools, json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shots as S
OUT_DIR = os.environ.get('FL_OUT', '_SOCIAL')   # thư mục kết quả trong dự án (đổi bằng biến môi trường FL_OUT)

SIZES = S.SIZE_LABELS
RIG_CLASS = {'chân máy': 'tripod', 'gimbal': 'smooth', 'slider': 'smooth', 'dolly': 'smooth', 'cầm tay': 'hand', 'rung': 'hand'}


def rig_class(label):
    label = (label or '').lower()
    if 'chân máy' in label and 'gimbal' not in label:
        return 'tripod'
    for k, v in RIG_CLASS.items():
        if k in label:
            return v
    return None


def load_segments(project):
    A = os.path.join(project, OUT_DIR, 'analysis')
    out = {}
    for f in glob.glob(os.path.join(A, 'shots', '*.json')):
        s = json.load(open(f))
        for x in s.get('segments', []):
            out[f"{s['id']}#s{x['i']:02d}"] = (s, x)
    return A, out


def sample(project, n=40):
    A, segs = load_segments(project)
    buckets = {}
    for k, (s, x) in segs.items():
        if not x.get('kf') or x['dur'] < 2:
            continue
        b = (s['kind'] if s['kind'] in ('CAM', 'POV') else 'PHONE', x['rig'].split(' (')[0], x['move'].split(' ')[0], x['size'] or '-')
        buckets.setdefault(b, []).append(k)
    random.seed(7)
    # chia theo loại thiết bị trước: máy chính cần hiệu chỉnh nhiều nhất (rig/chuyển động/cỡ cảnh)
    quota = {'CAM': int(n * 0.7), 'POV': int(n * 0.2)}
    quota['PHONE'] = n - quota['CAM'] - quota['POV']
    keys = []
    for kind, q in quota.items():
        pools = [v for b_, v in buckets.items() if b_[0] == kind]
        got = []
        while len(got) < q and any(pools):
            for p_ in pools:
                if p_ and len(got) < q:
                    got.append(p_.pop(random.randrange(len(p_))))
        keys += got
    if len(keys) < n:   # bù từ phần còn lại nếu loại nào thiếu
        rest = [k for v in buckets.values() for k in v]
        random.shuffle(rest); keys += rest[: n - len(keys)]
    os.makedirs(os.path.join(A, 'calib'), exist_ok=True)
    items = []
    for k in keys:
        s, x = segs[k]
        items.append(dict(key=k, kf=x['kf'], path=s['path'], start=x['start'], end=x['end'], kind=s['kind'],
                          rig=x['rig'], move=x['move'], size=x['size'], stability=x['stability'], sharp=x['sharp']))
    import cv2
    os.makedirs(os.path.join(A, 'calib', 'img'), exist_ok=True)
    for i, it in enumerate(items):   # ảnh nhỏ để đưa lên trang chấm
        im = cv2.imread(os.path.join(A, it['kf']))
        if im is not None:
            h, w = im.shape[:2]
            cv2.imwrite(os.path.join(A, 'calib', 'img', f'c{i:02d}.jpg'), cv2.resize(im, (480, int(h * 480 / w))), [cv2.IMWRITE_JPEG_QUALITY, 80])
            it['img'] = f'c{i:02d}.jpg'
    json.dump(items, open(os.path.join(A, 'calib', 'sample.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'{len(items)} cảnh → calib/sample.json')


def fit(project, answers_path):
    A, segs = load_segments(project)
    ans = json.load(open(answers_path))
    rep = ['# Báo cáo hiệu chỉnh', '']
    th = dict(S.TH)
    # --- độ chính xác hiện tại
    for field in ('rig', 'move', 'size', 'stability', 'sharp'):
        tot = ok = 0
        for k, a in ans.items():
            if k not in segs or not a.get(field):
                continue
            tot += 1
            ok += str(a[field]).split(' ')[0].lower() == str(segs[k][1].get(field) or '').split(' ')[0].lower()
        if tot:
            rep.append(f'- {field}: máy đúng {ok}/{tot} ({ok / tot:.0%})')
    # --- dò ngưỡng rig (chỉ máy cầm/gimbal/chân máy, không tính POV)
    data = []
    for k, a in ans.items():
        if k in segs and a.get('rig') and segs[k][0]['kind'] not in ('POV', 'ACTION'):
            c = rig_class(a['rig'])
            if c:
                data.append((segs[k][1]['raw']['jit'], c))
    if len(data) >= 6:
        grid_t = [0.0008, 0.0012, 0.0018, 0.0025, 0.0035]
        grid_s = [0.003, 0.004, 0.0055, 0.007, 0.009, 0.012]
        best = None
        for t, sm in itertools.product(grid_t, grid_s):
            if sm <= t:
                continue
            acc = sum((('tripod' if j < t else 'smooth' if j < sm else 'hand') == c) for j, c in data) / len(data)
            if best is None or acc > best[0]:
                best = (acc, t, sm)
        th['jit_tripod'], th['jit_smooth'] = best[1], best[2]
        rep.append(f'- Ngưỡng rig mới: chân máy < {best[1]}, gimbal/slider < {best[2]} (khớp {best[0]:.0%} trên {len(data)} cảnh)')
    # --- dò hệ số cỡ cảnh
    sd = []
    for k, a in ans.items():
        if k in segs and a.get('size') and segs[k][1]['raw'].get('face_h'):
            lab = next((i for i, s in enumerate(SIZES) if a['size'].split(' ')[0].lower() in s.lower()), None)
            if lab is not None:
                sd.append((segs[k][1]['raw']['face_h'], lab))
    if len(sd) >= 6:
        base = S.TH['size_face']
        best = None
        for f in [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6]:
            ths = [b * f for b in base]
            def cls(h):
                for i, t in enumerate(ths):
                    if h > t:
                        return i
                return 6
            acc = sum(abs(cls(h) - l) <= 0 for h, l in sd) / len(sd)
            if best is None or acc > best[0]:
                best = (acc, f, ths)
        th['size_face'] = [round(x, 4) for x in best[2]]
        rep.append(f'- Hệ số cỡ cảnh ×{best[1]} (khớp {best[0]:.0%} trên {len(sd)} cảnh có mặt người)')
    keep = {k: th[k] for k in th if th[k] != S.TH.get(k) or k in ('jit_tripod', 'jit_smooth', 'size_face')}
    json.dump(keep, open(os.path.join(HERE, 'thresholds.json'), 'w'), ensure_ascii=False, indent=1)
    os.makedirs(os.path.join(A, 'calib'), exist_ok=True)
    open(os.path.join(A, 'calib', 'report.md'), 'w').write('\n'.join(rep) + '\n')
    print('\n'.join(rep)); print('→ tools/thresholds.json (chạy lại shots.py --force để áp dụng)')


def page(project):
    import base64
    A = os.path.join(project, OUT_DIR, 'analysis')
    items = json.load(open(os.path.join(A, 'calib', 'sample.json')))
    data = []
    for it in items:
        src = ''
        p = os.path.join(A, 'calib', 'img', it.get('img', ''))
        if it.get('img') and os.path.exists(p):
            src = 'data:image/jpeg;base64,' + base64.b64encode(open(p, 'rb').read()).decode()
        data.append(dict(k=it['key'], src=src, kind=it['kind'], t=f"{it['start']:.1f}–{it['end']:.1f}s",
                         path=os.path.basename(it['path']), rig=it['rig'], move=it['move'], size=it['size'] or '',
                         stab=it['stability'], sharp=it['sharp']))
    tpl = open(os.path.join(HERE, '..', 'calib', 'template.html'), encoding='utf-8').read()
    out = os.path.join(A, 'calib', 'cham.html')
    open(out, 'w', encoding='utf-8').write(tpl.replace('/*__DATA__*/[]', json.dumps(data, ensure_ascii=False)))
    print(f'{len(data)} cảnh → {out}')


if __name__ == '__main__':
    cmd, proj = sys.argv[1], sys.argv[2]
    if cmd == 'sample':
        sample(proj, int(sys.argv[sys.argv.index('--n') + 1]) if '--n' in sys.argv else 40)
    elif cmd == 'page':
        page(proj)
    elif cmd == 'fit':
        fit(proj, sys.argv[3])
