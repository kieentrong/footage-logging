#!/usr/bin/env python3
"""Trợ lý social — bước 1: quét & QC kỹ thuật từng clip.

Dùng:  python3 analyze.py <project_dir> [--only POV] [--limit N] [--force]

Với mỗi clip video trong project (bỏ qua _SOCIAL, 99_EXPORT, file ._*):
  - đọc metadata (thiết bị, giờ quay, GPS, độ phân giải, fps)
  - ưu tiên phân tích trên PROXY nếu có (01_SOURCE/Proxy/<tên>_Proxy.mov)
  - giải mã 5 fps ở 360px, đo: độ sáng, cháy/sập, độ nét (Laplacian), rung (phase-correlation jitter), chuyển cảnh
  - đo âm lượng theo 0.5s
  - gắn cờ từng giây: dark / blown / blur / shaky / silent → tìm đoạn dùng được (usable)
  - xuất contact sheet (1 hàng 6 khung) để AI xem nội dung
Kết quả: <project>/_SOCIAL/analysis/clips/<clip_id>.json + sheets/<clip_id>.jpg
"""
import argparse, json, os, re, subprocess, sys, hashlib
from datetime import datetime, timedelta, timezone
import numpy as np
import cv2
OUT_DIR = os.environ.get('FL_OUT', '_SOCIAL')   # thư mục kết quả trong dự án (đổi bằng biến môi trường FL_OUT)
TZ = timezone(timedelta(hours=float(os.environ.get('FL_TZ', '7'))))   # múi giờ nơi quay (FL_TZ, mặc định UTC+7)

VIDEO_EXT = ('.mp4', '.mov', '.m4v', '.mts', '.avi', '.mkv', '.insv', '.lrv')
SKIP_DIRS = (OUT_DIR, '_SOCIAL', '99_EXPORT', 'Proxy', 'Proxies', 'THMBNL', 'SUB', '03_ELEMENT', '.Trash')
FPS = 5
W = 360


def sh(cmd, binary=False):
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout if binary else r.stdout.decode('utf-8', 'ignore')


def probe(path):
    out = sh(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path])
    try:
        return json.loads(out)
    except Exception:
        return {}


def detect_device(tags, path, vstream):
    model = (tags.get('com.apple.quicktime.model') or tags.get('model') or '').strip()
    make = (tags.get('com.apple.quicktime.make') or tags.get('make') or '').strip()
    name = os.path.basename(path).upper()
    low = path.lower()
    if 'ray-ban' in model.lower() or 'meta ai' in (tags.get('com.apple.quicktime.copyright') or '').lower():
        return 'rayban_meta', 'POV'
    if make.lower() == 'apple' or 'iphone' in model.lower():
        return model or 'iphone', 'PHONE'
    if re.match(r'^(GX|GH|GOPR|GP)\d+', name) or 'gopro' in (tags.get('handler_name', '') + model).lower():
        return 'gopro', 'ACTION'
    if re.match(r'^DJI_', name) or 'dji' in model.lower() or 'osmo' in model.lower():
        return model or 'dji', 'ACTION'
    if '/private/m4root/' in low or re.match(r'^(C\d{4}|NEX\d+|DSC\d+)', name):
        return 'sony', 'CAM'
    if 'samsung' in make.lower() or 'android' in (tags.get('com.android.version') or '').lower():
        return 'android', 'PHONE'
    # Sony XAVC ghi gần như không có tag trong MP4 — model máy nằm ở XML sidecar
    # (KEN9316.MP4 -> KEN9316M01.XML, thẻ <Device manufacturer=.. modelName=..>)
    try:
        side = re.sub(r'\.[^.]+$', 'M01.XML', path)
        if os.path.exists(side):
            txt = open(side, encoding='utf-8', errors='ignore').read()
            dev = re.search(r'<Device[^>]*>', txt)
            if dev:
                manu = re.search(r'manufacturer="([^"]+)"', dev.group(0))
                mod = re.search(r'modelName="([^"]+)"', dev.group(0))
                if mod:
                    return ((manu.group(1) + ' ') if manu else '') + mod.group(1), 'CAM'
    except Exception:
        pass
    return model or 'unknown', 'CAM'


def creation_time(tags, path):
    for k in ('com.apple.quicktime.creationdate', 'creation_time'):
        v = tags.get(k)
        if v:
            try:
                v2 = v.replace('Z', '+00:00')
                dt = datetime.fromisoformat(v2[:25] if '+' not in v2[19:] else v2)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(TZ).isoformat()
            except Exception:
                pass
    # Sony XML sidecar  (NEX1234M01.XML)
    base = os.path.splitext(path)[0]
    for x in (base + 'M01.XML', base + 'M01.xml'):
        if os.path.exists(x):
            m = re.search(r'CreationDate value="([^"]+)"', open(x, errors='ignore').read())
            if m:
                return m.group(1)
    m = re.search(r'(20\d{6})_(\d{6})', os.path.basename(path))
    if m:
        return datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S').replace(tzinfo=TZ).isoformat()
    return None


def find_proxy(project, path):
    stem = os.path.splitext(os.path.basename(path))[0]
    cands = []
    for root, dirs, files in os.walk(project):
        if os.path.basename(root).lower() in ('proxy', 'proxies'):
            for f in files:
                if f.startswith('._'):
                    continue
                s = os.path.splitext(f)[0]
                if s == stem + '_Proxy' or re.match(re.escape(stem) + r'(_\d+)?_Proxy$', s):
                    cands.append(os.path.join(root, f))
    return cands[0] if cands else None


def clip_id(project, path):
    rel = os.path.relpath(path, project)
    stem = re.sub(r'[^A-Za-z0-9_-]+', '_', os.path.splitext(os.path.basename(path))[0])[:60]
    return stem + '_' + hashlib.md5(rel.encode()).hexdigest()[:6]


def decode_gray(path, dur):
    cmd = ['ffmpeg', '-v', 'error', '-skip_loop_filter', 'all', '-flags2', '+fast', '-i', path, '-vf', f'fps={FPS},scale={W}:-2,format=gray', '-f', 'rawvideo', '-']
    raw = sh(cmd, binary=True)
    # find height from first frame size guess
    p = probe(path)
    vs = [s for s in p.get('streams', []) if s.get('codec_type') == 'video']
    if not vs or not raw:
        return None
    w0, h0 = vs[0].get('width', 16), vs[0].get('height', 9)
    rot = 0
    for sd in vs[0].get('side_data_list', []) or []:
        if 'rotation' in sd:
            rot = abs(int(sd['rotation']))
    if rot in (90, 270):
        w0, h0 = h0, w0
    h = int(round(W * h0 / w0 / 2) * 2)
    n = len(raw) // (W * h)
    if n == 0:
        return None
    return np.frombuffer(raw[:n * W * h], np.uint8).reshape(n, h, W)


def audio_rms(path):
    raw = sh(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-'], binary=True)
    if not raw:
        return []
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 4000
    n = len(a) // hop
    if n == 0:
        return []
    r = np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-10)
    return (20 * np.log10(r)).round(1).tolist()


def analyze_frames(fr):
    n = len(fr)
    luma = fr.reshape(n, -1).mean(1)
    blown = (fr.reshape(n, -1) > 245).mean(1)
    crushed = (fr.reshape(n, -1) < 12).mean(1)
    sharp = np.array([cv2.Laplacian(f, cv2.CV_64F).var() for f in fr])
    # motion: global shift via phase correlation
    win = cv2.createHanningWindow((fr.shape[2], fr.shape[1]), cv2.CV_32F)
    shifts = [(0.0, 0.0)]
    diffs = [0.0]
    hist_prev = None
    cuts = []
    for i in range(1, n):
        a = fr[i - 1].astype(np.float32)
        b = fr[i].astype(np.float32)
        (dx, dy), resp = cv2.phaseCorrelate(a, b, win)
        shifts.append((dx, dy))
        diffs.append(float(np.abs(a - b).mean()))
    for i in range(n):
        h = cv2.calcHist([fr[i]], [0], None, [32], [0, 256]).ravel()
        h /= h.sum() + 1e-9
        if hist_prev is not None:
            d = 0.5 * np.abs(h - hist_prev).sum()
            if d > 0.45:
                cuts.append(round(i / FPS, 2))
        hist_prev = h
    sh_ = np.array(shifts)
    mag = np.hypot(sh_[:, 0], sh_[:, 1]) / W  # fraction of width per 0.2s
    # jitter = deviation from smoothed motion path
    k = 5
    if n > k:
        ker = np.ones(k) / k
        smx = np.convolve(sh_[:, 0], ker, 'same')
        smy = np.convolve(sh_[:, 1], ker, 'same')
        jit = np.hypot(sh_[:, 0] - smx, sh_[:, 1] - smy) / W
    else:
        jit = np.zeros(n)
    return dict(luma=luma, blown=blown, crushed=crushed, sharp=sharp, motion=mag, jitter=jit, diff=np.array(diffs), cuts=cuts)


def per_second(arr, n_sec, fn=np.mean):
    out = []
    for s in range(n_sec):
        seg = arr[s * FPS:(s + 1) * FPS]
        out.append(float(fn(seg)) if len(seg) else 0.0)
    return out


def contact_sheet(path, dur, segs, out_jpg, label, n=6, tile_w=260):
    if dur <= 0:
        return
    # choose timestamps inside usable segments if possible
    pts = []
    if segs:
        tot = sum(e - s for s, e in segs)
        for i in range(n):
            t = (i + 0.5) * tot / n
            for s, e in segs:
                if t <= e - s:
                    pts.append(s + t)
                    break
                t -= e - s
    if len(pts) < n:
        pts = [(i + 0.5) * dur / n for i in range(n)]
    tiles = []
    for t in pts:
        raw = sh(['ffmpeg', '-v', 'error', '-ss', f'{t:.2f}', '-i', path, '-frames:v', '1', '-vf', f'scale={tile_w}:-2', '-f', 'image2pipe', '-vcodec', 'png', '-'], binary=True)
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR) if raw else None
        if img is None:
            continue
        cv2.putText(img, f'{t:.1f}s', (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
        cv2.putText(img, f'{t:.1f}s', (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        tiles.append(img)
    if not tiles:
        return
    h = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 4, cv2.BORDER_CONSTANT) for t in tiles]
    row = np.hstack(tiles)
    bar = np.zeros((30, row.shape[1], 3), np.uint8)
    cv2.putText(bar, label[:120], (6, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    cv2.imwrite(out_jpg, np.vstack([bar, row]), [cv2.IMWRITE_JPEG_QUALITY, 70])


def segments_from_flags(bad, min_len=1.5):
    segs, start = [], None
    for i, b in enumerate(bad + [True]):
        if not b and start is None:
            start = i
        if b and start is not None:
            if i - start >= min_len:
                segs.append([start, i])
            start = None
    return segs


def analyze(project, path, outdir, force=False):
    cid = clip_id(project, path)
    oj = os.path.join(outdir, 'clips', cid + '.json')
    if os.path.exists(oj) and not force:
        return cid, 'cached'
    p = probe(path)
    fmt = p.get('format', {})
    tags = dict(fmt.get('tags', {}))
    vs = [s for s in p.get('streams', []) if s.get('codec_type') == 'video']
    aus = [s for s in p.get('streams', []) if s.get('codec_type') == 'audio']
    if not vs:
        json.dump(dict(id=cid, path=os.path.relpath(path, project), error='corrupt-or-no-video',
                       note='File hỏng/không đọc được (vd. thiếu moov atom do rút thẻ khi đang ghi) — cần recover'),
                  open(oj, 'w'), ensure_ascii=False, indent=1)
        return cid, 'corrupt'
    v = vs[0]
    dur = float(fmt.get('duration') or v.get('duration') or 0)
    device, kind = detect_device(tags, path, v)
    proxy = find_proxy(project, path) if kind == 'CAM' else None
    src = proxy or path
    w, h = v.get('width'), v.get('height')
    rot = 0
    for sd in v.get('side_data_list', []) or []:
        if 'rotation' in sd:
            rot = abs(int(sd['rotation']))
    if rot in (90, 270):
        w, h = h, w
    if proxy:  # proxy reflects real orientation better (in-camera rotation flag)
        pv = [s for s in probe(proxy).get('streams', []) if s.get('codec_type') == 'video']
        if pv and (pv[0]['height'] > pv[0]['width']) != (h > w):
            w, h = h, w
    fps = v.get('r_frame_rate', '0/1')
    try:
        a, b = fps.split('/'); fps = round(float(a) / float(b), 3)
    except Exception:
        fps = 0
    gps = tags.get('com.apple.quicktime.location.ISO6709') or tags.get('location')
    fr = decode_gray(src, dur)
    res = dict(id=cid, path=os.path.relpath(path, project), proxy=os.path.relpath(proxy, project) if proxy else None,
               device=device, kind=kind, duration=round(dur, 2), width=w, height=h,
               orientation='vertical' if (h or 0) > (w or 0) else 'horizontal', fps=fps,
               created=creation_time(tags, path), gps=gps, has_audio=bool(aus))
    if fr is None or len(fr) < 2:
        res['error'] = 'decode-failed'
        json.dump(res, open(oj, 'w'), ensure_ascii=False, indent=1)
        return cid, 'decode-failed'
    m = analyze_frames(fr)
    n_sec = max(1, int(np.ceil(len(fr) / FPS)))
    sec = dict(
        luma=per_second(m['luma'], n_sec),
        blown=per_second(m['blown'], n_sec),
        sharp=per_second(m['sharp'], n_sec),
        motion=per_second(m['motion'], n_sec),
        jitter=per_second(m['jitter'], n_sec, np.max),
    )
    rms = audio_rms(src) if aus else []  # proxy có cùng audio, đọc nhẹ hơn file 4K
    # thresholds (calibrated for 360px gray)
    clip_sharp_ref = float(np.percentile(m['sharp'], 90)) if len(m['sharp']) else 0
    flags = []
    # POV/action cam luôn chuyển động theo đầu/người → ngưỡng rung nới hơn máy cầm tay
    jit_th = {'POV': 0.06, 'ACTION': 0.06, 'PHONE': 0.045}.get(kind, 0.03)
    for s in range(n_sec):
        f = []
        if sec['luma'][s] < 38: f.append('dark')
        if sec['blown'][s] > 0.25: f.append('blown')
        if sec['sharp'][s] < 25 or (clip_sharp_ref > 0 and sec['sharp'][s] < 0.35 * clip_sharp_ref and sec['sharp'][s] < 80): f.append('blur')
        if sec['jitter'][s] > jit_th: f.append('shaky')
        if sec['motion'][s] > (0.18 if kind in ('POV', 'ACTION') else 0.12): f.append('whip')
        flags.append(f)
    bad = [bool(set(f) & {'dark', 'blur', 'shaky', 'whip', 'blown'}) for f in flags]
    segs = segments_from_flags(bad)
    usable = sum(e - s for s, e in segs)
    # speech-ish energy
    loud = [x for x in rms if x > -35]
    speech_ratio = round(len(loud) / max(1, len(rms)), 2)
    q = 10.0
    q -= 6 * (1 - usable / max(1, n_sec))
    q -= 2 if np.mean(sec['luma']) < 50 else 0
    q -= 1.5 if np.mean([('shaky' in f) for f in flags]) > 0.3 else 0
    res.update(
        per_sec=sec, flags=flags, usable=segs, usable_sec=usable,
        usable_ratio=round(usable / max(1, n_sec), 2), cuts=m['cuts'],
        audio_db=rms, speech_ratio=speech_ratio,
        quality=round(max(0, q), 1),
        summary_flags={k: round(float(np.mean([k in f for f in flags])), 2) for k in ['dark', 'blown', 'blur', 'shaky', 'whip']},
    )
    os.makedirs(os.path.join(outdir, 'sheets'), exist_ok=True)
    label = f"{cid} | {device} | {dur:.1f}s | Q{res['quality']} | {res['created'] or ''}"
    contact_sheet(src, dur, segs, os.path.join(outdir, 'sheets', cid + '.jpg'), label)
    res['sheet'] = os.path.join('sheets', cid + '.jpg')
    json.dump(res, open(oj, 'w'), ensure_ascii=False, indent=1)
    return cid, 'ok'


def list_videos(project, only=None):
    vids = []
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRS]
        rel = os.path.relpath(root, project)
        if only and not any(rel.startswith(o) for o in only):
            continue
        for f in sorted(files):
            if f.startswith('._') or not f.lower().endswith(VIDEO_EXT):
                continue
            vids.append(os.path.join(root, f))
    return sorted(vids)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--budget', type=float, default=0, help='giây; ngừng nhận clip mới sau mốc này (chạy nhiều lượt)')
    ap.add_argument('--cost', type=float, default=0.4, help='giây xử lý cho mỗi giây video (máy ảo 4 nhân ~0.4 với HEVC POV)')
    a = ap.parse_args()
    outdir = os.path.join(a.project, OUT_DIR, 'analysis')
    os.makedirs(os.path.join(outdir, 'clips'), exist_ok=True)
    vids = list_videos(a.project, a.only)
    if a.limit:
        vids = vids[:a.limit]
    # bỏ qua clip đã có kết quả
    todo = [v for v in vids if a.force or not os.path.exists(os.path.join(outdir, 'clips', clip_id(a.project, v) + '.json'))]
    print(f'{len(vids)} clips, còn {len(todo)} chưa phân tích', flush=True)
    import time
    from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
    cv2.setNumThreads(1)
    t0 = time.time()
    done_n = 0
    # Ước lượng thời gian mỗi clip (giây wall-clock) = 4 + thời lượng × cost × số clip chạy song song.
    # Với --budget: chỉ nhận clip mới nếu dự kiến kịp xong trước mốc → mỗi lượt kết thúc gọn, chạy lại để tiếp tục.
    queue = list(todo)
    stop = False
    with ProcessPoolExecutor(a.workers) as ex:
        pending = set()
        while True:
            while queue and not stop and len(pending) < a.workers:
                v = queue[0]
                dur = float((probe(v).get('format') or {}).get('duration') or 5)
                est = 4 + dur * a.cost * (len(pending) + 1)
                if a.budget and time.time() - t0 + est > a.budget and (pending or done_n):
                    stop = True
                    break
                pending.add(ex.submit(analyze, a.project, queue.pop(0), outdir, a.force))
            if not pending:
                break
            fin, pending = wait(pending, return_when=FIRST_COMPLETED)
            for f in fin:
                done_n += 1
                try:
                    cid, st = f.result()
                except Exception as e:
                    cid, st = '?', f'ERR {e}'
                print(f'[{done_n}] {st} {cid}', flush=True)
    left = len(todo) - done_n
    print(f'XONG lượt này: {done_n} clip, còn lại {left}', flush=True)
