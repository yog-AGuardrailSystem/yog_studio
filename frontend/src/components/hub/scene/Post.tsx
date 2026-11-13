import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'

/** Bloom: only the bright parts (lit rims, the plug and beam, a lit card) glow, like the reference. Takes over rendering. */
export function Bloom() {
  const { gl, scene, camera, size } = useThree()
  const composer = useMemo(() => {
    const c = new EffectComposer(gl)
    c.addPass(new RenderPass(scene, camera))
    c.addPass(new UnrealBloomPass(new THREE.Vector2(size.width, size.height), 0.42, 0.45, 0.72))
    c.addPass(new OutputPass())
    return c
  }, [gl, scene, camera])                          // size is applied below, without rebuilding the passes
  useEffect(() => {
    composer.setPixelRatio(gl.getPixelRatio())
    composer.setSize(size.width, size.height)
  }, [composer, gl, size.width, size.height])
  useEffect(() => () => composer.dispose(), [composer])
  useFrame((_, dt) => { composer.render(dt) }, 1)
  return null
}
