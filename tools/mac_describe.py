#!/usr/bin/env python3
"""Footage Logging — AI local trên Mac (mlx-vlm) viết mô tả thô cho TỪNG CẢNH.

Chạy qua mac_local.sh (dùng chung môi trường ~/.tls_mlx với mac_whisper.sh).
Đọc <dự án>/_SOCIAL/analysis/shots/*.json + kf/<clip>__sNN.jpg (lưới 2×2 khung do shots.py tạo trong máy ảo),
ghi <dự án>/_SOCIAL/analysis/vlm/<clip>__sNN.json. Có thể Ctrl+C rồi chạy lại — làm tiếp chỗ dở.

Model mặc định chọn theo RAM: ≥16GB → Qwen2.5-VL-7B-Instruct-4bit (~5GB), <16GB → bản 3B.
Đổi model: TLS_VLM_MODEL=mlx-community/<tên> bash mac_local.sh describe ...
"""
import argparse, glob, json, os, re, subprocess, sys, time

PROMPT = """Bạn là trợ lý dựng phim đang log source. Ảnh là lưới 2×2 gồm 4 khung theo thứ tự thời gian (trái→phải, trên→dưới) của MỘT cảnh quay.
Thông tin máy đo được (có thể sai, hãy sửa nếu ảnh cho thấy khác): thiết bị {device}; cách đặt máy: {rig}; chuyển động: {move}; cỡ cảnh: {size}; số người: {people}.
{speech}
Trả lời DUY NHẤT một object JSON hợp lệ, tiếng Việt, không giải thích thêm:
{{"desc": "1–2 câu: ai đang làm gì, ở đâu, cụ thể",
 "scene_type": "một trong: phỏng vấn | B-roll | establishing | chi tiết/insert | hành động | phản ứng | hậu trường lộ thiết bị | cảnh kết quả | chuyển cảnh | quay nhầm",
 "scene": "bối cảnh ngắn gọn",
 "people": ["mô tả ngắn từng người, vd 'cô gái tóc vàng đội mũ cói'"],
 "action": "hành động chính",
 "objects": ["đồ vật/chủ đề nổi bật, tối đa 6"],
 "angle": "một trong: ngang tầm mắt | góc thấp | góc cao | top-down | nghiêng (Dutch) | qua vai | POV",
 "size": "một trong: đặc tả (ECU) | cận (CU) | cận trung (MCU) | trung (MS) | toàn trung (MWS) | toàn (WS) | đại cảnh (EWS)",
 "time_of_day": "một trong: sáng | trưa | chiều | giờ vàng | tối/đêm | trong nhà",
 "risks": ["chỉ ghi nếu thấy: hút thuốc | trẻ em | màn hình điện thoại/tin nhắn | giấy tờ | biển số xe | logo thương hiệu | người lạ nhìn rõ mặt | cảnh thiếu lịch sự"],
 "content": 0-10 (khoảnh khắc có đáng xem không: cảm xúc, hành động lạ/gay cấn, khung hình đẹp),
 "role": "một trong: hook | thân | trám/B-roll | chuyển cảnh | kết | payoff kết quả | bỏ"}}"""


def pick_model():
    m = os.environ.get('TLS_VLM_MODEL')
    if m:
        return m
    try:
        mem = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'])) / 2 ** 30
    except Exception:
        mem = 16
    return 'mlx-community/Qwen2.5-VL-7B-Instruct-4bit' if mem >= 15 else 'mlx-community/Qwen2.5-VL-3B-Instruct-4bit'


def parse_json(txt):
    txt = txt.strip()
    m = re.search(r'\{.*\}', txt, re.S)
    if not m:
        return None
    raw = m.group(0)
    for cand in (raw, re.sub(r',\s*([}\]])', r'\1', raw)):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--only', help='chỉ clip có đường dẫn bắt đầu bằng chuỗi này (vd POV)')
    ap.add_argument('--min-interest', type=float, default=0, help='bỏ qua cảnh có điểm "đáng chú ý" (máy) thấp hơn')
    ap.add_argument('--min-tech', type=float, default=0)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    A = os.path.join(a.project, '_SOCIAL', 'analysis')
    out = os.path.join(A, 'vlm'); os.makedirs(out, exist_ok=True)
    jobs = []
    for f in sorted(glob.glob(os.path.join(A, 'shots', '*.json'))):
        if os.path.basename(f).startswith('._'):
            continue
        s = json.load(open(f))
        if a.only and not s.get('path', '').startswith(a.only):
            continue
        for x in s.get('segments', []):
            if x['interest'] < a.min_interest or x['tech'] < a.min_tech or not x.get('kf'):
                continue
            o = os.path.join(out, f"{s['id']}__s{x['i']:02d}.json")
            if os.path.exists(o) and not a.force:
                continue
            jobs.append((s, x, o))
    jobs.sort(key=lambda j: -j[1]['interest'])  # cảnh đáng chú ý chạy trước
    if a.limit:
        jobs = jobs[:a.limit]
    print(f'{len(jobs)} cảnh cần mô tả', flush=True)
    if not jobs:
        return
    from mlx_vlm import load, generate
    from mlx_vlm.prompt_utils import apply_chat_template
    model_id = pick_model()
    print('→ model', model_id, '(lần đầu tải vài GB)', flush=True)
    model, processor = load(model_id)
    config = getattr(model, 'config', None)
    t0 = time.time()
    for k, (s, x, o) in enumerate(jobs):
        sp = (x.get('audio') or {}).get('speech') or ''
        prompt = PROMPT.format(device=s.get('device'), rig=x['rig'], move=x['move'], size=x['size'] or 'không rõ',
                               people=x['people'], speech=f'Lời thoại trong cảnh (máy nghe, có thể sai): "{sp[:300]}"' if sp else 'Cảnh không có lời thoại rõ.')
        img = os.path.join(A, x['kf'])
        try:
            fp = apply_chat_template(processor, config, prompt, num_images=1)
            try:
                r = generate(model, processor, fp, image=[img], max_tokens=420, temperature=0.1, verbose=False)
            except TypeError:
                r = generate(model, processor, img, fp, max_tokens=420, temp=0.1, verbose=False)
            txt = getattr(r, 'text', r)
            if isinstance(txt, tuple):
                txt = txt[0]
        except Exception as e:
            print('lỗi', o, str(e)[:200], flush=True)
            continue
        d = parse_json(txt) or {'desc': txt.strip()[:400], 'parse_error': True}
        d['model'] = model_id
        json.dump(d, open(o, 'w'), ensure_ascii=False, indent=1)
        el = time.time() - t0
        eta = el / (k + 1) * (len(jobs) - k - 1)
        print(f"[{k + 1}/{len(jobs)}] {os.path.basename(o)} ND {d.get('content')} | {str(d.get('desc', ''))[:70]} | còn ~{eta / 60:.0f} phút", flush=True)


if __name__ == '__main__':
    main()
