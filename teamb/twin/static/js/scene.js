// Renderer, camera, orbit controls, lights, sky, ground and camera presets.
// Everything else adds itself to `view.scene` and hooks into the render loop with
// view.onFrame((now, dt) => ...) or view.onAfterRender(fn).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { clamp, setLabelViewport, toVec3 } from './util.js';

const SKY_TOP = new THREE.Color('#4d84c4');
const SKY_HORIZON = new THREE.Color('#cbd8e4');
const FOG_COLOR = '#c4d2df';

export function createView(host, geometry) {
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: 'high-performance',
    // The road is built from thin stacked layers (asphalt, markings, overlays) seen from up to
    // ~2 km away; a logarithmic depth buffer keeps them from flickering (z-fighting).
    logarithmicDepthBuffer: true,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  host.appendChild(renderer.domElement);
  renderer.domElement.tabIndex = 0;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(FOG_COLOR);
  scene.fog = new THREE.Fog(FOG_COLOR, 1500, 5200);

  const camera = new THREE.PerspectiveCamera(42, 1, 0.5, 12000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.screenSpacePanning = false; // pan along the ground like a map
  controls.maxPolarAngle = THREE.MathUtils.degToRad(84);
  controls.minDistance = 12;
  controls.maxDistance = 3400;
  controls.zoomSpeed = 1.1;

  // --- lights: soft sky light + a warm sun with shadows that follow the camera target
  const hemi = new THREE.HemisphereLight('#dbe8ff', '#5d5649', 1.25);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight('#fff0d8', 2.6);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.4;
  scene.add(sun, sun.target);
  const SUN_DIR = new THREE.Vector3(-0.55, 0.78, 0.32).normalize(); // from the south-west, afternoon

  scene.add(makeSky());
  scene.add(makeGround(geometry));

  // --- camera presets (computed from the network so they survive network changes)
  const [xmin, ymin, xmax, ymax] = geometry.bounds;
  const tlsIds = Object.keys(geometry.tls).sort();
  const tlsX = tlsIds.map((j) => geometry.tls[j].x);
  const cx = tlsX.length ? (Math.min(...tlsX) + Math.max(...tlsX)) / 2 : (xmin + xmax) / 2;
  const span = Math.max(xmax - xmin, 400);
  // All presets look north from the south at 35–40°; city.js keeps buildings low enough
  // south of each east–west street that these views see the road (see heightCap there).
  const presets = {
    overview: { target: toVec3(cx, 70, 0), offset: new THREE.Vector3(span * 0.1, span * 0.5, span * 0.6), label: 'Overview' },
    top: { target: toVec3(cx, (ymin + ymax) / 2, 0), offset: new THREE.Vector3(0, span * 0.95, 1), label: 'Top' },
  };
  for (const j of tlsIds) {
    const t = geometry.tls[j];
    presets[j] = { target: toVec3(t.x, t.y, 0), offset: new THREE.Vector3(24, 72, 92), label: j };
  }

  const applyPreset = (name) => {
    const p = presets[name];
    camera.position.copy(p.target).add(p.offset);
    controls.target.copy(p.target);
  };
  applyPreset('overview');

  // --- smooth camera moves and follow mode
  let flight = null; // {fromPos, fromTarget, toPos, toTarget, t0, dur}
  let follow = null; // () => {x, y, heading} | null
  const followPos = new THREE.Vector3();
  const followTarget = new THREE.Vector3();

  function flyTo(name, duration = 1.2) {
    const p = presets[name];
    if (!p) return;
    follow = null;
    flight = {
      fromPos: camera.position.clone(),
      fromTarget: controls.target.clone(),
      toPos: p.target.clone().add(p.offset),
      toTarget: p.target.clone(),
      t0: performance.now(),
      dur: duration * 1000,
    };
  }

  /** Follow a moving thing: getPose() returns {x, y, heading} (SUMO coords) or null when gone. */
  function setFollow(getPose) {
    follow = getPose;
    flight = null;
  }

  // --- render loop
  const frameHooks = [];
  const afterHooks = [];
  let last = performance.now();
  let width = 1;
  let height = 1;

  function resize() {
    width = Math.max(1, host.clientWidth);
    height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    setLabelViewport(height, camera.fov);
  }
  new ResizeObserver(resize).observe(host);
  resize();

  function updateShadowCamera() {
    // Keep the shadow map focused on what is on screen: crisp shadows close up, still some far away.
    const dist = camera.position.distanceTo(controls.target);
    const half = clamp(dist * 0.85, 140, 1300);
    const cam = sun.shadow.camera;
    if (Math.abs(cam.right - half) > half * 0.08) {
      cam.left = -half;
      cam.right = half;
      cam.top = half;
      cam.bottom = -half;
      cam.near = 1;
      cam.far = 4000;
      cam.updateProjectionMatrix();
      sun.shadow.normalBias = 0.25 + half / 1200;
    }
    sun.target.position.copy(controls.target);
    sun.position.copy(controls.target).addScaledVector(SUN_DIR, 1800);
  }

  // Frame-rate guard for weaker presentation laptops: if frames stay slow, render fewer pixels.
  let frameEma = 1 / 60;
  let framesSeen = 0;
  function adaptResolution(rawDt) {
    if (rawDt <= 0 || rawDt > 0.1) return; // ignore pauses and throttled background tabs
    frameEma = frameEma * 0.95 + rawDt * 0.05;
    if (++framesSeen % 180 !== 0) return;
    const pr = renderer.getPixelRatio();
    if (frameEma > 1 / 38 && pr > 1) {
      renderer.setPixelRatio(Math.max(1, pr - 0.25));
      resize();
    }
  }

  // A failing layer or recorder hook must not stop the render loop: log it (once per hook) and go on.
  const failedHooks = new Set();
  function runHooks(hooks, now, dt) {
    for (const fn of hooks) {
      try {
        fn(now, dt);
      } catch (err) {
        if (!failedHooks.has(fn)) console.error('render hook failed', err);
        failedHooks.add(fn);
      }
    }
  }

  function tick(now) {
    const rawDt = (now - last) / 1000;
    const dt = Math.min(0.1, rawDt);
    last = now;
    adaptResolution(rawDt);
    if (!host.clientWidth) {
      // The live view is hidden (Results tab): don't spend the GPU on it.
      requestAnimationFrame(tick);
      return;
    }
    // Layers first (vehicles move to this frame's positions), then the camera that may follow them.
    runHooks(frameHooks, now, dt);
    if (flight) {
      const k = clamp((now - flight.t0) / flight.dur, 0, 1);
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; // ease in-out
      camera.position.lerpVectors(flight.fromPos, flight.toPos, e);
      controls.target.lerpVectors(flight.fromTarget, flight.toTarget, e);
      if (k >= 1) flight = null;
    } else if (follow) {
      const pose = follow();
      if (!pose) {
        follow = null;
        view.onFollowLost?.();
      } else {
        const r = (pose.heading * Math.PI) / 180;
        const fx = Math.sin(r);
        const fz = -Math.cos(r);
        // Chase camera: behind and above the vehicle, looking a little ahead of it.
        followTarget.set(pose.x + fx * 4, 0, -pose.y + fz * 4);
        followPos.set(pose.x - fx * 30, 17, -pose.y - fz * 30);
        // Frame-rate independent smoothing (uses real elapsed time, so slow machines keep up too).
        const a = 1 - Math.pow(0.02, Math.min(rawDt, 1));
        controls.target.lerp(followTarget, a);
        camera.position.lerp(followPos, a);
      }
    }
    controls.update();
    updateShadowCamera();
    renderer.render(scene, camera);
    runHooks(afterHooks, now, dt);
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  // Stop camera flights as soon as the user grabs the view.
  controls.addEventListener('start', () => {
    flight = null;
    if (follow) {
      follow = null;
      view.onFollowLost?.(true);
    }
  });

  const view = {
    renderer,
    scene,
    camera,
    controls,
    presets,
    flyTo,
    setFollow,
    get following() {
      return !!follow;
    },
    onFrame: (fn) => frameHooks.push(fn),
    onAfterRender: (fn) => afterHooks.push(fn),
    onFollowLost: null,
    /** Distance from the camera to what it looks at — used to scale markers when zoomed out. */
    viewDistance: () => camera.position.distanceTo(controls.target),
    size: () => ({ width, height }),
  };
  return view;
}

function makeSky() {
  const geo = new THREE.SphereGeometry(9000, 32, 16);
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    depthTest: false,
    fog: false,
    uniforms: { top: { value: SKY_TOP }, horizon: { value: SKY_HORIZON } },
    vertexShader: /* glsl */ `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 top; uniform vec3 horizon; varying vec3 vDir;
      void main() {
        float h = clamp(vDir.y, 0.0, 1.0);
        vec3 c = mix(horizon, top, pow(h, 0.55));
        gl_FragColor = vec4(c, 1.0);
        #include <colorspace_fragment>
      }`,
  });
  const sky = new THREE.Mesh(geo, mat);
  sky.renderOrder = -10;
  sky.frustumCulled = false;
  sky.onBeforeRender = (renderer, scene, camera) => {
    sky.position.copy(camera.position);
    sky.updateMatrixWorld();
  };
  return sky;
}

function makeGround(geometry) {
  // Subtle noise so the ground does not look like flat paint.
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2600; i++) {
    const v = 200 + Math.floor(Math.random() * 55);
    ctx.fillStyle = `rgb(${v},${v},${v})`;
    const s = 2 + Math.random() * 7;
    ctx.fillRect(Math.random() * 256, Math.random() * 256, s, s);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(140, 140);
  tex.anisotropy = 4;
  const [xmin, ymin, xmax, ymax] = geometry.bounds;
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(14000, 14000),
    new THREE.MeshStandardMaterial({ color: '#77816a', map: tex, roughness: 1, metalness: 0 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.set((xmin + xmax) / 2, -0.06, -(ymin + ymax) / 2);
  ground.receiveShadow = true;
  ground.name = 'ground';
  return ground;
}
