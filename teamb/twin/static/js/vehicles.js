// Vehicles: one set of InstancedMeshes per kind (car, probe, truck, bus, ambulance, firetruck),
// so a few hundred vehicles cost a handful of draw calls.
//
// Frames arrive up to 12 times a second (once per second at 1x). Between frames every vehicle
// moves smoothly from where it is drawn now to its newest position ("chase" interpolation),
// so playback looks continuous at any speed.
//
// SUMO reports the FRONT bumper position; models are centered, so they are shifted back by half
// their length along the heading. Model space: nose towards -z, width along x, y up.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { clamp, DEG, getGlowTexture, hashString, lerpAngleDeg, makeLabel, vehicleLabel } from './util.js';

const GLASS = '#25303c';
const TIRE = '#141619';
const TRIM = '#2b2e33';

function colored(g, color) {
  const c = new THREE.Color(color);
  const n = g.attributes.position.count;
  const arr = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) arr.set([c.r, c.g, c.b], i * 3);
  g.setAttribute('color', new THREE.BufferAttribute(arr, 3));
  return g;
}
const box = (w, h, l, x, y, z, color = '#ffffff') => colored(new THREE.BoxGeometry(w, h, l).translate(x, y, z), color);
function wheel(x, z, r) {
  const g = new THREE.CylinderGeometry(r, r, 0.26, 10).rotateZ(Math.PI / 2).translate(x, r, z);
  return colored(g, TIRE);
}
const merge = (parts) => mergeGeometries(parts.map((p) => p.toNonIndexed()));

// --- low-poly models: {paint (tinted per instance), detail (fixed colors), tail (brake lights), red/blue (light bar)}
function carModel() {
  const L = 4.5;
  return {
    paint: merge([box(1.8, 0.62, L, 0, 0.59, 0), box(1.6, 0.07, 2.0, 0, 1.47, 0.25)]),
    detail: merge([
      box(1.64, 0.52, 2.2, 0, 1.16, 0.25, GLASS),
      box(1.84, 0.17, 0.12, 0, 0.37, -L / 2 - 0.02, TRIM),
      box(1.84, 0.17, 0.12, 0, 0.37, L / 2 + 0.02, TRIM),
      box(0.36, 0.13, 0.05, -0.6, 0.75, -L / 2 - 0.02, '#fff4d6'),
      box(0.36, 0.13, 0.05, 0.6, 0.75, -L / 2 - 0.02, '#fff4d6'),
      wheel(-0.8, -1.45, 0.32), wheel(0.8, -1.45, 0.32), wheel(-0.8, 1.42, 0.32), wheel(0.8, 1.42, 0.32),
    ]),
    tail: merge([box(0.34, 0.14, 0.05, -0.62, 0.77, L / 2 + 0.03), box(0.34, 0.14, 0.05, 0.62, 0.77, L / 2 + 0.03)]),
  };
}

function truckModel() {
  const L = 9.0;
  return {
    paint: merge([box(2.35, 1.95, 2.3, 0, 1.42, -L / 2 + 1.15)]),
    detail: merge([
      box(2.48, 2.65, 6.4, 0, 1.92, 1.2, '#d6d9dc'),
      box(2.2, 0.36, 8.8, 0, 0.5, 0, TRIM),
      box(2.18, 0.75, 0.05, 0, 1.9, -L / 2 - 0.02, GLASS),
      box(0.3, 0.16, 0.05, -0.9, 0.85, -L / 2 - 0.02, '#fff4d6'),
      box(0.3, 0.16, 0.05, 0.9, 0.85, -L / 2 - 0.02, '#fff4d6'),
      wheel(-1.05, -3.3, 0.48), wheel(1.05, -3.3, 0.48), wheel(-1.05, 2.1, 0.48), wheel(1.05, 2.1, 0.48), wheel(-1.05, 3.4, 0.48), wheel(1.05, 3.4, 0.48),
    ]),
    tail: merge([box(0.3, 0.18, 0.05, -1.02, 0.9, L / 2 + 0.03), box(0.3, 0.18, 0.05, 1.02, 0.9, L / 2 + 0.03)]),
  };
}

function busModel() {
  const L = 12.0;
  return {
    paint: merge([box(2.55, 2.55, L, 0, 1.63, 0)]),
    detail: merge([
      box(2.58, 0.95, 10.4, 0, 2.08, 0.4, GLASS),
      box(2.3, 1.35, 0.05, 0, 1.95, -L / 2 - 0.02, GLASS),
      box(2.57, 0.26, L - 0.1, 0, 1.2, 0, '#1f5fae'),
      box(1.6, 0.26, 3.2, 0, 3.03, 1.5, '#cfd4d8'),
      box(0.32, 0.16, 0.05, -0.95, 0.85, -L / 2 - 0.02, '#fff4d6'),
      box(0.32, 0.16, 0.05, 0.95, 0.85, -L / 2 - 0.02, '#fff4d6'),
      wheel(-1.12, -3.9, 0.5), wheel(1.12, -3.9, 0.5), wheel(-1.12, 3.7, 0.5), wheel(1.12, 3.7, 0.5),
    ]),
    tail: merge([box(0.3, 0.22, 0.05, -1.05, 0.95, L / 2 + 0.03), box(0.3, 0.22, 0.05, 1.05, 0.95, L / 2 + 0.03)]),
  };
}

function ambulanceModel() {
  const L = 6.5;
  return {
    paint: merge([box(2.0, 1.25, 1.95, 0, 1.03, -L / 2 + 0.98), box(2.15, 2.25, 4.55, 0, 1.55, 0.95)]),
    detail: merge([
      box(2.17, 0.3, 4.57, 0, 1.3, 0.95, '#d62828'),
      box(2.02, 0.2, 1.97, 0, 1.0, -L / 2 + 0.98, '#d62828'),
      box(1.84, 0.55, 0.05, 0, 1.3, -L / 2 - 0.02, GLASS),
      box(2.03, 0.42, 0.9, 0, 1.35, -L / 2 + 1.0, GLASS),
      box(1.0, 0.5, 0.05, 0, 2.1, 3.26, '#d62828'),
      box(0.3, 0.14, 0.05, -0.75, 0.78, -L / 2 - 0.02, '#fff4d6'),
      box(0.3, 0.14, 0.05, 0.75, 0.78, -L / 2 - 0.02, '#fff4d6'),
      wheel(-0.96, -2.2, 0.38), wheel(0.96, -2.2, 0.38), wheel(-0.96, 2.0, 0.38), wheel(0.96, 2.0, 0.38),
    ]),
    tail: merge([box(0.3, 0.16, 0.05, -0.88, 0.95, 3.27), box(0.3, 0.16, 0.05, 0.88, 0.95, 3.27)]),
    red: merge([box(0.78, 0.17, 0.34, -0.42, 1.74, -L / 2 + 1.1), box(0.25, 0.2, 0.25, -0.92, 2.78, 3.0)]),
    blue: merge([box(0.78, 0.17, 0.34, 0.42, 1.74, -L / 2 + 1.1), box(0.25, 0.2, 0.25, 0.92, 2.78, 3.0)]),
  };
}

function firetruckModel() {
  const L = 9.0;
  return {
    paint: merge([box(2.45, 2.1, 2.6, 0, 1.55, -L / 2 + 1.3), box(2.45, 2.0, 6.25, 0, 1.55, 1.3)]),
    detail: merge([
      box(0.95, 0.22, 7.4, 0, 2.7, 0.4, '#c9cdd1'),
      box(2.47, 0.16, L - 0.2, 0, 1.15, 0, '#f2f2f2'),
      box(2.25, 0.8, 0.05, 0, 2.05, -L / 2 - 0.02, GLASS),
      box(2.5, 0.25, 0.16, 0, 0.62, -L / 2 - 0.05, '#d0d4d8'),
      box(0.3, 0.16, 0.05, -0.95, 0.95, -L / 2 - 0.02, '#fff4d6'),
      box(0.3, 0.16, 0.05, 0.95, 0.95, -L / 2 - 0.02, '#fff4d6'),
      wheel(-1.08, -3.3, 0.5), wheel(1.08, -3.3, 0.5), wheel(-1.08, 2.2, 0.5), wheel(1.08, 2.2, 0.5), wheel(-1.08, 3.4, 0.5), wheel(1.08, 3.4, 0.5),
    ]),
    tail: merge([box(0.3, 0.18, 0.05, -1.05, 1.0, L / 2 + 0.03), box(0.3, 0.18, 0.05, 1.05, 1.0, L / 2 + 0.03)]),
    red: merge([box(0.9, 0.18, 0.36, -0.5, 2.69, -L / 2 + 0.6)]),
    blue: merge([box(0.9, 0.18, 0.36, 0.5, 2.69, -L / 2 + 0.6)]),
  };
}

// Kinds from SimEnv.frame(): car, probe, truck, bus, ambulance, firetruck. Unknown kinds draw as cars.
const CAR_PAINTS = ['#e9ebee', '#e9ebee', '#f2f2ef', '#1d2024', '#25282d', '#a9adb2', '#9a9ea4', '#6c7178', '#5b6067', '#22345a', '#a3262a', '#2f5d9a', '#c9b99a', '#2f4f3a', '#7aa3c8', '#8a1f24'];
const TRUCK_PAINTS = ['#d9dcdf', '#2a5fa6', '#c43a2b', '#e8e2d0', '#3b3f45', '#e0a526', '#2f6b4a'];
export const KINDS = {
  car: { length: 4.5, model: carModel, paints: CAR_PAINTS, capacity: 512 },
  probe: { length: 4.5, model: carModel, paints: CAR_PAINTS, capacity: 512, beacon: true },
  truck: { length: 9.0, model: truckModel, paints: TRUCK_PAINTS, capacity: 64 },
  bus: { length: 12.0, model: busModel, paints: ['#eef2f4'], capacity: 32 },
  ambulance: { length: 6.5, model: ambulanceModel, paints: ['#f4f5f2'], capacity: 16, emergency: true },
  firetruck: { length: 9.0, model: firetruckModel, paints: ['#c42019'], capacity: 16, emergency: true },
};

const paintMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.42, metalness: 0.3 });
const detailMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.55, metalness: 0.15 });
const lightMat = new THREE.MeshBasicMaterial({ color: '#ffffff', toneMapped: false });
const beaconMat = new THREE.MeshBasicMaterial({ color: '#2f9bff', toneMapped: false });
const beaconGeo = new THREE.OctahedronGeometry(0.3, 0);
const BRAKE_ON = new THREE.Color('#ff2a1f');
const BRAKE_OFF = new THREE.Color('#5a0d0b');
const FLASH_RED = new THREE.Color('#ff2020');
const FLASH_BLUE = new THREE.Color('#2a6bff');
const FLASH_OFF = new THREE.Color('#202226');
// Light bar pattern in 90 ms ticks: red double flash, then blue double flash.
const RED_PATTERN = [1, 0, 1, 0, 0, 0, 0, 0];
const BLUE_PATTERN = [0, 0, 0, 0, 1, 0, 1, 0];

function instanced(geo, mat, capacity, { colors = false, shadow = false } = {}) {
  const mesh = new THREE.InstancedMesh(geo, mat, capacity);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  if (colors) {
    mesh.setColorAt(0, new THREE.Color(1, 1, 1));
    mesh.instanceColor.setUsage(THREE.DynamicDrawUsage);
  }
  mesh.count = 0;
  mesh.frustumCulled = false; // instances move around; the base geometry's bounds would cull wrongly
  mesh.castShadow = shadow;
  return mesh;
}

/** The meshes for one vehicle kind. Grows when more vehicles show up than it has room for. */
class KindLayer {
  constructor(parent, spec) {
    this.parent = parent;
    this.spec = spec;
    this.model = spec.model();
    this.meshes = [];
    this.n = 0;
    this.alloc(spec.capacity);
  }

  alloc(capacity) {
    for (const m of this.meshes) {
      this.parent.remove(m);
      m.dispose(); // frees the instance buffers on the GPU; the model geometry is shared and stays
    }
    this.capacity = capacity;
    this.paint = instanced(this.model.paint, paintMat, capacity, { colors: true, shadow: true });
    this.detail = instanced(this.model.detail, detailMat, capacity, { shadow: true });
    this.tail = instanced(this.model.tail, lightMat, capacity, { colors: true });
    this.meshes = [this.paint, this.detail, this.tail];
    if (this.model.red) {
      this.red = instanced(this.model.red, lightMat, capacity, { colors: true });
      this.blue = instanced(this.model.blue, lightMat, capacity, { colors: true });
      this.meshes.push(this.red, this.blue);
    }
    if (this.spec.beacon) {
      this.beacon = instanced(beaconGeo, beaconMat, capacity);
      this.meshes.push(this.beacon);
    }
    for (const m of this.meshes) this.parent.add(m);
  }

  ensure(n) {
    if (n > this.capacity) this.alloc(Math.max(n, this.capacity * 2));
  }

  commit() {
    for (const m of this.meshes) {
      m.count = this.n;
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    }
  }
}

export class VehicleLayer {
  constructor(scene) {
    this.group = new THREE.Group();
    this.group.name = 'vehicles';
    scene.add(this.group);
    this.layers = {};
    for (const [kind, spec] of Object.entries(KINDS)) this.layers[kind] = new KindLayer(this.group, spec);
    this.vehicles = new Map(); // id -> state
    this.extras = new Map(); // emergency vehicle id -> {glow, label}
    this.evOrder = []; // emergency vehicle ids in order of appearance (for "follow")
    this.frameTime = 0;
    this.interval = 300; // ms between frames (measured)
    this.lastArrival = 0;
    this.lastT = null;
    this.stamp = 0;
    this.glowGeo = new THREE.CircleGeometry(1, 32).rotateX(-Math.PI / 2);
    this._m = new THREE.Matrix4();
    this._m2 = new THREE.Matrix4();
    this._p = new THREE.Vector3();
    this._q = new THREE.Quaternion();
    this._s = new THREE.Vector3();
    this._up = new THREE.Vector3(0, 1, 0);
  }

  /** Forget everything (new session). */
  clear() {
    this.vehicles.clear();
    for (const id of [...this.extras.keys()]) this._dropExtras(id);
    this.evOrder = [];
    this.lastT = null;
    for (const layer of Object.values(this.layers)) {
      layer.n = 0;
      layer.commit();
    }
  }

  /** frame.vehicles: [[id, x, y, angle, speed, kind], ...] */
  applyFrame(frame, now) {
    const t = frame.t;
    const restarted = this.lastT == null || t < this.lastT;
    const simDt = restarted ? 1 : Math.max(1e-3, t - this.lastT);
    if (this.lastT === t && !restarted) return; // same sim time (e.g. a frame re-sent after a command)
    this.lastT = t;
    if (this.lastArrival) {
      const dt = now - this.lastArrival;
      if (dt < 2500) this.interval = clamp(this.interval * 0.7 + dt * 0.3, 60, 1600);
    }
    this.lastArrival = now;
    const stamp = ++this.stamp;
    const counts = {};
    for (const row of frame.vehicles || []) {
      const [id, x, y, angle, speed, rawKind] = row;
      const kind = KINDS[rawKind] ? rawKind : 'car';
      let v = this.vehicles.get(id);
      if (!v) {
        v = { id, kind, x0: x, y0: y, h0: angle, x1: x, y1: y, h1: angle, rx: x, ry: y, rh: angle, speed, brake: speed < 0.5 };
        v.phase = hashString(id) % 8;
        v.paint = this._paintFor(id, kind);
        this.vehicles.set(id, v);
        if (KINDS[kind].emergency) this.evOrder.push(id);
      } else {
        // Snap instead of gliding after teleports or long fast-forward jumps.
        const jump = restarted || Math.hypot(x - v.rx, y - v.ry) > Math.max(45, simDt * 32);
        v.x0 = jump ? x : v.rx;
        v.y0 = jump ? y : v.ry;
        v.h0 = jump ? angle : v.rh;
        v.x1 = x;
        v.y1 = y;
        v.h1 = angle;
        v.brake = speed < 0.5 || (v.speed - speed) / simDt > 0.35; // stopped or decelerating
        v.speed = speed;
        if (v.kind !== kind) {
          v.kind = kind;
          v.paint = this._paintFor(id, kind);
        }
      }
      v.stamp = stamp;
      counts[kind] = (counts[kind] || 0) + 1;
    }
    for (const [id, v] of this.vehicles) {
      if (v.stamp !== stamp) {
        this.vehicles.delete(id);
        if (this.extras.has(id)) this._dropExtras(id);
      }
    }
    this.evOrder = this.evOrder.filter((id) => this.vehicles.has(id));
    for (const [kind, n] of Object.entries(counts)) this.layers[kind].ensure(n);
    this.frameTime = now;
  }

  _paintFor(id, kind) {
    const paints = KINDS[kind].paints;
    return new THREE.Color(paints[hashString(id) % paints.length]);
  }

  /** Called every animation frame. viewDistance scales vehicles up a little when zoomed far out. */
  update(now, viewDistance) {
    const a = clamp((now - this.frameTime) / (this.interval * 1.05), 0, 1);
    const s = clamp(1 + (viewDistance - 320) / 650, 1, 1.6);
    const bs = clamp(viewDistance / 170, 1, 4.5);
    const tick = Math.floor(now / 90);
    for (const layer of Object.values(this.layers)) layer.n = 0;
    const { _m: m, _p: p, _q: q, _s: sc, _up: up } = this;
    for (const v of this.vehicles.values()) {
      const x = v.x0 + (v.x1 - v.x0) * a;
      const y = v.y0 + (v.y1 - v.y0) * a;
      const h = lerpAngleDeg(v.h0, v.h1, a);
      v.rx = x;
      v.ry = y;
      v.rh = h;
      const layer = this.layers[v.kind];
      const half = (layer.spec.length * s) / 2;
      const r = h * DEG;
      const fx = Math.sin(r);
      const fy = Math.cos(r);
      p.set(x - fx * half, 0, -(y - fy * half));
      q.setFromAxisAngle(up, -r);
      sc.setScalar(s);
      m.compose(p, q, sc);
      const i = layer.n++;
      layer.paint.setMatrixAt(i, m);
      layer.paint.setColorAt(i, v.paint);
      layer.detail.setMatrixAt(i, m);
      layer.tail.setMatrixAt(i, m);
      layer.tail.setColorAt(i, v.brake ? BRAKE_ON : BRAKE_OFF);
      if (layer.red) {
        const k = (tick + v.phase) % 8;
        layer.red.setMatrixAt(i, m);
        layer.blue.setMatrixAt(i, m);
        layer.red.setColorAt(i, RED_PATTERN[k] ? FLASH_RED : FLASH_OFF);
        layer.blue.setColorAt(i, BLUE_PATTERN[k] ? FLASH_BLUE : FLASH_OFF);
        this._updateExtras(v, p, RED_PATTERN[k] ? 'red' : BLUE_PATTERN[k] ? 'blue' : null, viewDistance, now);
      }
      if (layer.beacon) {
        // A small blue diamond above every car whose navigation app shares data.
        const bob = Math.sin(now / 420 + v.phase) * 0.15;
        q.setFromAxisAngle(up, now / 700 + v.phase);
        sc.setScalar(bs);
        p.set(x - fx * half, 1.75 * s + 0.45 * bs + bob, -(y - fy * half));
        this._m2.compose(p, q, sc);
        layer.beacon.setMatrixAt(i, this._m2);
      }
    }
    for (const layer of Object.values(this.layers)) layer.commit();
  }

  _updateExtras(v, center, flash, viewDistance, now) {
    let ex = this.extras.get(v.id);
    if (!ex) {
      const glow = new THREE.Mesh(
        this.glowGeo,
        new THREE.MeshBasicMaterial({ map: getGlowTexture(), color: '#ff3030', transparent: true, opacity: 0.85, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false }),
      );
      glow.renderOrder = 4;
      const kindColor = v.kind === 'firetruck' ? 'rgba(170,20,20,0.92)' : 'rgba(200,30,40,0.92)';
      const label = makeLabel(vehicleLabel(v.id), { fontSize: 16, px: 17, background: kindColor, border: 'rgba(255,255,255,0.6)' });
      this.group.add(glow, label);
      ex = { glow, label };
      this.extras.set(v.id, ex);
    }
    const r = 7 * clamp(viewDistance / 260, 1, 5);
    ex.glow.position.set(center.x, 0.12, center.z);
    ex.glow.scale.set(r, 1, r);
    if (flash) ex.glow.material.color.set(flash === 'red' ? '#ff2a2a' : '#2a6bff');
    ex.glow.material.opacity = 0.55 + 0.3 * Math.sin(now / 120);
    ex.label.position.set(center.x, 7, center.z);
  }

  _dropExtras(id) {
    const ex = this.extras.get(id);
    if (!ex) return;
    this.group.remove(ex.glow, ex.label);
    ex.glow.material.dispose();
    ex.label.userData.dispose();
    this.extras.delete(id);
  }

  /** Where a vehicle is drawn right now (SUMO coords), for the follow camera. */
  pose(id) {
    const v = this.vehicles.get(id);
    return v ? { x: v.rx, y: v.ry, heading: v.rh, speed: v.speed, kind: v.kind } : null;
  }

  /** The most recently dispatched emergency vehicle still on the road. */
  latestEmergency() {
    return this.evOrder.length ? this.evOrder[this.evOrder.length - 1] : null;
  }

  count() {
    return this.vehicles.size;
  }
}
