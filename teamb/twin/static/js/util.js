// Small helpers shared by all modules: coordinates, seeded randomness, formatting, text sprites.
//
// Coordinates: SUMO uses meters with x = east, y = north. three.js is y-up, so a SUMO point
// (x, y) at height h becomes (x, h, -y). Headings use SUMO's navigational convention
// (0° = north, 90° = east, clockwise); a model whose nose points along local -z gets
// rotation.y = -heading.
import * as THREE from 'three';

export const DEG = Math.PI / 180;

/** SUMO (x east, y north) + height -> three.js vector. */
export function toVec3(x, y, h = 0, out = new THREE.Vector3()) {
  return out.set(x, h, -y);
}

/** Navigational heading in degrees -> rotation about three's Y axis. */
export const headingToRotY = (deg) => -deg * DEG;

/** Unit direction [dx, dy] in SUMO coordinates for a navigational heading. */
export function headingDir(deg) {
  const r = deg * DEG;
  return [Math.sin(r), Math.cos(r)];
}

/** Right-hand normal of a SUMO direction (rotate 90° clockwise). */
export const rightOf = (dx, dy) => [dy, -dx];

/** Deterministic random numbers (mulberry32) so the city looks the same on every load. */
export function seededRandom(seed) {
  let a = seed >>> 0;
  return function rand() {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Stable 32-bit hash of a string (vehicle paint colors, flash phases). */
export function hashString(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export const lerp = (a, b, t) => a + (b - a) * t;
export const range = (rand, lo, hi) => lo + (hi - lo) * rand();

/** Interpolate angles in degrees along the shorter arc. */
export function lerpAngleDeg(a, b, t) {
  const d = ((((b - a) % 360) + 540) % 360) - 180;
  return a + d * t;
}

/** 1234.5 -> "20:34" (or "1:20:34"). */
export function fmtClock(t) {
  if (t == null || !isFinite(t)) return '--:--';
  const s = Math.max(0, Math.floor(t));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = h ? String(m).padStart(2, '0') : String(m);
  return (h ? `${h}:` : '') + `${mm}:${String(sec).padStart(2, '0')}`;
}

export function fmtNum(v, digits = 0) {
  if (v == null || !isFinite(v)) return '–';
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export const APPROACH_NAMES = { N: 'north', S: 'south', E: 'east', W: 'west' };
export const KIND_LABELS = { ambulance: 'Ambulance', firetruck: 'Fire truck', car: 'Car', probe: 'Probe car', truck: 'Truck', bus: 'Bus' };

/** "ambulance_3" -> "Ambulance 3" */
export function vehicleLabel(id) {
  const m = /^([a-z]+)_(\d+)$/.exec(id || '');
  if (!m) return id;
  return `${KIND_LABELS[m[1]] || m[1]} ${m[2]}`;
}

// --- text sprites ------------------------------------------------------------------
// 3D labels are sprites (drawn into the WebGL canvas) rather than HTML, so they also appear
// in videos made with the Record button. They keep a constant size on screen.
const labels = new Set();
let labelViewportHeight = 800;
let labelFovScale = 1;

/** Call on resize so constant-size labels stay `px` pixels tall. */
export function setLabelViewport(viewportHeight, fovDeg) {
  labelViewportHeight = Math.max(1, viewportHeight);
  labelFovScale = Math.tan((fovDeg * DEG) / 2);
  for (const sprite of labels) applyLabelScale(sprite);
}

function applyLabelScale(sprite) {
  const { px, aspect } = sprite.userData;
  // With sizeAttenuation off, a sprite of height s covers s / (2 tan(fov/2)) of the viewport.
  const s = (px / labelViewportHeight) * 2 * labelFovScale;
  sprite.scale.set(s * aspect, s, 1);
}

function drawLabel(canvas, text, opts) {
  const ctx = canvas.getContext('2d');
  const scale = 2; // draw at 2x for crisp text
  const font = `${opts.weight || 700} ${opts.fontSize * scale}px ${opts.font || '-apple-system, Segoe UI, Roboto, sans-serif'}`;
  ctx.font = font;
  const lines = String(text).split('\n');
  const padX = 10 * scale;
  const padY = 6 * scale;
  const lineH = opts.fontSize * 1.25 * scale;
  const w = Math.ceil(Math.max(...lines.map((l) => ctx.measureText(l).width)) + padX * 2);
  const h = Math.ceil(lineH * lines.length + padY * 2);
  canvas.width = w;
  canvas.height = h;
  ctx.font = font;
  const r = Math.min(h / 2, 10 * scale);
  ctx.beginPath();
  ctx.moveTo(r, 0);
  ctx.arcTo(w, 0, w, h, r);
  ctx.arcTo(w, h, 0, h, r);
  ctx.arcTo(0, h, 0, 0, r);
  ctx.arcTo(0, 0, w, 0, r);
  ctx.closePath();
  ctx.fillStyle = opts.background;
  ctx.fill();
  if (opts.border) {
    ctx.lineWidth = 2 * scale;
    ctx.strokeStyle = opts.border;
    ctx.stroke();
  }
  ctx.fillStyle = opts.color;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'center';
  lines.forEach((line, i) => ctx.fillText(line, w / 2, padY + lineH * (i + 0.5)));
  return w / h;
}

/**
 * A constant-screen-size text label. Returns a THREE.Sprite with sprite.userData.setText(text).
 * opts: color, background, border, fontSize (px), px (on-screen height of one line), depthTest.
 */
export function makeLabel(text, opts = {}) {
  const o = {
    color: '#ffffff',
    background: 'rgba(8, 13, 24, 0.82)',
    border: null,
    fontSize: 22,
    px: 22,
    ...opts,
  };
  const canvas = document.createElement('canvas');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  const material = new THREE.SpriteMaterial({ map: texture, sizeAttenuation: false, depthTest: !!o.depthTest, depthWrite: false, transparent: true });
  const sprite = new THREE.Sprite(material);
  sprite.renderOrder = 20;
  sprite.center.set(0.5, 0);
  let current = null;
  sprite.userData.setText = (t, newOpts) => {
    if (newOpts) Object.assign(o, newOpts);
    const key = `${t}|${o.color}|${o.background}|${o.border}`;
    if (key === current) return;
    current = key;
    const lines = String(t).split('\n').length;
    sprite.userData.aspect = drawLabel(canvas, t, o);
    sprite.userData.px = o.px * (1 + (lines - 1) * 0.8);
    texture.needsUpdate = true;
    applyLabelScale(sprite);
  };
  sprite.userData.dispose = () => {
    labels.delete(sprite);
    texture.dispose();
    material.dispose();
  };
  labels.add(sprite);
  sprite.userData.setText(text);
  return sprite;
}

/** A soft round glow texture (white), tinted by the material color. */
let glowTexture = null;
export function getGlowTexture() {
  if (glowTexture) return glowTexture;
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.25, 'rgba(255,255,255,0.7)');
  g.addColorStop(0.6, 'rgba(255,255,255,0.18)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  glowTexture = new THREE.CanvasTexture(c);
  glowTexture.colorSpace = THREE.SRGBColorSpace;
  return glowTexture;
}

/** Index the geometry for quick lookups: lanes by id, lanes per edge, edges, tls approaches. */
export function indexGeometry(geo) {
  const lanes = new Map(geo.lanes.map((l) => [l.id, l]));
  const edgeLanes = new Map();
  for (const lane of geo.lanes) {
    if (!edgeLanes.has(lane.edge)) edgeLanes.set(lane.edge, []);
    edgeLanes.get(lane.edge).push(lane);
  }
  for (const list of edgeLanes.values()) list.sort((a, b) => a.index - b.index);
  const edges = new Map(geo.edges.map((e) => [e.id, e]));
  const junctions = new Map(geo.junctions.map((j) => [j.id, j]));
  return { lanes, edgeLanes, edges, junctions, tls: geo.tls };
}

/**
 * Describe an approach for drawing: stop point, direction, right normal, total width and the
 * width of the exit lanes on the same side (the other half of the road).
 */
export function approachFrame(index, junctionId, side) {
  const tls = index.tls[junctionId];
  const a = tls.approaches[side];
  const [dx, dy] = headingDir(a.heading);
  const [rx, ry] = rightOf(dx, dy);
  const lanes = a.lanes.map((id) => index.lanes.get(id)).filter(Boolean);
  const width = lanes.reduce((s, l) => s + l.width, 0) || 3.2;
  const exitEdge = tls.exits ? tls.exits[side] : null;
  const exitLanes = exitEdge ? index.edgeLanes.get(exitEdge) || [] : [];
  const exitWidth = exitLanes.reduce((s, l) => s + l.width, 0);
  const length = lanes.length ? Math.min(...lanes.map((l) => l.length)) : 100;
  return { junction: junctionId, side, edge: a.edge, stop: a.stop, heading: a.heading, dx, dy, rx, ry, width, exitWidth, length, nLanes: lanes.length || 1 };
}
