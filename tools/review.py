#!/usr/bin/env python3
"""Trợ lý social — gom kết quả cho AI "xem" và cho người duyệt.

  python3 review.py pages <project> [--only POV] [--per 4]
      → _SOCIAL/analysis/pages/page_XXX.jpg (mỗi trang 4 clip, mỗi clip 1 hàng 6 khung)
        + pages/page_XXX.txt (thông số kỹ thuật + lời thoại tóm tắt từng clip) để AI viết mô tả
  python3 review.py log <project>
      → gộp clips/*.json + transcripts/*.json + notes/*.json (mô tả do AI viết)
        thành _SOCIAL/analysis/clip_log.csv + clip_log.json + clip_log.html (bảng log có ảnh)

notes/<clip_id>.json do AI ghi sau khi xem trang ảnh:
  {"desc": "...", "scene": "sân bay|đồi chè|xưởng|xe|quán", "people": ["Sofia","Kiên"],
   "tags": ["đón khách","hài"], "highlights": [{"start": 3, "end": 9, "why": "Sofia nếm trà, phản ứng mạnh", "score": 9}],
   "usable": true, "reject_reason": null, "rating": 1-5}
"""
import csv, glob, html, json, os, sys
import numpy as np
import cv2


def load(project):
    A = os.path.join(project, '_SOCIAL', 'analysis')
    clips = {}
    for f in sorted(glob.glob(os.path.join(A, 'clips', '*.json'))):
        d = json.load(open(f)); clips[d['id']] = d
    for f in glob.glob(os.path.join(A, 'transcripts', '*.json')):
        d = json.load(open(f))
        if d['id'] in clips: clips[d['id']]['transcript'] = d
    for f in glob.glob(os.path.join(A, 'notes', '*.json')):
        d = json.load(open(f))
        if os.path.basename(f).startswith('notes_'):  # file gộp {clip_id: note}
            for cid, nt in d.items():
                if cid in clips: clips[cid]['notes'] = nt
        else:
            cid = os.path.basename(f)[:-5]
            if cid in clips: clips[cid]['notes'] = d
    return A, clips


def tx_text(c, maxlen=400):
    t = c.get('transcript') or {}
    segs = t.get('segments') or []
    s = ' / '.join(f"[{x['start']:.0f}s {x.get('lang', '')}] {x['text']}" for x in segs)
    return s[:maxlen] + ('…' if len(s) > maxlen else '')


def flags_text(c):
    if c.get('error'):
        return 'LỖI: ' + c['error']
    sf = c.get('summary_flags', {})
    bad = ', '.join(f'{k} {int(v * 100)}%' for k, v in sf.items() if v >= 0.1)
    us = ' '.join(f'{a}-{b}s' for a, b in c.get('usable', [])[:8])
    return f"Q{c.get('quality')} | {bad or 'sạch'} | dùng được: {us or 'không'}"


def pages(project, only=None, per=4, minq=0, tag=''):
    A, clips = load(project)
    out = os.path.join(A, 'pages'); os.makedirs(out, exist_ok=True)
    ids = [k for k, c in clips.items() if (not only or c['path'].startswith(only)) and (c.get('quality') or 0) >= minq and not c.get('error')]
    ids.sort(key=lambda k: (clips[k].get('created') or '', k))
    n = 0
    for p in range(0, len(ids), per):
        rows, txt = [], []
        for cid in ids[p:p + per]:
            c = clips[cid]
            sp = os.path.join(A, c.get('sheet') or '')
            im = cv2.imread(sp) if c.get('sheet') and os.path.exists(sp) else None
            if im is None:
                im = np.zeros((60, 1584, 3), np.uint8)
                cv2.putText(im, cid + ' (khong co anh)', (8, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
            rows.append(im)
            txt.append(f"## {cid}\n{c['path']} | {c.get('device')} | {c.get('duration')}s | {c.get('created')}\n{flags_text(c)}\nLời: {tx_text(c) or '(không có lời)'}\n")
        wmax = max(r.shape[1] for r in rows)
        rows = [cv2.copyMakeBorder(r, 0, 8, 0, wmax - r.shape[1], cv2.BORDER_CONSTANT, value=(40, 40, 40)) for r in rows]
        cv2.imwrite(os.path.join(out, f'page{tag}_{n:03d}.jpg'), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 72])
        open(os.path.join(out, f'page{tag}_{n:03d}.txt'), 'w').write('\n'.join(txt))
        n += 1
    print(f'{n} trang trong {out}')


def log(project):
    A, clips = load(project)
    rows = []
    for cid, c in sorted(clips.items(), key=lambda kv: (kv[1].get('created') or '', kv[0])):
        nt = c.get('notes') or {}
        hl = '; '.join(f"{h['start']}-{h['end']}s ({h.get('score', '')}) {h.get('why', '')}" for h in nt.get('highlights', []))
        rows.append(dict(id=cid, path=c['path'], device=c.get('device'), created=c.get('created'), duration=c.get('duration'),
                         orientation=c.get('orientation'), quality=c.get('quality'), rating=nt.get('rating'),
                         usable=nt.get('usable', not c.get('error')), reject=nt.get('reject_reason') or (c.get('error') or ''),
                         flags=flags_text(c), scene=nt.get('scene', ''), people=', '.join(nt.get('people', [])),
                         tags=', '.join(nt.get('tags', [])), desc=nt.get('desc', ''), highlights=hl, speech=tx_text(c, 2000),
                         sheet=c.get('sheet', '')))
    with open(os.path.join(A, 'clip_log.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    json.dump(rows, open(os.path.join(A, 'clip_log.json'), 'w'), ensure_ascii=False, indent=1)
    # HTML log có ảnh — mở bằng trình duyệt
    tr = []
    for r in rows:
        badge = '#2ecc71' if r['usable'] and (r['rating'] or 3) >= 4 else ('#e74c3c' if not r['usable'] else '#f1c40f')
        tr.append(f"""<tr><td><span class=b style="background:{badge}"></span><b>{html.escape(r['id'])}</b><br><small>{html.escape(r['path'])}<br>{r['device']} · {r['duration']}s · {html.escape(str(r['created'] or ''))}</small></td>
<td><img src="{html.escape(r['sheet'])}" loading=lazy></td>
<td><b>{'★' * int(r['rating'] or 0)}</b> {html.escape(r['scene'])}<br>{html.escape(r['desc'])}<br><i>{html.escape(r['highlights'])}</i><br><small>{html.escape(r['flags'])}</small>{'<br><b style=color:#e74c3c>Loại: ' + html.escape(r['reject']) + '</b>' if r['reject'] else ''}</td>
<td><small>{html.escape(r['speech'][:600])}</small></td></tr>""")
    page = f"""<!doctype html><meta charset=utf-8><title>Clip log</title><style>
body{{font:14px -apple-system,Segoe UI,sans-serif;background:#111;color:#eee;margin:16px}}table{{border-collapse:collapse;width:100%}}
td{{border-bottom:1px solid #333;padding:8px;vertical-align:top}}img{{width:640px;max-width:45vw}}.b{{display:inline-block;width:10px;height:10px;border-radius:5px;margin-right:6px}}
small{{color:#aaa}}</style><h2>Clip log — {len(rows)} clip</h2><table>{''.join(tr)}</table>"""
    open(os.path.join(A, 'clip_log.html'), 'w', encoding='utf-8').write(page)
    print('→ clip_log.csv / clip_log.json / clip_log.html')


if __name__ == '__main__':
    cmd, proj = sys.argv[1], sys.argv[2]
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
    per = int(sys.argv[sys.argv.index('--per') + 1]) if '--per' in sys.argv else 4
    minq = float(sys.argv[sys.argv.index('--minq') + 1]) if '--minq' in sys.argv else 0
    tag = sys.argv[sys.argv.index('--tag') + 1] if '--tag' in sys.argv else ''
    pages(proj, only, per, minq, tag) if cmd == 'pages' else log(proj)
