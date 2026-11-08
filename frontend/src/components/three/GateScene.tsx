/**
 * GateScene: the 3D hero. An agent fires an action; it flies at the YOG gate; the decision comes from
 * lib/yogMirror.evaluate() (mirrors YOG: DENY > ALLOW > default DENY). ALLOW: the packet passes and the lock
 * opens. DENY: the ring flashes red, the packet bursts, the lock shakes and stays shut.
 *
 * Heavy (three.js). Never import this directly from a page: use ./Gate (lazy + fallback).
 * Test hooks on the wrapper: data-testid=gate-scene, data-ready, data-decision, data-n.
 */
import { Canvas, useFrame, useThree, type RootState } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { evaluate, type Call, type Result } from '../../lib/yogMirror'

export interface Scenario {
  id: string
  label: string
  call: Call
}
export const SCENARIOS: Scenario[] = [
  { id: 'unlock-3am', label: 'Unlock at 3am', call: { tool: 'unlock_door', hour: 3 } },
  { id: 'unlock-2pm', label: 'Unlock at 2pm', call: { tool: 'unlock_door', hour: 14 } },
  { id: 'thermo-35', label: 'Thermostat 35°C', call: { tool: 'set_thermostat', hour: 12, temperature: 35 } },
  { id: 'valve-80', label: 'Open valve 80%', call: { tool: 'open_valve', hour: 12, percent: 80 } },
]
export const toolLabel = (c: Call) =>
  c.tool === 'unlock_door' ? `unlock_door @ ${String(c.hour).padStart(2, '0')}:00`
    : c.tool === 'lock_door' ? 'lock_door'
    : c.tool === 'set_thermostat' ? `set_thermostat(${c.temperature})`
    : `open_valve(${c.percent}%)`

export interface Request {
  n: number
  call: Call
}
export interface GateSceneProps {
  /** change `request.n` to fire a call from outside (used by /how-it-works) */
  request?: Request | null
  /** idle auto-cycle through SCENARIOS */
  autoplay?: boolean
  /** show the scenario chips + readout */
  showControls?: boolean
  onDecision?: (r: Result, call: Call) => void
  /** no continuous animation: render one still frame */
  still?: boolean
  className?: string
}

const GREEN = new THREE.Color('#22c55e')
const RED = new THREE.Color('#ef4444')
const SKY = new THREE.Color('#38bdf8')
const ease = (t: number) => 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3)

const FLY = 1.1 // seconds for the packet to reach the gate
const AFTER = 0.8 // ALLOW: packet travels on to the door
const RELOCK = 4.4 // seconds after firing the lock closes again
const N_PART = 70

interface Anim {
  t0: number
  result: Result
  n: number
}

function World({ anim, mobile }: { anim: React.RefObject<Anim | null>; mobile: boolean }) {
  const ring = useRef<THREE.Mesh>(null)
  const ringMat = useRef<THREE.MeshStandardMaterial>(null)
  const halo = useRef<THREE.Mesh>(null)
  const packet = useRef<THREE.Mesh>(null)
  const packetMat = useRef<THREE.MeshStandardMaterial>(null)
  const shackle = useRef<THREE.Group>(null)
  const doorGroup = useRef<THREE.Group>(null)
  const lockMat = useRef<THREE.MeshStandardMaterial>(null)
  const pts = useRef<THREE.Points>(null)
  const agent = useRef<THREE.Mesh>(null)
  const rig = useRef<THREE.Group>(null)
  // keep the whole scene (agent .. door, about 6.4 units wide) in frame on any aspect ratio
  const { camera, size } = useThree()
  useEffect(() => {
    const aspect = size.width / Math.max(1, size.height)
    camera.position.z = Math.max(7, 3.7 / (Math.tan(THREE.MathUtils.degToRad(21)) * aspect))
    camera.updateProjectionMatrix()
  }, [camera, size])
  const shackleOpen = useRef(0)
  const flash = useRef(0)
  const flashColor = useRef(SKY.clone())
  const burst = useRef<{ t: number; vel: Float32Array } | null>(null)
  const lastN = useRef(-1)

  const nPart = mobile ? 40 : N_PART
  const positions = useMemo(() => new Float32Array(nPart * 3), [nPart])
  const stars = useMemo(() => {
    const a = new Float32Array((mobile ? 90 : 220) * 3)
    for (let i = 0; i < a.length; i += 3) {
      a[i] = (Math.random() - 0.5) * 22
      a[i + 1] = (Math.random() - 0.5) * 12
      a[i + 2] = -2 - Math.random() * 8
    }
    return a
  }, [mobile])

  useFrame((state, dt) => {
    const t = state.clock.elapsedTime
    // pointer parallax on the whole rig
    if (rig.current) {
      rig.current.rotation.y += (state.pointer.x * 0.35 - rig.current.rotation.y) * Math.min(1, dt * 3)
      rig.current.rotation.x += (-state.pointer.y * 0.15 - rig.current.rotation.x) * Math.min(1, dt * 3)
    }
    if (agent.current) {
      agent.current.rotation.x = t * 0.8
      agent.current.rotation.y = t * 0.6
    }
    if (halo.current && ringMat.current) {
      // idle breathing
      const idle = 0.55 + Math.sin(t * 2) * 0.12
      halo.current.scale.setScalar(1 + Math.sin(t * 2) * 0.015)
      ringMat.current.emissiveIntensity = idle + flash.current * 2.2
    }

    const a = anim.current
    if (a && a.n !== lastN.current) {
      lastN.current = a.n
      burst.current = null
      flash.current = 0
      flashColor.current.copy(SKY)
    }
    let pktVisible = false
    let shake = 0
    let wantOpen = 0
    if (a) {
      const e = t - a.t0
      const allow = a.result.decision === 'ALLOW'
      const col = allow ? GREEN : RED
      if (e < FLY) {
        pktVisible = true
        const x = THREE.MathUtils.lerp(-2.8, -0.55, ease(e / FLY))
        packet.current?.position.set(x, Math.sin(e * 6) * 0.08, 0)
        packetMat.current?.color.copy(SKY)
        packetMat.current?.emissive.copy(SKY)
      } else {
        // decision moment (first frame after FLY)
        if (flash.current === 0 && e < FLY + 0.2) {
          flash.current = 1
          flashColor.current.copy(col)
          if (!allow) {
            const vel = new Float32Array(nPart * 3)
            for (let i = 0; i < nPart; i++) {
              const th = Math.random() * Math.PI * 2
              const ph = Math.acos(2 * Math.random() - 1)
              const sp = 1.2 + Math.random() * 2.2
              vel[i * 3] = Math.sin(ph) * Math.cos(th) * sp * 0.7 - 0.6
              vel[i * 3 + 1] = Math.sin(ph) * Math.sin(th) * sp
              vel[i * 3 + 2] = Math.cos(ph) * sp
              positions[i * 3] = -0.55
              positions[i * 3 + 1] = 0
              positions[i * 3 + 2] = 0
            }
            burst.current = { t: 0, vel }
          }
        }
        if (allow && e < FLY + AFTER) {
          pktVisible = true
          const k = ease((e - FLY) / AFTER)
          packet.current?.position.set(THREE.MathUtils.lerp(-0.55, 1.5, k), 0, 0)
          packetMat.current?.color.copy(GREEN)
          packetMat.current?.emissive.copy(GREEN)
        }
        if (allow && e > FLY + AFTER && e < RELOCK) wantOpen = 1
        if (!allow && e < FLY + 0.7) shake = (1 - (e - FLY) / 0.7) * 0.07
      }
      if (e > RELOCK) wantOpen = 0
    }
    if (packet.current) {
      packet.current.visible = pktVisible
      packet.current.rotation.x = t * 3
      packet.current.rotation.z = t * 2
    }
    // flash decays; ring colour follows
    flash.current = Math.max(0, flash.current - dt * 1.6)
    if (ringMat.current) {
      ringMat.current.emissive.copy(SKY).lerp(flashColor.current, Math.min(1, flash.current * 1.6))
      ringMat.current.color.copy(ringMat.current.emissive).multiplyScalar(0.4)
    }
    if (lockMat.current) {
      const target = shackleOpen.current > 0.5 ? GREEN : shake > 0 ? RED : SKY
      lockMat.current.emissive.lerp(target, Math.min(1, dt * 6))
    }
    shackleOpen.current += (wantOpen - shackleOpen.current) * Math.min(1, dt * 5)
    if (shackle.current) {
      shackle.current.rotation.z = shackleOpen.current * 0.9
      shackle.current.position.y = 0.42 + shackleOpen.current * 0.22
    }
    if (doorGroup.current) doorGroup.current.position.x = 1.9 + (shake ? Math.sin(t * 90) * shake : 0)

    // particles
    const b = burst.current
    if (pts.current) {
      pts.current.visible = !!b
      if (b) {
        b.t += dt
        for (let i = 0; i < nPart; i++) {
          positions[i * 3] += b.vel[i * 3] * dt
          positions[i * 3 + 1] += b.vel[i * 3 + 1] * dt
          positions[i * 3 + 2] += b.vel[i * 3 + 2] * dt
        }
        pts.current.geometry.attributes.position.needsUpdate = true
        const m = pts.current.material as THREE.PointsMaterial
        m.opacity = Math.max(0, 1 - b.t / 1.3)
        if (b.t > 1.3) burst.current = null
      }
    }
  })

  return (
    <group ref={rig}>
      <ambientLight intensity={0.35} />
      <pointLight position={[-4, 2, 4]} intensity={40} color="#38bdf8" />
      <pointLight position={[4, 1, 4]} intensity={25} color="#ffffff" />

      {/* faint floor grid */}
      <gridHelper args={[26, 26, '#0e3a5c', '#0b2238']} position={[0, -1.95, 0]} />

      {/* stars */}
      <points position={[0, 0, 0]}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[stars, 3]} />
        </bufferGeometry>
        <pointsMaterial size={0.04} color="#7dd3fc" transparent opacity={0.7} sizeAttenuation />
      </points>

      {/* agent */}
      <mesh ref={agent} position={[-3.0, 0, 0]}>
        <icosahedronGeometry args={[0.38, 0]} />
        <meshStandardMaterial color="#082f49" emissive="#38bdf8" emissiveIntensity={1.2} wireframe />
      </mesh>

      {/* the YOG gate: ring perpendicular to the flight path */}
      <mesh ref={ring} position={[-0.55, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[1.35, 0.07, 20, 96]} />
        <meshStandardMaterial ref={ringMat} color="#0c4a6e" emissive="#38bdf8" emissiveIntensity={0.6} metalness={0.5} roughness={0.3} />
      </mesh>
      <mesh ref={halo} position={[-0.55, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[1.35, 0.2, 12, 96]} />
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.08} depthWrite={false} blending={THREE.AdditiveBlending} />
      </mesh>

      {/* packet */}
      <mesh ref={packet} position={[-2.8, 0, 0]} visible={false}>
        <octahedronGeometry args={[0.22, 0]} />
        <meshStandardMaterial ref={packetMat} color="#38bdf8" emissive="#38bdf8" emissiveIntensity={2.2} />
      </mesh>

      {/* DENY burst */}
      <points ref={pts} visible={false}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
        <pointsMaterial size={0.09} color="#ef4444" transparent opacity={1} depthWrite={false} blending={THREE.AdditiveBlending} sizeAttenuation />
      </points>

      {/* door + lock */}
      <group ref={doorGroup} position={[1.9, 0, 0]}>
        <mesh>
          <boxGeometry args={[0.18, 3.3, 2.1]} />
          <meshStandardMaterial color="#1d3a5c" metalness={0.55} roughness={0.35} emissive="#103a63" emissiveIntensity={0.8} />
        </mesh>
        <mesh position={[-0.11, 0, 0]}>
          <boxGeometry args={[0.04, 3.1, 1.9]} />
          <meshStandardMaterial color="#1f4268" metalness={0.4} roughness={0.5} emissive="#0e2f4f" emissiveIntensity={0.6} />
        </mesh>
        {/* lock body */}
        <mesh position={[-0.2, -0.15, 0]}>
          <boxGeometry args={[0.16, 0.62, 0.56]} />
          <meshStandardMaterial ref={lockMat} color="#0f2a44" emissive="#38bdf8" emissiveIntensity={0.9} metalness={0.7} roughness={0.25} />
        </mesh>
        {/* shackle */}
        <group ref={shackle} position={[-0.2, 0.42, 0]}>
          <mesh rotation={[0, 0, 0]}>
            <torusGeometry args={[0.2, 0.05, 12, 32, Math.PI]} />
            <meshStandardMaterial color="#9fb3c8" metalness={0.9} roughness={0.2} />
          </mesh>
        </group>
      </group>
    </group>
  )
}

export default function GateScene({ request, autoplay = true, showControls = true, onDecision, still = false, className = '' }: GateSceneProps) {
  const wrap = useRef<HTMLDivElement>(null)
  const anim = useRef<Anim | null>(null)
  const clock = useRef<RootState['clock'] | null>(null)
  const [cur, setCur] = useState<{ n: number; call: Call; result: Result } | null>(null)
  const [visible, setVisible] = useState(true)
  const [tabOn, setTabOn] = useState(true)
  const [ready, setReady] = useState(false)
  const lastUser = useRef(0)
  const nRef = useRef(0)
  const mobile = typeof window !== 'undefined' && window.innerWidth < 640

  function fire(call: Call, byUser = false) {
    if (byUser) lastUser.current = Date.now()
    const result = evaluate(call)
    const n = ++nRef.current
    anim.current = { t0: clock.current?.elapsedTime ?? 0, result, n }
    setCur({ n, call, result })
    onDecision?.(result, call)
  }

  // external requests (how-it-works)
  const reqN = request?.n
  useEffect(() => {
    if (request && request.n > 0) fire(request.call, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqN])

  // pause when off-screen / tab hidden
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.05 })
    io.observe(el)
    const vis = () => setTabOn(!document.hidden)
    document.addEventListener('visibilitychange', vis)
    return () => {
      io.disconnect()
      document.removeEventListener('visibilitychange', vis)
    }
  }, [])

  const running = visible && tabOn && !still
  // idle autoplay: first shot soon, then every 4.5s unless the user has been playing
  useEffect(() => {
    if (!autoplay || !running || !ready) return
    let i = 0
    const first = setTimeout(() => fire(SCENARIOS[0].call), 900)
    const id = setInterval(() => {
      if (Date.now() - lastUser.current < 9000) return
      i = (i + 1) % SCENARIOS.length
      fire(SCENARIOS[i].call)
    }, 4500)
    return () => {
      clearTimeout(first)
      clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoplay, running, ready])

  const decision = cur?.result.decision
  return (
    <div
      ref={wrap}
      className={`gate-scene relative ${className}`}
      data-testid="gate-scene"
      data-ready={ready ? 'true' : 'false'}
      data-decision={decision ?? 'none'}
      data-n={cur?.n ?? 0}
    >
      <Canvas
        camera={{ position: [0, 0.4, 7.4], fov: 42 }}
        dpr={[1, mobile ? 1 : 1.75]}
        frameloop={running ? 'always' : 'demand'}
        gl={{ antialias: !mobile, alpha: true, powerPreference: 'high-performance' }}
        onCreated={(s) => {
          clock.current = s.clock
          setReady(true)
        }}
        aria-label="3D scene: an agent's action is checked at the YOG gate before it can reach the door lock"
      >
        <World anim={anim} mobile={mobile} />
      </Canvas>

      {showControls && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 p-3 sm:p-4">
          <div className="gate-readout pointer-events-auto mx-auto max-w-md rounded-xl border border-white/10 bg-slate-950/70 p-3 backdrop-blur" aria-live="polite">
            {cur ? (
              <div className="flex items-center gap-3">
                <span
                  className={`rounded-md border-2 px-3 py-0.5 font-display text-xl font-extrabold tracking-wider ${
                    decision === 'ALLOW' ? 'border-emerald-400 text-emerald-300' : 'border-red-400 text-red-300'
                  }`}
                >
                  {decision}
                </span>
                <div className="min-w-0">
                  <p className="truncate font-mono text-xs text-slate-300">{toolLabel(cur.call)}</p>
                  <p className="text-xs text-slate-400">{cur.result.reason}</p>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400">Pick an action. YOG decides before it reaches the lock.</p>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {SCENARIOS.map((s) => (
                <button key={s.id} type="button" onClick={() => fire(s.call, true)} className="chip" data-scenario={s.id}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
