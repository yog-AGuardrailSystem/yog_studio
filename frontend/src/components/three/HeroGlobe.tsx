/**
 * HeroGlobe: a gold orb made of thousands of dots, with the YOG wordmark living INSIDE it as a letter-shaped prism of dots.
 *
 * Nothing rearranges. The orb turns: seen side-on the logo core is a bright band through the middle, and as the orb
 * comes round to face you the band becomes the letters. On landing the orb scales/fades in while swinging from side-on to
 * front-on. It then keeps turning slowly; dragging turns it (with inertia), hovering dents the skin and lets a few (48) dots come loose
 * particles, a click sends a ripple across it and a burst of debris off it.
 *
 * Layers (all one shader, drawn as separate point sets):
 *   shell   a sparse subset of the orb's points at 1.3x radius: bigger, softer dots (depth-of-field) forming the halo
 *   main    the orb surface (rim-lit, lit from the top-left, shadowed lower right, back side drawn faintly) + the logo core
 *   free    up to 48 loose particles that float around the pointer while it is over the orb
 *   debris  up to three click bursts
 *
 * Heavy (three.js). Never import this directly from a page: use ./HeroGlobeView (lazy, with fallbacks, pause, off-screen stop).
 * Test hooks on the host element: data-ready, data-phase (reveal | orbit), data-yaw, data-pitch, data-hover, data-free (loose particles, at most 48), data-impacts.
 */
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState, type MutableRefObject, type RefObject } from 'react'
import * as THREE from 'three'
import { fibonacciSphere, hash01, jitterPoints, logoVolume, subsetIndices, type Mask } from '../../lib/globePoints'
import type { GlobeInput } from './globeInput'

const RADIUS_FRAC = 0.34     // orb radius as a fraction of the smaller side of the box (the 1.3x shell then still fits)
const SHELL_SCALE = 1.3
const LOGO_WIDTH = 1.6       // how many orb radii the wordmark spans
const REVEAL = 2.5           // seconds to swing from side-on to front-on
const ENTER = 1.4            // seconds for the orb to scale up and fade in
const SPIN = 0.06            // rad/s, slow turn after the reveal
const REST_PITCH = 0.05
const BURSTS = 3
const HITS = 4
const FREE = 48              // loose particles that float around the pointer while it is over the orb (never more than 50)

const VERT = /* glsl */ `
uniform vec2 uSize;
uniform float uDpr;
uniform float uTime;
uniform float uRadiusPx;
uniform float uEnter;
uniform float uMode;          // 0 main, 1 shell, 3 debris
uniform float uHover;
uniform float uBlur;
uniform float uShellScale;
uniform float uGain;
uniform float uLogoGain;
uniform vec2 uRot;            // yaw, pitch
uniform vec2 uPointer;        // CSS px, origin top-left
uniform vec4 uHit[${HITS}];   // x: start time (-1 = unused), y: power
uniform vec3 uHitDir[${HITS}];
uniform vec4 uBurst;          // x: start time, y: seed, z: life, w: power
uniform vec3 uBurstDir;
uniform vec2 uBurstRot;
uniform vec3 uShade;
uniform vec3 uLight;
uniform vec3 uImpact;
attribute float aSeed;
attribute float aKind;        // 0 orb surface, 1 logo core
varying vec3 vColour;
varying float vAlpha;
varying float vBlur;

mat3 rotY(float a) { float c = cos(a), s = sin(a); return mat3(c, 0.0, -s, 0.0, 1.0, 0.0, s, 0.0, c); }
mat3 rotX(float a) { float c = cos(a), s = sin(a); return mat3(1.0, 0.0, 0.0, 0.0, c, s, 0.0, -s, c); }

void main() {
  float seed = aSeed;
  float strand = 0.5 + 0.5 * sin(seed * 51.0);
  bool core = aKind > 0.5;
  vec3 p = rotX(uRot.y) * rotY(uRot.x) * position;
  vec3 n = normalize(p + vec3(1e-5));
  vBlur = 0.0;
  float sz = 1.0;
  float a = 0.0;
  vec3 col = uLight;

  if (core) {
    // The logo core: always there, always the same dots. Near half of the prism bright, far half dim.
    float near = smoothstep(-0.25, 0.85, p.z);
    float lit = clamp(0.62 - n.x * 0.30 + n.y * 0.25, 0.25, 1.0);
    col = mix(uShade * 1.15, vec3(1.0, 0.95, 0.80), clamp(lit * 1.15, 0.0, 1.0));
    a = (0.22 + 0.78 * near) * (0.6 + 0.4 * lit) * uLogoGain;
    sz = 1.1 + seed * 0.9;
  } else {
    // --- surface motion: idle ripple, fine noise, click shock waves, hover dent
    vec3 u = normalize(position);
    float shock = 0.0;
    float blush = 0.0;
    for (int i = 0; i < ${HITS}; i++) {
      float t0 = uHit[i].x;
      if (t0 >= 0.0) {
        float age = max(0.0, uTime - t0);
        float ang = acos(clamp(dot(u, uHitDir[i]), -1.0, 1.0));      // angle on the sphere: the wave stays attached while it turns
        float phase = ang - age * 1.9;
        float env = (1.0 - exp(-age * 45.0)) * exp(-age * 1.15) * uHit[i].y;
        float band = exp(-phase * phase / 0.055);
        shock += cos(phase * 15.0) * band * env;
        blush += band * env;
      }
    }
    shock = clamp(shock, -1.0, 1.0);
    blush = 1.0 - exp(-blush);
    float idle = sin(p.x * 11.0 + p.y * 7.0 + uTime * 0.7) * 0.006;
    float grain = sin(p.x * 19.0 + p.z * 13.0 + uTime * 1.2) * sin(p.y * 17.0 - p.z * 11.0 + uTime * 0.9);
    grain = grain * 0.65 + sin(seed * 73.0 + uTime * 1.5) * 0.35;
    vec2 d = (uSize * 0.5 + n.xy * vec2(uRadiusPx, -uRadiusPx)) - uPointer;
    float hover = exp(-dot(d, d) / 6500.0) * uHover * smoothstep(-0.1, 0.4, n.z);
    float radius = 1.0 + idle + grain * 0.012 + shock * 0.13 - hover * 0.09;

    // a soft patch of dust travelling round the silhouette
    float dustAngle = 0.6 + uTime * 0.105;
    vec2 dustDir = vec2(cos(dustAngle), sin(dustAngle));
    float dustPatch = smoothstep(0.55, 0.95, dot(n.xy, dustDir)) * (1.0 - smoothstep(0.2, 0.7, abs(n.z)));
    float dust = smoothstep(0.62, 1.0, seed) * dustPatch;

    p = n * radius + n * dust * (0.10 + 0.15 * sin(seed * 40.0 + uTime * 0.4));

    if (uMode > 2.5) {
      // debris: points near the burst direction leave the surface, drift along it and fade
      float flight = max(0.0, uTime - uBurst.x);
      float s2 = fract(sin(seed * 713.0 + uBurst.y * 97.0) * 43758.5453);
      vec3 surf = rotX(uBurstRot.y) * rotY(uBurstRot.x) * position;
      float dist = acos(clamp(dot(u, uBurstDir), -1.0, 1.0));
      float fade = exp(-dist * dist / 0.16) * (1.0 - exp(-flight * 30.0)) * (1.0 - smoothstep(1.2, uBurst.z, flight));
      vec3 tangent = normalize(cross(surf, vec3(0.3, 1.0, 0.2)));
      p = surf * (1.0 + flight * (0.12 + s2 * 0.38) * mix(0.3, 1.0, uBurst.w)) + tangent * flight * sin(s2 * 91.0) * 0.22;
      p.y -= flight * flight * 0.02;
      a = fade * uBurst.w * step(mix(0.97, 0.86, uBurst.w), s2) * (0.35 + s2 * 0.5) * uGain;
      sz = 1.2 + s2 * 1.6;
      col = mix(uImpact, uLight, 0.4);
    } else {
      float edge = pow(max(1.0 - abs(n.z), 0.0), 3.0);                  // rim light: the silhouette is brighter and bigger
      float lit = clamp(0.52 - n.x * 0.48 + n.y * 0.32, 0.08, 1.0);      // lit from the top left
      float front = smoothstep(-0.1, 0.65, n.z);                         // the far side is drawn faintly, not hidden
      float shadow = smoothstep(-0.25, 0.65, n.x) * smoothstep(-0.25, 0.65, -n.y);   // lower right
      float mott = 0.65 + 0.35 * sin(n.x * 9.0 + n.z * 4.0) * cos(n.y * 8.0 - n.z * 5.0);
      col = mix(uShade, uLight, lit);
      col = mix(col, uImpact, blush * 0.45);
      float rim = edge * (0.95 + lit * lit * 0.55);
      a = (0.035 + rim + front * (0.16 + mott * 0.25)) * mix(lit, 0.62 + lit * 0.38, front * 0.65);
      a *= mix(0.45, 1.0, strand);
      a *= 1.0 - shadow * 0.9;
      a += dust * 0.11;
      a *= uGain * (1.0 + blush * 0.6);
      a *= 1.0 - hover * 0.45;                                           // dots under the pointer thin out: some of them are the ones that came loose
      sz = (1.3 + front * (0.2 + seed * 0.4) + edge * (1.5 + strand * 2.5)) * (1.0 - dust * 0.45);
      if (uMode > 0.5) {
        // shell: a bigger, sparser, softer copy of the surface; dots near the viewer go out of focus
        p *= uShellScale;
        float coreSz = 1.5 + strand * 1.5;
        vBlur = uBlur * smoothstep(0.55, 1.3, p.z);
        a = (0.18 + max(n.z, 0.0) * 0.55 + edge * 0.16) * lit * 0.7 * uGain;
        sz = coreSz + vBlur;
        a *= pow(coreSz / sz, 1.2);
        col = mix(col, vec3(1.0, 0.97, 0.91), 0.16);
      }
    }
  }

  float s = uRadiusPx * mix(0.78, 1.0, uEnter);
  vec2 px = uSize * 0.5 + p.xy * vec2(s, -s);
  gl_Position = vec4(px / uSize * vec2(2.0, -2.0) + vec2(-1.0, 1.0), 0.0, 1.0);
  gl_PointSize = sz * uDpr;
  vColour = col;
  vAlpha = a * uEnter;
}
`

const FRAG = /* glsl */ `
precision highp float;
varying vec3 vColour;
varying float vAlpha;
varying float vBlur;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float sharp = 1.0 - smoothstep(0.25, 0.5, d);
  float soft = exp(-d * d * 18.0) * (1.0 - smoothstep(0.35, 0.5, d));
  float a = vAlpha * mix(sharp, soft, min(vBlur / 3.0, 1.0));
  gl_FragColor = vec4(vColour * a, a);
}
`

/** Rasterise the wordmark off-screen into an alpha mask. Waits (briefly) for the page font. */
export async function buildLogoMask(text = 'YOG'): Promise<Mask> {
  try {
    await Promise.race([document.fonts.load('800 200px "Inter Tight"'), new Promise((r) => setTimeout(r, 1500))])
  } catch { /* use the fallback face */ }
  const W = 720, H = 280
  const cv = document.createElement('canvas')
  cv.width = W; cv.height = H
  const ctx = cv.getContext('2d')
  const alpha = new Uint8Array(W * H)
  if (!ctx) return { w: W, h: H, alpha }
  ctx.fillStyle = '#fff'
  ctx.font = '800 230px "Inter Tight", "Arial Black", "Segoe UI", system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ;(ctx as CanvasRenderingContext2D & { letterSpacing?: string }).letterSpacing = '6px'
  ctx.fillText(text, W / 2, H / 2 + 10)
  const img = ctx.getImageData(0, 0, W, H).data
  for (let i = 0; i < alpha.length; i++) alpha[i] = img[i * 4 + 3]
  return { w: W, h: H, alpha }
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const easeOut = (t: number) => 1 - Math.pow(1 - clamp01(t), 3)
const TAU = Math.PI * 2

interface GlobeProps {
  mask: Mask
  nOrb: number
  nLogo: number
  calm: boolean
  input: MutableRefObject<GlobeInput>
  host: RefObject<HTMLDivElement | null>
}

/** The loose pointer particles: simple soft gold dots placed directly in CSS px. */
function makeFreeMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true, depthTest: false, depthWrite: false,
    blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
    uniforms: { uSize: { value: new THREE.Vector2(1, 1) }, uDpr: { value: 1 } },
    vertexShader: /* glsl */ `
      uniform vec2 uSize; uniform float uDpr;
      attribute float aSeed; attribute float aAlpha;
      varying float vA; varying float vS;
      void main() {
        gl_Position = vec4(position.xy / uSize * vec2(2.0, -2.0) + vec2(-1.0, 1.0), 0.0, 1.0);
        gl_PointSize = (4.5 + aSeed * 5.5) * uDpr;
        vA = aAlpha; vS = aSeed;
      }`,
    fragmentShader: /* glsl */ `
      precision highp float;
      varying float vA; varying float vS;
      void main() {
        float d = length(gl_PointCoord - 0.5);
        float core = 1.0 - smoothstep(0.16, 0.5, d);
        float glow = exp(-d * d * 14.0);
        float a = vA * (0.95 * core + 0.75 * glow);
        vec3 col = mix(vec3(1.0, 0.78, 0.33), vec3(1.0, 0.95, 0.78), step(0.5, vS) * 0.6);
        gl_FragColor = vec4(col * a, a);
      }`,
  })
}

interface Loose { x: number; y: number; vx: number; vy: number; a: number; ang: number; rad: number; w: number; wait: number; on: boolean }

function makeMaterial(mode: number): THREE.ShaderMaterial {
  const hit = Array.from({ length: HITS }, () => new THREE.Vector4(-1, 0, 0, 0))
  const hitDir = Array.from({ length: HITS }, () => new THREE.Vector3(0, 0, 1))
  return new THREE.ShaderMaterial({
    vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthTest: false, depthWrite: false,
    blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
    uniforms: {
      uSize: { value: new THREE.Vector2(1, 1) }, uDpr: { value: 1 }, uTime: { value: 0 }, uRadiusPx: { value: 100 }, uEnter: { value: 0 },
      uMode: { value: mode }, uHover: { value: 0 }, uBlur: { value: 5 }, uShellScale: { value: SHELL_SCALE }, uGain: { value: 2.4 },
      uLogoGain: { value: 3.4 }, uRot: { value: new THREE.Vector2() }, uPointer: { value: new THREE.Vector2(-1e4, -1e4) },
      uHit: { value: hit }, uHitDir: { value: hitDir }, uBurst: { value: new THREE.Vector4(-100, 0, 1, 1) },
      uBurstDir: { value: new THREE.Vector3(0, 0, 1) }, uBurstRot: { value: new THREE.Vector2() },
      uShade: { value: new THREE.Vector3(0.85, 0.29, 0.055) }, uLight: { value: new THREE.Vector3(1, 0.86, 0.43) },
      uImpact: { value: new THREE.Vector3(1, 0.52, 0.16) },
    },
  })
}

function Globe({ mask, nOrb, nLogo, calm, input, host }: GlobeProps) {
  const built = useMemo(() => {
    const orb = jitterPoints(fibonacciSphere(nOrb), 0.004)
    const logo = logoVolume(mask, nLogo, LOGO_WIDTH, 3, 21, 0.62)
    const total = nOrb + nLogo
    const pos = new Float32Array(total * 3)
    pos.set(orb, 0); pos.set(logo, nOrb * 3)
    const seed = new Float32Array(total), kind = new Float32Array(total)
    for (let i = 0; i < total; i++) { seed[i] = hash01(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]); kind[i] = i < nOrb ? 0 : 1 }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1))
    geo.setAttribute('aKind', new THREE.BufferAttribute(kind, 1))
    const subset = (keep: number, s: number) => {
      const g = new THREE.BufferGeometry()
      for (const k of ['position', 'aSeed', 'aKind']) g.setAttribute(k, geo.getAttribute(k))
      g.setIndex(new THREE.BufferAttribute(subsetIndices(nOrb, keep, s), 1))        // only orb points: indices below nOrb
      return g
    }
    const shellGeo = subset(0.24, 5), debrisGeo = subset(0.3, 7)
    const make = (g: THREE.BufferGeometry, m: THREE.ShaderMaterial, order: number) => {
      const p = new THREE.Points(g, m); p.frustumCulled = false; p.renderOrder = order; return p
    }
    const shellM = makeMaterial(1), mainM = makeMaterial(0)
    const debrisM = Array.from({ length: BURSTS }, () => makeMaterial(3))
    const shell = make(shellGeo, shellM, 0), main = make(geo, mainM, 1)
    const debris = debrisM.map((m, i) => make(debrisGeo, m, 3 + i))
    debris.forEach((d) => { d.visible = false })

    // the few loose particles that float around the pointer while it is over the orb (positions are CSS px, updated every frame)
    const freeGeo = new THREE.BufferGeometry()
    freeGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(FREE * 3), 3))
    freeGeo.setAttribute('aSeed', new THREE.BufferAttribute(Float32Array.from({ length: FREE }, (_, k) => hash01(k * 1.7, k * 0.3, 2)), 1))
    freeGeo.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(FREE), 1))
    const freeM = makeFreeMaterial()
    const free = make(freeGeo, freeM, 10)
    free.visible = false
    return { geos: [geo, shellGeo, debrisGeo, freeGeo], mats: [shellM, mainM, ...debrisM], shellM, mainM, debrisM, freeM, freeGeo, objects: [shell, main, ...debris, free], debris, free }
  }, [mask, nOrb, nLogo])
  useEffect(() => () => { built.geos.forEach((g) => g.dispose()); built.mats.forEach((m) => m.dispose()); built.freeM.dispose() }, [built])

  // when motion is paused (or resumed) while the canvas is idle, draw one frame now so it snaps to the still pose
  const invalidate = useThree((s) => s.invalidate)
  useEffect(() => {
    // one frame later: the canvas applies its new frameloop in its own effect, which runs after this one
    const id = requestAnimationFrame(() => requestAnimationFrame(() => invalidate()))
    return () => cancelAnimationFrame(id)
  }, [calm, invalidate])

  const st = useRef({
    t0: performance.now() / 1000, phase: 'reveal' as 'reveal' | 'orbit', yaw: -Math.PI / 2, pitch: REST_PITCH, vyaw: SPIN, hover: 0,
    lastClick: 0, lastFace: 0, faceUntil: 0, faceTarget: 0, impacts: 0, slot: 0, burst: 0, ready: false, lastData: 0,
    over: false, px: 0, py: 0, shown: 0, loose: [] as Loose[],
  })

  useFrame((state, delta) => {
    const s = st.current
    const el = host.current
    const i = input.current
    const now = performance.now() / 1000
    const dt = Math.min(delta, 0.05)
    const w = state.size.width, h = state.size.height
    const radiusPx = RADIUS_FRAC * Math.min(w, h)
    const dpr = state.gl.getPixelRatio()
    let enterMain: number, enterShell: number

    if (calm) {                                         // paused / reduced motion: one still frame, logo facing the viewer
      s.yaw = 0; s.pitch = REST_PITCH; s.phase = 'orbit'; s.hover = 0; s.over = false
      enterMain = enterShell = 1
    } else {
      const age = now - s.t0
      enterMain = easeOut(age / ENTER); enterShell = easeOut((age - 0.16) / ENTER)
      if (i.dragging) {
        if (s.phase === 'reveal') s.phase = 'orbit'
        s.faceUntil = 0
        s.yaw += i.dragDX * 0.0035
        s.pitch = Math.max(-1.2, Math.min(1.2, s.pitch + i.dragDY * 0.0035))     // drag up: the face of the orb moves up with the pointer
        const v = Math.max(-3, Math.min(3, (i.dragDX * 0.0035) / Math.max(dt, 1e-3)))
        s.vyaw += (v - s.vyaw) * (1 - Math.exp(-dt / 0.04))
        i.dragDX = 0; i.dragDY = 0
      } else if (s.phase === 'reveal') {
        const k = clamp01(age / REVEAL)
        s.yaw = (-Math.PI / 2) * (1 - easeOut(k))
        s.pitch += (REST_PITCH - s.pitch) * (1 - Math.exp(-dt / 0.6))
        if (k >= 1) s.phase = 'orbit'
      } else if (now < s.faceUntil) {                   // "Show the logo": ease to the nearest front view
        s.yaw += (s.faceTarget - s.yaw) * (1 - Math.exp(-dt * 5))
        s.pitch += (REST_PITCH - s.pitch) * (1 - Math.exp(-dt * 5))
        s.vyaw = 0
      } else {                                          // coast after a drag, then settle into the slow spin
        s.yaw += s.vyaw * dt
        s.vyaw += (SPIN - s.vyaw) * (1 - Math.exp(-dt / 1.6))
        s.pitch += (REST_PITCH - s.pitch) * (1 - Math.exp(-dt / 2.4))
      }
      if (i.faceId > s.lastFace) {
        s.lastFace = i.faceId; s.phase = 'orbit'
        s.faceTarget = Math.round(s.yaw / TAU) * TAU; s.faceUntil = now + 1.4
      }
      // "over the globe" means over the orb itself, not just somewhere in its box
      s.over = i.inside && !i.dragging && Math.hypot(i.x - w / 2, i.y - h / 2) < radiusPx * 1.03
      s.hover += ((s.over ? 1 : 0) - s.hover) * (1 - Math.exp(-dt / 0.1))
    }

    // Loose particles: while the pointer is over the orb, a few dots (48 at most) come off the surface near it and float
    // around it on springs with a little drift; when the pointer leaves they fade out where they are.
    if (!s.loose.length) {
      for (let k = 0; k < FREE; k++) {
        s.loose.push({ x: 0, y: 0, vx: 0, vy: 0, a: 0, ang: Math.random() * TAU, rad: 16 + Math.random() * 46,
          w: (0.7 + Math.random() * 1.6) * (Math.random() < 0.5 ? -1 : 1), wait: Math.random() * 0.5, on: false })
      }
    }
    if (!calm) {
      if (s.over) { s.px = i.x; s.py = i.y }
      const t = state.clock.elapsedTime
      const pos = built.freeGeo.getAttribute('position') as THREE.BufferAttribute
      const al = built.freeGeo.getAttribute('aAlpha') as THREE.BufferAttribute
      let shown = 0
      s.loose.forEach((q, k) => {
        if (s.over && !q.on) {
          q.wait -= dt                                                  // they come loose one after another, not all at once
          if (q.wait <= 0) {
            const r = Math.random() * 34, an = Math.random() * TAU     // start on the orb, close to the pointer
            q.x = s.px + Math.cos(an) * r; q.y = s.py + Math.sin(an) * r
            q.vx = (Math.random() - 0.5) * 40; q.vy = (Math.random() - 0.5) * 40
            q.a = 0; q.on = true
          }
        }
        if (q.on) {
          q.ang += q.w * dt
          const rad = q.rad * (1 + 0.25 * Math.sin(t * 1.3 + k))
          const tx = s.px + Math.cos(q.ang) * rad, ty = s.py + Math.sin(q.ang) * rad * 0.8
          q.vx += ((tx - q.x) * 18 - q.vx * 4.5 + Math.sin(t * 2.1 + k * 3.7) * 40) * dt
          q.vy += ((ty - q.y) * 18 - q.vy * 4.5 + Math.cos(t * 1.7 + k * 2.3) * 40) * dt
          q.x += q.vx * dt; q.y += q.vy * dt
          if (s.over) q.a = Math.min(1, q.a + dt / 0.35)
          else { q.a -= dt / 0.45; if (q.a <= 0) { q.a = 0; q.on = false; q.wait = Math.random() * 0.5 } }
        }
        pos.setXYZ(k, q.x, q.y, 0)
        al.setX(k, q.on ? q.a : 0)
        if (q.on && q.a > 0.05) shown++
      })
      pos.needsUpdate = true; al.needsUpdate = true
      s.shown = shown
    } else {
      s.shown = 0
      s.loose.forEach((q) => { q.on = false; q.a = 0 })
    }
    built.free.visible = !calm && s.shown > 0
    built.freeM.uniforms.uSize.value.set(w, h)
    built.freeM.uniforms.uDpr.value = dpr

    // a click: ripple across the surface + a burst of debris. The hit direction is stored un-rotated so the wave stays attached.
    if (!calm && i.clickId > s.lastClick) {
      s.lastClick = i.clickId
      let c = (i.clickX - w / 2) / radiusPx, d = -(i.clickY - h / 2) / radiusPx
      const len = Math.hypot(c, d)
      if (len > 1) { c /= len; d /= len }
      const z = Math.sqrt(Math.max(0, 1 - c * c - d * d))
      const cp = Math.cos(s.pitch), sp = Math.sin(s.pitch), cy = Math.cos(s.yaw), sy = Math.sin(s.yaw)
      const y1 = cp * d + sp * z, z1 = -sp * d + cp * z                  // undo the pitch, then the yaw
      const dir = new THREE.Vector3(cy * c - sy * z1, y1, sy * c + cy * z1).normalize()
      const slot = s.slot++ % HITS
      for (const m of built.mats) {
        ;(m.uniforms.uHit.value as THREE.Vector4[])[slot].set(state.clock.elapsedTime, 1, 0, 0)
        ;(m.uniforms.uHitDir.value as THREE.Vector3[])[slot].copy(dir)
      }
      const b = built.debrisM[s.burst++ % BURSTS]
      ;(b.uniforms.uBurst.value as THREE.Vector4).set(state.clock.elapsedTime, Math.random(), 2.4 + Math.random(), 1)
      ;(b.uniforms.uBurstDir.value as THREE.Vector3).copy(dir)
      ;(b.uniforms.uBurstRot.value as THREE.Vector2).set(s.yaw, s.pitch)
      s.impacts++
    }

    const time = calm ? 0 : state.clock.elapsedTime
    for (const m of built.mats) {
      const u = m.uniforms
      u.uSize.value.set(w, h); u.uDpr.value = dpr; u.uTime.value = time; u.uRadiusPx.value = radiusPx
      u.uRot.value.set(s.yaw, s.pitch); u.uPointer.value.set(i.x, i.y); u.uHover.value = s.hover
      for (const hh of u.uHit.value as THREE.Vector4[]) if (hh.x >= 0 && time - hh.x > 4) hh.x = -1     // a ripple is over: stop doing the maths
    }
    built.mainM.uniforms.uEnter.value = enterMain
    built.shellM.uniforms.uEnter.value = enterShell
    built.debrisM.forEach((m, k) => {
      m.uniforms.uEnter.value = 1
      const b = m.uniforms.uBurst.value as THREE.Vector4
      built.debris[k].visible = !calm && time - b.x < b.z
    })

    if (el) {
      if (!s.ready) { s.ready = true; el.dataset.ready = 'true' }
      if (now - s.lastData > 0.2) {
        s.lastData = now
        el.dataset.phase = s.phase
        el.dataset.yaw = (((s.yaw + Math.PI) % TAU + TAU) % TAU - Math.PI).toFixed(2)
        el.dataset.hover = s.hover > 0.5 ? 'true' : 'false'
        el.dataset.impacts = String(s.impacts)
        el.dataset.free = String(s.shown)
        el.dataset.pitch = s.pitch.toFixed(2)
      }
    }
  })

  return <group>{built.objects.map((o, k) => <primitive key={k} object={o} />)}</group>
}

export interface HeroGlobeProps {
  calm: boolean
  active: boolean
  nOrb: number
  nLogo: number
  input: MutableRefObject<GlobeInput>
  host: RefObject<HTMLDivElement | null>
}

export default function HeroGlobe({ calm, active, nOrb, nLogo, input, host }: HeroGlobeProps) {
  const [mask, setMask] = useState<Mask | null>(null)
  useEffect(() => {
    let alive = true
    buildLogoMask().then((m) => { if (alive) setMask(m) })
    return () => { alive = false }
  }, [])
  // Pausing must always end on the still pose. Asking an idle canvas for one more frame is order-dependent, so instead the
  // loop is kept running for a moment after motion is paused (a frame is guaranteed), then it goes idle.
  const [settling, setSettling] = useState(false)
  useEffect(() => {
    if (!calm) return
    const start = setTimeout(() => setSettling(true), 0)
    const stop = setTimeout(() => setSettling(false), 500)
    return () => { clearTimeout(start); clearTimeout(stop) }
  }, [calm])
  if (!mask) return null
  return (
    <Canvas frameloop={calm ? (settling ? 'always' : 'demand') : active ? 'always' : 'never'} dpr={[1, 2]} camera={{ position: [0, 0, 4] }}
      gl={{ antialias: false, alpha: true, powerPreference: 'default' }} onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}>
      <Globe mask={mask} nOrb={nOrb} nLogo={nLogo} calm={calm} input={input} host={host} />
    </Canvas>
  )
}
