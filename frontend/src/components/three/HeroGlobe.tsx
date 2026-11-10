/**
 * HeroGlobe: ~3000 gold dots that gather out of the dark, form the YOG wordmark, melt into a slowly turning globe that
 * leans toward the cursor and can be dragged, and re-form the wordmark on hover-dwell or click.
 *
 * Heavy (three.js). Never import this directly from a page: use ./HeroGlobeView (lazy, with fallbacks, pause, off-screen stop).
 * All morphing runs in the vertex shader; JS only moves a handful of uniforms per frame.
 * Test hooks on the host element: data-ready, data-phase (gather | morph | logo | globe).
 */
import { Canvas, useFrame } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState, type MutableRefObject, type RefObject } from 'react'
import * as THREE from 'three'
import { fibonacciSphere, jitterPoints, pickTargets, scatterCloud } from '../../lib/globePoints'
import type { GlobeInput } from './globeInput'

const CAM_Z = 4.4
const FOV = 38
const LOGO_WIDTH = 2.5        // world units the YOG wordmark spans
const RADIUS = 1.2            // world radius of the globe
const GATHER = 1.9            // seconds for the dots to come together
const LOGO_AT = 1.0           // when the globe starts turning into the logo
const FIRST_HOLD = 4.6        // the logo is held until this many seconds after load
const CLICK_HOLD = 3.4        // seconds the logo is held after a click

const VERT = /* glsl */ `
attribute vec3 aSphere;
attribute vec3 aLogo;
attribute vec3 aScatter;
attribute float aSeed;
uniform float uAssemble;
uniform float uMix;
uniform float uTime;
uniform float uSize;
uniform float uPixel;
uniform float uRadius;
uniform vec2 uRot;
uniform vec3 uPointer;
uniform float uPointerOn;
varying float vShade;
varying float vA;

mat3 rotY(float a) { float c = cos(a), s = sin(a); return mat3(c, 0.0, -s, 0.0, 1.0, 0.0, s, 0.0, c); }
mat3 rotX(float a) { float c = cos(a), s = sin(a); return mat3(1.0, 0.0, 0.0, 0.0, c, s, 0.0, -s, c); }

void main() {
  float m = smoothstep(0.0, 1.0, uMix);
  float rotFade = 1.0 - m;                                   // the wordmark faces the viewer: no spin left at mix = 1
  vec3 sphere = rotX(uRot.y * rotFade) * rotY(uRot.x * rotFade) * aSphere * uRadius;
  float mi = smoothstep(0.0, 1.0, clamp(uMix * 1.6 - aSeed * 0.6, 0.0, 1.0));   // dots leave at slightly different times
  vec3 p = mix(sphere, aLogo, mi);
  float burst = sin(3.14159265 * mi);                        // outward swirl while morphing, so dots do not slide in straight lines
  p += normalize(aScatter + vec3(1e-4)) * burst * (0.22 + 0.4 * aSeed);
  p += vec3(sin(uTime * 0.7 + aSeed * 41.0), cos(uTime * 0.6 + aSeed * 23.0), sin(uTime * 0.5 + aSeed * 57.0)) * 0.011;

  float a = 1.0 - smoothstep(0.0, 1.0, clamp(uAssemble * 1.5 - aSeed * 0.5, 0.0, 1.0));   // gather from the dark
  p = mix(p, aScatter, a);

  vec2 d = p.xy - uPointer.xy;                               // dots part around the cursor
  float push = (1.0 - smoothstep(0.0, 0.75, length(d))) * uPointerOn;
  p.xy += normalize(d + vec2(1e-4)) * push * 0.3;
  p.z += push * 0.3;

  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float front = clamp(p.z / uRadius * 0.5 + 0.5, 0.0, 1.0);
  vShade = mix(0.25 + 0.75 * front, 1.0, mi * 0.85);        // far side of the globe is dim, the wordmark is fully lit
  vA = (0.42 + 0.58 * vShade) * (1.0 - a * 0.65);
  gl_PointSize = uSize * uPixel * (${CAM_Z.toFixed(1)} / -mv.z) * (0.55 + 0.75 * vShade) * (1.0 + 0.25 * mi);
}
`

const FRAG = /* glsl */ `
precision mediump float;
varying float vShade;
varying float vA;
void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  float core = smoothstep(0.5, 0.0, d);
  vec3 gold = vec3(1.0, 0.72, 0.24);
  vec3 hot = vec3(1.0, 0.92, 0.68);
  gl_FragColor = vec4(mix(gold, hot, pow(core, 2.5) * vShade), core * vA);
}
`

/** Rasterise the wordmark off-screen and pick `n` dots inside its letters. Waits (briefly) for the page font. */
export async function buildLogoTargets(n: number, text = 'YOG'): Promise<Float32Array> {
  try {
    await Promise.race([document.fonts.load('800 200px "Inter Tight"'), new Promise((r) => setTimeout(r, 1500))])
  } catch { /* use the fallback face */ }
  const W = 720, H = 280
  const cv = document.createElement('canvas')
  cv.width = W; cv.height = H
  const ctx = cv.getContext('2d')
  if (!ctx) return new Float32Array(n * 3)
  ctx.fillStyle = '#fff'
  ctx.font = '800 230px "Inter Tight", "Arial Black", "Segoe UI", system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ;(ctx as CanvasRenderingContext2D & { letterSpacing?: string }).letterSpacing = '6px'
  ctx.fillText(text, W / 2, H / 2 + 10)
  const img = ctx.getImageData(0, 0, W, H).data
  const alpha = new Uint8Array(W * H)
  for (let i = 0; i < alpha.length; i++) alpha[i] = img[i * 4 + 3]
  return pickTargets({ w: W, h: H, alpha }, n, LOGO_WIDTH)
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

interface GlobeProps {
  n: number
  logo: Float32Array
  calm: boolean
  input: MutableRefObject<GlobeInput>
  host: RefObject<HTMLDivElement | null>
}

function Globe({ n, logo, calm, input, host }: GlobeProps) {
  const mat = useRef<THREE.ShaderMaterial>(null)
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const seed = new Float32Array(n)
    for (let i = 0; i < n; i++) seed[i] = ((i * 0.6180339887) % 1)
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3))
    g.setAttribute('aSphere', new THREE.BufferAttribute(jitterPoints(fibonacciSphere(n), 0.022), 3))
    g.setAttribute('aLogo', new THREE.BufferAttribute(logo, 3))
    g.setAttribute('aScatter', new THREE.BufferAttribute(scatterCloud(n, 4.2), 3))
    g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1))
    return g
  }, [n, logo])
  useEffect(() => () => geo.dispose(), [geo])

  const uniforms = useMemo(() => ({
    uAssemble: { value: calm ? 1 : 0 }, uMix: { value: calm ? 1 : 0 }, uTime: { value: 0 },
    uSize: { value: n > 3500 ? 2.6 : 3.2 }, uPixel: { value: 1 }, uRadius: { value: RADIUS },
    uRot: { value: new THREE.Vector2(0.6, 0.2) }, uPointer: { value: new THREE.Vector3() }, uPointerOn: { value: 0 },
  }), []) // eslint-disable-line react-hooks/exhaustive-deps

  const st = useRef({ t0: performance.now() / 1000, mix: calm ? 1 : 0, yaw: 0.6, pitch: 0.2, vyaw: 0, bias: 0, on: 0,
    logoUntil: performance.now() / 1000 + FIRST_HOLD, lastClick: -1, wasCalm: calm, ready: false })

  useFrame((state, delta) => {
    const m = mat.current
    const el = host.current
    if (!m) return
    const u = m.uniforms
    const s = st.current
    const now = performance.now() / 1000
    u.uPixel.value = state.gl.getPixelRatio()
    if (calm) {                                              // paused / reduced motion: one still frame, wordmark formed
      u.uAssemble.value = 1; u.uMix.value = 1; u.uTime.value = 0; u.uPointerOn.value = 0
      s.mix = 1; s.wasCalm = true
    } else {
      if (s.wasCalm) { s.wasCalm = false; s.t0 = now - GATHER; s.logoUntil = now + 2.5 }   // resuming: hold the logo a moment, then melt
      const dt = Math.min(delta, 0.05)
      const age = now - s.t0
      u.uAssemble.value = clamp01(age / GATHER)
      const i = input.current
      if (i.inside && now - i.enteredAt > 0.7) s.logoUntil = Math.max(s.logoUntil, now + 0.5)   // hover-dwell forms the logo
      if (i.clickAt > s.lastClick) { s.lastClick = i.clickAt; s.logoUntil = Math.max(s.logoUntil, now + CLICK_HOLD) }
      const want = age > LOGO_AT && now < s.logoUntil ? 1 : 0
      s.mix += (want - s.mix) * (1 - Math.exp(-dt * (want ? 2.3 : 1.6)))
      if (Math.abs(s.mix - want) < 0.003) s.mix = want
      u.uMix.value = s.mix

      if (i.dragging) {
        s.yaw += i.dragDX * 5; s.pitch = Math.max(-1.1, Math.min(1.1, s.pitch + i.dragDY * 3.5))
        s.vyaw = i.dragDX * 5 / Math.max(dt, 1e-3)
        i.dragDX = 0; i.dragDY = 0
      } else {
        s.vyaw *= Math.exp(-dt * 1.8)
        s.pitch += ((i.inside ? 0.2 - i.y * 0.5 : 0.2) - s.pitch) * (1 - Math.exp(-dt * 2.4))
      }
      s.bias += ((i.inside && !i.dragging ? i.x * 0.55 : 0) - s.bias) * (1 - Math.exp(-dt * 2.4))
      s.yaw += (0.15 + Math.max(-4, Math.min(4, s.vyaw))) * dt
      u.uRot.value.set(s.yaw + s.bias, s.pitch)

      const cam = state.camera as THREE.PerspectiveCamera
      const halfH = Math.tan((cam.fov * Math.PI) / 360) * CAM_Z
      u.uPointer.value.set(i.x * halfH * cam.aspect, i.y * halfH, 0)
      s.on += ((i.inside && !i.dragging ? 1 : 0) - s.on) * (1 - Math.exp(-dt * 6))
      u.uPointerOn.value = s.on
      u.uTime.value = state.clock.elapsedTime
    }
    if (el) {
      if (!s.ready) { s.ready = true; el.dataset.ready = 'true' }
      const mixNow = u.uMix.value as number, asm = u.uAssemble.value as number
      el.dataset.phase = asm < 0.98 ? 'gather' : mixNow > 0.97 ? 'logo' : mixNow < 0.03 ? 'globe' : 'morph'
    }
  })

  return (
    <points geometry={geo} frustumCulled={false}>
      <shaderMaterial ref={mat} uniforms={uniforms} vertexShader={VERT} fragmentShader={FRAG}
        transparent depthWrite={false} blending={THREE.AdditiveBlending} />
    </points>
  )
}

export interface HeroGlobeProps {
  calm: boolean
  active: boolean
  n: number
  input: MutableRefObject<GlobeInput>
  host: RefObject<HTMLDivElement | null>
}

export default function HeroGlobe({ calm, active, n, input, host }: HeroGlobeProps) {
  const [logo, setLogo] = useState<Float32Array | null>(null)
  useEffect(() => {
    let alive = true
    buildLogoTargets(n).then((l) => { if (alive) setLogo(l) })
    return () => { alive = false }
  }, [n])
  if (!logo) return null
  return (
    <Canvas frameloop={calm ? 'demand' : active ? 'always' : 'never'} dpr={[1, 2]} camera={{ position: [0, 0, CAM_Z], fov: FOV }}
      gl={{ antialias: false, alpha: true, powerPreference: 'default' }} onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}>
      <Globe n={n} logo={logo} calm={calm} input={input} host={host} />
    </Canvas>
  )
}
