#!/usr/bin/env python3
"""Footage Logging — trang cho AI xem (2 lượt) và bảng log theo TỪNG CẢNH.

  python3 review.py pages <dự án> [--only POV] [--per 3] [--minq 0] [--tag _pov]
      Lượt 1: ghép contact sheet có chú thích (sheets2/, do shots.py vẽ) thành trang
      → analysis/pages/page<tag>_NNN.jpg + .txt (số đo máy + lời thoại + mô tả AI local từng cảnh)
  python3 review.py candidates <dự án> [--top 40] [--only POV]
      Liệt kê cảnh ứng viên cho lượt 2 (điểm đáng chú ý cao, AI local chấm cao, có đỉnh âm thanh)
  python3 review.py strip <dự án> <clip_id> <start> <end> [--step 0.4] [--w 200]
      Lượt 2: dải khung dày (mặc định 0.4s/khung) của một đoạn → analysis/strips/<clip>_<start>-<end>.jpg
  python3 review.py log <dự án>
      Gộp shots/ + vlm/ + transcripts/ + notes/ → clip_log.csv / clip_log.json / clip_log.html (một dòng = một cảnh)

Notes do Claude ghi — analysis/notes/notes_<nhóm>.json, khoá là "<clip_id>#sNN" (một cảnh) hoặc "<clip_id>" (cả clip):
  {"<clip_id>#s03": {"desc": "...", "scene_type": "phản ứng", "scene": "quán cà phê phố đường tàu",
     "people": ["Sofia"], "action": "...", "tags": ["tàu hoả"], "angle": "ngang tầm mắt",
     "size": "cận (CU)", "move": "...", "rig": "...",              # chỉ ghi khi SỬA lại số đo máy
     "highlights": [{"start": 4.0, "end": 12.0, "why": "...", "score": 10}],
     "content": 9, "role": "hook", "risks": ["hút thuốc 18–30s"], "usable": true, "reject_reason": null,
     "in": 4.2, "out": 11.8}}
Thứ tự ưu tiên khi gộp: Claude (notes) > AI local (vlm) > máy đo (shots). Cột *_src ghi nguồn.
"""
import csv, glob, html, json, os, re, subprocess, sys
import numpy as np
import cv2


def A_(project):
    return os.path.join(project, '_SOCIAL', 'analysis')


def load(project):
    A = A_(project)
    clips, shots, vlm, notes, tx = {}, {}, {}, {}, {}
    for f in sorted(glob.glob(os.path.join(A, 'clips', '*.json'))):
        d = json.load(open(f)); clips[d['id']] = d
    for f in sorted(glob.glob(os.path.join(A, 'shots', '*.json'))):
        d = json.load(open(f)); shots[d['id']] = d
    for f in glob.glob(os.path.join(A, 'vlm', '*.json')):
        try:
            vlm[os.path.basename(f)[:-5].replace('__s', '#s')] = json.load(open(f))
        except Exception:
            pass
    for f in sorted(glob.glob(os.path.join(A, 'notes', '*.json'))):
        d = json.load(open(f))
        if os.path.basename(f).startswith('notes_'):
            for k, v in d.items():
                notes.setdefault(k, {}).update(v)
        else:
            notes.setdefault(os.path.basename(f)[:-5], {}).update(d)
    for f in glob.glob(os.path.join(A, 'transcripts', '*.json')):
        try:
            d = json.load(open(f)); tx[d['id']] = d
        except Exception:
            pass
    return A, clips, shots, vlm, notes, tx


CJK = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]')


def speech_for(tx, cid, t0, t1):
    """Lời thoại trong khoảng [t0, t1] lấy từ transcript mới nhất (ưu tiên bản mlx-whisper trên Mac)."""
    d = tx.get(cid) or {}
    out = [x['text'] for x in d.get('segments', []) if x['end'] > t0 and x['start'] < t1 and not CJK.search(x['text'])]
    return ' / '.join(out)


def seg_key(cid, i):
    return f'{cid}#s{i:02d}'


def seg_text(cid, s, vlm, tx=None):
    a = dict(s.get('audio') or {})
    if tx is not None and a:
        a['speech'] = speech_for(tx, cid, s['start'], s['end'])
    v = vlm.get(seg_key(cid, s['i'])) or {}
    lines = [f"  s{s['i']:02d} {s['start']}–{s['end']}s ({s['split']}) | máy: {s['rig']} · {s['move']} ({s['move_speed']}) · cỡ {s['size'] or '?'} · {s['people']} người"
             f" · {s['composition'] or ''} · DOF {s['dof'] or '?'}",
             f"      ổn định: {s['stability']} | nét: {s['sharp']} | sáng: {s['exposure']}{' | FLICKER' if s.get('flicker') else ''}"
             f" | nhiễu {s['noise']} | {s['cast'] or ''} {'; '.join(s.get('obstruction') or [])} | KT {s['tech']} · chú ý {s['interest']} · dùng {s['in_']}–{s['out_']}"]
    if a:
        lines.append(f"      tiếng: {', '.join(a['types'])} {a['level_db']}dB {'; '.join(a['issues'])} {('đỉnh ' + str(a['peaks'])) if a.get('peaks') else ''}")
        if a.get('speech'):
            lines.append(f"      lời: {a['speech'][:240]}")
    if v.get('desc'):
        lines.append(f"      AI local: {v.get('desc')} | {v.get('scene_type', '')} | góc {v.get('angle', '')} | điểm {v.get('content', '')} | rủi ro {v.get('risks', '')}")
    return '\n'.join(lines)


# ---------------------------------------------------------------- lượt 1

def pages(project, only=None, per=3, minq=0, tag=''):
    A, clips, shots, vlm, notes, tx = load(project)
    out = os.path.join(A, 'pages'); os.makedirs(out, exist_ok=True)
    ids = [k for k, s in shots.items() if s.get('segments') and (not only or s.get('path', '').startswith(only))
           and max(x['tech'] for x in s['segments']) >= minq]
    ids.sort(key=lambda k: (shots[k].get('created') or '', k))
    n = 0
    p = 0
    while p < len(ids):
        rows, txt, h = [], [], 0
        while p < len(ids) and (len(rows) < per):
            cid = ids[p]; s = shots[cid]
            im = cv2.imread(os.path.join(A, s.get('sheet', ''))) if s.get('sheet') else None
            if im is None:
                p += 1; continue
            if rows and h + im.shape[0] > 3600:   # giữ trang vừa phải để đọc rõ
                break
            rows.append(im); h += im.shape[0]
            m = s.get('meta', {})
            head = f"## {cid}\n{s['path']} | {s.get('device')} | {s['duration']}s | {s.get('created')} | {m.get('profile')} | {m.get('speed')}"
            if s.get('mics'):
                head += f" | mic rời: {', '.join(x['file'].split('/')[-1] + ' @' + str(x['offset']) + 's' for x in s['mics'])}"
            if s.get('take_group'):
                head += f" | take {s['take_group']} ({s['take_n']}){' ★tốt nhất' if s.get('best_take') else ''}"
            txt.append(head + '\n' + '\n'.join(seg_text(cid, x, vlm, tx) for x in s['segments']) + '\n')
            p += 1
        if not rows:
            continue
        wmax = max(r.shape[1] for r in rows)
        rows = [cv2.copyMakeBorder(r, 0, 10, 0, wmax - r.shape[1], cv2.BORDER_CONSTANT, value=(50, 50, 50)) for r in rows]
        cv2.imwrite(os.path.join(out, f'page{tag}_{n:03d}.jpg'), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 72])
        open(os.path.join(out, f'page{tag}_{n:03d}.txt'), 'w').write('\n'.join(txt))
        n += 1
    print(f'{n} trang ({len(ids)} clip) trong {out}')


# ---------------------------------------------------------------- lượt 2

def candidates(project, top=40, only=None):
    A, clips, shots, vlm, notes, tx = load(project)
    rows = []
    for cid, s in shots.items():
        if only and not s.get('path', '').startswith(only):
            continue
        for x in s.get('segments', []):
            v = vlm.get(seg_key(cid, x['i'])) or {}
            score = x['interest'] + 0.6 * float(v.get('content') or 0) + (1 if (x.get('audio') or {}).get('peaks') else 0)
            if x['tech'] < 4 and not v.get('content'):
                continue
            rows.append((round(score, 1), cid, x['i'], x['start'], x['end'], x['tech'], v.get('desc', '')[:90]))
    rows.sort(reverse=True)
    for r in rows[:top]:
        print(f'{r[0]:5} {r[1]}#s{r[2]:02d} {r[3]}-{r[4]}s KT{r[5]} {r[6]}')


def strip(project, cid, t0, t1, step=0.4, w=200):
    A, clips, shots, vlm, notes, tx = load(project)
    c = clips[cid]
    src = os.path.join(project, c.get('proxy') or c['path'])
    # một lần giải mã cho cả đoạn (nhanh hơn nhiều so với tua từng khung)
    p = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_streams', '-of', 'json', src], capture_output=True, text=True)
    try:
        st = json.loads(p.stdout)['streams'][0]; W0, H0 = st['width'], st['height']
        if any(abs(int(sd.get('rotation', 0))) in (90, 270) for sd in st.get('side_data_list', []) or []):
            W0, H0 = H0, W0
    except Exception:
        W0, H0 = 16, 9
    h = int(round(w * H0 / W0 / 2) * 2)
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t0:.2f}', '-t', f'{t1 - t0 + 0.01:.2f}', '-i', src,
                          '-vf', f'fps=1/{step},scale={w}:{h}', '-pix_fmt', 'bgr24', '-f', 'rawvideo', '-'], capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    tiles = []
    for k in range(min(n, 40)):
        im = np.frombuffer(raw[k * w * h * 3:(k + 1) * w * h * 3], np.uint8).reshape(h, w, 3).copy()
        t = t0 + k * step
        cv2.putText(im, f'{t:.1f}', (4, 18), 0, 0.55, (0, 0, 0), 3); cv2.putText(im, f'{t:.1f}', (4, 18), 0, 0.55, (0, 255, 255), 1)
        tiles.append(im)
    if not tiles:
        print('không cắt được khung'); return
    per = 8
    rows = [np.hstack(tiles[i:i + per] + [np.zeros_like(tiles[0])] * (per - len(tiles[i:i + per]))) for i in range(0, len(tiles), per)]
    os.makedirs(os.path.join(A, 'strips'), exist_ok=True)
    p = os.path.join(A, 'strips', f'{cid}_{t0:g}-{t1:g}.jpg')
    cv2.imwrite(p, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 75])
    print(p)


# ---------------------------------------------------------------- bảng log

COLS = [
    ('id', 'Cảnh'), ('path', 'File'), ('device', 'Thiết bị'), ('created', 'Giờ quay'), ('start', 'Từ (s)'), ('end', 'Đến (s)'),
    ('in', 'In đề xuất'), ('out', 'Out đề xuất'),
    # ngôn ngữ máy
    ('rig', 'Cách đặt máy'), ('move', 'Chuyển động'), ('move_speed', 'Tốc độ'), ('size', 'Cỡ cảnh'), ('angle', 'Góc máy'),
    ('dof', 'DOF'), ('composition', 'Bố cục'), ('headroom', 'Headroom'), ('speed', 'Tốc độ khung'), ('crop916', 'Crop 9:16'),
    # kỹ thuật
    ('stability', 'Ổn định'), ('sharp', 'Nét'), ('exposure', 'Phơi sáng'), ('profile', 'Profile màu'), ('cast', 'Ám màu'),
    ('noise', 'Nhiễu'), ('flicker', 'Flicker'), ('obstruction', 'Vật cản'),
    # nội dung
    ('scene_type', 'Loại cảnh'), ('scene', 'Bối cảnh'), ('people', 'Người'), ('people_n', 'Số người'), ('action', 'Hành động'),
    ('desc', 'Mô tả'), ('tags', 'Tag'), ('time_of_day', 'Thời điểm'),
    # âm thanh
    ('audio_types', 'Loại tiếng'), ('audio_issues', 'Lỗi tiếng'), ('audio_db', 'Mức (dB)'), ('speech', 'Lời thoại'), ('mics', 'Mic rời'),
    # biên tập
    ('tech', 'Điểm KT'), ('content', 'Điểm ND'), ('role', 'Vai trò'), ('highlights', 'Đoạn hay'), ('risks', 'Rủi ro đăng'),
    ('take', 'Take'), ('usable', 'Dùng được'), ('reject_reason', 'Lý do loại'),
    ('src', 'Nguồn'), ('kf', 'Ảnh'),
]


def pick(field, note, v, machine):
    if note.get(field) not in (None, '', []):
        return note[field], 'Claude'
    if v.get(field) not in (None, '', []):
        return v[field], 'AI local'
    return machine, 'máy'


def j(x):
    if isinstance(x, list):
        return '; '.join(str(i) for i in x)
    if isinstance(x, dict):
        return x.get('note', '') + (f" (focus_x {x['focus_x']})" if x.get('focus_x') is not None else '')
    if x is True:
        return 'có'
    if x is False:
        return ''
    return '' if x is None else str(x)


def log(project):
    A, clips, shots, vlm, notes, tx = load(project)
    rows = []
    for cid in sorted(shots, key=lambda k: (shots[k].get('created') or '', k)):
        s = shots[cid]
        cn = notes.get(cid, {})
        if s.get('error'):
            rows.append(dict(id=cid, path=s.get('path', clips.get(cid, {}).get('path')), usable='không', reject_reason='file hỏng: ' + s['error'], src='máy'))
            continue
        for x in s['segments']:
            key = seg_key(cid, x['i'])
            n = dict(cn); n.update(notes.get(key, {}))
            v = vlm.get(key, {})
            srcs = {}
            r = dict(id=key, path=s['path'], device=s.get('device'), created=s.get('created'), start=x['start'], end=x['end'])
            r['in'] = n.get('in', x['in_']); r['out'] = n.get('out', x['out_'])
            for f in ('rig', 'move', 'size'):
                r[f], srcs[f] = pick(f, n, {}, x[f])
            r['move_speed'] = x['move_speed']
            r['angle'], srcs['angle'] = pick('angle', n, v, None)
            for f in ('dof', 'composition', 'headroom', 'stability', 'sharp', 'exposure', 'cast', 'noise', 'flicker', 'obstruction'):
                r[f] = n.get(f, x.get(f))
            r['speed'] = s['meta'].get('speed'); r['profile'] = s['meta'].get('profile'); r['crop916'] = x.get('crop916')
            for f in ('scene_type', 'scene', 'action', 'desc', 'time_of_day'):
                r[f], srcs[f] = pick(f, n, v, None)
            r['people'] = n.get('people') or v.get('people')
            r['people_n'] = x['people']
            r['tags'] = n.get('tags') or v.get('objects') or v.get('tags')
            a = x.get('audio') or {}
            r['audio_types'] = a.get('types'); r['audio_issues'] = a.get('issues'); r['audio_db'] = a.get('level_db')
            r['speech'] = speech_for(tx, cid, x['start'], x['end']) or a.get('speech'); r['mics'] = [m['file'].split('/')[-1] + ' @' + str(m['offset']) + 's' for m in s.get('mics', [])]
            r['tech'] = n.get('tech', x['tech'])
            r['content'], srcs['content'] = pick('content', n, v, None)
            r['role'], srcs['role'] = pick('role', n, v, None)
            hl = n.get('highlights') or []
            r['highlights'] = '; '.join(f"{h['start']}-{h['end']}s ({h.get('score', '')}) {h.get('why', '')}" for h in hl)
            risks = list(n.get('risks') or []) + [z for z in (v.get('risks') or []) if z and z not in (n.get('risks') or [])]
            r['risks'] = risks
            r['take'] = (s.get('take_group', '') + (' ★' if s.get('best_take') else '')) if s.get('take_group') else ''
            usable = n.get('usable')
            if usable is None:
                usable = x['tech'] >= 5 and x['usable_ratio'] > 0.3
            r['usable'] = 'có' if usable else 'không'
            r['reject_reason'] = n.get('reject_reason') or ('' if usable else 'kỹ thuật kém (máy)')
            r['src'] = ', '.join(f'{k}:{v_}' for k, v_ in srcs.items() if v_ != 'máy') or 'máy'
            r['kf'] = x.get('kf', '')
            rows.append(r)
    keys = [k for k, _ in COLS]
    with open(os.path.join(A, 'clip_log.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow([lab for _, lab in COLS])
        for r in rows:
            w.writerow([j(r.get(k)) for k in keys])
    json.dump(rows, open(os.path.join(A, 'clip_log.json'), 'w'), ensure_ascii=False, indent=1)
    write_html(A, rows)
    n_ok = sum(1 for r in rows if r.get('usable') == 'có')
    print(f'→ clip_log.csv / .json / .html — {len(rows)} cảnh, {n_ok} dùng được')


def write_html(A, rows):
    def cell(r, k):
        return html.escape(j(r.get(k)))
    tr = []
    for r in rows:
        ok = r.get('usable') == 'có'
        c = r.get('content')
        badge = '#e5484d' if not ok else ('#30a46c' if (c or 0) >= 7 else '#f5a623' if c else '#8b8d98')
        tags = ' '.join(f'<span class=t>{html.escape(x)}</span>' for x in [r.get('rig'), r.get('move'), r.get('size'), r.get('angle'), r.get('dof') and 'DOF ' + r['dof']] if x)
        tech = ' · '.join(x for x in [j(r.get('stability')), j(r.get('sharp')), j(r.get('exposure')), j(r.get('profile')), j(r.get('cast')), j(r.get('noise')) and 'nhiễu ' + j(r.get('noise')), 'FLICKER' if r.get('flicker') else '', j(r.get('obstruction'))] if x)
        aud = ' · '.join(x for x in [j(r.get('audio_types')), j(r.get('audio_issues')), j(r.get('mics'))] if x)
        tr.append(f"""<tr data-ok="{int(ok)}" data-c="{c or 0}"><td class=id><span class=b style="background:{badge}"></span><b>{cell(r, 'id')}</b><br><small>{cell(r, 'path')}<br>{cell(r, 'device')} · {r.get('start')}–{r.get('end')}s · in {cell(r, 'in')} out {cell(r, 'out')}<br>{cell(r, 'created')}</small></td>
<td>{f'<img src="{html.escape(r["kf"])}" loading=lazy>' if r.get('kf') else ''}</td>
<td><div>{tags}</div><div class=d>{cell(r, 'desc')}</div><div><i>{cell(r, 'highlights')}</i></div>
<small>{html.escape(tech)}</small><br><small>{html.escape(aud)}</small>{('<br><small>Crop 9:16: ' + cell(r, 'crop916') + '</small>') if r.get('crop916') else ''}
{('<br><b class=rk>Rủi ro: ' + cell(r, 'risks') + '</b>') if r.get('risks') else ''}{('<br><b class=rk>Loại: ' + cell(r, 'reject_reason') + '</b>') if r.get('reject_reason') else ''}</td>
<td class=n>KT <b>{cell(r, 'tech')}</b><br>ND <b>{cell(r, 'content') or '–'}</b><br>{cell(r, 'role')}<br><small>{cell(r, 'take')}</small><br><small class=s>{cell(r, 'src')}</small></td>
<td><small>{cell(r, 'speech')[:400]}</small></td></tr>""")
    page = f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Footage log</title><style>
:root{{--bg:#111214;--fg:#ececec;--mut:#9a9ba3;--line:#2a2b30;--chip:#23252a}}
body{{font:14px/1.45 -apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--fg);margin:16px}}
table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid var(--line);padding:8px;vertical-align:top}}
img{{width:300px;max-width:30vw;border-radius:6px}}.b{{display:inline-block;width:10px;height:10px;border-radius:5px;margin-right:6px}}
small{{color:var(--mut)}}.t{{display:inline-block;background:var(--chip);border-radius:10px;padding:1px 8px;margin:0 4px 4px 0;font-size:12px}}
.d{{margin:4px 0}}.rk{{color:#ff8b8b}}.n{{white-space:nowrap}}.s{{font-size:11px}}.id{{width:220px}}
.bar{{position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:2}}button{{background:var(--chip);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px 10px;margin-right:6px;cursor:pointer}}
</style><h2>Footage log — {len(rows)} cảnh</h2>
<div class=bar><button onclick="f(0)">Tất cả</button><button onclick="f(1)">Dùng được</button><button onclick="f(2)">ND ≥ 7</button><button onclick="f(3)">Bị loại</button></div>
<table>{''.join(tr)}</table>
<script>function f(m){{document.querySelectorAll('tr').forEach(r=>{{const ok=r.dataset.ok==='1',c=+r.dataset.c;r.style.display=(m==0||m==1&&ok||m==2&&c>=7||m==3&&!ok)?'':'none'}})}}</script>"""
    open(os.path.join(A, 'clip_log.html'), 'w', encoding='utf-8').write(page)


if __name__ == '__main__':
    cmd, proj = sys.argv[1], sys.argv[2]
    arg = lambda k, d=None, t=str: t(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    if cmd == 'pages':
        pages(proj, arg('--only'), arg('--per', 3, int), arg('--minq', 0, float), arg('--tag', ''))
    elif cmd == 'candidates':
        candidates(proj, arg('--top', 40, int), arg('--only'))
    elif cmd == 'strip':
        strip(proj, sys.argv[3], float(sys.argv[4]), float(sys.argv[5]), arg('--step', 0.4, float), arg('--w', 200, int))
    else:
        log(proj)
