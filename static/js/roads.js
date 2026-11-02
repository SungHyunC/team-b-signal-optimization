// Roads from the SUMO lane shapes: asphalt, junction pads, US-style markings (white edge and
// lane lines, double yellow center line), stop lines and crosswalks at the signals, plus a
// short extension past the network edge so cars do not appear out of nowhere.
// buildRoads() also returns pickEdge(raycaster) for "click a road to close it".
import * as THREE from 'three';
import { approachFrame, rightOf } from './util.js';

const H = { pad: 0.02, lane: 0.03, mark: 0.05 }; // heights above the ground (m)
const EXTENSION_M = 260; // asphalt drawn past dead ends (no traffic there, it just looks right)
const DASH_M = 3; // US lane line: 10 ft dash ...
const GAP_M = 9; // ... 30 ft gap
const SOLID_BEFORE_STOP_M = 30; // lane lines turn solid before a signal

/** Collects flat quads (SUMO coordinates in, three.js out) into one BufferGeometry. */
class FlatBuilder {
  constructor() {
    this.pos = [];
    this.idx = [];
    this.tags = []; // one entry per triangle (used for picking)
  }

  quad(p, h, tag = null) {
    // Make the quad counter-clockwise seen from above (shoelace sign) so it faces up.
    let area = 0;
    for (let i = 0; i < 4; i++) {
      const a = p[i];
      const b = p[(i + 1) % 4];
      area += a[0] * b[1] - b[0] * a[1];
    }
    const q = area < 0 ? [p[0], p[3], p[2], p[1]] : p;
    const base = this.pos.length / 3;
    for (const v of q) this.pos.push(v[0], h, -v[1]);
    this.idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
    this.tags.push(tag, tag);
  }

  /** A strip along a polyline between offsets a and b (meters to the right of the line). */
  strip(points, a, b, h, tag = null) {
    for (let i = 0; i < points.length - 1; i++) {
      const [x0, y0] = points[i];
      const [x1, y1] = points[i + 1];
      const len = Math.hypot(x1 - x0, y1 - y0);
      if (len < 1e-6) continue;
      const [rx, ry] = rightOf((x1 - x0) / len, (y1 - y0) / len);
      this.quad(
        [
          [x0 + rx * a, y0 + ry * a],
          [x1 + rx * a, y1 + ry * a],
          [x1 + rx * b, y1 + ry * b],
          [x0 + rx * b, y0 + ry * b],
        ],
        h,
        tag,
      );
    }
  }

  /** Dashed strip; the last `solidTail` meters are drawn solid. */
  dashed(points, a, b, h, solidTail = 0) {
    const path = measure(points);
    const solidFrom = Math.max(0, path.total - solidTail);
    for (let s = 0; s < solidFrom; s += DASH_M + GAP_M) {
      const e = Math.min(s + DASH_M, solidFrom);
      if (e - s > 0.3) this.strip([path.at(s), path.at(e)], a, b, h);
    }
    if (solidTail > 0 && solidFrom < path.total) this.strip([path.at(solidFrom), path.at(path.total)], a, b, h);
  }

  build() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    const normals = new Float32Array(this.pos.length);
    for (let i = 1; i < normals.length; i += 3) normals[i] = 1;
    g.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
    g.setIndex(this.idx);
    g.computeBoundingSphere();
    return g;
  }
}

/** Arc-length helper for a polyline: path.at(s) -> point s meters along it. */
function measure(points) {
  const cum = [0];
  for (let i = 1; i < points.length; i++) {
    cum.push(cum[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
  }
  const total = cum[cum.length - 1];
  return {
    total,
    at(s) {
      s = Math.max(0, Math.min(total, s));
      let i = 1;
      while (i < cum.length - 1 && cum[i] < s) i++;
      const seg = cum[i] - cum[i - 1] || 1;
      const k = (s - cum[i - 1]) / seg;
      const p0 = points[i - 1];
      const p1 = points[i];
      return [p0[0] + (p1[0] - p0[0]) * k, p0[1] + (p1[1] - p0[1]) * k];
    },
  };
}

/** Straight piece continuing a lane past a dead end (backwards at its start or forwards at its end). */
function extensionShape(shape, atStart) {
  const [a, b] = atStart ? [shape[1], shape[0]] : [shape[shape.length - 2], shape[shape.length - 1]];
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
  const ux = (b[0] - a[0]) / len;
  const uy = (b[1] - a[1]) / len;
  const far = [b[0] + ux * EXTENSION_M, b[1] + uy * EXTENSION_M];
  return atStart ? [far, b] : [b, far];
}

export function buildRoads(scene, geo, index) {
  const asphalt = new FlatBuilder();
  const white = new FlatBuilder();
  const yellow = new FlatBuilder();
  const junctionType = new Map(geo.junctions.map((j) => [j.id, j]));
  const edgeIds = new Set(geo.edges.map((e) => e.id));

  // --- lanes and their markings ---------------------------------------------
  const markLanes = (lanes, edge, shapeOf, tag, solidTail) => {
    const reverse = edgeIds.has(`${edge.to}_${edge.from}`);
    lanes.forEach((lane, i) => {
      const shape = shapeOf(lane);
      const w = lane.width;
      asphalt.strip(shape, -w / 2, w / 2, H.lane, tag);
      if (i === 0) white.strip(shape, w / 2 - 0.35, w / 2 - 0.2, H.mark); // edge line
      if (i < lanes.length - 1) white.dashed(shape, -w / 2 - 0.06, -w / 2 + 0.06, H.mark, solidTail); // lane line
      if (i === lanes.length - 1) {
        if (reverse) yellow.strip(shape, -w / 2 + 0.08, -w / 2 + 0.2, H.mark); // half of the double yellow
        else white.strip(shape, -w / 2 + 0.2, -w / 2 + 0.35, H.mark);
      }
    });
  };

  for (const edge of geo.edges) {
    const lanes = index.edgeLanes.get(edge.id) || [];
    if (!lanes.length) continue;
    const toSignal = junctionType.get(edge.to)?.signalized;
    markLanes(lanes, edge, (l) => l.shape, edge.id, toSignal ? SOLID_BEFORE_STOP_M : 0);
    // Continue roads past dead ends so vehicles drive in from "off the map".
    if (junctionType.get(edge.from)?.type === 'dead_end') markLanes(lanes, edge, (l) => extensionShape(l.shape, true), null, 0);
    if (junctionType.get(edge.to)?.type === 'dead_end') markLanes(lanes, edge, (l) => extensionShape(l.shape, false), null, 0);
  }

  // --- stop lines and crosswalks at every signalized approach ----------------------
  for (const j of Object.keys(geo.tls)) {
    for (const side of Object.keys(geo.tls[j].approaches)) {
      const a = approachFrame(index, j, side);
      const [sx, sy] = a.stop;
      const P = (along, right) => [sx + a.dx * along + a.rx * right, sy + a.dy * along + a.ry * right];
      const half = a.width / 2;
      // Stop line across the approach lanes, just before the junction.
      white.quad([P(-1.05, half), P(-0.55, half), P(-0.55, -half), P(-1.05, -half)], H.mark + 0.003);
      // Continental crosswalk over the whole arm (approach + exit lanes), inside the junction pad.
      const left = -(half + (a.exitWidth || a.width));
      const from = 0.7;
      const to = 3.5;
      const total = half - left;
      const n = Math.max(1, Math.floor((total + 0.2) / 1.1)); // 0.5 m stripes, 0.6 m gaps
      let off = half - (total - (n * 1.1 - 0.6)) / 2; // centered on the arm
      for (let k = 0; k < n; k++, off -= 1.1) {
        white.quad([P(from, off), P(to, off), P(to, off - 0.5), P(from, off - 0.5)], H.mark);
      }
    }
  }

  // --- junction pads -----------------------------------------------------------
  const padShapes = [];
  for (const j of geo.junctions) {
    if (j.type === 'dead_end' || !j.shape || j.shape.length < 3) continue;
    const shape = new THREE.Shape(j.shape.map(([x, y]) => new THREE.Vector2(x, y)));
    const g = new THREE.ShapeGeometry(shape);
    g.rotateX(-Math.PI / 2); // (x, y, 0) -> (x, 0, -y)
    g.translate(0, H.pad, 0);
    g.deleteAttribute('uv');
    padShapes.push(g);
  }

  const asphaltMat = new THREE.MeshStandardMaterial({ color: '#42464d', roughness: 0.93, metalness: 0 });
  const padMat = new THREE.MeshStandardMaterial({ color: '#3d4148', roughness: 0.95, metalness: 0 });
  const whiteMat = new THREE.MeshStandardMaterial({ color: '#eceff2', roughness: 0.65 });
  const yellowMat = new THREE.MeshStandardMaterial({ color: '#e4b43c', roughness: 0.65 });

  const roadMesh = new THREE.Mesh(asphalt.build(), asphaltMat);
  roadMesh.name = 'roads';
  const group = new THREE.Group();
  group.name = 'road-network';
  group.add(roadMesh, new THREE.Mesh(white.build(), whiteMat), new THREE.Mesh(yellow.build(), yellowMat));
  for (const g of padShapes) group.add(new THREE.Mesh(g, padMat));
  group.traverse((o) => {
    if (o.isMesh) o.receiveShadow = true;
  });
  scene.add(group);

  return {
    group,
    roadMesh,
    /** Edge id under the ray (only real network lanes, not the decorative extensions). */
    pickEdge(raycaster) {
      const hit = raycaster.intersectObject(roadMesh, false)[0];
      if (!hit || hit.faceIndex == null) return null;
      return asphalt.tags[hit.faceIndex] || null;
    },
  };
}
