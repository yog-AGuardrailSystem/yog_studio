// The 3D half of the Studio hub (three.js; only ever loaded through HubStageView). Five black lacquered cabinets on a dark
// mirror floor, seen 3/4 from the front-right like the reference. Clicking one (a DOM button, see HubOverlay) flies the camera
// to it, opens its lid and raises its tools as glass cards. The scene never handles clicks: each frame it moves the real
// buttons onto the shapes they stand for.
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { GOLD, type HubState } from '../../lib/hubModel'
import { GROUPS } from '../../lib/tools'
import type { HitsRef, UiRef } from './hubShared'
import { Cabinet, MIRROR_FREE } from './scene/Cabinet'
import { Floor } from './scene/Floor'
import { CAB, RIGHT, cabinetPositions, fitDistance, toCamera } from './scene/layout'
import { Bloom } from './scene/Post'
import { radialGlow } from './scene/textures'
import { MAX_DT, damp } from './scene/util'

type Tier = 'high' | 'medium' | 'low'

function useFontsReady(): boolean {
  const [ok, setOk] = useState(false)
  useEffect(() => {
    let alive = true
    const done = () => { if (alive) setOk(true) }
    Promise.all([document.fonts.load('600 34px "Inter Tight"'), document.fonts.load('500 24px "JetBrains Mono"')]).catch(() => undefined).then(done)
    const t = window.setTimeout(done, 1500)                  // never wait forever for a font
    return () => { alive = false; window.clearTimeout(t) }
  }, [])
  return ok
}

/** A small dark studio for reflections: two dim softboxes (above, front-left) and a warm strip on the plug side. Its
 *  brightest value is low, so no glossy surface ever reflects a hot spot (seen from below in the floor mirror it bloomed). */
function studio(): THREE.Scene {
  const s = new THREE.Scene()
  const room = new THREE.Mesh(new THREE.SphereGeometry(20, 24, 16), new THREE.MeshBasicMaterial({ color: '#0b0a08', side: THREE.BackSide }))
  s.add(room)
  const panel = (w: number, h: number, color: string, k: number, pos: [number, number, number]) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(k), side: THREE.DoubleSide }))
    m.position.set(...pos)
    m.lookAt(0, 0, 0)
    s.add(m)
  }
  panel(10, 4, '#ffffff', 1.6, [0, 12, 2])         // softbox overhead
  panel(6, 5, '#fff1d6', 1.2, [-10, 5, 8])         // key, front-left
  panel(3, 8, '#f5b942', 1.4, [12, 3, -6])         // warm strip, back-right (the plug side)
  panel(16, 5, '#fff1d6', 0.38, [-10, 7, -9])      // where the lid tops reflect from the camera: a soft sheen across each lid
  return s
}

function Environment() {
  const { gl, scene } = useThree()
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl)
    const src = studio()
    const env = pmrem.fromScene(src, 0.03).texture
    scene.environment = env
    scene.environmentIntensity = 1.0
    src.traverse((o) => { if (o instanceof THREE.Mesh) { o.geometry.dispose(); (o.material as THREE.Material).dispose() } })
    return () => { scene.environment = null; env.dispose(); pmrem.dispose() }
  }, [gl, scene])
  return null
}

const MOTES = 30
const PUSH_PX = 140                                  // the cursor pushes motes within this many pixels

/** Glowing gold motes drifting around whatever the camera looks at. The cursor pushes the near ones away; they drift back. */
function Motes({ calm, ui }: { calm: boolean; ui: UiRef }) {
  const { camera, size } = useThree()
  const pts = useRef<THREE.Points>(null)
  const data = useMemo(() => {
    const home = new Float32Array(MOTES * 3), off = new Float32Array(MOTES * 3), phase = new Float32Array(MOTES)
    for (let i = 0; i < MOTES; i++) {
      home[i * 3] = (Math.random() - 0.5) * 16; home[i * 3 + 1] = (Math.random() - 0.35) * 6; home[i * 3 + 2] = (Math.random() - 0.5) * 9
      phase[i] = Math.random() * Math.PI * 2
    }
    return { home, off, phase }
  }, [])
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(MOTES * 3), 3))
    return g
  }, [])
  const mat = useMemo(() => new THREE.PointsMaterial({ map: radialGlow(), color: GOLD, size: 0.21, transparent: true, opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false }), [])
  useEffect(() => () => { geo.dispose(); mat.dispose() }, [geo, mat])
  const tmp = useMemo(() => ({ center: new THREE.Vector3(), fwd: new THREE.Vector3(), right: new THREE.Vector3(), up: new THREE.Vector3(), p: new THREE.Vector3() }), [])

  useFrame((_, dtRaw) => {
    const dt = Math.min(dtRaw, MAX_DT)
    const pos = geo.getAttribute('position') as THREE.BufferAttribute
    const arr = pos.array as Float32Array
    const { home, off, phase } = data
    // the cloud sits a little in front of the camera, so it surrounds the view at rest and when a cabinet is open
    camera.getWorldDirection(tmp.fwd)
    tmp.center.copy(camera.position).addScaledVector(tmp.fwd, 9)
    tmp.right.setFromMatrixColumn(camera.matrixWorld, 0)
    tmp.up.setFromMatrixColumn(camera.matrixWorld, 1)
    const t = performance.now() / 1000
    const ptr = ui.current.pointer
    for (let i = 0; i < MOTES; i++) {
      const k = i * 3, ph = phase[i]
      const wx = calm ? 0 : Math.sin(t * 0.33 + ph) * 0.9, wy = calm ? 0 : Math.sin(t * 0.27 + ph * 1.3) * 0.55, wz = calm ? 0 : Math.cos(t * 0.21 + ph) * 0.6
      tmp.p.set(tmp.center.x + home[k] + wx + off[k], tmp.center.y + home[k + 1] + wy + off[k + 1], tmp.center.z + home[k + 2] + wz + off[k + 2])
      if (!calm && ptr) {
        const s = tmp.p.clone().project(camera)
        const sx = (s.x * 0.5 + 0.5) * size.width, sy = (-s.y * 0.5 + 0.5) * size.height
        const dx = sx - ptr.x, dy = sy - ptr.y, d = Math.hypot(dx, dy)
        if (d < PUSH_PX && d > 0.001 && s.z < 1) {
          const f = (1 - d / PUSH_PX) * 3.2 * dt                    // push away from the cursor, in the screen plane
          off[k] += (tmp.right.x * dx - tmp.up.x * dy) / d * f
          off[k + 1] += (tmp.right.y * dx - tmp.up.y * dy) / d * f
          off[k + 2] += (tmp.right.z * dx - tmp.up.z * dy) / d * f
        }
      }
      // drift back home
      const back = 1 - Math.exp(-0.9 * dt)
      off[k] -= off[k] * back; off[k + 1] -= off[k + 1] * back; off[k + 2] -= off[k + 2] * back
      arr[k] = tmp.p.x; arr[k + 1] = tmp.p.y; arr[k + 2] = tmp.p.z
    }
    pos.needsUpdate = true
    geo.computeBoundingSphere()
  })
  return <points ref={(o: THREE.Points | null) => { pts.current = o; o?.layers.set(MIRROR_FREE) }} geometry={geo} material={mat} frustumCulled={false} />
}

/** Camera: wide over all five cabinets; at the reference framing over the open one. Also keeps the fog relative to it. */
function Rig({ state, places, stacked, calm }: { state: HubState; places: THREE.Vector3[]; stacked: boolean; calm: boolean }) {
  const { camera, size, scene } = useThree()
  const cur = useRef<{ pos: THREE.Vector3; look: THREE.Vector3 } | null>(null)
  const want = useMemo(() => ({ pos: new THREE.Vector3(), look: new THREE.Vector3() }), [])
  const center = useMemo(() => places.reduce((s, p) => s.add(p), new THREE.Vector3()).multiplyScalar(1 / places.length), [places])
  useEffect(() => { camera.layers.enable(MIRROR_FREE) }, [camera])
  useFrame((_, dtRaw) => {
    const dt = Math.min(dtRaw, MAX_DT)
    const cam = camera as THREE.PerspectiveCamera
    const aspect = size.width / Math.max(1, size.height)
    let dist: number
    if (state.mode === 'rest') {
      const across = places.map((p) => p.dot(RIGHT))
      const w = Math.max(...across) - Math.min(...across) + CAB.L * 1.15
      const h = stacked ? 7.2 : 2.6
      dist = fitDistance(w, h, cam.fov, aspect) * 1.02
      want.look.copy(center).setY(0.3)
      want.pos.copy(want.look).addScaledVector(toCamera(stacked ? 0.92 : undefined), dist)
    } else {
      const i = GROUPS.findIndex((g) => g.id === state.group)
      const p = places[i] ?? center
      dist = fitDistance(CAB.L * 2.15, 3.6, cam.fov, aspect)        // the reference: the open cabinet fills about 45% of the width
      want.look.copy(p).setY(0.62)
      want.pos.copy(want.look).addScaledVector(toCamera(), dist)
    }
    const k = calm ? 80 : 2.2
    if (!cur.current) cur.current = { pos: want.pos.clone(), look: want.look.clone() }
    const c = cur.current
    c.pos.set(damp(c.pos.x, want.pos.x, k, dt), damp(c.pos.y, want.pos.y, k, dt), damp(c.pos.z, want.pos.z, k, dt))
    c.look.set(damp(c.look.x, want.look.x, k, dt), damp(c.look.y, want.look.y, k, dt), damp(c.look.z, want.look.z, k, dt))
    camera.position.copy(c.pos)
    camera.lookAt(c.look)
    camera.updateMatrixWorld(true)
    const d = c.pos.distanceTo(c.look)
    if (scene.fog instanceof THREE.Fog) { scene.fog.near = d * 0.95; scene.fog.far = d * 2.1 }
  })
  return null
}

/** Reports readiness after the first frames, and steps quality down (bloom off, then mirror off) if frames are slow. */
function Governor({ tier, setTier, onReady }: { tier: Tier; setTier: (t: Tier) => void; onReady: () => void }) {
  const n = useRef(0), sum = useRef(0), told = useRef(false)
  const forced = useMemo(() => !!new URLSearchParams(window.location.search).get('fx'), [])
  useFrame((_, dt) => {
    n.current++
    if (n.current === 3 && !told.current) { told.current = true; onReady() }
    if (forced || tier === 'low' || n.current < 12) return
    sum.current += dt
    if (n.current === 52) {
      if (sum.current / 40 > 0.028) setTier(tier === 'high' ? 'medium' : 'low')
      n.current = 12; sum.current = 0
    }
  })
  return null
}

export interface HubSceneProps {
  state: HubState
  ui: UiRef
  hits: HitsRef
  calm: boolean
  active: boolean
  small: boolean
  onReady: () => void
  /** Calm mode draws on demand: true for a moment after anything changed, so the canvas can paint the new pose. */
  burst: boolean
}

/** `?fx=high|medium|low` pins the quality (for screenshots and slow machines); otherwise phones start low, desktops high. */
function initialTier(small: boolean): Tier {
  const fx = new URLSearchParams(window.location.search).get('fx')
  if (fx === 'high' || fx === 'medium' || fx === 'low') return fx
  return small ? 'low' : 'high'
}

export default function HubScene({ state, ui, hits, calm, active, small, onReady, burst }: HubSceneProps) {
  const fonts = useFontsReady()
  const [tier, setTier] = useState<Tier>(() => initialTier(small))
  const places = useMemo(() => cabinetPositions(GROUPS.length, small), [small])
  const center = useMemo(() => places.reduce((s, p) => s.add(p), new THREE.Vector3()).multiplyScalar(1 / places.length), [places])
  // a clicked card's lift-and-fly animation is timed from the moment of the click
  const enterId = state.mode === 'enter' ? state.tool : null
  const enter = useMemo(() => ({ id: enterId, at: enterId ? performance.now() : 0 }), [enterId])

  return (
    <Canvas frameloop={calm ? (burst ? 'always' : 'demand') : active ? 'always' : 'never'}
      dpr={tier === 'low' ? 1 : [1, 1.5]} camera={{ fov: 30, near: 0.05, far: 140, position: [6, 8, 20] }}
      gl={{ antialias: tier !== 'low', alpha: false, powerPreference: 'high-performance' }}
      onCreated={({ gl }) => { gl.setClearColor(0x000000, 1); gl.toneMapping = THREE.ACESFilmicToneMapping; gl.toneMappingExposure = 1.05 }}>
      <fog attach="fog" args={['#000000', 18, 40]} />
      <Environment />
      <ambientLight intensity={0.18} />
      <directionalLight position={[-7, 3, 1.5]} intensity={0.35} color="#fff3dc" />
      <directionalLight position={[7, 3.5, -5]} intensity={1.6} color={GOLD} />
      <Floor mirror={tier === 'high'} center={center} />
      <Motes calm={calm} ui={ui} />
      {GROUPS.map((g, i) => (
        <Cabinet key={g.id} group={g.id} at={places[i]} state={state} ui={ui} hits={hits} calm={calm} fonts={fonts} enter={enter} />
      ))}
      <Rig state={state} places={places} stacked={small} calm={calm} />
      {tier !== 'low' && <Bloom />}
      <Governor tier={tier} setTier={setTier} onReady={onReady} />
    </Canvas>
  )
}
