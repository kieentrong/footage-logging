// Trợ lý social — bước 2: nghe lời thoại (Whisper small, chạy offline)
// Dùng: node transcribe.mjs <project_dir> [--only POV] [--force]
// Đọc _SOCIAL/analysis/clips/*.json (do analyze.py tạo), chọn clip có tiếng,
// mỗi cửa sổ 30s: đo xác suất "không có lời" + nhận diện vi/en, rồi bóc lời theo đúng ngôn ngữ.
// Xuất _SOCIAL/analysis/transcripts/<id>.json  {lang, segments:[{start,end,text,lang}]}
// Nếu đã có transcript chất lượng cao từ Mac (mlx-whisper) cùng tên thì giữ nguyên (không ghi đè trừ --force).
import { pipeline, AutoProcessor, WhisperForConditionalGeneration, Tensor, env } from '@huggingface/transformers';
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const _here = path.dirname(decodeURIComponent(new URL(import.meta.url).pathname));
const MODEL_ROOT = process.env.WHISPER_MODELS || [path.join(_here, 'node_modules/sts-whisper-small/models/'), path.join(_here, '..', 'node_modules/sts-whisper-small/models/')].find(p => fs.existsSync(p));
env.localModelPath = MODEL_ROOT;
env.allowRemoteModels = false;
const ID = 'Xenova/whisper-small';
const TOK = { sot: 50258, en: 50259, vi: 50278, ns: 50362 };
const SR = 16000, WIN = 30;
const HALLU = [/subscribe/i, /đăng ký kênh/i, /hãy subscribe/i, /cảm ơn các bạn đã (theo dõi|xem)/i, /thanks for watching/i, /ghiền mì gõ/i, /la la school/i, /amara\.org/i, /^\s*[\.\-♪]+\s*$/];

const args = process.argv.slice(2);
const project = args[0];
const only = args.includes('--only') ? args[args.indexOf('--only') + 1] : null;
const force = args.includes('--force');
const audioDir = args.includes('--audio-dir') ? args[args.indexOf('--audio-dir') + 1] : null; // wav 16k đã tách sẵn (chạy ở máy khác)
const budget = args.includes('--budget') ? +args[args.indexOf('--budget') + 1] : 0; // giây, chạy nhiều lượt
const T0 = Date.now();
let left = 0;
const ana = path.join(project, process.env.FL_OUT || '_SOCIAL', 'analysis');
const outDir = path.join(ana, 'transcripts');
fs.mkdirSync(outDir, { recursive: true });

const asr = await pipeline('automatic-speech-recognition', ID, { dtype: 'q8', session_options: { enableCpuMemArena: false, enableMemPattern: false } });
const proc = asr.processor, model = asr.model; // dùng chung 1 bản model để tiết kiệm RAM (máy ảo 3GB)

function loadAudio(file) {
  const raw = execFileSync('ffmpeg', ['-v', 'error', '-i', file, '-vn', '-ac', '1', '-ar', String(SR), '-f', 'f32le', '-'], { maxBuffer: 2 ** 30 });
  return new Float32Array(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength));
}
async function probeWindow(a) {
  const inp = await proc(a);
  const out = await model({ input_features: inp.input_features, decoder_input_ids: new Tensor('int64', BigInt64Array.from([BigInt(TOK.sot)]), [1, 1]) });
  const l = out.logits.data, V = out.logits.dims[2];
  let mx = -1e9; for (let i = 0; i < V; i++) mx = Math.max(mx, l[i]);
  let s = 0; for (let i = 0; i < V; i++) s += Math.exp(l[i] - mx);
  const p = i => Math.exp(l[i] - mx) / s;
  return { ns: p(TOK.ns), en: p(TOK.en), vi: p(TOK.vi) };
}
function rmsDb(a) { let s = 0; for (const x of a) s += x * x; return 10 * Math.log10(s / Math.max(1, a.length) + 1e-10); }

const files = fs.readdirSync(path.join(ana, 'clips')).filter(f => f.endsWith('.json')).sort();
if (args.includes('--reverse')) files.reverse(); // chạy song song 2 máy: một máy xuôi, một máy ngược
let i = 0;
for (const f of files) {
  i++;
  const clip = JSON.parse(fs.readFileSync(path.join(ana, 'clips', f)));
  if (only && !clip.path.startsWith(only)) continue;
  const out = path.join(outDir, clip.id + '.json');
  if (fs.existsSync(out) && !force) continue;
  if (!clip.has_audio || (clip.speech_ratio ?? 1) < 0.08) {
    fs.writeFileSync(out, JSON.stringify({ id: clip.id, lang: null, skipped: 'no-audio-or-silent', segments: [] }));
    continue;
  }
  if (budget && (Date.now() - T0) / 1000 + 6 + (clip.duration || 0) * 0.4 > budget) { left++; continue; }
  const t0 = Date.now();
  if (process.env.DEBUG) console.error('mem', Math.round(process.memoryUsage().rss / 1e6), 'MB', clip.id, clip.duration);
  let audio;
  try { const aw = audioDir && path.join(audioDir, clip.id + '.wav'); audio = loadAudio(aw && fs.existsSync(aw) ? aw : path.join(project, clip.path)); } catch (e) { console.log('ERR audio', clip.id, String(e.message).slice(0, 200)); continue; }
  const nW = Math.max(1, Math.ceil(audio.length / (SR * WIN)));
  const wins = [];
  for (let w = 0; w < nW; w++) {
    const a = audio.subarray(w * SR * WIN, Math.min(audio.length, (w + 1) * SR * WIN));
    if (a.length < SR * 0.8) { wins.push({ w, speech: false }); continue; }
    const db = rmsDb(a);
    const pr = await probeWindow(a);
    const speech = pr.ns < 0.6 && db > -48;
    wins.push({ w, speech, lang: pr.vi >= pr.en ? 'vi' : 'en', ...pr, db });
  }
  // group consecutive speech windows with the same language
  const groups = [];
  for (const wn of wins) {
    if (!wn.speech) continue;
    const g = groups[groups.length - 1];
    if (g && g.lang === wn.lang && g.end === wn.w) g.end = wn.w + 1; else groups.push({ lang: wn.lang, start: wn.w, end: wn.w + 1 });
  }
  const segments = [];
  for (const g of groups) {
    const off = g.start * WIN;
    const a = audio.subarray(g.start * SR * WIN, Math.min(audio.length, g.end * SR * WIN));
    const r = await asr(a, { return_timestamps: true, chunk_length_s: 30, stride_length_s: 5, language: g.lang, task: 'transcribe' });
    for (const c of r.chunks || []) {
      const txt = (c.text || '').trim();
      if (!txt || HALLU.some(h => h.test(txt))) continue;
      if (/(\S+(?:\s+\S+){0,2})(?:\s+\1){3,}/u.test(txt)) continue; // lặp từ kiểu 'bánh mì bánh mì bánh mì…' = ảo giác
      let [s, e] = c.timestamp; s = (s ?? 0) + off; e = (e ?? s + 2) + off;
      // drop near-silent chunks (hallucination guard)
      const seg = audio.subarray(Math.floor(s * SR), Math.floor(Math.min(e, audio.length / SR) * SR));
      if (seg.length && rmsDb(seg) < -50) continue;
      const prev = segments[segments.length - 1];
      if (prev && prev.text === txt) continue; // repeated loop
      segments.push({ start: +s.toFixed(2), end: +e.toFixed(2), text: txt, lang: g.lang });
    }
  }
  const langs = segments.map(s => s.lang);
  const lang = langs.length ? (langs.filter(l => l === 'vi').length >= langs.length / 2 ? 'vi' : 'en') : null;
  fs.writeFileSync(out, JSON.stringify({ id: clip.id, model: 'whisper-small-q8', lang, windows: wins, segments }, null, 1));
  console.log(`[${i}/${files.length}] ${clip.id} ${clip.duration}s → ${segments.length} câu (${lang}) ${(Date.now() - t0) / 1000}s`);
}
console.log(left ? `TẠM DỪNG: còn ${left} clip, chạy lại để tiếp` : 'DONE');
