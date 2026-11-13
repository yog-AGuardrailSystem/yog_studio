import { useThree } from '@react-three/fiber'
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { Reflector } from 'three/addons/objects/Reflector.js'
import { backdrop, floorFade } from './textures'

/** The dark mirror the cabinets stand on. `mirror` false (phones, slow machines): a glossy floor without the reflection pass. */
export function Floor({ mirror, center }: { mirror: boolean; center: THREE.Vector3 }) {
  const { size, gl } = useThree()
  const reflector = useMemo(() => {
    if (!mirror) return null
    const ratio = Math.min(gl.getPixelRatio(), 1.5) * 0.5            // half resolution: the overlay blurs it anyway
    const r = new Reflector(new THREE.PlaneGeometry(120, 120), {
      clipBias: 0.003, textureWidth: Math.round(size.width * ratio), textureHeight: Math.round(size.height * ratio), color: 0x3c3c3c,
    })
    r.rotation.x = -Math.PI / 2
    // The mirror copies the main camera, layers included; keep it on layer 0 so bright light sources (layer 1) are not mirrored.
    const own = r.getReflectionCamera.bind(r)
    r.getReflectionCamera = (camera: THREE.Camera) => { const c = own(camera); c.layers.set(0); return c }
    return r
  }, [mirror, gl, size.width, size.height])
  useEffect(() => () => { reflector?.getRenderTarget().dispose(); reflector?.geometry.dispose(); (reflector?.material as THREE.Material | undefined)?.dispose() }, [reflector])

  const fade = useMemo(() => new THREE.MeshBasicMaterial({ map: floorFade(), transparent: true, depthWrite: false, toneMapped: false }), [])
  const gloss = useMemo(() => new THREE.MeshPhysicalMaterial({ color: "#020202", roughness: 0.55, metalness: 0.2, clearcoat: 0.6, clearcoatRoughness: 0.35 }), [])
  const back = useMemo(() => new THREE.MeshBasicMaterial({ map: backdrop(), fog: false, toneMapped: false, depthWrite: false }), [])
  useEffect(() => () => { fade.dispose(); gloss.dispose(); back.dispose() }, [fade, gloss, back])

  return (
    <group>
      {reflector ? <primitive object={reflector} /> : (
        <mesh rotation={[-Math.PI / 2, 0, 0]} material={gloss}><planeGeometry args={[120, 120]} /></mesh>
      )}
      {/* darkens the mirror so reflections are dim and fade out away from the cabinets */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[center.x, 0.0015, center.z]} material={fade} renderOrder={-1}>
        <planeGeometry args={[46, 46]} />
      </mesh>
      {/* the far wall: a dim warm glow fading to black */}
      <mesh ref={(o) => { o?.layers.set(1) }} position={[center.x, 10, center.z - 34]} material={back} renderOrder={-2}><planeGeometry args={[140, 60]} /></mesh>
    </group>
  )
}
