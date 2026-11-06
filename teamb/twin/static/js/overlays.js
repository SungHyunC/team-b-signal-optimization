// Overlays drawn on top of the city from frame data. Each overlay is a small class:
//
//   constructor(ctx)        ctx = {scene, geometry, index, view}
//   update(frame)           called for every frame from the server
//   animate(now, dt)        called every animation frame (smooth motion, blinking)
//   reset()                 optional: a new session started
//
// To add one, write a class like these and append it to OVERLAYS at the bottom.
import * as THREE from 'three';
import { approachFrame, clamp, DEG, getGlowTexture, makeLabel, APPROACH_NAMES } from './util.js';
import { addKo, t } from './i18n.js';

addKo({
  FLOODED: '침수',
  SINKHOLE: '싱크홀',
  CRASH: '사고',
  'EARTHQUAKE: BRIDGE DAMAGE': '지진: 다리 손상',
  'EARTHQUAKE: DEBRIS': '지진: 잔해',
  'ROAD CLOSED · {cause}\n{edge}': '도로 폐쇄 · {cause}\n{edge}',
  'FAKE DATA': '가짜 데이터',
  'FAKE NAV DATA · {n} phantom phones\n{junction} {side} approach': '가짜 내비 데이터 · 가짜 휴대폰 {n}대\n{junction} {side} 진입로',
  'FAKE DATA SUSPECTED': '가짜 데이터 의심',
  'FAKE DATA SUSPECTED\nprobes say {probe} queued · loops see {loops}': '가짜 데이터 의심\n내비 데이터 대기 {probe}대 · 루프 감지기 {loops}대',
});

const flatPlane = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);

/** Center line, direction and width of an edge from its lanes (straight edges). */
function edgeFrame(index, edgeId) {
  const lanes = index.edgeLanes.get(edgeId);
  if (!lanes || !lanes.length) return null;
  const avg = (pick) => {
    const pts = lanes.map(pick);
    return [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length];
  };
  const p0 = avg((l) => l.shape[0]);
  const p1 = avg((l) => l.shape[l.shape.length - 1]);
  const len = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]) || 1;
  const dx = (p1[0] - p0[0]) / len;
  const dy = (p1[1] - p0[1]) / len;
  const heading = (Math.atan2(dx, dy) / DEG + 360) % 360;
  const width = lanes.reduce((s, l) => s + l.width, 0);
  return { p0, p1, len, dx, dy, rx: dy, ry: -dx, heading, width };
}

// --- queue heat strips ------------------------------------------------------------
/** A strip on each approach as long as its queue (kpi.queues), green → yellow → red. */
export class QueueOverlay {
  constructor({ scene, geometry, index }) {
    this.items = [];
    const low = new THREE.Color('#22c55e');
    const mid = new THREE.Color('#fbbf24');
    const high = new THREE.Color('#ef4444');
    this.ramp = (k) => (k < 0.5 ? low.clone().lerp(mid, k * 2) : mid.clone().lerp(high, (k - 0.5) * 2));
    for (const [j, tls] of Object.entries(geometry.tls)) {
      for (const side of Object.keys(tls.approaches)) {
        const a = approachFrame(index, j, side);
        const mat = new THREE.MeshBasicMaterial({ color: '#22c55e', transparent: true, opacity: 0.5, depthWrite: false, toneMapped: false });
        const mesh = new THREE.Mesh(flatPlane, mat);
        mesh.rotation.y = -a.heading * DEG;
        mesh.visible = false;
        mesh.renderOrder = 2;
        scene.add(mesh);
        this.items.push({ j, side, a, mesh, target: 0, len: 0 });
      }
    }
  }

  update(frame) {
    const queues = frame.kpi && frame.kpi.queues;
    if (!queues) return;
    for (const it of this.items) {
      const q = (queues[it.j] && queues[it.j][it.side]) || 0;
      it.target = Math.min((q * 7.0) / it.a.nLanes, it.a.length - 8); // 7 m per queued car, per lane
    }
  }

  animate(now, dt) {
    for (const it of this.items) {
      it.len += (it.target - it.len) * Math.min(1, dt * 3);
      const show = it.len > 1;
      it.mesh.visible = show;
      if (!show) continue;
      const c = 4.6 + it.len / 2; // starts just upstream of the colored stop bar
      const [sx, sy] = it.a.stop;
      it.mesh.position.set(sx - it.a.dx * c, 0.07, -(sy - it.a.dy * c));
      it.mesh.scale.set(Math.max(1, it.a.width - 0.5), 1, it.len);
      it.mesh.material.color.copy(this.ramp(clamp(it.len / 110, 0, 1)));
    }
  }

  reset() {
    for (const it of this.items) {
      it.target = it.len = 0;
      it.mesh.visible = false;
    }
  }
}

// --- road closures: barriers + flood water / sinkhole / crash -------------------------------
function rippleTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  g.fillStyle = '#ffffff';
  g.fillRect(0, 0, 128, 128);
  g.strokeStyle = 'rgba(150,190,230,0.55)';
  g.lineWidth = 2;
  for (let i = 0; i < 22; i++) {
    const x = Math.random() * 128;
    const y = Math.random() * 128;
    g.beginPath();
    g.ellipse(x, y, 6 + Math.random() * 14, 2 + Math.random() * 3, 0, 0, Math.PI * 2);
    g.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function barricadeGeometry() {
  // US "Type III" barricade: two legs, three striped boards; long axis along local x.
  const parts = [];
  const add = (w, h, d, x, y, z, color) => {
    const g = new THREE.BoxGeometry(w, h, d).translate(x, y, z).toNonIndexed();
    const col = new THREE.Color(color);
    const arr = new Float32Array(g.attributes.position.count * 3);
    for (let i = 0; i < arr.length; i += 3) arr.set([col.r, col.g, col.b], i);
    g.setAttribute('color', new THREE.BufferAttribute(arr, 3));
    parts.push(g);
  };
  add(0.08, 1.35, 0.5, -1.0, 0.675, 0, '#d8d8d8');
  add(0.08, 1.35, 0.5, 1.0, 0.675, 0, '#d8d8d8');
  for (const y of [0.55, 0.88, 1.21]) {
    for (let k = 0; k < 6; k++) add(0.4, 0.2, 0.05, -1.0 + 0.2 + k * 0.4, y, 0.04, k % 2 ? '#f4f4f4' : '#ff6a13');
  }
  return mergeParts(parts);
}

function mergeParts(parts) {
  // Small local merge (avoids importing BufferGeometryUtils here).
  let count = 0;
  for (const p of parts) count += p.attributes.position.count;
  const pos = new Float32Array(count * 3);
  const nrm = new Float32Array(count * 3);
  const col = new Float32Array(count * 3);
  let o = 0;
  for (const p of parts) {
    pos.set(p.attributes.position.array, o);
    nrm.set(p.attributes.normal.array, o);
    col.set(p.attributes.color.array, o);
    o += p.attributes.position.array.length;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return g;
}

export class ClosureOverlay {
  constructor({ scene, index }) {
    this.scene = scene;
    this.index = index;
    this.items = new Map(); // edge -> {group, water, lights, tex}
    this.ripple = rippleTexture();
    this.barricade = barricadeGeometry();
    this.barricadeMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6 });
    this.amberOn = new THREE.MeshBasicMaterial({ color: '#ffb020', toneMapped: false });
    this.amberOff = new THREE.MeshStandardMaterial({ color: '#4a3a10' });
    this.coneGeo = new THREE.ConeGeometry(0.22, 0.75, 10).translate(0, 0.375, 0);
    this.coneMat = new THREE.MeshStandardMaterial({ color: '#ff6a13', roughness: 0.6 });
    // Shared by every closure (closures come and go with every seek of the online demo): only
    // the per-closure water texture, water material and label are created and disposed per item.
    this.lampGeo = new THREE.SphereGeometry(0.1, 8, 6);
    this.holeGeo = new THREE.CircleGeometry(1, 28).rotateX(-Math.PI / 2);
    this.holeMat = new THREE.MeshStandardMaterial({ color: '#16110d', roughness: 1 });
    this.rimGeo = new THREE.RingGeometry(1, 1.22, 28).rotateX(-Math.PI / 2);
    this.rimMat = new THREE.MeshStandardMaterial({ color: '#6b5843', roughness: 1 });
  }

  update(frame) {
    const closures = frame.closures || [];
    const open = new Set(this.items.keys());
    for (const c of closures) {
      open.delete(c.edge);
      if (!this.items.has(c.edge)) {
        const item = this._build(c);
        if (item) this.items.set(c.edge, item);
      }
    }
    for (const edge of open) this._remove(edge);
  }

  _build(closure) {
    const f = edgeFrame(this.index, closure.edge);
    if (!f) return null;
    const cause = closure.cause || 'flood';
    const group = new THREE.Group();
    group.name = `closure-${closure.edge}`;
    const mid = [(f.p0[0] + f.p1[0]) / 2, (f.p0[1] + f.p1[1]) / 2];
    let water = null;
    let tex = null;
    if (cause === 'flood') {
      tex = this.ripple.clone();
      tex.needsUpdate = true;
      tex.repeat.set((f.width + 1.6) / 7, (f.len - 4) / 7);
      water = new THREE.Mesh(
        flatPlane,
        new THREE.MeshStandardMaterial({ color: '#3a7cc0', map: tex, transparent: true, opacity: 0.8, roughness: 0.08, metalness: 0.35, depthWrite: false }),
      );
      // From just short of the center line to a little over the curb (the closed direction only).
      const shift = 0.47;
      water.position.set(mid[0] + f.rx * shift, 0.1, -(mid[1] + f.ry * shift));
      water.rotation.y = -f.heading * DEG;
      water.scale.set(f.width + 0.65, 1, f.len - 4);
      water.renderOrder = 3;
      group.add(water);
    }
    if (cause !== 'flood') {
      // Sinkhole (or crash site) in the middle of the closed lanes, ringed by cones. The local
      // frame follows the edge: x = across the lanes (to the right), z = along the road.
      const site = new THREE.Group();
      site.position.set(mid[0], 0, -mid[1]);
      site.rotation.y = -f.heading * DEG;
      if (cause === 'sinkhole') {
        const hole = new THREE.Mesh(this.holeGeo, this.holeMat);
        hole.position.y = 0.09;
        hole.scale.set(f.width * 0.4, 1, f.width * 0.85);
        const rim = new THREE.Mesh(this.rimGeo, this.rimMat);
        rim.position.y = 0.095;
        rim.scale.copy(hole.scale);
        site.add(hole, rim);
      }
      for (let k = 0; k < 12; k++) {
        const ang = (k / 12) * Math.PI * 2;
        const cone = new THREE.Mesh(this.coneGeo, this.coneMat);
        cone.position.set(Math.cos(ang) * f.width * 0.47, 0.03, Math.sin(ang) * f.width * 1.25);
        cone.castShadow = true;
        site.add(cone);
      }
      group.add(site);
    }
    const lights = [];
    const n = Math.max(1, Math.ceil(f.width / 2.5));
    for (const along of [2.5, f.len - 2.5]) {
      const cx = f.p0[0] + f.dx * along;
      const cy = f.p0[1] + f.dy * along;
      for (let k = 0; k < n; k++) {
        const off = -f.width / 2 + (f.width / n) * (k + 0.5);
        const b = new THREE.Mesh(this.barricade, this.barricadeMat);
        b.position.set(cx + f.rx * off, 0.03, -(cy + f.ry * off));
        b.rotation.y = -f.heading * DEG;
        b.scale.setScalar(Math.min(1, f.width / n / 2.3));
        b.castShadow = true;
        const lamp = new THREE.Mesh(this.lampGeo, this.amberOn);
        lamp.position.set(0, 1.42, 0);
        b.add(lamp);
        lights.push(lamp);
        group.add(b);
      }
    }
    const what =
      {
        flood: t('FLOODED'),
        sinkhole: t('SINKHOLE'),
        accident: t('CRASH'),
        // the earthquake scenario's causes (English: the cause in capitals, as for any other cause)
        'earthquake: bridge damage': t('EARTHQUAKE: BRIDGE DAMAGE'),
        'earthquake: debris': t('EARTHQUAKE: DEBRIS'),
      }[cause] || cause.toUpperCase();
    const label = makeLabel(t('ROAD CLOSED · {cause}\n{edge}', { cause: what, edge: closure.edge }), { fontSize: 15, px: 17, background: 'rgba(160,70,8,0.92)', border: 'rgba(255,200,120,0.8)' });
    label.position.set(mid[0], 9, -mid[1]);
    group.add(label);
    this.scene.add(group);
    return { group, water, tex, lights, label };
  }

  _remove(edge) {
    const item = this.items.get(edge);
    if (!item) return;
    this.scene.remove(item.group);
    // Everything else in the group (barricades, cones, lamps, sinkhole) uses the shared resources.
    item.label.userData.dispose();
    if (item.tex) item.tex.dispose();
    if (item.water) item.water.material.dispose();
    this.items.delete(edge);
  }

  animate(now) {
    const blink = Math.floor(now / 450) % 2 === 0;
    for (const item of this.items.values()) {
      if (item.tex) {
        item.tex.offset.x = Math.sin(now / 3000) * 0.08;
        item.tex.offset.y = (now / 9000) % 1;
        item.water.material.opacity = 0.74 + 0.06 * Math.sin(now / 700);
      }
      item.lights.forEach((l, i) => {
        l.material = (blink ? i % 2 === 0 : i % 2 === 1) ? this.amberOn : this.amberOff;
      });
    }
  }

  reset() {
    for (const edge of [...this.items.keys()]) this._remove(edge);
  }
}

// --- fake navigation data: phantom phones + "fake data suspected" alerts ---------------------
export class AttackOverlay {
  constructor({ scene, index, view }) {
    this.scene = scene;
    this.index = index;
    this.view = view;
    const phone = new THREE.BoxGeometry(0.85, 1.5, 0.12);
    this.phoneMat = new THREE.MeshBasicMaterial({ color: '#b070ff', transparent: true, opacity: 0.78, depthWrite: false, toneMapped: false });
    this.capacity = 256;
    this.phones = new THREE.InstancedMesh(phone, this.phoneMat, this.capacity);
    this.phones.count = 0;
    this.phones.frustumCulled = false;
    this.phones.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.phones.renderOrder = 5;
    scene.add(this.phones);
    this.positions = [];
    this.ring = new THREE.Mesh(
      new THREE.RingGeometry(0.82, 1, 48).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: '#b070ff', transparent: true, opacity: 0.7, depthWrite: false, toneMapped: false, side: THREE.DoubleSide }),
    );
    this.ring.visible = false;
    this.ring.renderOrder = 5;
    scene.add(this.ring);
    this.attackLabel = makeLabel(t('FAKE DATA'), { fontSize: 15, px: 17, background: 'rgba(88,28,160,0.92)', border: 'rgba(220,180,255,0.8)' });
    this.attackLabel.visible = false;
    scene.add(this.attackLabel);
    this.alertLabels = new Map(); // "J2:N" -> {label, until}
    this._m = new THREE.Matrix4();
    this._q = new THREE.Quaternion();
    this._p = new THREE.Vector3();
    this._s = new THREE.Vector3();
    this._up = new THREE.Vector3(0, 1, 0);
  }

  update(frame) {
    this.positions = frame.phantoms || [];
    if (this.positions.length > this.capacity) {
      const old = this.phones;
      this.scene.remove(old);
      old.dispose(); // frees its instance buffers on the GPU (the shared geometry stays)
      this.capacity = this.positions.length * 2;
      this.phones = new THREE.InstancedMesh(old.geometry, this.phoneMat, this.capacity);
      this.phones.count = 0;
      this.phones.frustumCulled = false;
      this.phones.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      this.phones.renderOrder = 5;
      this.scene.add(this.phones);
    }
    const attack = frame.attack;
    if (attack && this.index.tls[attack.junction] && this.index.tls[attack.junction].approaches[attack.approach]) {
      const a = approachFrame(this.index, attack.junction, attack.approach);
      const c = 30;
      this.ring.position.set(a.stop[0] - a.dx * c, 0.12, -(a.stop[1] - a.dy * c));
      this.ring.visible = true;
      this.attackLabel.visible = true;
      this.attackLabel.position.set(a.stop[0] - a.dx * c, 13, -(a.stop[1] - a.dy * c));
      // APPROACH_NAMES is already in the current language.
      this.attackLabel.userData.setText(
        t('FAKE NAV DATA · {n} phantom phones\n{junction} {side} approach', {
          n: attack.n,
          junction: attack.junction,
          side: APPROACH_NAMES[attack.approach] || attack.approach,
        }),
      );
    } else {
      this.ring.visible = false;
      this.attackLabel.visible = false;
    }
    // Alerts flicker step to step; keep each label up for a few seconds after the last one.
    const now = performance.now();
    for (const alert of frame.alerts || []) {
      if (!alert.junction || !this.index.tls[alert.junction] || !this.index.tls[alert.junction].approaches[alert.approach]) continue;
      const key = `${alert.junction}:${alert.approach}`;
      let entry = this.alertLabels.get(key);
      if (!entry) {
        const a = approachFrame(this.index, alert.junction, alert.approach);
        const label = makeLabel(t('FAKE DATA SUSPECTED'), { fontSize: 15, px: 17, background: 'rgba(170,20,30,0.94)', border: 'rgba(255,170,170,0.9)' });
        // Further up the approach than the attack label (30 m) so the two never overlap.
        label.position.set(a.stop[0] - a.dx * 75, 6, -(a.stop[1] - a.dy * 75));
        this.scene.add(label);
        entry = { label };
        this.alertLabels.set(key, entry);
      }
      const probe = alert.probe_queue != null ? Math.round(alert.probe_queue) : '?';
      entry.label.userData.setText(t('FAKE DATA SUSPECTED\nprobes say {probe} queued · loops see {loops}', { probe, loops: alert.detector_queue ?? '?' }));
      entry.until = now + 4000;
    }
  }

  animate(now) {
    const dist = this.view.viewDistance();
    const s = clamp(dist / 230, 1, 4);
    const cam = this.view.camera.position;
    const { _m: m, _q: q, _p: p, _s: sc, _up: up } = this;
    sc.setScalar(s);
    this.positions.forEach(([x, y], i) => {
      if (i >= this.capacity) return;
      p.set(x, 1.4 * s + Math.sin(now / 380 + i * 0.7) * 0.25, -y);
      q.setFromAxisAngle(up, Math.atan2(cam.x - p.x, cam.z - p.z)); // face the camera
      m.compose(p, q, sc);
      this.phones.setMatrixAt(i, m);
    });
    this.phones.count = Math.min(this.positions.length, this.capacity);
    this.phones.instanceMatrix.needsUpdate = true;
    this.phoneMat.opacity = 0.6 + 0.25 * Math.sin(now / 260);
    if (this.ring.visible) {
      const k = (now % 1600) / 1600;
      const r = 12 + 26 * k;
      this.ring.scale.set(r, 1, r);
      this.ring.material.opacity = 0.75 * (1 - k);
    }
    for (const [key, entry] of this.alertLabels) {
      if (now > entry.until) {
        this.scene.remove(entry.label);
        entry.label.userData.dispose();
        this.alertLabels.delete(key);
      } else {
        entry.label.visible = Math.floor(now / 500) % 4 !== 3; // gentle blink
      }
    }
  }

  reset() {
    this.positions = [];
    this.phones.count = 0;
    this.ring.visible = false;
    this.attackLabel.visible = false;
    for (const entry of this.alertLabels.values()) {
      this.scene.remove(entry.label);
      entry.label.userData.dispose();
    }
    this.alertLabels.clear();
  }
}

// --- emergency preemption: pulsing ring around the junction ------------------------------
export class PreemptionOverlay {
  constructor({ scene, geometry }) {
    this.rings = new Map();
    for (const [j, tls] of Object.entries(geometry.tls)) {
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.86, 1, 64).rotateX(-Math.PI / 2),
        new THREE.MeshBasicMaterial({ color: '#ff3030', transparent: true, opacity: 0.8, depthWrite: false, toneMapped: false, side: THREE.DoubleSide }),
      );
      ring.position.set(tls.x, 0.14, -tls.y);
      ring.visible = false;
      ring.renderOrder = 4;
      const glow = new THREE.Mesh(
        new THREE.CircleGeometry(1, 48).rotateX(-Math.PI / 2),
        new THREE.MeshBasicMaterial({ map: getGlowTexture(), color: '#ff3030', transparent: true, opacity: 0.5, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false }),
      );
      glow.position.set(tls.x, 0.13, -tls.y);
      glow.scale.set(30, 1, 30);
      glow.visible = false;
      scene.add(ring, glow);
      this.rings.set(j, { ring, glow });
    }
  }

  update(frame) {
    const active = new Set(frame.preempting || []);
    for (const [j, r] of this.rings) r.ring.visible = r.glow.visible = active.has(j);
  }

  animate(now) {
    const red = Math.floor(now / 360) % 2 === 0;
    const k = (now % 1200) / 1200;
    for (const { ring, glow } of this.rings.values()) {
      if (!ring.visible) continue;
      const r = 14 + 6 * k;
      ring.scale.set(r, 1, r);
      ring.material.opacity = 0.9 - 0.5 * k;
      ring.material.color.set(red ? '#ff3030' : '#2f6bff');
      glow.material.color.set(red ? '#ff3030' : '#2f6bff');
    }
  }

  reset() {
    for (const r of this.rings.values()) r.ring.visible = r.glow.visible = false;
  }
}

export const OVERLAYS = [QueueOverlay, ClosureOverlay, AttackOverlay, PreemptionOverlay];
