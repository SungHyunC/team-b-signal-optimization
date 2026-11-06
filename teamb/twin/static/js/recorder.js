// Record button: captures the 3D view to a WebM file for the demo video.
//
// The WebGL canvas is copied into a 2D canvas right after each render (the drawing buffer is
// only valid until the frame is shown, so it must happen in the same animation frame), and a
// small HUD (title, sim clock, KPIs, latest event) is drawn on top, because the HTML panels
// around the 3D view are not part of the canvas.
import { fmtClock, fmtNum } from './util.js';
import { toast } from './ui/dom.js';
import { addKo, t } from './i18n.js';

addKo({
  'This browser cannot record video (try Chrome or Edge).': '이 브라우저에서는 영상을 녹화할 수 없어요 (Chrome이나 Edge를 써 보세요).',
  'Stop {time}': '중지 {time}',
  'Recording the 3D view… press Stop to save the video.': '3D 화면을 녹화하고 있어요… 저장하려면 중지를 누르세요.',
  Record: '녹화',
  'Saved {file} ({size} MB)': '녹화를 저장했어요: {file} ({size} MB)',
});

export class Recorder {
  /** hud() returns {title, subtitle, clock, phase, kpis: [[label, value]], event} */
  constructor(view, button, hud) {
    this.view = view;
    this.button = button;
    this.hud = hud;
    this.recorder = null;
    this.canvas = document.createElement('canvas');
    this.g = this.canvas.getContext('2d');
    this.startedAt = 0;
    button.addEventListener('click', () => this.toggle());
    view.onAfterRender(() => this.capture());
  }

  get active() {
    return !!this.recorder && this.recorder.state === 'recording';
  }

  toggle() {
    if (this.active) this.stop();
    else this.start();
  }

  start() {
    if (typeof MediaRecorder === 'undefined' || !this.canvas.captureStream) {
      toast(t('This browser cannot record video (try Chrome or Edge).'), 'error');
      return;
    }
    const src = this.view.renderer.domElement;
    this.canvas.width = src.width;
    this.canvas.height = src.height;
    const types = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
    const mimeType = types.find((t) => MediaRecorder.isTypeSupported(t)) || '';
    this.stream = this.canvas.captureStream(30);
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream, { mimeType, videoBitsPerSecond: 12_000_000 });
    this.recorder.ondataavailable = (e) => e.data && e.data.size && this.chunks.push(e.data);
    this.recorder.onstop = () => this.save();
    this.recorder.start(1000);
    this.startedAt = performance.now();
    this.button.classList.add('recording');
    this.button.querySelector('.rec-label').textContent = t('Stop {time}', { time: '0:00' });
    toast(t('Recording the 3D view… press Stop to save the video.'));
  }

  stop() {
    if (!this.recorder) return;
    this.recorder.stop();
    for (const track of this.stream.getTracks()) track.stop();
    this.button.classList.remove('recording');
    this.button.querySelector('.rec-label').textContent = t('Record');
  }

  save() {
    const blob = new Blob(this.chunks, { type: 'video/webm' });
    this.recorder = null;
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `signal-twin-${stamp}.webm`;
    document.body.append(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 2000);
    toast(t('Saved {file} ({size} MB)', { file: a.download, size: fmtNum(blob.size / 1e6, 1) }), 'ok', 6000);
  }

  capture() {
    if (!this.active) return;
    const src = this.view.renderer.domElement;
    const c = this.canvas;
    if (c.width !== src.width || c.height !== src.height) {
      c.width = src.width;
      c.height = src.height;
    }
    const g = this.g;
    g.drawImage(src, 0, 0);
    this.drawHud(g, c.width, c.height);
    const secs = Math.floor((performance.now() - this.startedAt) / 1000);
    this.button.querySelector('.rec-label').textContent = t('Stop {time}', { time: fmtClock(secs) });
  }

  drawHud(g, W, H) {
    const info = this.hud();
    const s = Math.max(1, H / 900);
    const panel = (x, y, w, h) => {
      g.fillStyle = 'rgba(6,10,18,0.74)';
      g.beginPath();
      if (typeof g.roundRect === 'function') g.roundRect(x, y, w, h, 10 * s);
      else g.rect(x, y, w, h); // Chrome < 99, Firefox < 112: square corners
      g.fill();
    };
    g.textBaseline = 'top';
    // title (top left); the panel fits the wider of title and subtitle
    g.font = `500 ${13 * s}px -apple-system, Segoe UI, Roboto, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif`;
    const sw = g.measureText(info.subtitle).width;
    g.font = `700 ${18 * s}px -apple-system, Segoe UI, Roboto, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif`;
    const tw = Math.max(g.measureText(info.title).width, sw, 260 * s);
    panel(14 * s, 14 * s, tw + 28 * s, 58 * s);
    g.fillStyle = '#ffffff';
    g.fillText(info.title, 28 * s, 22 * s);
    g.font = `500 ${13 * s}px -apple-system, Segoe UI, Roboto, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif`;
    g.fillStyle = '#9fb0c9';
    g.fillText(info.subtitle, 28 * s, 46 * s);
    // clock (top right)
    g.font = `700 ${26 * s}px ui-monospace, Menlo, monospace`;
    const cw = g.measureText(info.clock).width + 32 * s;
    panel(W - cw - 14 * s, 14 * s, cw, 62 * s);
    g.fillStyle = '#ffffff';
    g.fillText(info.clock, W - cw + 2 * s, 20 * s);
    g.font = `600 ${11 * s}px -apple-system, Segoe UI, Roboto, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif`;
    g.fillStyle = '#9fb0c9';
    g.fillText(info.phase.toUpperCase(), W - cw + 2 * s, 54 * s);
    // KPIs (bottom left)
    const kp = info.kpis || [];
    if (kp.length) {
      const colW = 150 * s;
      panel(14 * s, H - 74 * s, colW * kp.length + 20 * s, 60 * s);
      kp.forEach(([label, value], i) => {
        const x = 28 * s + i * colW;
        g.font = `600 ${11 * s}px -apple-system, Segoe UI, Roboto, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif`;
        g.fillStyle = '#9fb0c9';
        g.fillText(label.toUpperCase(), x, H - 66 * s);
        g.font = `700 ${22 * s}px -apple-system, Segoe UI, Roboto, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif`;
        g.fillStyle = '#ffffff';
        g.fillText(value, x, H - 48 * s);
      });
    }
    // latest event (bottom right)
    if (info.event) {
      g.font = `600 ${13 * s}px -apple-system, Segoe UI, Roboto, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif`;
      const ew = g.measureText(info.event).width + 28 * s;
      panel(W - ew - 14 * s, H - 50 * s, ew, 36 * s);
      g.fillStyle = '#ffd7a8';
      g.fillText(info.event, W - ew, H - 40 * s);
    }
  }
}
