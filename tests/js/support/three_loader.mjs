// Module hook for tests/js: the app imports 'three' through the page's import map, which node
// does not have. The pure parts tested here never touch three.js at import time, so an empty
// stand-in module is enough. Use: register('./support/three_loader.mjs', import.meta.url).
const STUB = new URL('./three_stub.mjs', import.meta.url).href;

export async function resolve(specifier, context, nextResolve) {
  if (specifier === 'three' || specifier.startsWith('three/')) return { url: STUB, shortCircuit: true };
  return nextResolve(specifier, context);
}
