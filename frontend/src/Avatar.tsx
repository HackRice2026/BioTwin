import {
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  Component,
} from "react";
import type { ReactNode, RefObject } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { RotateCcw, Move, Volume2 } from "lucide-react";
import type { TwinState, SimulationOverlay } from "./contracts";
import { AvatarFSM } from "./fsm";
import { humanize } from "./api";

class CanvasBoundary extends Component<
  { children: ReactNode },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <div className="canvas-fallback">
        3D rendering is unavailable on this device. Your measurements and plan
        remain available.
      </div>
    ) : (
      this.props.children
    );
  }
}

function Body({
  live,
  overlay,
  reduced,
  speaking,
  onPerf,
  onMotion,
}: {
  live: RefObject<TwinState | null>;
  overlay: RefObject<SimulationOverlay | null>;
  reduced: boolean;
  speaking: boolean;
  onPerf: (n: number) => void;
  onMotion: (s: string) => void;
}) {
  const { scene } = useGLTF("/assets/twin.glb");
  const model = useMemo(() => {
    const clone = scene.clone(true);
    clone.traverse((o) => {
      if (o instanceof THREE.Mesh)
        o.material = (o.material as THREE.Material).clone();
    });
    return clone;
  }, [scene]);
  const nodes = useMemo(() => {
    const m: Record<string, THREE.Object3D> = {};
    model.traverse((o) => {
      m[o.name] = o;
    });
    return m;
  }, [model]);
  const fsm = useRef(new AvatarFSM());
  const phase = useRef({ pulse: 0, breath: 0, step: 0 });
  const performance = useRef<number[]>([]);
  const reported = useRef(0);
  const label = useRef("IDLE");
  useFrame((_, rawDt) => {
    if (!live.current) return;
    const dt = Math.min(rawDt, 0.1),
      state = live.current,
      simulation = overlay.current;
    const d = simulation?.drivers ?? state.drivers;
    const clock = _.clock.elapsedTime;
    const motion = fsm.current.update(d, clock);
    if (motion !== label.current) {
      label.current = motion;
      onMotion(motion);
    }
    const stepActive = [
      "EXERTION_RISING",
      "EXERCISING",
      "EXERTION_FALLING",
    ].includes(motion);
    phase.current.step += dt * (2 + d.exertion * 5);
    phase.current.breath += dt * (d.breath_hz ?? 0) * Math.PI * 2;
    phase.current.pulse += dt * (d.pulse_hz ?? 0) * Math.PI * 2;
    const damp = (current: number, target: number) =>
      THREE.MathUtils.damp(current, target, 4 / fsm.current.crossfade, dt);
    const gesture = [
      "very_drained",
      "drained",
      "below_average",
      "balanced",
      "strong",
      "peak",
    ].indexOf(state.readiness.state);
    const fatigue = d.fatigue;
    const gait =
      !reduced && stepActive ? Math.sin(phase.current.step) * d.exertion : 0;
    const breath =
      !reduced && d.breath_hz != null
        ? Math.sin(phase.current.breath) * 0.018
        : 0;
    nodes.Torso.rotation.x = damp(nodes.Torso.rotation.x, fatigue * 0.18);
    nodes.Torso.scale.z = damp(nodes.Torso.scale.z, 1 + breath);
    nodes.Head.rotation.x = damp(
      nodes.Head.rotation.x,
      fatigue * 0.35 - (gesture === 5 ? 0.12 : 0),
    );
    nodes.Hips.position.y = damp(
      nodes.Hips.position.y,
      1.04 -
        fatigue * 0.055 +
        (!reduced && stepActive ? Math.abs(gait) * 0.035 : 0),
    );
    for (const [side, sign] of [
      ["Left", 1],
      ["Right", -1],
    ] as const) {
      const arm = nodes[side + "Arm"],
        forearm = nodes[side + "Forearm"];
      const peak = gesture === 5 && !stepActive;
      const openness = [0.01, 0.05, 0.1, 0.16, 0.34, 1.32][
        Math.max(0, gesture)
      ];
      arm.rotation.z = damp(arm.rotation.z, sign * (peak ? 1.32 : openness));
      arm.rotation.x = damp(
        arm.rotation.x,
        -gait * sign * 0.65 +
          (speaking && !reduced ? Math.sin(clock * 2 + sign) * 0.13 - 0.25 : 0),
      );
      forearm.rotation.z = damp(forearm.rotation.z, peak ? sign * 1.9 : 0);
      forearm.rotation.x = damp(
        forearm.rotation.x,
        stepActive ? -0.7 : fatigue * -0.12 + (speaking ? -0.25 : 0),
      );
      nodes[side + "Hand"].rotation.x = damp(
        nodes[side + "Hand"].rotation.x,
        -fatigue * 0.2,
      );
      nodes[side + "Thigh"].rotation.x = damp(
        nodes[side + "Thigh"].rotation.x,
        gait * sign * 0.5 + fatigue * 0.08,
      );
      nodes[side + "Shin"].rotation.x = damp(
        nodes[side + "Shin"].rotation.x,
        Math.max(0, -gait * sign) * 0.6 - fatigue * 0.1,
      );
      nodes[side + "Foot"].rotation.x = damp(
        nodes[side + "Foot"].rotation.x,
        -gait * sign * 0.12,
      );
      for (let i = 0; i < 4; i++) {
        const finger = nodes[`Finger${sign}_${i}`];
        if (finger)
          finger.rotation.x = damp(
            finger.rotation.x,
            peak ? -1.1 : -0.15 - fatigue * 0.3,
          );
      }
    }
    const heart = nodes.Heart as THREE.Mesh;
    (heart.material as THREE.MeshStandardMaterial).emissiveIntensity =
      reduced || d.pulse_hz == null
        ? 0.5
        : 0.6 + Math.max(0, Math.sin(phase.current.pulse)) ** 8 * 2;
    nodes.Mouth.scale.y =
      speaking && !reduced
        ? 0.004 + Math.abs(Math.sin(clock * 12)) * 0.013
        : 0.004;
    if (clock > 3 && rawDt < 0.5) performance.current.push(rawDt * 1000);
    if (clock - reported.current > 5 && performance.current.length > 60) {
      const values = performance.current.splice(0).sort((a, b) => a - b);
      const p95 = values[Math.floor(values.length * 0.95)];
      onPerf(p95);
      reported.current = clock;
    }
  });
  return <primitive object={model} position={[0, -1.0, 0]} />;
}

export default function Avatar({
  live,
  overlay,
  state,
  reduced,
  speaking = false,
}: {
  live: RefObject<TwinState | null>;
  overlay: RefObject<SimulationOverlay | null>;
  state: TwinState;
  reduced: boolean;
  speaking?: boolean;
}) {
  const controls = useRef<OrbitControlsImpl>(null);
  const [quality, setQuality] = useState("Auto");
  const [dpr, setDpr] = useState(1.5);
  const [p95, setP95] = useState<number | null>(null);
  const [motion, setMotion] = useState("IDLE");
  useEffect(() => {
    setDpr(quality === "Low" ? 1 : quality === "High" ? 2 : 1.5);
  }, [quality]);
  const perf = (n: number) => {
    setP95(n);
    if (quality === "Auto" && n > 25) setDpr(1);
  };
  return (
    <div className="avatar-card">
      <div className="avatar-top">
        <span className="eyebrow">YOUR DIGITAL TWIN</span>
        <span className="avatar-state">
          <i />
          {state.readiness.score == null
            ? "Awaiting data"
            : humanize(state.readiness.state)}
        </span>
      </div>
      <div className="avatar-coordinates">
        <span>01 / PHYSIOLOGICAL VIEW</span>
        <span>{overlay.current ? "SIMULATION" : humanize(motion)}</span>
      </div>
      <CanvasBoundary>
        <Canvas
          dpr={dpr}
          camera={{ position: [0, 0.28, 3.7], fov: 37 }}
          gl={{
            antialias: true,
            alpha: true,
            powerPreference: "high-performance",
          }}
          style={{ height: 390 }}
        >
          <ambientLight intensity={1.8} />
          <directionalLight
            position={[3, 5, 4]}
            intensity={3}
            color="#edfff4"
          />
          <directionalLight
            position={[-4, 2, -3]}
            intensity={4}
            color="#51bb9d"
          />
          <Suspense fallback={null}>
            <Body
              live={live}
              overlay={overlay}
              reduced={reduced}
              speaking={speaking}
              onPerf={perf}
              onMotion={setMotion}
            />
          </Suspense>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.0, 0]}>
            <ringGeometry args={[0.47, 0.48, 72]} />
            <meshBasicMaterial
              color="#70b59f"
              transparent
              opacity={0.4}
              side={THREE.DoubleSide}
            />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.01, 0]}>
            <ringGeometry args={[0.72, 0.724, 72]} />
            <meshBasicMaterial
              color="#70b59f"
              transparent
              opacity={0.22}
              side={THREE.DoubleSide}
            />
          </mesh>
          <OrbitControls
            ref={controls}
            enablePan={false}
            enableZoom
            minDistance={2.5}
            maxDistance={5}
            target={[0, 0.1, 0]}
            minPolarAngle={0.8}
            maxPolarAngle={1.8}
          />
        </Canvas>
      </CanvasBoundary>
      <div className="avatar-caption">
        <Move size={13} />
        <span>Drag to explore your twin</span>
        {speaking && (
          <span className="speaking">
            <Volume2 size={12} /> Speaking
          </span>
        )}
      </div>
      <div className="avatar-bottom">
        <span>
          <i className="mint-dot" />{" "}
          {reduced
            ? "Reduced motion"
            : p95
              ? `${Math.round(1000 / p95)} fps · p95 ${p95.toFixed(1)} ms`
              : "Initializing 3D"}
        </span>
        <div>
          <select
            aria-label="Graphics quality"
            value={quality}
            onChange={(e) => setQuality(e.target.value)}
          >
            {["Auto", "Low", "Medium", "High"].map((q) => (
              <option key={q}>{q}</option>
            ))}
          </select>
          <button
            className="icon-btn light"
            aria-label="Reset avatar view"
            onClick={() => controls.current?.reset()}
          >
            <RotateCcw size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
useGLTF.preload("/assets/twin.glb");
