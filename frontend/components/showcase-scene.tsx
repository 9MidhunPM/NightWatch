'use client';

import { Suspense, useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { RoundedBox, useTexture } from '@react-three/drei';
import * as THREE from 'three';

type ShowcaseController = {
  progress: number;
  pointerX: number;
  pointerY: number;
  subscribe: (listener: () => void) => () => void;
};

type ShowcaseSceneProps = {
  controller: ShowcaseController;
  onReady: () => void;
  onError: () => void;
};

type Point = [number, number, number];
type SceneTextures = { rock: THREE.Texture; ground: THREE.Texture };

const MINT = '#76dcb0';
const CORAL = '#f28b76';
const SILVER = '#cbd5cf';
const clamp = (value: number) => Math.min(1, Math.max(0, value));
const ease = (value: number) => {
  const t = clamp(value);
  return t * t * (3 - 2 * t);
};

function seeded(seed: number) {
  let value = seed;
  return () => {
    value = (value * 16807) % 2147483647;
    return (value - 1) / 2147483646;
  };
}

function useSceneTextures(): SceneTextures {
  const [rock, ground] = useTexture(['/textures/rock.svg', '/textures/ground.svg']);

  useEffect(() => {
    for (const texture of [rock, ground]) {
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
      texture.repeat.set(3, 3);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = 2;
      texture.needsUpdate = true;
    }
  }, [rock, ground]);

  return { rock, ground };
}

function FacetedRock({ radius, depth, seed, texture }: {
  radius: number; depth: number; seed: number; texture: THREE.Texture;
}) {
  const geometry = useMemo(() => {
    const random = seeded(seed);
    const shape = new THREE.CylinderGeometry(radius, radius * .19, depth, 12, 3, false);
    const positions = shape.attributes.position;
    const offsets = Array.from({ length: 13 }, () => random() * .42 - .21);
    for (let index = 0; index < positions.count; index++) {
      const x = positions.getX(index);
      const y = positions.getY(index);
      const z = positions.getZ(index);
      const angle = Math.atan2(x, z);
      const slice = Math.round((angle + Math.PI) / (Math.PI * 2) * 12) % 12;
      const offset = offsets[slice];
      const ring = Math.hypot(x, z);
      const factor = ring > .1 ? 1 + offset * .17 : 1;
      const lowerRoughness = y < depth * .49 ? offsets[(slice + 4) % 12] * .9 : 0;
      positions.setXYZ(index, x * factor, y + lowerRoughness, z * factor);
    }
    shape.computeVertexNormals();
    return shape;
  }, [radius, depth, seed]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  return <group>
    <mesh geometry={geometry} position={[0, -depth / 2 - .4, 0]} castShadow receiveShadow>
      <meshStandardMaterial map={texture} color="#78877b" roughness={.96} flatShading />
    </mesh>
    <mesh position={[radius * .07, -depth - .67, -.1]} rotation={[Math.PI, .2, 0]} castShadow>
      <coneGeometry args={[radius * .21, 1.6, 5]} />
      <meshStandardMaterial color="#526c5d" roughness={.95} flatShading />
    </mesh>
    <mesh position={[-radius * .5, -depth * .55, radius * .42]} rotation={[.2, .5, -.35]} castShadow>
      <dodecahedronGeometry args={[radius * .22, 0]} />
      <meshStandardMaterial color="#a2ada1" roughness={.9} flatShading />
    </mesh>
    <mesh position={[radius * .64, -depth * .65, -radius * .17]} rotation={[.1, .3, .7]} castShadow>
      <dodecahedronGeometry args={[radius * .16, 0]} />
      <meshStandardMaterial color="#5c7669" roughness={.94} flatShading />
    </mesh>
  </group>;
}

function Cypress({ position, height = 1 }: { position: Point; height?: number }) {
  return <group position={position} scale={height}>
    <mesh position={[0, .25, 0]} castShadow>
      <cylinderGeometry args={[.05, .09, .5, 5]} />
      <meshStandardMaterial color="#655f4d" roughness={1} />
    </mesh>
    <mesh position={[0, .78, 0]} castShadow>
      <coneGeometry args={[.38, 1.4, 6]} />
      <meshStandardMaterial color="#365d48" roughness={.95} flatShading />
    </mesh>
    <mesh position={[0, 1.1, 0]} castShadow>
      <coneGeometry args={[.27, 1.05, 6]} />
      <meshStandardMaterial color="#659270" roughness={.93} flatShading />
    </mesh>
  </group>;
}

function Island({ position, radius, depth, seed, textures, children }: {
  position: Point;
  radius: number;
  depth: number;
  seed: number;
  textures: SceneTextures;
  children: React.ReactNode;
}) {
  const greenery = useMemo(() => {
    const random = seeded(seed + 5);
    return Array.from({ length: radius > 4 ? 13 : 7 }, (_, index) => {
      const angle = index / (radius > 4 ? 13 : 7) * Math.PI * 2 + .4;
      return {
        position: [Math.cos(angle) * radius * .84, .26, Math.sin(angle) * radius * .84] as Point,
        height: .72 + random() * .42,
      };
    });
  }, [radius, seed]);

  return <group position={position}>
    <FacetedRock radius={radius} depth={depth} seed={seed} texture={textures.rock} />
    <mesh position={[0, -.15, 0]} receiveShadow castShadow>
      <cylinderGeometry args={[radius * .99, radius, .62, 12]} />
      <meshStandardMaterial map={textures.ground} color="#a8b69c" roughness={.94} flatShading />
    </mesh>
    <mesh position={[0, -.48, 0]}>
      <cylinderGeometry args={[radius * 1.006, radius * 1.006, .035, 12]} />
      <meshStandardMaterial color={MINT} emissive={MINT} emissiveIntensity={.35} metalness={.3} roughness={.5} />
    </mesh>
    <mesh position={[0, .184, -.1]} receiveShadow>
      <cylinderGeometry args={[radius * .68, radius * .68, .065, 12]} />
      <meshStandardMaterial color="#c3cdc1" roughness={.75} />
    </mesh>
    <mesh position={[0, .223, -.1]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[radius * .65, radius * .66, 48]} />
      <meshBasicMaterial color="#718b76" transparent opacity={.8} />
    </mesh>
    {greenery.map((tree, index) => <Cypress key={index} {...tree} />)}
    {children}
  </group>;
}

function ServerTower({ position, height, accent = MINT }: {
  position: Point; height: number; accent?: string;
}) {
  const rows = Math.floor(height / .33);
  return <group position={position}>
    <RoundedBox args={[1.66, .2, 1.75]} position={[0, .1, 0]} radius={.045} smoothness={2} receiveShadow castShadow>
      <meshStandardMaterial color="#688270" metalness={.35} roughness={.53} />
    </RoundedBox>
    <RoundedBox args={[1.35, height, 1.25]} position={[0, height / 2 + .25, 0]} radius={.055} smoothness={2} castShadow receiveShadow>
      <meshStandardMaterial color={SILVER} metalness={.68} roughness={.34} />
    </RoundedBox>
    <mesh position={[0, height / 2 + .25, .637]}>
      <boxGeometry args={[1.12, height - .18, .035]} />
      <meshStandardMaterial color="#253d38" metalness={.46} roughness={.42} />
    </mesh>
    {Array.from({ length: rows }, (_, row) => <group key={row} position={[0, .47 + row * .32, .665]}>
      <mesh>
        <boxGeometry args={[.96, .245, .06]} />
        <meshStandardMaterial color="#69877a" metalness={.54} roughness={.37} />
      </mesh>
      <mesh position={[.32, 0, .04]}>
        <boxGeometry args={[.15, .045, .03]} />
        <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={.85} />
      </mesh>
      {[-.28, -.17, -.06].map(x => <mesh key={x} position={[x, 0, .039]}>
        <boxGeometry args={[.03, .14, .025]} />
        <meshStandardMaterial color="#253c36" roughness={.6} />
      </mesh>)}
    </group>)}
    <mesh position={[0, height + .31, 0]} castShadow>
      <boxGeometry args={[1.47, .13, 1.36]} />
      <meshStandardMaterial color="#e1e7da" metalness={.48} roughness={.4} />
    </mesh>
    <mesh position={[0, height + .388, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[.22, .32, 18]} />
      <meshStandardMaterial color="#345148" metalness={.45} roughness={.52} />
    </mesh>
    <mesh position={[-.686, height / 2 + .25, 0]}>
      <boxGeometry args={[.018, height - .24, .9]} />
      <meshStandardMaterial color="#6d897a" metalness={.65} roughness={.3} />
    </mesh>
  </group>;
}

function Database({ position }: { position: Point }) {
  return <group position={position}>
    <mesh position={[0, .18, 0]} castShadow receiveShadow>
      <cylinderGeometry args={[1.45, 1.52, .26, 24]} />
      <meshStandardMaterial color="#678270" metalness={.3} roughness={.62} />
    </mesh>
    {[0, 1, 2].map(tier => <group key={tier} position={[0, .66 + tier * .71, 0]}>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[1.13, 1.13, .63, 32]} />
        <meshStandardMaterial color={tier === 1 ? '#9ab5a1' : '#d1dbc9'} metalness={.58} roughness={.33} />
      </mesh>
      <mesh position={[0, -.32, 0]}>
        <cylinderGeometry args={[1.16, 1.16, .036, 32]} />
        <meshStandardMaterial color={MINT} emissive={MINT} emissiveIntensity={.62} metalness={.4} roughness={.4} />
      </mesh>
      <mesh position={[.06, 0, 1.129]}>
        <boxGeometry args={[.27, .06, .045]} />
        <meshStandardMaterial color={MINT} emissive={MINT} emissiveIntensity={1} />
      </mesh>
    </group>)}
    <mesh position={[0, 2.42, 0]} castShadow>
      <cylinderGeometry args={[1.17, 1.17, .16, 32]} />
      <meshStandardMaterial color="#e2e7d8" metalness={.5} roughness={.38} />
    </mesh>
    <mesh position={[0, 2.511, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[.35, .39, 32]} />
      <meshStandardMaterial color="#88ad96" metalness={.2} roughness={.5} />
    </mesh>
  </group>;
}

function DomainGateway({ routeMaterial }: { routeMaterial: React.RefObject<THREE.MeshStandardMaterial | null> }) {
  return <group position={[2.5, .29, 2.12]} rotation={[0, -.22, 0]}>
    <RoundedBox args={[2.55, .18, 1.18]} position={[0, .09, 0]} radius={.07} smoothness={2} receiveShadow castShadow>
      <meshStandardMaterial color="#6c8c77" metalness={.4} roughness={.56} />
    </RoundedBox>
    {[-1, 1].map(side => <group key={side} position={[side * .84, .98, 0]}>
      <mesh castShadow>
        <boxGeometry args={[.32, 1.6, .54]} />
        <meshStandardMaterial color="#d2deca" metalness={.55} roughness={.35} />
      </mesh>
      <mesh position={[0, 0, .278]}>
        <boxGeometry args={[.09, 1.25, .035]} />
        <meshStandardMaterial color={MINT} emissive={MINT} emissiveIntensity={.7} />
      </mesh>
    </group>)}
    <mesh position={[0, 1.78, 0]} castShadow>
      <torusGeometry args={[.84, .17, 8, 28, Math.PI]} />
      <meshStandardMaterial color="#d2deca" metalness={.5} roughness={.38} />
    </mesh>
    <mesh position={[0, 1.78, .13]}>
      <torusGeometry args={[.84, .037, 6, 28, Math.PI]} />
      <meshStandardMaterial ref={routeMaterial} color={MINT} emissive={MINT} emissiveIntensity={.8} />
    </mesh>
    <mesh position={[0, .215, .15]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[1.28, .78]} />
      <meshStandardMaterial color="#93ad92" roughness={.7} />
    </mesh>
  </group>;
}

function Endpoint({ position }: { position: Point }) {
  return <group position={position}>
    <mesh castShadow>
      <cylinderGeometry args={[.38, .47, .21, 16]} />
      <meshStandardMaterial color="#b6c9b3" metalness={.55} roughness={.35} />
    </mesh>
    <mesh position={[0, .15, 0]}>
      <sphereGeometry args={[.11, 12, 8]} />
      <meshStandardMaterial color={MINT} emissive={MINT} emissiveIntensity={1.2} />
    </mesh>
  </group>;
}

function Connection({ curve, materialRef, packetRef, muted = false }: {
  curve: THREE.CubicBezierCurve3;
  materialRef?: React.RefObject<THREE.MeshStandardMaterial | null>;
  packetRef?: React.RefObject<THREE.Mesh | null>;
  muted?: boolean;
}) {
  return <group>
    <mesh>
      <tubeGeometry args={[curve, 56, muted ? .018 : .035, 6, false]} />
      <meshStandardMaterial ref={materialRef} color={MINT} emissive={MINT} emissiveIntensity={muted ? .28 : .65} metalness={.2} roughness={.5} transparent opacity={muted ? .45 : .9} />
    </mesh>
    {packetRef && <mesh ref={packetRef}>
      <sphereGeometry args={[.092, 12, 8]} />
      <meshStandardMaterial color="#ecffdd" emissive={MINT} emissiveIntensity={1.8} />
    </mesh>}
  </group>;
}

function RendererLifecycle({ controller, onError }: Pick<ShowcaseSceneProps, 'controller' | 'onError'>) {
  const { gl, invalidate } = useThree();
  const errorCallback = useRef(onError);

  useEffect(() => { errorCallback.current = onError; }, [onError]);

  useEffect(() => {
    const unsubscribe = controller.subscribe(invalidate);
    invalidate();
    return unsubscribe;
  }, [controller, invalidate]);

  useEffect(() => {
    const canvas = gl.domElement;
    const lost = (event: Event) => {
      event.preventDefault();
      errorCallback.current();
    };
    canvas.addEventListener('webglcontextlost', lost);
    return () => canvas.removeEventListener('webglcontextlost', lost);
  }, [gl]);

  return null;
}

function Diorama({ controller, onReady }: ShowcaseSceneProps) {
  const textures = useSceneTextures();
  const whole = useRef<THREE.Group>(null);
  const route = useRef<THREE.MeshStandardMaterial>(null);
  const gateway = useRef<THREE.MeshStandardMaterial>(null);
  const packet = useRef<THREE.Mesh>(null);
  const halo = useRef<THREE.Mesh>(null);
  const { camera, invalidate, size } = useThree();
  const ready = useRef(false);
  const mounted = useRef(false);
  const readyFrame = useRef<number | null>(null);
  const readyCallback = useRef(onReady);
  const mintColor = useMemo(() => new THREE.Color(MINT), []);
  const coralColor = useMemo(() => new THREE.Color(CORAL), []);
  const tempColor = useMemo(() => new THREE.Color(), []);
  const target = useMemo(() => new THREE.Vector3(), []);
  const packetPoint = useMemo(() => new THREE.Vector3(), []);
  const curves = useMemo(() => ({
    service: new THREE.CubicBezierCurve3(
      new THREE.Vector3(2.5, 1.6, 2.12), new THREE.Vector3(2.1, 3.5, 1.4),
      new THREE.Vector3(-.7, 3.5, 1.1), new THREE.Vector3(-1.05, 1.3, .45),
    ),
    database: new THREE.CubicBezierCurve3(
      new THREE.Vector3(3.6, .48, -.3), new THREE.Vector3(5.3, 2, -.5),
      new THREE.Vector3(6.5, 2, -2.5), new THREE.Vector3(8.4, -.37, -2.75),
    ),
    worker: new THREE.CubicBezierCurve3(
      new THREE.Vector3(-3.75, .46, -1.4), new THREE.Vector3(-5.2, 2, -1.8),
      new THREE.Vector3(-6.8, 1.65, -3.1), new THREE.Vector3(-8.25, .58, -4.3),
    ),
  }), []);

  useEffect(() => {
    readyCallback.current = onReady;
  }, [onReady]);

  useEffect(() => {
    mounted.current = true;
    invalidate();
    return () => {
      mounted.current = false;
      ready.current = false;
      if (readyFrame.current !== null) cancelAnimationFrame(readyFrame.current);
      readyFrame.current = null;
    };
  }, [invalidate]);

  useFrame(() => {
    const progress = clamp(controller.progress);
    const approach = ease(progress / .52);
    const release = ease((progress - .68) / .32);
    const failure = ease((progress - .19) / .18) * (1 - ease((progress - .65) / .16));
    const portrait = size.width / Math.max(size.height, 1) < .9;
    const distance = portrait ? 1.19 : 1;
    camera.position.set(
      (14.8 - approach * 4.9 + release * 4.1) * distance + controller.pointerX * .55,
      (13.7 - approach * 5.1 + release * 3.5) * distance - controller.pointerY * .35,
      (19.8 - approach * 5.6 + release * 4.3) * distance,
    );
    target.set(approach * .75 - release * .75, -.45 + approach * 1.55 - release * 1.05, .3 + approach * .75 - release * .7);
    camera.lookAt(target);
    if (whole.current) {
      whole.current.rotation.y = -.08 + controller.pointerX * .027 + progress * .065;
      whole.current.rotation.x = controller.pointerY * .012;
    }
    tempColor.copy(mintColor).lerp(coralColor, failure);
    for (const material of [route.current, gateway.current]) {
      if (material) {
        material.color.copy(tempColor);
        material.emissive.copy(tempColor);
      }
    }
    if (packet.current) {
      curves.service.getPoint(clamp(.25 + progress * .72), packetPoint);
      packet.current.position.copy(packetPoint);
      const material = packet.current.material as THREE.MeshStandardMaterial;
      material.emissive.copy(tempColor);
    }
    if (halo.current) {
      const material = halo.current.material as THREE.MeshBasicMaterial;
      material.color.copy(tempColor);
      material.opacity = .28 + failure * .35;
      halo.current.scale.setScalar(1 + failure * .13);
    }
    // The suspended textures are available here. An animation-frame callback runs
    // after Fiber's current render, so the DOM loader cannot hide an empty canvas.
    if (!ready.current && mounted.current && readyFrame.current === null) {
      readyFrame.current = requestAnimationFrame(() => {
        readyFrame.current = null;
        if (!mounted.current) return;
        ready.current = true;
        readyCallback.current();
      });
    }
  });

  return <group ref={whole}>
    <Island position={[0, 0, 0]} radius={5.3} depth={4.1} seed={31} textures={textures}>
      <group rotation={[0, -.16, 0]}>
        <ServerTower position={[-1.85, .23, -.35]} height={3.15} />
        <ServerTower position={[.02, .23, -1.4]} height={4.05} />
        <ServerTower position={[1.91, .23, -1.48]} height={2.65} />
      </group>
      <DomainGateway routeMaterial={gateway} />
      <Endpoint position={[3.6, .34, -.3]} />
      <Endpoint position={[-3.75, .34, -1.4]} />
      <mesh ref={halo} position={[2.5, .25, 2.12]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.45, 1.48, 48]} />
        <meshBasicMaterial color={MINT} transparent opacity={.28} />
      </mesh>
      <mesh position={[-.1, .26, 2.44]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[1.55, 1.42]} />
        <meshStandardMaterial color="#96ae92" roughness={.95} />
      </mesh>
      <group position={[-.1, .4, 2.44]}>
        {[0, 1, 2].map(index => <mesh key={index} position={[(index - 1) * .35, 0, 0]} castShadow>
          <boxGeometry args={[.2, .28, .68]} />
          <meshStandardMaterial color="#cad8be" metalness={.35} roughness={.5} />
        </mesh>)}
      </group>
    </Island>
    <Island position={[-8.25, .15, -4.3]} radius={2.72} depth={2.8} seed={73} textures={textures}>
      <ServerTower position={[-.2, .23, -.1]} height={2.5} accent="#edcf8a" />
      <Endpoint position={[1.6, .36, .65]} />
    </Island>
    <Island position={[8.4, -.85, -2.75]} radius={3.05} depth={3.1} seed={109} textures={textures}>
      <Database position={[0, .25, -.14]} />
      <Endpoint position={[-1.75, .36, .15]} />
    </Island>
    <Connection curve={curves.service} materialRef={route} packetRef={packet} />
    <Connection curve={curves.database} muted />
    <Connection curve={curves.worker} muted />
    <mesh position={[-5.5, -3.3, 3]} rotation={[.6, .8, .2]}>
      <dodecahedronGeometry args={[.31, 0]} />
      <meshStandardMaterial color="#809c88" flatShading roughness={.92} />
    </mesh>
    <mesh position={[5.6, -5.1, -.45]} rotation={[.2, .2, .8]}>
      <dodecahedronGeometry args={[.43, 0]} />
      <meshStandardMaterial color="#668973" flatShading roughness={.92} />
    </mesh>
  </group>;
}

export default function ShowcaseScene(props: ShowcaseSceneProps) {
  return <Canvas
    shadows="percentage"
    frameloop="demand"
    dpr={[1, 1.5]}
    camera={{ position: [14.8, 13.7, 19.8], fov: 40, near: .1, far: 100 }}
    gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
    fallback={<span>Illustrative infrastructure scene</span>}
    onCreated={({ gl }) => {
      gl.toneMapping = THREE.ACESFilmicToneMapping;
      gl.toneMappingExposure = 1.23;
      gl.outputColorSpace = THREE.SRGBColorSpace;
    }}
    style={{ pointerEvents: 'none' }}
    aria-hidden="true"
  >
    <fog attach="fog" args={['#0b1215', 42, 85]} />
    <ambientLight intensity={.55} />
    <hemisphereLight args={['#e5f0dc', '#233b30', 1.6]} />
    <directionalLight
      position={[5, 18, 13]} intensity={3.4} color="#f5f1dd" castShadow
      shadow-mapSize={[1024, 1024]} shadow-camera-left={-16} shadow-camera-right={16}
      shadow-camera-top={12} shadow-camera-bottom={-12} shadow-camera-near={.1}
      shadow-camera-far={50} shadow-bias={-.0007} shadow-normalBias={.06}
    />
    <directionalLight position={[-12, 5, -7]} intensity={2.5} color="#8cccab" />
    <directionalLight position={[12, 3, -7]} intensity={1.8} color="#bed7ee" />
    <RendererLifecycle controller={props.controller} onError={props.onError} />
    <Suspense fallback={null}>
      <Diorama {...props} />
    </Suspense>
  </Canvas>;
}
