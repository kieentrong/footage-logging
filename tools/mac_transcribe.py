#!/usr/bin/env python3
"""Bóc lời bằng mlx-whisper large-v3-turbo trên Mac (chạy qua mac_whisper.sh).

Đọc <dự án>/_SOCIAL/analysis/clips/*.json (do analyze.py tạo trong máy ảo), bóc lời các clip có tiếng,
ghi đè transcripts/<id>.json cùng định dạng transcribe.mjs (thêm 'words' có mốc thời gian từng từ).
Bỏ qua clip đã có bản mlx (trừ khi --force). Có thể Ctrl+C rồi chạy lại — làm tiếp chỗ dở.
"""
import argparse, json, os, re, sys, time

import mlx_whisper

MODEL = os.environ.get('TLS_WHISPER_MODEL', 'mlx-community/whisper-large-v3-turbo')
HALLU = [r'subscribe', r'đăng ký kênh', r'cảm ơn các bạn đã (theo dõi|xem)', r'thanks for watching', r'ghiền mì gõ',
         r'la la school', r'amara\.org', r'^\s*[\.\-♪]+\s*$']
REPEAT = re.compile(r'(\S+(?:\s+\S+){0,2})(?:\s+\1){3,}')


def clean(segs, lang):
    out = []
    for s in segs:
        t = (s.get('text') or '').strip()
        if not t or any(re.search(h, t, re.I) for h in HALLU) or REPEAT.search(t):
            continue
        if s.get('no_speech_prob', 0) > 0.6 and s.get('avg_logprob', 0) < -1.0:
            continue
        if s.get('compression_ratio', 0) > 2.4:
            continue
        if out and out[-1]['text'] == t:
            continue
        item = dict(start=round(s['start'], 2), end=round(s['end'], 2), text=t, lang=lang)
        if s.get('words'):
            item['words'] = [dict(w=w['word'].strip(), s=round(w['start'], 2), e=round(w['end'], 2)) for w in s['words']]
        out.append(item)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--only', help='chỉ clip có đường dẫn bắt đầu bằng chuỗi này, vd POV')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--lang', help='ép ngôn ngữ (vi/en); mặc định tự nhận')
    a = ap.parse_args()
    A = os.path.join(a.project, '_SOCIAL', 'analysis')
    cdir, tdir = os.path.join(A, 'clips'), os.path.join(A, 'transcripts')
    if not os.path.isdir(cdir):
        sys.exit(f'Chưa có {cdir} — cần chạy analyze.py trước (Claude chạy trong máy ảo).')
    os.makedirs(tdir, exist_ok=True)
    clips = []
    for f in sorted(os.listdir(cdir)):
        if not f.endswith('.json') or f.startswith('._'):
            continue
        c = json.load(open(os.path.join(cdir, f)))
        if a.only and not c.get('path', '').startswith(a.only):
            continue
        if c.get('error') or not c.get('has_audio') or (c.get('speech_ratio') or 0) < 0.08:
            continue
        out = os.path.join(tdir, c['id'] + '.json')
        if os.path.exists(out) and not a.force:
            try:
                if str(json.load(open(out)).get('model', '')).startswith('mlx'):
                    continue
            except Exception:
                pass
        clips.append((c, out))
    total = sum(c.get('duration') or 0 for c, _ in clips)
    print(f'{len(clips)} clip cần bóc lời (~{total / 60:.0f} phút audio) — model {MODEL}', flush=True)
    t0 = time.time()
    for i, (c, out) in enumerate(clips, 1):
        src = os.path.join(a.project, c['path'])
        t1 = time.time()
        try:
            r = mlx_whisper.transcribe(src, path_or_hf_repo=MODEL, language=a.lang, word_timestamps=True,
                                       condition_on_previous_text=False, verbose=None)
        except Exception as e:
            print(f'[{i}/{len(clips)}] LỖI {c["id"]}: {e}', flush=True)
            continue
        lang = r.get('language')
        segs = clean(r.get('segments', []), lang)
        json.dump(dict(id=c['id'], model='mlx-whisper-large-v3-turbo', lang=lang if segs else None, segments=segs),
                  open(out, 'w'), ensure_ascii=False, indent=1)
        print(f'[{i}/{len(clips)}] {c["id"]} {c.get("duration")}s → {len(segs)} câu ({lang}) {time.time() - t1:.1f}s', flush=True)
    print(f'XONG trong {(time.time() - t0) / 60:.1f} phút. Quay lại báo Claude để dùng transcript mới.')


if __name__ == '__main__':
    main()
