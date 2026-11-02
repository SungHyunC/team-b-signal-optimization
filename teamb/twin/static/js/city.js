// The city around the corridor: blocks with curbs and sidewalks, low-poly buildings, trees and
// street lights. It is generated from the road layout with a fixed seed, so it looks the same on
// every load (and moves with the network if the network changes).
//
// Blocks come from "road bands": every straight edge gives a strip of asphalt; touching strips
// are merged into whole streets, and the spaces between streets are the blocks.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { range, seededRandom } from './util.js';

const SEED = 20261105; // presentation day
const EXTEND_M = 260; // the city continues this far past the network edge (matches roads.js)
const SIDEWALK_M = 4.0;
const CURB_H = 0.16;
const CORNER_R = 4.0; // matches the rounded corners of the SUMO junction pads
const TILE_W = 3.6; // one window bay (m) ...
const TILE_H = 3.4; // ... per floor (m)

const STYLES = {
  // Blocks on the arterial between the first and last signal: the "downtown" frontage.
  downtown: {
    width: [18, 42], depth: [16, 34], gap: [3, 9], vacancy: 0.07, setback: 1.0,
    height: (rand, facesArterial) => (facesArterial ? 14 + 48 * Math.pow(rand(), 2.0) : 10 + 24 * Math.pow(rand(), 1.6)),
    colors: ['#d8d2c6', '#c9c1b3', '#b8c2c9', '#a7b2bb', '#cfc4b2', '#9ea8b0', '#c3b29f', '#e1dcd2', '#b5a690', '#cdd3d8'],
  },
  midtown: {
    width: [14, 30], depth: [12, 24], gap: [4, 12], vacancy: 0.18, setback: 1.5,
    height: (rand) => 7 + 17 * Math.pow(rand(), 1.4),
    colors: ['#d9cfbf', '#c8bba6', '#bfc6c9', '#d3c8b8', '#b9ab98', '#a99b88', '#c7c0b5', '#9b6b55'],
  },
  outer: {
    width: [10, 20], depth: [10, 16], gap: [7, 18], vacancy: 0.35, setback: 3.0,
    height: (rand) => 5 + 8 * rand(),
    colors: ['#e2d9c8', '#d6c7ae', '#c4b59c', '#cfd2cd', '#b7a68c', '#a87d62'],
  },
};
const GLASS = ['#8fa3b4', '#7b92a6', '#a6b6c3', '#6f8798', '#93a9b0'];

// --- road bands and blocks ----------------------------------------------------------
function roadBands(geo) {
  const byEdge = new Map();
  for (const lane of geo.lanes) {
    if (!byEdge.has(lane.edge)) byEdge.set(lane.edge, []);
    byEdge.get(lane.edge).push(lane);
  }
  const bands = [];
  for (const lanes of byEdge.values()) {
    let axis = null;
    let c0 = Infinity, c1 = -Infinity, a0 = Infinity, a1 = -Infinity;
    let straight = true;
    for (const l of lanes) {
      const xs = l.shape.map((p) => p[0]);
      const ys = l.shape.map((p) => p[1]);
      const spanX = Math.max(...xs) - Math.min(...xs);
      const spanY = Math.max(...ys) - Math.min(...ys);
      const ax = spanY < 0.5 ? 'h' : spanX < 0.5 ? 'v' : null;
      if (!ax || (axis && ax !== axis)) {
        straight = false;
        break;
      }
      axis = ax;
      const c = ax === 'h' ? ys[0] : xs[0];
      c0 = Math.min(c0, c - l.width / 2);
      c1 = Math.max(c1, c + l.width / 2);
      const along = ax === 'h' ? xs : ys;
      a0 = Math.min(a0, ...along);
      a1 = Math.max(a1, ...along);
    }
    if (straight && axis) bands.push({ axis, c0, c1, a0, a1 });
  }
  // Merge both directions of a street and its pieces on either side of a junction.
  for (let changed = true; changed; ) {
    changed = false;
    outer: for (let i = 0; i < bands.length; i++) {
      for (let j = i + 1; j < bands.length; j++) {
        const a = bands[i];
        const b = bands[j];
        if (a.axis === b.axis && a.c0 <= b.c1 + 0.5 && b.c0 <= a.c1 + 0.5 && a.a0 <= b.a1 + 30 && b.a0 <= a.a1 + 30) {
          bands[i] = { axis: a.axis, c0: Math.min(a.c0, b.c0), c1: Math.max(a.c1, b.c1), a0: Math.min(a.a0, b.a0), a1: Math.max(a.a1, b.a1) };
          bands.splice(j, 1);
          changed = true;
          break outer;
        }
      }
    }
  }
  return bands;
}

function cityBlocks(geo, bands) {
  const [bx0, by0, bx1, by1] = geo.bounds;
  const W = { x0: bx0 - EXTEND_M, x1: bx1 + EXTEND_M, y0: by0 - EXTEND_M, y1: by1 + EXTEND_M };
  for (const b of bands) {
    // Streets that reach the network edge continue to the edge of the drawn city.
    const [lo, hi, wlo, whi] = b.axis === 'h' ? [bx0, bx1, W.x0, W.x1] : [by0, by1, W.y0, W.y1];
    if (b.a0 <= lo + 1) b.a0 = wlo;
    if (b.a1 >= hi - 1) b.a1 = whi;
  }
  const vertical = bands.filter((b) => b.axis === 'v').sort((a, b) => a.c0 - b.c0);
  const horizontal = bands.filter((b) => b.axis === 'h');
  const cols = [];
  let x = W.x0;
  let roadW = false;
  for (const v of vertical) {
    cols.push([x, v.c0, roadW, true]);
    x = v.c1;
    roadW = true;
  }
  cols.push([x, W.x1, roadW, false]);

  const blocks = [];
  for (const [x0, x1, w, e] of cols) {
    if (x1 - x0 < 20) continue;
    const mid = (x0 + x1) / 2;
    const crossing = horizontal.filter((h) => h.a0 <= mid && h.a1 >= mid).sort((a, b) => a.c0 - b.c0);
    let y = W.y0;
    let south = null;
    for (const h of [...crossing, null]) {
      const yTop = h ? h.c0 : W.y1;
      if (yTop - y > 20) blocks.push({ x0, x1, y0: y, y1: yTop, road: { w, e, s: !!south, n: !!h }, south, north: h });
      if (h) {
        y = h.c1;
        south = h;
      }
    }
  }
  return { blocks, world: W, vertical, horizontal };
}

function blockShape(x0, y0, x1, y1, r) {
  const s = new THREE.Shape();
  s.moveTo(x0 + r.sw, y0);
  s.lineTo(x1 - r.se, y0);
  if (r.se) s.absarc(x1 - r.se, y0 + r.se, r.se, -Math.PI / 2, 0, false);
  s.lineTo(x1, y1 - r.ne);
  if (r.ne) s.absarc(x1 - r.ne, y1 - r.ne, r.ne, 0, Math.PI / 2, false);
  s.lineTo(x0 + r.nw, y1);
  if (r.nw) s.absarc(x0 + r.nw, y1 - r.nw, r.nw, Math.PI / 2, Math.PI, false);
  s.lineTo(x0, y0 + r.sw);
  if (r.sw) s.absarc(x0 + r.sw, y0 + r.sw, r.sw, Math.PI, Math.PI * 1.5, false);
  return s;
}

// --- buildings ------------------------------------------------------------------------
/**
 * The preset cameras look north at roughly 35–40°. A building hides the ground behind it for
 * about its own height divided by tan(elevation), so a building just south of an east–west
 * street would hide that street. Buildings therefore stay low right south of a street and step
 * up further away: the corridor stays visible and the skyline rises behind it.
 */
function heightCap(lot, streets) {
  let cap = Infinity;
  for (const b of streets) {
    if (b.a0 > lot.x1 || b.a1 < lot.x0) continue;
    const gap = b.c0 - lot.y1; // from the lot's north face to the street's south edge
    if (gap >= 0) cap = Math.min(cap, Math.max(4.5, 0.68 * (gap - 2)));
  }
  return cap;
}

function placeLots(block, styleName, arterial, streets, rand) {
  const S = STYLES[styleName];
  const inset = (side) => (block.road[side] ? SIDEWALK_M + S.setback : 3);
  const ix0 = block.x0 + inset('w');
  const ix1 = block.x1 - inset('e');
  const iy0 = block.y0 + inset('s');
  const iy1 = block.y1 - inset('n');
  if (ix1 - ix0 < 14 || iy1 - iy0 < 14) return [];
  const lots = [];
  const free = (r) => lots.every((o) => r.x1 + 2 < o.x0 || o.x1 + 2 < r.x0 || r.y1 + 2 < o.y0 || o.y1 + 2 < r.y0);
  const sides = ['s', 'n', 'w', 'e'].filter((s) => block.road[s]);
  for (const side of sides) {
    const alongX = side === 's' || side === 'n';
    const [a0, a1] = alongX ? [ix0, ix1] : [iy0, iy1];
    const maxDepth = (alongX ? iy1 - iy0 : ix1 - ix0) / 2 - 3;
    const facesArterial = (side === 's' && block.south === arterial) || (side === 'n' && block.north === arterial);
    let p = a0 + range(rand, 0, 5);
    while (p < a1 - 8) {
      const w = Math.min(range(rand, ...S.width), a1 - p);
      const d = Math.min(range(rand, ...S.depth), maxDepth);
      if (w >= 8 && d >= 8 && rand() >= S.vacancy) {
        const r =
          side === 's' ? { x0: p, x1: p + w, y0: iy0, y1: iy0 + d }
          : side === 'n' ? { x0: p, x1: p + w, y0: iy1 - d, y1: iy1 }
          : side === 'w' ? { x0: ix0, x1: ix0 + d, y0: p, y1: p + w }
          : { x0: ix1 - d, x1: ix1, y0: p, y1: p + w };
        if (free(r)) {
          r.h = Math.min(S.height(rand, facesArterial), heightCap(r, streets));
          const palette = r.h > 38 ? GLASS : S.colors;
          r.color = palette[Math.floor(rand() * palette.length)];
          lots.push(r);
        }
      }
      p += w + range(rand, ...S.gap);
    }
  }
  return lots;
}

/** Accumulates boxes with world-scaled window UVs and per-vertex tint into one geometry. */
class BoxBuilder {
  constructor() {
    this.pos = [];
    this.nrm = [];
    this.uv = [];
    this.col = [];
    this.idx = [];
  }

  face(corners, normal, uvs, color) {
    const base = this.pos.length / 3;
    for (let i = 0; i < 4; i++) {
      this.pos.push(...corners[i]);
      this.nrm.push(...normal);
      this.uv.push(...uvs[i]);
      this.col.push(color.r, color.g, color.b);
    }
    this.idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }

  /** Box in SUMO ground coords [x0,x1]×[y0,y1], from height h0 to h1. windows=false: plain color. */
  box(x0, x1, y0, y1, h0, h1, color, windows = true) {
    const z0 = -y1; // three.js z = -SUMO y
    const z1 = -y0;
    const U = (len) => (windows ? len / TILE_W : 0.001);
    const V = (h) => (windows ? h / TILE_H : 0.001);
    const flat = [0.03, 0.03]; // a spot of plain wall in the window texture
    const roof = color.clone().multiplyScalar(0.78);
    const hgt = h1 - h0;
    this.face([[x0, h1, z1], [x1, h1, z1], [x1, h1, z0], [x0, h1, z0]], [0, 1, 0], [flat, flat, flat, flat], roof);
    const sx = x1 - x0;
    const sz = z1 - z0;
    this.face([[x0, h0, z1], [x1, h0, z1], [x1, h1, z1], [x0, h1, z1]], [0, 0, 1], [[0, 0], [U(sx), 0], [U(sx), V(hgt)], [0, V(hgt)]], color);
    this.face([[x1, h0, z0], [x0, h0, z0], [x0, h1, z0], [x1, h1, z0]], [0, 0, -1], [[0, 0], [U(sx), 0], [U(sx), V(hgt)], [0, V(hgt)]], color);
    this.face([[x1, h0, z1], [x1, h0, z0], [x1, h1, z0], [x1, h1, z1]], [1, 0, 0], [[0, 0], [U(sz), 0], [U(sz), V(hgt)], [0, V(hgt)]], color);
    this.face([[x0, h0, z0], [x0, h0, z1], [x0, h1, z1], [x0, h1, z0]], [-1, 0, 0], [[0, 0], [U(sz), 0], [U(sz), V(hgt)], [0, V(hgt)]], color);
  }

  build() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.nrm, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    g.setIndex(this.idx);
    g.computeBoundingSphere();
    return g;
  }
}

function windowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  g.fillStyle = '#ffffff';
  g.fillRect(0, 0, 64, 64);
  const grad = g.createLinearGradient(0, 16, 0, 52);
  grad.addColorStop(0, '#6d8396');
  grad.addColorStop(1, '#2c3b4c');
  g.fillStyle = grad;
  g.fillRect(11, 16, 42, 34);
  g.fillStyle = 'rgba(255,255,255,0.22)';
  g.fillRect(11, 16, 42, 3);
  g.fillStyle = 'rgba(0,0,0,0.12)';
  g.fillRect(31, 16, 2, 34);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  return tex;
}

// --- trees and street lights (instanced) ---------------------------------------------------
function makeTrees(points, rand) {
  const n = points.length;
  const trunkGeo = new THREE.CylinderGeometry(0.16, 0.24, 2.6, 5).translate(0, 1.3, 0);
  const roundGeo = new THREE.IcosahedronGeometry(2.3, 0).translate(0, 4.1, 0);
  const coneGeo = new THREE.ConeGeometry(2.1, 5.2, 6).translate(0, 4.9, 0);
  const trunks = new THREE.InstancedMesh(trunkGeo, new THREE.MeshStandardMaterial({ color: '#6b5440', roughness: 1 }), n);
  const leafMat = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.9, flatShading: true });
  const nCone = points.filter((p) => p.cone).length;
  const rounds = new THREE.InstancedMesh(roundGeo, leafMat, Math.max(1, n - nCone));
  const cones = new THREE.InstancedMesh(coneGeo, leafMat, Math.max(1, nCone));
  const greens = ['#527d3c', '#5e8b45', '#456f35', '#6a9450', '#4f7a3f', '#62853f'].map((c) => new THREE.Color(c));
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  let ir = 0;
  let ic = 0;
  points.forEach((p, i) => {
    const s = p.scale;
    q.setFromAxisAngle(up, rand() * Math.PI * 2);
    m.compose(new THREE.Vector3(p.x, 0, -p.y), q, new THREE.Vector3(s, s * (0.9 + 0.25 * rand()), s));
    trunks.setMatrixAt(i, m);
    const color = greens[Math.floor(rand() * greens.length)];
    if (p.cone) {
      cones.setMatrixAt(ic, m);
      cones.setColorAt(ic++, color);
    } else {
      rounds.setMatrixAt(ir, m);
      rounds.setColorAt(ir++, color);
    }
  });
  rounds.count = ir;
  cones.count = ic;
  const group = new THREE.Group();
  group.name = 'trees';
  for (const mesh of [trunks, rounds, cones]) {
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    group.add(mesh);
  }
  return group;
}

function makeStreetLights(lights) {
  // Pole + arm + lamp merged into one instanced geometry; the arm reaches over the road (+x local).
  const pole = new THREE.CylinderGeometry(0.09, 0.13, 8, 6).translate(0, 4, 0);
  const arm = new THREE.BoxGeometry(2.4, 0.1, 0.12).translate(1.15, 7.9, 0);
  const lamp = new THREE.BoxGeometry(0.7, 0.16, 0.34).translate(2.25, 7.8, 0);
  const geo = mergeGeometries([pole, arm, lamp]);
  const mesh = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ color: '#5a626c', roughness: 0.6, metalness: 0.4 }), Math.max(1, lights.length));
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  lights.forEach((l, i) => {
    q.setFromAxisAngle(up, l.rot);
    m.compose(new THREE.Vector3(l.x, 0, -l.y), q, new THREE.Vector3(1, 1, 1));
    mesh.setMatrixAt(i, m);
  });
  mesh.count = lights.length;
  mesh.castShadow = true;
  mesh.name = 'street-lights';
  return mesh;
}

// --- the whole city ---------------------------------------------------------------------
export function buildCity(scene, geo) {
  const rand = seededRandom(SEED);
  const bands = roadBands(geo);
  const { blocks, vertical, horizontal } = cityBlocks(geo, bands);
  const arterial = horizontal.reduce((best, b) => (!best || b.c1 - b.c0 > best.c1 - best.c0 ? b : best), null);
  const netX = vertical.length ? [vertical[0].c0, vertical[vertical.length - 1].c1] : [-Infinity, Infinity];

  const slabs = [];
  const lawns = [];
  const boxes = new BoxBuilder();
  const roofUnits = new BoxBuilder();
  const treePts = [];
  const lights = [];

  for (const block of blocks) {
    const cx = (block.x0 + block.x1) / 2;
    const inside = cx >= netX[0] && cx <= netX[1];
    const onArterial = block.south === arterial || block.north === arterial;
    const style = inside && onArterial ? 'downtown' : inside || onArterial ? 'midtown' : 'outer';
    const { road } = block;
    const r = {
      sw: road.s && road.w ? CORNER_R : 0,
      se: road.s && road.e ? CORNER_R : 0,
      ne: road.n && road.e ? CORNER_R : 0,
      nw: road.n && road.w ? CORNER_R : 0,
    };
    // Curb + sidewalk slab.
    const slab = new THREE.ExtrudeGeometry(blockShape(block.x0, block.y0, block.x1, block.y1, r), { depth: CURB_H, bevelEnabled: false, curveSegments: 5 });
    slab.rotateX(-Math.PI / 2);
    slabs.push(slab);
    // Lawn inside the sidewalk ring.
    const ins = (side) => (road[side] ? SIDEWALK_M : 0);
    const lr = { sw: r.sw ? 2 : 0, se: r.se ? 2 : 0, ne: r.ne ? 2 : 0, nw: r.nw ? 2 : 0 };
    const lawn = new THREE.ShapeGeometry(blockShape(block.x0 + ins('w'), block.y0 + ins('s'), block.x1 - ins('e'), block.y1 - ins('n'), lr), 4);
    lawn.rotateX(-Math.PI / 2);
    lawn.translate(0, CURB_H + 0.02, 0);
    lawns.push(lawn);

    // Buildings along the street frontage.
    const lots = placeLots(block, style, arterial, horizontal, rand);
    for (const lot of lots) {
      const color = new THREE.Color(lot.color);
      boxes.box(lot.x0, lot.x1, lot.y0, lot.y1, CURB_H, CURB_H + lot.h, color, true);
      if (lot.h > 12 && rand() < 0.55) {
        // Rooftop units (HVAC, stair towers).
        const units = 1 + Math.floor(rand() * 3);
        for (let k = 0; k < units; k++) {
          const w = 2 + rand() * 4;
          const d = 2 + rand() * 4;
          const ux = range(rand, lot.x0 + 2, Math.max(lot.x0 + 2.1, lot.x1 - w - 2));
          const uy = range(rand, lot.y0 + 2, Math.max(lot.y0 + 2.1, lot.y1 - d - 2));
          const top = CURB_H + lot.h;
          roofUnits.box(ux, ux + w, uy, uy + d, top, top + 1.2 + rand() * 1.8, new THREE.Color('#9aa1a8'), false);
        }
      }
    }

    // Street trees on the sidewalk, away from the corners (sight lines at the junctions).
    for (const side of ['s', 'n', 'w', 'e']) {
      if (!road[side]) continue;
      const horizontalSide = side === 's' || side === 'n';
      const [a0, a1] = horizontalSide ? [block.x0, block.x1] : [block.y0, block.y1];
      const spacing = style === 'downtown' ? 17 : 14;
      for (let p = a0 + 15 + rand() * 6; p < a1 - 15; p += spacing + rand() * 6) {
        const inset = 1.7;
        const pt = side === 's' ? [p, block.y0 + inset] : side === 'n' ? [p, block.y1 - inset] : side === 'w' ? [block.x0 + inset, p] : [block.x1 - inset, p];
        treePts.push({ x: pt[0], y: pt[1], scale: 0.75 + rand() * 0.45, cone: false });
      }
      // Street lights along the arterial.
      if ((side === 's' && block.south === arterial) || (side === 'n' && block.north === arterial)) {
        for (let p = a0 + 22; p < a1 - 15; p += 36) {
          const y = side === 's' ? block.y0 + 0.6 : block.y1 - 0.6;
          // The arm (local +x) points over the road: north for a block's north side, south otherwise.
          lights.push({ x: p, y, rot: side === 'n' ? Math.PI / 2 : -Math.PI / 2 });
        }
      }
    }
    // Courtyard trees, away from the buildings.
    const tries = Math.min(70, Math.round(((block.x1 - block.x0) * (block.y1 - block.y0)) / 1200));
    for (let k = 0; k < tries; k++) {
      const x = range(rand, block.x0 + SIDEWALK_M + 4, block.x1 - SIDEWALK_M - 4);
      const y = range(rand, block.y0 + SIDEWALK_M + 4, block.y1 - SIDEWALK_M - 4);
      const clear = lots.every((o) => x < o.x0 - 4 || x > o.x1 + 4 || y < o.y0 - 4 || y > o.y1 + 4);
      if (clear) treePts.push({ x, y, scale: 0.8 + rand() * 0.7, cone: rand() < 0.35 });
    }
  }

  const group = new THREE.Group();
  group.name = 'city';
  const slabMesh = new THREE.Mesh(mergeGeometries(slabs), new THREE.MeshStandardMaterial({ color: '#b5b1a8', roughness: 0.95 }));
  slabMesh.receiveShadow = true;
  const lawnMesh = new THREE.Mesh(mergeGeometries(lawns), new THREE.MeshStandardMaterial({ color: '#6f8159', roughness: 1 }));
  lawnMesh.receiveShadow = true;
  const buildingMat = new THREE.MeshStandardMaterial({ map: windowTexture(), vertexColors: true, roughness: 0.82, metalness: 0.05 });
  const buildingMesh = new THREE.Mesh(boxes.build(), buildingMat);
  buildingMesh.castShadow = true;
  buildingMesh.receiveShadow = true;
  buildingMesh.name = 'buildings';
  const unitMesh = new THREE.Mesh(roofUnits.build(), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8 }));
  unitMesh.castShadow = true;
  group.add(slabMesh, lawnMesh, buildingMesh, unitMesh, makeTrees(treePts, rand), makeStreetLights(lights));
  scene.add(group);
  return { group, blocks };
}
