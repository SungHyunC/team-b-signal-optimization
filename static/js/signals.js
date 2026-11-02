// Signal poles with mast arms and 3-lamp heads at every approach, plus a colored stop bar on the
// road so the state is readable from the overview camera. update(frame.signals) lights the lamps
// from signals[J].colors[approach] ('G' | 'Y' | 'R').
//
// The hardware that never changes (poles, arms, housings, backplates, visors) is baked into ONE
// merged mesh to keep draw calls low; only lamps, glows and stop bars are separate objects
// because they change color.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { approachFrame, DEG, getGlowTexture, makeLabel } from './util.js';
import { addKo, t } from './i18n.js';

addKo({ '{junction} · EV priority': '{junction} · 긴급차량 우선 신호' });

const LAMP_ON = { R: '#ff3b30', Y: '#ffc21a', G: '#1cf28f' };
const LAMP_OFF = { R: '#3a1513', Y: '#3a3012', G: '#103424' };
const BAR = { R: '#ff3b3b', Y: '#ffc533', G: '#22e07a' };
const LAMP_Y = { R: 0.42, Y: 0, G: -0.42 }; // lamp height inside the head (red on top)
const HEAD_Y = 5.6; // head center above the road (m)
const ARM_Y = 6.32;
const METAL = '#4b535d';
const HOUSING = '#1a1e24';
const PLATE = '#d3ab0a'; // yellow retroreflective backplate border (US style)

/** Copy of a part's geometry in world space with a vertex color, ready to be merged. */
function bake(geometry, object, color) {
  object.updateMatrixWorld(true);
  const g = geometry.clone().applyMatrix4(object.matrixWorld).toNonIndexed();
  g.deleteAttribute('uv');
  const c = new THREE.Color(color);
  const arr = new Float32Array(g.attributes.position.count * 3);
  for (let i = 0; i < arr.length; i += 3) arr.set([c.r, c.g, c.b], i);
  g.setAttribute('color', new THREE.BufferAttribute(arr, 3));
  return g;
}

export class SignalLayer {
  constructor(scene, geo, index) {
    this.group = new THREE.Group();
    this.group.name = 'signals';
    this.heads = new Map(); // "J1:W" -> {lamps, glow, bar, state}
    this.labels = new Map(); // "J1" -> sprite

    this.onMat = {};
    this.offMat = {};
    this.glowMat = {};
    this.barMat = {};
    for (const k of ['R', 'Y', 'G']) {
      this.onMat[k] = new THREE.MeshBasicMaterial({ color: LAMP_ON[k], toneMapped: false });
      this.offMat[k] = new THREE.MeshStandardMaterial({ color: LAMP_OFF[k], roughness: 0.35, metalness: 0.1 });
      this.glowMat[k] = new THREE.SpriteMaterial({
        map: getGlowTexture(), color: LAMP_ON[k], blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false,
      });
      this.barMat[k] = new THREE.MeshBasicMaterial({ color: BAR[k], transparent: true, opacity: 0.9, depthWrite: false, toneMapped: false });
    }
    const poleGeo = new THREE.CylinderGeometry(0.13, 0.17, 6.9, 8).translate(0, 3.45, 0);
    const housingGeo = new THREE.BoxGeometry(0.5, 1.34, 0.36);
    const plateGeo = new THREE.BoxGeometry(0.84, 1.66, 0.04).translate(0, 0, -0.2);
    const hangerGeo = new THREE.BoxGeometry(0.06, 0.14, 0.06);
    const visorGeo = new THREE.BoxGeometry(0.42, 0.035, 0.22);
    const lampGeo = new THREE.CircleGeometry(0.16, 18);
    const barGeo = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
    const hardware = []; // baked static parts
    const probe = new THREE.Object3D(); // positions parts before baking

    for (const [j, tls] of Object.entries(geo.tls)) {
      for (const side of Object.keys(tls.approaches)) {
        const a = approachFrame(index, j, side);
        const [sx, sy] = a.stop;
        const back = 1.3; // poles stand just before the stop line
        const off = a.width / 2 + 1.35; // ... on the right-hand sidewalk
        const px = sx + a.rx * off - a.dx * back;
        const py = sy + a.ry * off - a.dy * back;
        probe.position.set(px, 0, -py);
        probe.rotation.set(0, 0, 0);
        hardware.push(bake(poleGeo, probe, METAL));

        // Mast arm from the pole over the approach lanes (a box pointed with lookAt).
        const hx = sx - a.dx * back;
        const hy = sy - a.dy * back;
        const armLen = off + 0.15;
        probe.position.set((px + hx) / 2, ARM_Y, -(py + hy) / 2);
        probe.lookAt(hx, ARM_Y, -hy);
        hardware.push(bake(new THREE.BoxGeometry(0.11, 0.11, armLen), probe, METAL));

        // Head: faces the approaching drivers (local +z points upstream).
        const head = new THREE.Group();
        head.position.set(hx, HEAD_Y, -hy);
        head.rotation.y = -a.heading * DEG;
        head.updateMatrixWorld(true);
        const part = (geometry, x, y, z, color) => {
          const m = new THREE.Mesh(geometry);
          m.position.set(x, y, z);
          head.add(m);
          hardware.push(bake(geometry, m, color));
          head.remove(m);
        };
        part(housingGeo, 0, 0, 0, HOUSING);
        part(plateGeo, 0, 0, 0, PLATE);
        part(hangerGeo, 0, ARM_Y - HEAD_Y, 0, METAL);
        const lamps = {};
        for (const k of ['R', 'Y', 'G']) {
          part(visorGeo, 0, LAMP_Y[k] + 0.19, 0.29, HOUSING);
          const lamp = new THREE.Mesh(lampGeo, this.offMat[k]);
          lamp.position.set(0, LAMP_Y[k], 0.185);
          head.add(lamp);
          lamps[k] = lamp;
        }
        const glow = new THREE.Sprite(this.glowMat.R);
        glow.scale.set(1.7, 1.7, 1);
        glow.position.set(0, LAMP_Y.R, 0.4);
        head.add(glow);

        // Colored bar on the road just upstream of the stop line.
        const bar = new THREE.Mesh(barGeo, this.barMat.R);
        const c = 2.8; // center 2.8 m before the stop point, 3.2 m long
        bar.position.set(sx - a.dx * c, 0.075, -(sy - a.dy * c));
        bar.rotation.y = -a.heading * DEG;
        bar.scale.set(Math.max(1, a.width - 0.3), 1, 3.2);
        bar.renderOrder = 3;

        this.group.add(head, bar);
        this.heads.set(`${j}:${side}`, { lamps, glow, bar, state: null });
      }
      const label = makeLabel(j, { fontSize: 20, px: 20, background: 'rgba(8,13,24,0.8)', border: 'rgba(255,255,255,0.25)' });
      label.position.set(tls.x, 24, -tls.y);
      this.group.add(label);
      this.labels.set(j, label);
    }
    const hw = new THREE.Mesh(mergeGeometries(hardware), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5, metalness: 0.45 }));
    hw.name = 'signal-hardware';
    hw.castShadow = true;
    this.group.add(hw);
    scene.add(this.group);
  }

  /** frame.signals: {J1: {colors: {W: 'G', ...}, preempted_by, ...}} */
  update(signals) {
    if (!signals) return;
    for (const [j, s] of Object.entries(signals)) {
      for (const [side, color] of Object.entries(s.colors || {})) {
        const head = this.heads.get(`${j}:${side}`);
        if (!head || head.state === color || !LAMP_ON[color]) continue;
        head.state = color;
        for (const k of ['R', 'Y', 'G']) head.lamps[k].material = k === color ? this.onMat[k] : this.offMat[k];
        head.glow.material = this.glowMat[color];
        head.glow.position.y = LAMP_Y[color];
        head.bar.material = this.barMat[color];
      }
      const label = this.labels.get(j);
      if (label) {
        const pre = !!s.preempted_by;
        label.userData.setText(pre ? t('{junction} · EV priority', { junction: j }) : j, {
          background: pre ? 'rgba(150,20,28,0.9)' : 'rgba(8,13,24,0.8)',
          border: pre ? 'rgba(255,160,160,0.7)' : 'rgba(255,255,255,0.25)',
        });
      }
    }
  }
}
