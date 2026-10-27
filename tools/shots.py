#!/usr/bin/env python3
"""Footage Logging — đo chi tiết theo TỪNG CẢNH (shot) trong clip.

Chạy sau analyze.py (đọc _SOCIAL/analysis/clips/*.json để biết đường dẫn, proxy, loại thiết bị).

  python3 shots.py <dự án> [--only POV "01_SOURCE/Day 2"] [--budget 135] [--workers 4] [--force]
  python3 shots.py <dự án> --mics            # chỉ dò file mic rời (WAV) khớp giờ với từng clip
  python3 shots.py <dự án> --takes           # gom nhóm take giống nhau, chọn take tốt nhất

Mỗi clip → _SOCIAL/analysis/shots/<id>.json + sheets2/<id>.jpg (contact sheet có chú thích)
          + kf/<id>__sNN.jpg (lưới 2×2 khung của từng cảnh, cho AI local/Claude xem).

Đo gì (mọi giá trị đều là MÁY ĐOÁN, có trường *_conf; Claude/AI local xác nhận ở bước sau):
  - Chia cảnh: cắt cứng (histogram), trôi cảnh (POV đi sang chỗ khác), cảnh dài >20s chia nhỏ.
  - Optical flow (Farneback) → mô hình tương tự: tịnh tiến tx/ty, tỉ lệ (zoom/tiến lùi), xoay,
    phần dư sau mô hình (thị sai) → phân biệt pan/tilt (ít thị sai) với truck/dolly (nhiều thị sai),
    zoom (tỉ lệ đều) với dolly in/out (tỉ lệ + thị sai). Độ giật cao tần → chân máy / gimbal / cầm tay.
  - Mặt người + dáng người (mediapipe) → số người, cỡ cảnh, vị trí chủ thể, headroom, crop 9:16.
  - Nét: vùng chủ thể so với rìa (DOF nông/sâu), dao động nét khi máy đứng yên (focus hunting),
    nét sau/lệch nét (mặt mờ hơn nền), nhoè do chuyển động.
  - Phơi sáng, vùng cháy/sập, flicker (dao động sáng có chu kỳ), nhiễu (Immerkær), ám màu (Lab),
    vật cản rìa khung (vành mũ, tay), profile màu (S-Log3/HLG/Rec709 từ metadata).
  - Âm thanh: mức, clip đỉnh, gió (năng lượng <150Hz), đoán có nhạc, có thoại (theo transcript).
  - Metadata: fps quay (slow-mo), gamma, model máy, ống kính iPhone, GPS.
  - Điểm kỹ thuật 0–10 và điểm "đáng chú ý" (máy) — điểm nội dung cuối cùng do Claude chấm.
"""
import argparse, glob, json, math, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone
import numpy as np
import cv2

FPS = 5          # khung/giây phân tích
GW = 320         # rộng ảnh xám cho optical flow
CW = 480         # rộng ảnh màu cho mặt người / nét / màu
SEG_MAX = 20.0   # cảnh dài hơn thì chia nhỏ (giây)
VERSION = 4

# Ngưỡng — chỉnh bằng calibrate.py (ghi đè từ tools/thresholds.json nếu có)
TH = {
    'jit_tripod': 0.0018, 'jit_smooth': 0.0055, 'jit_hand': 0.016,
    'move_min': 0.012,       # |tịnh tiến| (phần bề rộng khung / giây) dưới mức này coi như đứng yên
    'zoom_min': 0.010,       # |tỉ lệ| / giây
    'parallax_hi': 0.30,     # thị sai / chuyển động > ngưỡng → truck/dolly thay vì pan/tilt
    'speed_slow': 0.06, 'speed_fast': 0.25,
    'dark': 38, 'blown': 0.25, 'sharp_low': 25,
    'noise_hi': 6.0, 'noise_mid': 3.5,
    'cast': 7.0,
    'size_face': [0.45, 0.22, 0.13, 0.075, 0.035, 0.012],   # chiều cao mặt / chiều cao khung: ECU, CU, MCU, MS, MWS, WS
}
_thf = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'thresholds.json')
if os.path.exists(_thf):
    try:
        TH.update(json.load(open(_thf)))
    except Exception:
        pass

SIZE_LABELS = ['đặc tả (ECU)', 'cận (CU)', 'cận trung (MCU)', 'trung (MS)', 'toàn trung (MWS)', 'toàn (WS)', 'đại cảnh (EWS)']


def sh(cmd, binary=False):
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout if binary else r.stdout.decode('utf-8', 'ignore')


def probe(path):
    try:
        return json.loads(sh(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path]))
    except Exception:
        return {}


# ---------------------------------------------------------------- metadata

_XML = {}


def XML_INDEX(project):
    """Sony sidecar <tên>M01.XML có thể nằm ở PRIVATE/M4ROOT/CLIP trong khi MP4 đã chép ra ngoài."""
    if project not in _XML:
        idx = {}
        for root, dirs, files in os.walk(project):
            dirs[:] = [d for d in dirs if not d.startswith(('.', '_SOCIAL'))]
            for f in files:
                if f.startswith('._'):
                    continue
                m = re.match(r'(.+)M01\.XML$', f, re.I)
                if m:
                    idx.setdefault(m.group(1).upper(), []).append(os.path.join(root, f))
        _XML[project] = idx
    return _XML[project]

def read_meta(project, clip):
    path = os.path.join(project, clip['path'])
    p = probe(path)
    fmt = p.get('format', {}); tags = fmt.get('tags', {}) or {}
    vs = [s for s in p.get('streams', []) if s.get('codec_type') == 'video']
    v = vs[0] if vs else {}
    m = {'model': tags.get('com.apple.quicktime.model') or None, 'codec': v.get('codec_name'),
         'transfer': v.get('color_transfer'), 'primaries': v.get('color_primaries'),
         'res': f"{clip.get('width')}x{clip.get('height')}"}
    try:
        a, b = (v.get('avg_frame_rate') or v.get('r_frame_rate') or '0/1').split('/')
        m['fps'] = round(float(a) / float(b), 3) if float(b) else None
    except Exception:
        m['fps'] = None
    base = os.path.splitext(path)[0]
    stem = os.path.basename(base)
    for x in [base + 'M01.XML', base + 'M01.xml'] + XML_INDEX(project).get(stem.upper(), []):
        if os.path.exists(x):
            t = open(x, errors='ignore').read()
            g = re.search(r'captureFps="([\d.]+)', t); f = re.search(r'formatFps="([\d.]+)', t)
            gm = re.search(r'CaptureGammaEquation" value="([^"]+)', t)
            md = re.search(r'modelName="([^"]+)', t)
            m['capture_fps'] = float(g.group(1)) if g else None
            m['format_fps'] = float(f.group(1)) if f else None
            m['gamma'] = gm.group(1) if gm else None
            m['model'] = md.group(1) if md else m['model']
            break
    lens = tags.get('com.apple.quicktime.camera.lens_model')
    if lens:
        m['lens'] = lens
    fl = tags.get('com.apple.quicktime.camera.focal_length.35mm_equivalent')
    if fl:
        m['focal_35mm'] = fl
    if clip.get('gps'):
        m['gps'] = clip['gps']
    # profile màu
    gam = (m.get('gamma') or '').lower()
    if 's-log3' in gam or 'slog3' in gam:
        m['profile'] = 'S-Log3 (cần delog)'
    elif 'hlg' in gam or m.get('transfer') == 'arib-std-b67':
        m['profile'] = 'HLG (HDR)'
    elif m.get('transfer') == 'smpte2084':
        m['profile'] = 'PQ (HDR)'
    elif clip.get('kind') == 'POV':
        m['profile'] = 'Rec709 (Ray-Ban)'
    else:
        m['profile'] = 'Rec709'
    # slow-mo
    cf = m.get('capture_fps') or m.get('fps') or 0
    ff = m.get('format_fps') or m.get('fps') or 0
    if cf and ff and cf > ff * 1.5:
        m['speed'] = f'slow-mo trong máy ({cf:g}→{ff:g}p)'
    elif cf >= 47:
        m['speed'] = f'{cf:g}p — làm chậm {cf / 25 if cf < 55 else cf / 30:.0f}x được trên timeline 25/30p'
    else:
        m['speed'] = 'thời gian thực'
    return m


# ---------------------------------------------------------------- flow

def flow_model(prev, cur):
    """Optical flow → (tx, ty, scale, rot, resid, outlier_frac, outlier_mag, texture) theo đơn vị bề rộng khung."""
    fl = cv2.calcOpticalFlowFarneback(prev, cur, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    h, w = prev.shape
    step = 8
    ys, xs = np.mgrid[step // 2:h:step, step // 2:w:step]
    u = fl[ys, xs, 0].ravel() / w; v = fl[ys, xs, 1].ravel() / w
    gx = cv2.Sobel(prev, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(prev, cv2.CV_32F, 0, 1, ksize=3)
    g = np.hypot(gx, gy)[ys, xs].ravel()
    tex = g > 20
    texture = float(tex.mean())
    X = (xs.ravel() - w / 2) / w; Y = (ys.ravel() - h / 2) / w
    if tex.sum() < 40:
        return dict(tx=0, ty=0, s=0, r=0, resid=0, out=0, outmag=0, tex=texture, ok=False)
    m = tex.copy()
    for _ in range(3):
        n = m.sum()
        A = np.zeros((2 * n, 4), np.float32)
        A[:n, 0] = 1; A[:n, 2] = X[m]; A[:n, 3] = -Y[m]
        A[n:, 1] = 1; A[n:, 2] = Y[m]; A[n:, 3] = X[m]
        bvec = np.concatenate([u[m], v[m]])
        sol, *_ = np.linalg.lstsq(A, bvec, rcond=None)
        tx, ty, s, r = sol
        pu = tx + s * X - r * Y; pv = ty + s * Y + r * X
        res = np.hypot(u - pu, v - pv)
        med = np.median(res[m]) + 1e-6
        newm = tex & (res < max(3 * med, 0.004))
        if newm.sum() < 40 or (newm == m).all():
            break
        m = newm
    inl = m; outl = tex & ~m
    return dict(tx=float(tx), ty=float(ty), s=float(s), r=float(r),
                resid=float(np.median(res[inl])) if inl.any() else 0.0,
                out=float(outl.sum() / max(1, tex.sum())), outmag=float(np.mean(res[outl])) if outl.any() else 0.0,
                tex=texture, ok=True)


# ---------------------------------------------------------------- per-frame measures

def noise_sigma(gray):
    """Immerkær — ước lượng độ nhiễu (đơn vị mức xám)."""
    M = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    h, w = gray.shape
    conv = cv2.filter2D(gray.astype(np.float32), -1, M)
    edges = cv2.Canny(gray, 60, 150)
    mask = cv2.dilate(edges, np.ones((5, 5), np.uint8)) == 0
    if mask.sum() < 1000:
        return None
    return float(math.sqrt(math.pi / 2) * np.abs(conv[mask]).mean() / 6)


def region_sharp(gray, box):
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    roi = gray[y0:y1, x0:x1]
    if roi.size < 400:
        return None
    return float(cv2.Laplacian(roi, cv2.CV_64F).var())


class People:
    def __init__(self):
        import logging
        os.environ.setdefault('GLOG_minloglevel', '3')
        logging.getLogger('absl').setLevel(logging.ERROR)
        import mediapipe as mp
        self.fd = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.55)
        self.pose = mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1, min_detection_confidence=0.5)

    def __call__(self, bgr):
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = bgr.shape[:2]
        faces = []
        r = self.fd.process(rgb)
        for d in (r.detections or []):
            b = d.location_data.relative_bounding_box
            faces.append(dict(x=max(0, b.xmin), y=max(0, b.ymin), w=b.width, h=b.height, score=round(float(d.score[0]), 2)))
        faces.sort(key=lambda f: -f['h'])
        body = None
        p = self.pose.process(rgb)
        if p.pose_landmarks:
            L = p.pose_landmarks.landmark
            vis = [(l.x, l.y) for l in L if l.visibility > 0.5]
            if len(vis) >= 6:
                xs = [a for a, _ in vis]; ys = [b for _, b in vis]
                ankles = sum(1 for i in (27, 28) if L[i].visibility > 0.5)
                hips = sum(1 for i in (23, 24) if L[i].visibility > 0.5)
                knees = sum(1 for i in (25, 26) if L[i].visibility > 0.5)
                body = dict(x0=min(xs), x1=max(xs), y0=min(ys), y1=max(ys), ankles=ankles, knees=knees, hips=hips,
                            nose_vis=L[0].visibility > 0.5)
        return faces, body


def shot_size(faces, body, frame_h_ratio=1.0):
    """Cỡ cảnh từ chiều cao mặt (so với chiều cao khung) hoặc phần thân thấy được (lấy cỡ rộng hơn)."""
    fs = _size_face(faces)
    bs = _size_body(body)
    if fs[0] is None:
        return bs
    if bs[0] is not None and bs[0] > fs[0] and body.get('ankles'):
        return bs[0], max(fs[1], bs[1])
    return fs


def _size_body(body):
    if not body:
        return None, 0.0
    span = body['y1'] - body['y0']
    if body['ankles']:
        if span < 0.18: return 6, 0.5
        if span < 0.55: return 5, 0.55
        return 4, 0.55
    if body['knees']: return 4, 0.45
    if body['hips']: return 3, 0.45
    return 2, 0.35


def _size_face(faces):
    if faces:
        fh = faces[0]['h']
        conf = [0.8, 0.8, 0.75, 0.7, 0.6, 0.55]
        for k, th in enumerate(TH['size_face']):
            if fh > th:
                return k, conf[k]
        return 6, 0.4
    return None, 0.0


# ---------------------------------------------------------------- audio

def audio_analysis(src, dur):
    raw = sh(['ffmpeg', '-v', 'error', '-i', src, '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], binary=True)
    if not raw:
        return None
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 8000  # 0.5s
    n = len(a) // hop
    if n == 0:
        return None
    out = dict(db=[], clip=[], wind=[], music=[])
    win = 1024
    freqs = np.fft.rfftfreq(win, 1 / 16000)
    lowb = freqs < 150
    prev_peaks = None
    for i in range(n):
        seg = a[i * hop:(i + 1) * hop]
        rms = math.sqrt(float((seg ** 2).mean()) + 1e-12)
        out['db'].append(round(20 * math.log10(rms + 1e-9), 1))
        out['clip'].append(int((np.abs(seg) > 0.985).sum()))
        frames = seg[: len(seg) // win * win].reshape(-1, win) * np.hanning(win)
        S = np.abs(np.fft.rfft(frames, axis=1)) ** 2 + 1e-12
        tot = S.sum(1)
        out['wind'].append(round(float(np.median(S[:, lowb].sum(1) / tot)), 2))
        # nhạc: phổ có các đỉnh bền giữa các frame + độ phẳng phổ thấp
        flat = np.exp(np.log(S).mean(1)) / S.mean(1)
        pk = [set(np.argsort(f[8:200])[-6:]) for f in S]
        keep = [len(pk[j] & pk[j - 1]) / 6 for j in range(1, len(pk))]
        out['music'].append(round(float(np.mean(keep)) * float(np.mean(flat < 0.05)), 2))
    return out


def transcript_spans(project, cid):
    f = os.path.join(project, '_SOCIAL', 'analysis', 'transcripts', cid + '.json')
    if not os.path.exists(f):
        return []
    try:
        d = json.load(open(f))
        return [(s['start'], s['end'], s.get('text', ''), s.get('lang')) for s in d.get('segments', [])]
    except Exception:
        return []


# ---------------------------------------------------------------- main per clip

def decode_stream(src, width, ss=None, tt=None):
    p = probe(src)
    vs = [s for s in p.get('streams', []) if s.get('codec_type') == 'video']
    if not vs:
        return None, None, None
    w0, h0 = vs[0]['width'], vs[0]['height']
    rot = 0
    for sd in vs[0].get('side_data_list', []) or []:
        if 'rotation' in sd:
            rot = abs(int(sd['rotation']))
    if rot in (90, 270):
        w0, h0 = h0, w0
    h = int(round(width * h0 / w0 / 2) * 2)
    cmd = ['ffmpeg', '-v', 'error', '-skip_loop_filter', 'all', '-flags2', '+fast'] + \
          (['-ss', f'{ss:.3f}'] if ss else []) + (['-t', f'{tt:.3f}'] if tt else []) + ['-i', src,
           '-vf', f'fps={FPS},scale={width}:{h}', '-pix_fmt', 'bgr24', '-f', 'rawvideo', '-']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=width * h * 3 * 4)
    return proc, width, h


def hist(gray):
    hh = cv2.calcHist([gray], [0], None, [32], [0, 256]).ravel()
    return hh / (hh.sum() + 1e-9)


CHUNK = 45.0
_PEOPLE = None
CACHE = os.path.expanduser('~/.tls_cache/shots')


def chunk_path(cid, k):
    return os.path.join(CACHE, f'{cid}_v{VERSION}_{k:03d}.pkl')


def n_chunks(clip):
    return max(1, int(math.ceil((clip.get('duration') or 1) / CHUNK)))


def process_chunk(project, clip, k):
    """Giải mã + đo một khúc CHUNK giây của clip, lưu tạm vào ~/.tls_cache (máy ảo)."""
    import pickle
    cid = clip['id']
    src = os.path.join(project, clip.get('proxy') or clip['path'])
    t_off = k * CHUNK
    proc, W, H = decode_stream(src, CW, ss=t_off, tt=CHUNK)
    if proc is None:
        return 'no-video'
    global _PEOPLE
    if _PEOPLE is None:            # một bộ nhận diện cho mỗi tiến trình (tạo lại mỗi khúc làm rò bộ nhớ → sập)
        _PEOPLE = People()
    people = _PEOPLE
    fb = W * H * 3
    frames_meta, keep = [], {}
    prev_g = prev_h = None
    i0 = int(round(t_off * FPS))
    i = 0
    while True:
        buf = proc.stdout.read(fb)
        if len(buf) < fb:
            break
        gi = i0 + i
        bgr = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        gray_c = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(gray_c, (GW, int(round(GW * H / W))), interpolation=cv2.INTER_AREA)
        hh = hist(g)
        fm = dict(t=round(gi / FPS, 2), luma=float(gray_c.mean()), blown=float((gray_c > 245).mean()),
                  crush=float((gray_c < 12).mean()), sharp=float(cv2.Laplacian(g, cv2.CV_64F).var()))
        fm['hd'] = float(0.5 * np.abs(hh - prev_h).sum()) if prev_h is not None else 0.0
        if prev_g is not None:
            fm.update(flow_model(prev_g, g))
        else:
            fm.update(dict(tx=0, ty=0, s=0, r=0, resid=0, out=0, outmag=0, tex=0, ok=False))
        # mỗi giây: người, nét vùng, nhiễu, màu
        if gi % FPS == 0:
            faces, body = people(bgr)
            fm['faces'] = faces; fm['body'] = body
            if faces:
                f0 = faces[0]
                box = (f0['x'] * W, f0['y'] * H, (f0['x'] + f0['w']) * W, (f0['y'] + f0['h']) * H)
            elif body:
                box = (body['x0'] * W, body['y0'] * H, body['x1'] * W, body['y1'] * H)
            else:
                box = (W / 3, H / 3, 2 * W / 3, 2 * H / 3)
            fm['subj_sharp'] = region_sharp(gray_c, box)
            bw = int(W * 0.12)
            fm['edge_sharp'] = float(cv2.Laplacian(np.concatenate([gray_c[:, :bw], gray_c[:, -bw:]], 1), cv2.CV_64F).var())
            fm['noise'] = noise_sigma(gray_c)
            lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
            mid = (lab[:, 0] > 40) & (lab[:, 0] < 215)
            if mid.sum() > 500:
                fm['a'] = float(lab[mid, 1].mean() - 128); fm['b'] = float(lab[mid, 2].mean() - 128)
            fm['sat'] = float(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 1].mean())
            # vật cản rìa trên/dưới: dải 15% tối + phẳng so với phần giữa
            bh = int(H * 0.15)
            top, botm, midb = gray_c[:bh], gray_c[-bh:], gray_c[bh:-bh]
            def flatness(x): return float(cv2.Laplacian(x, cv2.CV_64F).var())
            ms = flatness(midb) + 1e-6
            fm['occ_top'] = (top.mean() < midb.mean() * 0.55 and flatness(top) < 0.25 * ms)
            fm['occ_bot'] = (botm.mean() < midb.mean() * 0.55 and flatness(botm) < 0.25 * ms)
            keep[gi] = cv2.resize(bgr, (320, int(320 * H / W)), interpolation=cv2.INTER_AREA)
        frames_meta.append(fm)
        prev_g, prev_h = g, hh
        i += 1
    proc.wait()
    os.makedirs(CACHE, exist_ok=True)
    keep = {k_: cv2.imencode('.jpg', v_, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes() for k_, v_ in keep.items()}   # nén để file tạm nhỏ
    pickle.dump(dict(W=W, H=H, frames=frames_meta, keep=keep), open(chunk_path(cid, k) + '.tmp', 'wb'))
    os.replace(chunk_path(cid, k) + '.tmp', chunk_path(cid, k))
    return f'khúc {k + 1}/{n_chunks(clip)}'


def assemble(project, clip, outdir):
    """Ghép các khúc → chia cảnh, tổng hợp, vẽ sheet, ghi shots/<id>.json."""
    import pickle
    cid = clip['id']
    oj = os.path.join(outdir, 'shots', cid + '.json')
    kind = clip.get('kind', 'CAM')
    meta = read_meta(project, clip)
    src = os.path.join(project, clip.get('proxy') or clip['path'])
    frames_meta, keep = [], {}
    for k in range(n_chunks(clip)):
        d = pickle.load(open(chunk_path(cid, k), 'rb'))
        frames_meta += d['frames']
        keep.update({k_: (cv2.imdecode(np.frombuffer(v_, np.uint8), 1) if isinstance(v_, bytes) else v_) for k_, v_ in d['keep'].items()})
    n = len(frames_meta)
    if n < 3:
        json.dump(dict(id=cid, version=VERSION, error='decode-failed', segments=[]), open(oj, 'w'), ensure_ascii=False)
        return cid, 'decode-failed'
    if clip.get('device') == 'sony' and not meta.get('gamma'):
        sat = med([f.get('sat') for f in frames_meta if 'sat' in f], 99)
        lum = np.array([f['luma'] for f in frames_meta])
        crush = med([f['crush'] for f in frames_meta], 0)
        if sat < 55 and crush < 0.01 and 40 < lum.mean() < 170:
            meta['profile'] = 'có thể S-Log3 (không có XML; ảnh nhạt, không có vùng đen)'
    au = audio_analysis(src, n / FPS) if clip.get('has_audio') else None
    tx_spans = transcript_spans(project, cid)

    # --- chia cảnh: cắt cứng (khác biệt histogram liên tiếp) hoặc trôi tích luỹ (POV đi sang chỗ khác)
    starts = [0]
    reasons = ['đầu clip']
    drift = 0.0
    for k in range(1, n):
        hd = frames_meta[k]['hd']
        drift += hd
        if hd > 0.45 and k - starts[-1] >= FPS:
            starts.append(k); reasons.append('cắt cảnh'); drift = 0
        elif drift > 3.5 and (k - starts[-1]) / FPS >= 6:
            starts.append(k); reasons.append('đổi bối cảnh'); drift = 0
    bounds = []
    for j, s0 in enumerate(starts):
        e0 = starts[j + 1] if j + 1 < len(starts) else n
        L = (e0 - s0) / FPS
        if L > SEG_MAX:
            parts = int(math.ceil(L / 15.0))
            step = (e0 - s0) / parts
            for q in range(parts):
                a = int(round(s0 + q * step)); b = int(round(s0 + (q + 1) * step))
                bounds.append((a, b, reasons[j] if q == 0 else 'chia đoạn dài'))
        else:
            bounds.append((s0, e0, reasons[j]))
    # gộp đoạn quá ngắn (<1.5s) vào đoạn trước
    merged = []
    for a, b, rs in bounds:
        if merged and (b - a) / FPS < 1.5:
            merged[-1] = (merged[-1][0], b, merged[-1][2])
        else:
            merged.append((a, b, rs))

    segs = []
    for si, (a, b, reason) in enumerate(merged):
        segs.append(summarize(si, a, b, reason, frames_meta, kind, meta, au, tx_spans, clip))
    res = dict(id=cid, version=VERSION, path=clip['path'], proxy=clip.get('proxy'), kind=kind, device=clip.get('device'),
               created=clip.get('created'), duration=round(n / FPS, 2), meta=meta, segments=segs)
    # contact sheet có chú thích + lưới khung từng cảnh
    os.makedirs(os.path.join(outdir, 'sheets2'), exist_ok=True)
    os.makedirs(os.path.join(outdir, 'kf'), exist_ok=True)
    draw_sheet(res, frames_meta, keep, os.path.join(outdir, 'sheets2', cid + '.jpg'))
    for s in segs:
        p = os.path.join(outdir, 'kf', f"{cid}__s{s['i']:02d}.jpg")
        kf_grid(s, keep, p)
        s['kf'] = os.path.relpath(p, outdir)
    res['sheet'] = os.path.join('sheets2', cid + '.jpg')
    json.dump(res, open(oj, 'w'), ensure_ascii=False, indent=1)
    for k in range(n_chunks(clip)):   # xoá file tạm (máy ảo chỉ ~10GB)
        try:
            os.remove(chunk_path(cid, k))
        except OSError:
            pass
    return cid, f'ok {len(segs)} cảnh'


def med(xs, default=0.0):
    xs = [x for x in xs if x is not None]
    return float(np.median(xs)) if xs else default


def summarize(si, a, b, reason, F, kind, meta, au, tx_spans, clip):
    seg = F[a:b]
    t0, t1 = round(a / FPS, 2), round(b / FPS, 2)
    dur = t1 - t0
    ok = [f for f in seg if f.get('ok')]
    tx = np.array([f['tx'] for f in ok]) if ok else np.zeros(1)
    ty = np.array([f['ty'] for f in ok]) if ok else np.zeros(1)
    ss = np.array([f['s'] for f in ok]) if ok else np.zeros(1)
    rr = np.array([f['r'] for f in ok]) if ok else np.zeros(1)
    # tốc độ / giây
    vtx, vty, vs = float(np.median(tx)) * FPS, float(np.median(ty)) * FPS, float(np.median(ss)) * FPS
    mov = math.hypot(vtx, vty)
    # độ giật cao tần
    k = 5
    if len(tx) > k:
        ker = np.ones(k) / k
        jx = tx - np.convolve(tx, ker, 'same'); jy = ty - np.convolve(ty, ker, 'same')
        jit = float(np.median(np.hypot(jx, jy)[2:-2])) if len(tx) > 6 else float(np.median(np.hypot(jx, jy)))
        jit_p90 = float(np.percentile(np.hypot(jx, jy), 90))
        rj = float(np.median(np.abs(rr - np.convolve(rr, ker, 'same'))))
    else:
        jit, jit_p90, rj = 0.0, 0.0, 0.0
    resid = med([f['resid'] for f in ok])
    parallax = max(0.0, resid * FPS - 0.006) / (mov + abs(vs) + 1e-4) if (mov + abs(vs)) > 0.025 else 0.0
    outfrac = med([f['out'] for f in ok])
    texture = med([f['tex'] for f in ok])
    # độ đều vận tốc (slider/dolly rất đều)
    if len(tx) > 5 and mov > TH['move_min']:
        sp = np.hypot(tx, ty)
        evenness = float(1 - min(1, np.std(sp) / (np.mean(sp) + 1e-6)))
    else:
        evenness = 0.0

    # --- rig
    if kind == 'POV':
        rig, rig_conf = 'POV kính (đầu người)', 0.9
    elif kind == 'ACTION':
        rig, rig_conf = 'action cam', 0.7
    elif jit < TH['jit_tripod'] and mov < TH['move_min'] and abs(vs) < TH['zoom_min']:
        rig, rig_conf = 'chân máy (tĩnh)', 0.8
    elif jit < TH['jit_smooth']:
        if mov >= TH['move_min'] and evenness > 0.75 and dur < 20:
            rig, rig_conf = 'slider/dolly', 0.5
        elif mov < TH['move_min'] and abs(vs) < TH['zoom_min']:
            rig, rig_conf = 'chân máy / gimbal đứng', 0.55
        else:
            rig, rig_conf = 'gimbal', 0.6
    elif jit < TH['jit_hand']:
        rig, rig_conf = 'cầm tay', 0.65
    else:
        rig, rig_conf = 'cầm tay (rung)', 0.7
    if kind == 'PHONE' and rig.startswith('gimbal'):
        rig = 'điện thoại (chống rung/gimbal)'

    # --- chuyển động máy (hướng máy = ngược hướng nội dung trôi)
    moves = []
    if abs(vs) >= TH['zoom_min'] and abs(vs) * 1.0 >= mov * 0.6:
        d = 'tiến vào' if vs > 0 else 'lùi ra'
        if kind in ('POV', 'ACTION'):
            moves.append(('đi tới' if vs > 0 else 'lùi lại', ''))
        elif parallax > TH['parallax_hi'] or kind == 'PHONE':
            moves.append(('push in' if vs > 0 else 'pull out', d))
        else:
            moves.append(('zoom in' if vs > 0 else 'zoom out', d))
    if mov >= TH['move_min']:
        horiz = abs(vtx) >= abs(vty)
        if horiz:
            d = 'sang trái' if vtx > 0 else 'sang phải'
            name = 'truck ngang' if parallax > TH['parallax_hi'] and kind not in ('POV',) else 'pan'
        else:
            d = 'lên' if vty > 0 else 'xuống'
            name = 'pedestal/crane' if parallax > TH['parallax_hi'] and kind not in ('POV', 'PHONE', 'ACTION') else 'tilt'
        if kind == 'POV':
            name = {'pan': 'quay đầu (pan)', 'tilt': 'cúi/ngẩng (tilt)'}.get(name, name)
        # bám chủ thể: có người ổn định vị trí trong khi nền trôi
        subj_x = [ (f['faces'][0]['x'] + f['faces'][0]['w'] / 2) if f.get('faces') else ((f['body']['x0'] + f['body']['x1']) / 2 if f.get('body') else None) for f in seg if 'faces' in f]
        subj_x = [x for x in subj_x if x is not None]
        if len(subj_x) >= max(2, 0.6 * max(1, len([f for f in seg if 'faces' in f]))) and np.std(subj_x) < 0.08 and mov > 0.03:
            name = 'bám theo (follow)' if parallax <= 0.6 else 'bám theo / orbit'
        moves.append((name, d))
    if not moves:
        moves.append(('tĩnh', ''))
    if abs(float(np.median(rr))) * FPS > 0.03:
        moves.append(('xoay (roll)', 'trái' if np.median(rr) > 0 else 'phải'))
    speed = max(mov, abs(vs))
    spd = 'đứng yên' if moves[0][0] == 'tĩnh' else ('chậm' if speed < TH['speed_slow'] else 'vừa' if speed < TH['speed_fast'] else 'nhanh')
    move_conf = 0.75 if moves[0][0] in ('tĩnh', 'pan', 'tilt') else 0.5
    if texture < 0.08:
        move_conf = 0.25

    # --- người / cỡ cảnh / bố cục
    pf = [f for f in seg if 'faces' in f]
    sizes, confs, nfaces, npers, sx, head = [], [], [], [], [], []
    looks = 0
    for f in pf:
        sz, c = shot_size(f['faces'], f['body'])
        if sz is not None:
            sizes.append(sz); confs.append(c)
        nfaces.append(len(f['faces'])); npers.append(max(len(f['faces']), 1 if f['body'] else 0))
        if f['faces']:
            f0 = f['faces'][0]
            sx.append(f0['x'] + f0['w'] / 2); head.append(f0['y'])
            looks += 1 if f0['score'] > 0.8 and f0['w'] > 0.04 else 0
        elif f['body']:
            sx.append((f['body']['x0'] + f['body']['x1']) / 2)
    size = SIZE_LABELS[int(round(np.median(sizes)))] if sizes else None
    size_conf = round(float(np.mean(confs)), 2) if confs else 0.0
    people_n = int(round(np.percentile(npers, 75))) if npers else 0
    subj_x = float(np.median(sx)) if sx else None
    third = None
    if subj_x is not None:
        third = '1/3 trái' if subj_x < 0.4 else ('1/3 phải' if subj_x > 0.6 else 'giữa')
    headroom = None
    if head:
        h0 = float(np.median(head))
        headroom = 'thiếu (sát mép trên)' if h0 < 0.03 else ('thừa' if h0 > 0.35 and size in SIZE_LABELS[:3] else 'ổn')
    # crop 9:16 cho khung ngang
    crop = None
    W_, H_ = clip.get('width') or 16, clip.get('height') or 9
    if W_ > H_:
        frac = (H_ * 9 / 16) / W_
        if sx:
            lo, hi = float(np.percentile(sx, 10)), float(np.percentile(sx, 90))
            fits = (hi - lo) <= frac * 0.9
            fx = min(max((subj_x - frac / 2) / (1 - frac), 0), 1)
            crop = dict(ok=bool(fits), focus_x=round(fx, 2), note='chủ thể nằm gọn trong khung dọc' if fits else 'chủ thể dàn rộng, crop dọc sẽ mất người — dùng fit blur/2 thẻ')
        else:
            crop = dict(ok=None, focus_x=0.5, note='không có người — Claude chọn điểm crop')

    # --- nét
    subj = [f['subj_sharp'] for f in pf if f.get('subj_sharp')]
    edge = [f['edge_sharp'] for f in pf if f.get('edge_sharp')]
    sharp_series = np.array([f['sharp'] for f in seg])
    dof = None
    if kind in ('POV', 'ACTION'):
        dof = 'sâu (ống góc rộng)'      # kính/action cam nét sâu cố định; chênh nét tâm–rìa chỉ do méo/vignette
    elif subj and edge:
        ratio = med(subj) / (med(edge) + 1e-6)
        dof = 'nông (xoá phông)' if ratio > 2.5 else ('sâu' if ratio < 1.4 else 'vừa')
    focus = []
    if pf and any(f['faces'] for f in pf):
        fs = [f['subj_sharp'] for f in pf if f['faces'] and f['faces'][0]['h'] > 0.12 and f.get('subj_sharp')]
        es = [f['edge_sharp'] for f in pf if f['faces'] and f['faces'][0]['h'] > 0.12 and f.get('edge_sharp')]
        if len(fs) >= 2 and med(fs) < 0.3 * med(es) and med(es) > 80:
            focus.append('lệch nét (mặt mờ hơn nền)')
    if moves[0][0] == 'tĩnh' and len(sharp_series) > 10:
        cv = float(np.std(sharp_series) / (np.mean(sharp_series) + 1e-6))
        sign = np.sign(np.diff(sharp_series - np.convolve(sharp_series, np.ones(5) / 5, 'same')))
        flips = int((np.diff(sign) != 0).sum())
        if cv > 0.35 and flips > len(sharp_series) * 0.4:
            focus.append('focus hunting (nét dao động khi máy đứng yên)')
    blur_moving = [f for f in seg if f.get('ok') and f['sharp'] < TH['sharp_low'] and math.hypot(f['tx'], f['ty']) * FPS > 0.15]
    if len(blur_moving) > 0.3 * len(seg):
        focus.append('nhoè do chuyển động')
    lowsharp = float(np.mean(sharp_series < TH['sharp_low']))
    if lowsharp > 0.5 and not blur_moving:
        focus.append('mờ / out nét')
    sharp_label = 'nét' if not focus else '; '.join(focus)

    # --- ổn định
    if kind == 'POV':
        stab = 'ổn định' if jit < 0.012 else ('rung nhẹ (POV chấp nhận được)' if jit < 0.03 else 'rung nặng')
    else:
        stab = 'ổn định' if jit < TH['jit_smooth'] else ('rung nhẹ' if jit < TH['jit_hand'] else 'rung nặng')
    whip = sum(1 for f in seg if f.get('ok') and math.hypot(f['tx'], f['ty']) * FPS > (0.9 if kind in ('POV', 'ACTION') else 0.6))
    if whip >= 2:
        stab += f'; lia gắt {whip / FPS:.1f}s'
    if jit_p90 > 0.04 and speed > 0.2 and kind != 'POV':
        stab += '; nguy cơ jello (rolling shutter)'

    # --- phơi sáng / màu / nhiễu / flicker / vật cản
    luma = np.array([f['luma'] for f in seg]); blown = med([f['blown'] for f in seg]); crush = med([f['crush'] for f in seg])
    L = float(luma.mean())
    log_like = 'S-Log' in (meta.get('profile') or '')
    if log_like:
        exp = 'log (đánh giá sau delog)' if 25 < L < 200 else ('thiếu sáng' if L <= 25 else 'thừa sáng')
    else:
        exp = 'thiếu sáng' if L < TH['dark'] else ('thừa sáng' if L > 200 or blown > TH['blown'] else 'chuẩn')
    if blown > 0.08: exp += f'; cháy {blown * 100:.0f}%'
    if crush > 0.15: exp += f'; sập đen {crush * 100:.0f}%'
    flicker = False
    if moves[0][0] == 'tĩnh' and len(luma) >= 20:
        d = luma - np.convolve(luma, np.ones(9) / 9, 'same')
        spec = np.abs(np.fft.rfft(d[4:-4]))
        if len(spec) > 4 and spec[2:].max() > 6 * (np.median(spec[2:]) + 1e-6) and np.std(d[4:-4]) > 0.012 * L:
            flicker = True
    nz = med([f.get('noise') for f in pf], None)
    noise = None if nz is None else ('cao' if nz > TH['noise_hi'] else 'vừa' if nz > TH['noise_mid'] else 'thấp')
    aa, bb = med([f.get('a') for f in pf], 0), med([f.get('b') for f in pf], 0)
    cast = None
    if not log_like:
        if bb > TH['cast'] and bb > abs(aa): cast = 'ám vàng/ấm'
        elif bb < -TH['cast'] and -bb > abs(aa): cast = 'ám xanh/lạnh'
        elif aa > TH['cast']: cast = 'ám hồng/magenta'
        elif aa < -TH['cast']: cast = 'ám xanh lá'
    occ = []
    if pf and np.mean([f.get('occ_top', False) for f in pf]) > 0.6: occ.append('vật cản rìa trên (vành mũ/tóc?)')
    if pf and np.mean([f.get('occ_bot', False) for f in pf]) > 0.6: occ.append('vật cản rìa dưới (tay/đồ vật?)')

    # --- âm thanh
    aud = None
    if au:
        i0, i1 = int(t0 * 2), max(int(t0 * 2) + 1, int(t1 * 2))
        db = au['db'][i0:i1] or [-90]
        clipn = sum(au['clip'][i0:i1]); wind = med(au['wind'][i0:i1]); mus = med(au['music'][i0:i1])
        speech = [x for x in tx_spans if x[1] > t0 and x[0] < t1 and not re.search(r'[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]', x[2])]
        loud = float(np.percentile(db, 80))
        kinds = []
        if speech: kinds.append('thoại')
        if mus > 0.5: kinds.append('có thể có nhạc nền')
        if loud > -45 and not speech: kinds.append('tiếng hiện trường')
        if loud <= -45: kinds.append('im lặng')
        issues = []
        if clipn > 20: issues.append('clip đỉnh (vỡ tiếng)')
        if wind > 0.55 and loud > -40: issues.append('gió/ù tần thấp')
        if speech and loud < -38: issues.append('thoại nhỏ')
        aud = dict(level_db=round(loud, 1), types=kinds, issues=issues,
                   speech=' / '.join(x[2] for x in speech)[:300] if speech else '',
                   lang=(speech[0][3] if speech else None), music_guess=round(mus, 2))
        # đỉnh âm thanh (cười, hét) — gợi ý highlight
        peaks = [round(t0 + (j / 2), 1) for j, x in enumerate(db) if x > loud + 8]
        aud['peaks'] = peaks[:5]

    # --- vùng dùng được trong cảnh, in/out đề xuất
    bad = []
    for f in seg:
        b_ = (f['luma'] < TH['dark'] and not log_like) or f['blown'] > TH['blown'] or f['sharp'] < TH['sharp_low'] * 0.6 or \
             (f.get('ok') and math.hypot(f['tx'], f['ty']) * FPS > (0.9 if kind in ('POV', 'ACTION') else 0.6))
        bad.append(b_)
    first = next((j for j, x in enumerate(bad) if not x), None)
    lastg = next((j for j in range(len(bad) - 1, -1, -1) if not bad[j]), None)
    in_, out_ = (round(t0 + first / FPS, 1), round(t0 + (lastg + 1) / FPS, 1)) if first is not None else (None, None)
    usable_ratio = 1 - float(np.mean(bad))

    # --- điểm kỹ thuật
    q = 10.0
    q -= 4 * (1 - usable_ratio)
    if 'rung nặng' in stab: q -= 2 if kind != 'POV' else 1
    elif 'rung nhẹ' in stab and kind not in ('POV', 'ACTION'): q -= 0.7
    if 'lia gắt' in stab: q -= 0.8
    if focus: q -= 1.5 if any('mờ' in x or 'lệch' in x for x in focus) else 0.8
    if 'thiếu' in exp or 'thừa' in exp: q -= 1.2
    if noise == 'cao': q -= 1
    if flicker: q -= 1
    if occ: q -= 1
    if aud and aud['issues']: q -= 0.5
    tech = round(max(0, min(10, q)), 1)
    # điểm đáng chú ý (máy) — gợi ý cho Claude, không phải điểm nội dung
    interest = 0.0
    if people_n: interest += 2
    if aud and 'thoại' in aud['types']: interest += 2.5
    if aud and aud['peaks']: interest += 1.5
    if outfrac > 0.15: interest += 1.5   # có vật/người chuyển động trong khung
    act = float(np.percentile([f['outmag'] * f['out'] for f in ok], 90)) * FPS if ok else 0.0
    if act > 0.02: interest += 1.5         # chuyển động lớn của vật thể (tàu chạy qua, người lao tới)
    if aud and aud.get('peaks') and aud['level_db'] > -35: interest += 1
    if size in SIZE_LABELS[:3]: interest += 1
    if moves[0][0] not in ('tĩnh',) and 'rung' not in stab: interest += 0.5
    interest = round(min(10, interest + tech * 0.15), 1)
    # khung đại diện: đầu, giữa, cuối + đỉnh chuyển động trong khung
    idx = [k for k in range(a, b) if k % FPS == 0]
    if not idx:
        idx = [a - a % FPS]
    pick = sorted(set([idx[0], idx[len(idx) // 2], idx[-1]] + ([max(idx, key=lambda k: F[k].get('out', 0))] if len(idx) > 3 else [])))[:4]
    return dict(i=si, start=t0, end=t1, dur=round(dur, 2), split=reason,
                rig=rig, rig_conf=rig_conf,
                move=', '.join(m[0] + (f' {m[1]}' if m[1] else '') for m in moves), move_speed=spd, move_conf=move_conf,
                size=size, size_conf=size_conf, people=people_n, subject_x=None if subj_x is None else round(subj_x, 2),
                composition=third, headroom=headroom, dof=dof, sharp=sharp_label, stability=stab,
                exposure=exp, flicker=flicker, noise=noise, cast=cast, obstruction=occ,
                audio=aud, crop916=crop, in_=in_, out_=out_, usable_ratio=round(usable_ratio, 2),
                tech=tech, interest=interest, subject_motion=round(outfrac, 2), action=round(act, 3),
                raw=dict(jit=round(jit, 4), jit_p90=round(jit_p90, 4), vtx=round(vtx, 3), vty=round(vty, 3), vs=round(vs, 3),
                         parallax=round(parallax, 2), evenness=round(evenness, 2), texture=round(texture, 2),
                         luma=round(L, 1), noise=None if nz is None else round(nz, 2), a=round(aa, 1), b=round(bb, 1),
                         face_h=round(med([f['faces'][0]['h'] for f in pf if f['faces']], 0), 3),
                         sharp=round(float(np.median(sharp_series)), 1), lowsharp=round(lowsharp, 2)),
                keyframes=[round(k / FPS, 1) for k in pick])


# ---------------------------------------------------------------- vẽ

def arrow_for(seg, img):
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2
    r = seg['raw']
    dx, dy = -r['vtx'], -r['vty']       # hướng máy
    mag = math.hypot(dx, dy)
    if mag > 0.012:
        L = min(0.4, 0.15 + mag) * w
        ex, ey = int(cx + dx / mag * L), int(cy + dy / mag * L)
        cv2.arrowedLine(img, (cx, cy), (ex, ey), (0, 0, 0), 6, tipLength=0.3)
        cv2.arrowedLine(img, (cx, cy), (ex, ey), (0, 255, 255), 3, tipLength=0.3)
    if abs(r['vs']) > 0.01:
        for k in (1, 2):
            rr = int(w * 0.08 * k)
            cv2.circle(img, (cx, cy), rr, (255, 0, 255), 2)
        cv2.putText(img, 'IN' if r['vs'] > 0 else 'OUT', (cx - 20, cy + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)


def kf_grid(seg, keep, path):
    ims = []
    for t in seg['keyframes']:
        k = int(round(t * FPS))
        k = min(keep, key=lambda x: abs(x - k)) if keep else None
        if k is not None:
            ims.append(keep[k].copy())
    if not ims:
        return
    while len(ims) < 4:
        ims.append(np.zeros_like(ims[0]))
    h = max(i.shape[0] for i in ims); w = ims[0].shape[1]
    ims = [cv2.resize(i, (w, h)) for i in ims]
    grid = np.vstack([np.hstack(ims[:2]), np.hstack(ims[2:4])])
    cv2.imwrite(path, grid, [cv2.IMWRITE_JPEG_QUALITY, 80])


def draw_sheet(res, F, keep, path):
    rows = []
    tile_w = 220
    for s in res['segments']:
        tiles = []
        for t in s['keyframes']:
            k = int(round(t * FPS))
            if not keep:
                break
            k = min(keep, key=lambda x: abs(x - k))
            im = cv2.resize(keep[k], (tile_w, int(tile_w * keep[k].shape[0] / keep[k].shape[1])))
            fm = F[k]
            for f in fm.get('faces') or []:
                x0, y0 = int(f['x'] * im.shape[1]), int(f['y'] * im.shape[0])
                cv2.rectangle(im, (x0, y0), (int(x0 + f['w'] * im.shape[1]), int(y0 + f['h'] * im.shape[0])), (0, 255, 0), 2)
            arrow_for(s, im)
            cv2.putText(im, f'{t:.1f}s', (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
            cv2.putText(im, f'{t:.1f}s', (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            tiles.append(im)
        if not tiles:
            continue
        hmax = max(t.shape[0] for t in tiles)
        tiles = [cv2.copyMakeBorder(t, 0, hmax - t.shape[0], 0, 3, cv2.BORDER_CONSTANT) for t in tiles]
        while len(tiles) < 4:
            tiles.append(np.zeros_like(tiles[0]))
        row = np.hstack(tiles)
        # thanh thời gian: xanh = dùng được, vàng = rung/lia, đỏ = tối/mờ/cháy
        bar = np.zeros((14, row.shape[1], 3), np.uint8)
        a, b = int(s['start'] * FPS), int(s['end'] * FPS)
        for k in range(a, b):
            f = F[k]
            col = (60, 180, 60)
            if f['luma'] < TH['dark'] or f['blown'] > TH['blown'] or f['sharp'] < TH['sharp_low'] * 0.6:
                col = (40, 40, 220)
            elif f.get('ok') and math.hypot(f['tx'], f['ty']) * FPS > 0.6:
                col = (0, 200, 230)
            x0 = int((k - a) / max(1, b - a) * row.shape[1]); x1 = int((k - a + 1) / max(1, b - a) * row.shape[1])
            bar[:, x0:max(x0 + 1, x1)] = col
        label = np.zeros((26, row.shape[1], 3), np.uint8)
        txt = f"s{s['i']:02d} {s['start']:.1f}-{s['end']:.1f}s | {s['rig']} | {s['move']} | {s['size'] or '-'} | T{s['tech']}"
        cv2.putText(label, strip_vn(txt)[:110], (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        rows.append(np.vstack([label, row, bar]))
    if not rows:
        return
    wmax = max(r.shape[1] for r in rows)
    rows = [cv2.copyMakeBorder(r, 0, 6, 0, wmax - r.shape[1], cv2.BORDER_CONSTANT, value=(30, 30, 30)) for r in rows]
    head = np.zeros((28, wmax, 3), np.uint8)
    cv2.putText(head, strip_vn(f"{res['id']} | {res.get('device')} | {res['duration']}s | {res['meta'].get('profile')} | {res['meta'].get('speed')}")[:120],
                (5, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imwrite(path, np.vstack([head] + rows), [cv2.IMWRITE_JPEG_QUALITY, 75])


def strip_vn(s):
    import unicodedata
    s = s.replace('đ', 'd').replace('Đ', 'D')
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()


# ---------------------------------------------------------------- mic & take

def mics(project):
    A = os.path.join(project, '_SOCIAL', 'analysis')
    wavs = []
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if not d.startswith(('.', '_SOCIAL'))]
        for f in files:
            if f.startswith('._') or not f.lower().endswith(('.wav', '.bwf')):
                continue
            m = re.search(r'(20\d{6})_(\d{6})', f)
            if not m:
                continue
            st = datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S').replace(tzinfo=timezone(timedelta(hours=7)))
            p = os.path.join(root, f)
            d = float((probe(p).get('format') or {}).get('duration') or 0)
            wavs.append((st, st + timedelta(seconds=d), os.path.relpath(p, project)))
    n = 0
    for f in glob.glob(os.path.join(A, 'shots', '*.json')):
        s = json.load(open(f))
        if not s.get('created'):
            continue
        try:
            c0 = datetime.fromisoformat(s['created'])
        except Exception:
            continue
        c1 = c0 + timedelta(seconds=s.get('duration') or 0)
        hits = [dict(file=w[2], offset=round((c0 - w[0]).total_seconds(), 2)) for w in wavs if w[0] <= c1 and w[1] >= c0]
        s['mics'] = hits
        json.dump(s, open(f, 'w'), ensure_ascii=False, indent=1)
        n += bool(hits)
    print(f'{len(wavs)} file mic, {n} clip có mic rời khớp giờ (offset = giây tính từ đầu file mic; sai số vài giây do đồng hồ máy)')


def dhash(path):
    im = cv2.imread(path, 0)
    if im is None:
        return None
    h, w = im.shape
    im = im[: h // 2, : w // 2]  # khung đầu trong lưới 2×2
    im = cv2.resize(im, (9, 8))
    return (im[:, 1:] > im[:, :-1]).flatten()


def takes(project):
    A = os.path.join(project, '_SOCIAL', 'analysis')
    items = []
    for f in sorted(glob.glob(os.path.join(A, 'shots', '*.json'))):
        s = json.load(open(f))
        if not s.get('segments') or not s.get('created'):
            continue
        try:
            t = datetime.fromisoformat(s['created'])
        except Exception:
            continue
        seg = max(s['segments'], key=lambda x: x['dur'])
        hsh = dhash(os.path.join(A, seg.get('kf', ''))) if seg.get('kf') else None
        items.append([t, s['id'], s.get('kind'), hsh, max(x['tech'] for x in s['segments']), f])
    items.sort()
    groups, cur = [], []
    for it in items:
        if cur and it[2] == cur[-1][2] and (it[0] - cur[-1][0]).total_seconds() < 600 and it[3] is not None and cur[-1][3] is not None \
                and int((it[3] != cur[-1][3]).sum()) <= 14:
            cur.append(it)
        else:
            if len(cur) > 1:
                groups.append(cur)
            cur = [it]
    if len(cur) > 1:
        groups.append(cur)
    for gi, g in enumerate(groups):
        best = max(g, key=lambda x: x[4])
        for it in g:
            s = json.load(open(it[5]))
            s['take_group'] = f'G{gi:03d}'; s['take_n'] = len(g); s['best_take'] = it[1] == best[1]
            json.dump(s, open(it[5], 'w'), ensure_ascii=False, indent=1)
    print(f'{len(groups)} nhóm take giống nhau ({sum(len(g) for g in groups)} clip)')


# ---------------------------------------------------------------- CLI

def _chunk_worker(args):
    project, clip, k = args
    cv2.setNumThreads(1)
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, '_running.log'), 'a') as lf:
        lf.write(f"{os.getpid()} {clip['id']} {k}\n")
    try:
        return clip['id'], process_chunk(project, clip, k)
    except Exception as e:
        import traceback
        return clip['id'], 'ERR ' + str(e)[:200] + ' ' + traceback.format_exc()[-300:]


def _assemble_worker(args):
    project, clip, outdir = args
    cv2.setNumThreads(1)
    try:
        return assemble(project, clip, outdir)
    except Exception as e:
        import traceback
        return clip['id'], 'ERR ' + str(e)[:200] + ' ' + traceback.format_exc()[-300:]


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--budget', type=float, default=0, help='giây; ngừng nhận việc mới để lượt kết thúc gọn')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--cost', type=float, default=0.9, help='giây xử lý / giây video / tiến trình (POV HEVC ~0.9, proxy ~0.15)')
    ap.add_argument('--mics', action='store_true')
    ap.add_argument('--takes', action='store_true')
    ap.add_argument('--ids', nargs='*', help='chỉ các clip id này (thử nghiệm)')
    a = ap.parse_args()
    outdir = os.path.join(a.project, '_SOCIAL', 'analysis')
    if a.mics:
        mics(a.project); sys.exit()
    if a.takes:
        takes(a.project); sys.exit()
    os.makedirs(os.path.join(outdir, 'shots'), exist_ok=True)
    clips = []
    for f in sorted(glob.glob(os.path.join(outdir, 'clips', '*.json'))):
        c = json.load(open(f))
        if a.only and not any(c['path'].startswith(o) for o in a.only):
            continue
        if a.ids and c['id'] not in a.ids:
            continue
        clips.append(c)

    def done(c):
        p = os.path.join(outdir, 'shots', c['id'] + '.json')
        if not os.path.exists(p):
            return False
        try:
            return json.load(open(p)).get('version') == VERSION
        except Exception:
            return False
    todo = [c for c in clips if a.force or not done(c)]
    for c in todo:
        if c.get('error'):
            json.dump(dict(id=c['id'], version=VERSION, path=c['path'], error=c['error'], segments=[]),
                      open(os.path.join(outdir, 'shots', c['id'] + '.json'), 'w'), ensure_ascii=False)
    todo = [c for c in todo if not c.get('error')]
    jobs = [(c, k) for c in todo for k in range(n_chunks(c)) if a.force or not os.path.exists(chunk_path(c['id'], k))]
    print(f'{len(clips)} clip, còn {len(todo)} ({len(jobs)} khúc chưa đo)', flush=True)
    from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
    from concurrent.futures.process import BrokenProcessPool
    t0 = time.time(); n = 0
    crash_f = os.path.join(CACHE, '_crash.json'); os.makedirs(CACHE, exist_ok=True)
    crashes = json.load(open(crash_f)) if os.path.exists(crash_f) else {}
    q = [(c, k) for c, k in jobs if crashes.get(f"{c['id']}:{k}", 0) < 2]
    for c, k in jobs:
        if crashes.get(f"{c['id']}:{k}", 0) >= 2:   # khúc làm sập tiến trình 2 lần → ghi khúc rỗng để clip vẫn ghép được
            import pickle
            pickle.dump(dict(W=0, H=0, frames=[], keep={}, crashed=True), open(chunk_path(c['id'], k), 'wb'))
    stop = False
    while True:
        ex = ProcessPoolExecutor(a.workers)
        pend = {}
        broken = False
        while True:
            while q and not stop and len(pend) < a.workers:
                c, k = q[0]
                L = min(CHUNK, (c.get('duration') or CHUNK) - k * CHUNK)
                est = 6 + L * a.cost
                if a.budget and time.time() - t0 + est > a.budget and (pend or n):
                    stop = True; break
                q.pop(0)
                pend[ex.submit(_chunk_worker, (a.project, c, k))] = (c, k)
            if not pend:
                break
            fin, _ = wait(set(pend), return_when=FIRST_COMPLETED)
            for f in fin:
                c, k = pend.pop(f)
                try:
                    cid, st = f.result()
                except BrokenProcessPool:
                    broken = True
                    for c2, k2 in [(c, k)] + list(pend.values()):
                        key = f"{c2['id']}:{k2}"
                        crashes[key] = crashes.get(key, 0) + (1 if (c2, k2) == (c, k) else 0)
                        q.insert(0, (c2, k2))
                    json.dump(crashes, open(crash_f, 'w'))
                    print(f'tiến trình sập ở {c["id"]} khúc {k} — khởi động lại', flush=True)
                    break
                n += 1
                if st.startswith('ERR'):
                    print(f'[{n}] {st} {cid}', flush=True)
            if broken:
                break
        ex.shutdown(wait=False, cancel_futures=True)
        if not broken:
            break
    with ProcessPoolExecutor(a.workers) as ex:
        # ghép những clip đã đủ khúc
        ready = [c for c in todo if all(os.path.exists(chunk_path(c['id'], k)) for k in range(n_chunks(c)))]
        m = 0
        pend = set(); q = list(ready)
        while True:
            while q and len(pend) < a.workers and not (a.budget and time.time() - t0 > a.budget + 12):
                pend.add(ex.submit(_assemble_worker, (a.project, q.pop(0), outdir)))
            if not pend:
                break
            fin, pend = wait(pend, return_when=FIRST_COMPLETED)
            for f in fin:
                try:
                    cid, st = f.result()
                except Exception as e:
                    print('ghép lỗi (tiến trình sập), chạy lại lượt sau:', str(e)[:100], flush=True); q = []; pend = set(); break
                m += 1
                if st.startswith('ERR') or m % 10 == 0:
                    print(f'[ghép {m}] {st} {cid}', flush=True)
    left = len([c for c in todo if not done(c)])
    print(f'XONG lượt: {n} khúc, ghép {m} clip, còn {left} clip', flush=True)
