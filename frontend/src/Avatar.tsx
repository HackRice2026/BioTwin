import {
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  Component,
} from "react";
import type { ReactNode, RefObject } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Environment, OrbitControls, useGLTF } from "@react-three/drei";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import {
  Dumbbell,
  LoaderCircle,
  Mic,
  Move,
  RotateCcw,
  Volume2,
} from "lucide-react";
import type { TwinState, SimulationOverlay } from "./contracts";
import { humanize } from "./api";
import {
  axisAngleToQuaternion,
  emitAvatarSemantic,
  listenAvatarAudio,
  listenAvatarSemantic,
  parseBodyFrame,
  parseFaceFrame,
} from "./avatar/avatarBus";
import {
  audio2FaceMorphMap,
  emotionMorphs,
  mouthFallback,
} from "./avatar/config/morphMappings";
import type {
  AvatarAction,
  AvatarSemanticState,
  BodyFrame,
  FaceFrame,
} from "./avatar/state/AvatarState";
import {
  blendEmotion,
  clamp01,
  defaultAvatarState,
  defaultEmotion,
} from "./avatar/state/AvatarState";

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

const faceHttp =
  import.meta.env.VITE_FACE_SERVICE_HTTP || "http://localhost:8765";
const faceWs =
  import.meta.env.VITE_FACE_SERVICE_WS || "ws://localhost:8765/ws/face";
const bodyHttp =
  import.meta.env.VITE_BODY_SERVICE_HTTP || "http://localhost:8766";
const bodyWs =
  import.meta.env.VITE_BODY_SERVICE_WS || "ws://localhost:8766/ws/body";

const demoStates: Record<string, Partial<AvatarSemanticState>> = {
  "1": {
    emotion: defaultEmotion,
    action: "idle",
    gaze: "user",
    camera: "conversation",
  },
  "2": {
    emotion: {
      energy: 0.28,
      happiness: 0.22,
      fatigue: 0.72,
      stress: 0.14,
      confidence: 0.78,
      excitement: 0.08,
      concern: 0.62,
    },
    action: "listen",
    gaze: "user",
  },
  "3": {
    emotion: {
      energy: 0.42,
      happiness: 0.18,
      fatigue: 0.28,
      stress: 0.7,
      confidence: 0.76,
      excitement: 0.12,
      concern: 0.58,
    },
    action: "think",
    gaze: "away",
  },
  "4": {
    emotion: {
      energy: 0.9,
      happiness: 0.78,
      fatigue: 0.02,
      stress: 0.04,
      confidence: 0.96,
      excitement: 0.86,
      concern: 0.03,
    },
    action: "celebrate",
    gaze: "user",
  },
  "5": { action: "point", gaze: "panel" },
  "6": { action: "walk", camera: "full_body" },
  "7": { action: "squat", gaze: "workout", camera: "exercise" },
  "8": { action: "celebrate", gaze: "user" },
};

function readinessEmotion(state: TwinState): typeof defaultEmotion {
  const d = state.drivers;
  const score = (state.readiness.score ?? 55) / 100;
  return {
    energy: clamp01(score * 0.8 + d.recovery_progress * 0.18),
    happiness: clamp01(0.28 + score * 0.38),
    fatigue: clamp01(d.fatigue),
    stress: clamp01((state.latest?.stress_level ?? 20) / 100),
    confidence: clamp01(0.72 + score * 0.24),
    excitement: clamp01(d.exertion * 0.35 + Math.max(0, score - 0.55)),
    concern: clamp01((1 - score) * 0.45 + d.fatigue * 0.25),
  };
}

function mergeSemantic(
  current: AvatarSemanticState,
  next: Partial<AvatarSemanticState>,
): AvatarSemanticState {
  return {
    emotion: next.emotion ?? current.emotion,
    action: next.action ?? current.action,
    gaze: next.gaze ?? current.gaze,
    camera: next.camera ?? current.camera,
  };
}

function createNodes(root: THREE.Object3D) {
  const nodes: Record<string, THREE.Object3D> = {};
  root.traverse((object) => {
    if (object.name) nodes[object.name] = object;
  });
  return nodes;
}

function baseTransforms(nodes: Record<string, THREE.Object3D>) {
  const base: Record<
    string,
    { rotation: THREE.Euler; position: THREE.Vector3 }
  > = {};
  for (const [name, node] of Object.entries(nodes)) {
    base[name] = {
      rotation: node.rotation.clone(),
      position: node.position.clone(),
    };
  }
  return base;
}

function actionLabel(
  semantic: AvatarSemanticState,
  speaking: boolean,
  listening: boolean,
  thinking: boolean,
) {
  if (semantic.action !== "idle") return semantic.action.toUpperCase();
  if (speaking) return "TALK";
  if (listening) return "LISTEN";
  if (thinking) return "THINK";
  return "IDLE";
}

function Body({
  live,
  overlay,
  reduced,
  speaking,
  listening,
  thinking,
  semantic,
  faceFrames,
  bodyFrames,
  audioEnergy,
  onPerf,
  onMotion,
}: {
  live: RefObject<TwinState | null>;
  overlay: RefObject<SimulationOverlay | null>;
  reduced: boolean;
  speaking: boolean;
  listening: boolean;
  thinking: boolean;
  semantic: RefObject<AvatarSemanticState>;
  faceFrames: RefObject<FaceFrame[]>;
  bodyFrames: RefObject<BodyFrame[]>;
  audioEnergy: RefObject<number>;
  onPerf: (n: number) => void;
  onMotion: (s: string) => void;
}) {
  const { scene } = useGLTF("/assets/model.glb");
  const { gl: renderer } = useThree();
  const model = useMemo(() => {
    const clone = cloneSkeleton(scene) as THREE.Group;
    // Textures default to anisotropy 1 (blurry at a grazing angle, exactly
    // what close-up/orbit zoom produces) -- the GPU's real max is usually
    // 8-16 and costs nothing noticeable on hardware that can already run
    // this scene, so just ask for it instead of leaving the default.
    const maxAnisotropy = renderer.capabilities.getMaxAnisotropy();
    clone.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        const cloned = materials.map((material) => {
          const next = material.clone() as THREE.MeshStandardMaterial;
          (
            [next.map, next.normalMap, next.roughnessMap, next.metalnessMap, next.emissiveMap] as (
              | THREE.Texture
              | null
              | undefined
            )[]
          ).forEach((tex) => {
            if (tex) tex.anisotropy = maxAnisotropy;
          });
          // The GLB ships corneas at roughness 1 (fully matte), so eyes carry
          // no catchlight at any zoom -- the one thing a face-zoom draws the
          // eye to first. A wet, glossy cornea is standard for believable
          // eyes; the iris/pupil underneath is untouched.
          if (next.name.includes("Cornea")) {
            next.roughness = 0.05;
          }
          return next;
        });
        mesh.material = Array.isArray(mesh.material) ? cloned : cloned[0];
      }
    });
    return clone;
  }, [scene, renderer]);
  const nodes = useMemo(() => createNodes(model), [model]);
  const base = useMemo(() => baseTransforms(nodes), [nodes]);
  const morphMeshes = useMemo(() => {
    const targets: THREE.Mesh[] = [];
    const names = new Set<string>();
    model.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (mesh.morphTargetDictionary && mesh.morphTargetInfluences) {
        targets.push(mesh);
        Object.keys(mesh.morphTargetDictionary).forEach((name) =>
          names.add(name),
        );
      }
    });
    console.info("[avatar] GLB morph targets", [...names].sort());
    return targets;
  }, [model]);
  const emotion = useRef(defaultEmotion);
  const phase = useRef({ breath: 0, gait: 0, blinkAt: 1.5, blinkStart: -10 });
  const performance = useRef<number[]>([]);
  const reported = useRef(0);
  const lastMotion = useRef("IDLE");
  const { camera } = useThree();

  useFrame((three, rawDt) => {
    if (!live.current) return;
    const dt = Math.min(rawDt, 0.1);
    const state = live.current;
    const d = overlay.current?.drivers ?? state.drivers;
    const clock = three.clock.elapsedTime;
    const semanticState = semantic.current;
    const targetEmotion = {
      ...readinessEmotion(state),
      ...semanticState.emotion,
    };
    emotion.current = blendEmotion(
      emotion.current,
      targetEmotion,
      1 - Math.exp(-dt * 2.8),
    );
    const motion = actionLabel(semanticState, speaking, listening, thinking);
    if (motion !== lastMotion.current) {
      lastMotion.current = motion;
      onMotion(motion);
    }

    const action = semanticState.action;
    const fatigue = clamp01(Math.max(d.fatigue, emotion.current.fatigue));
    const energy = clamp01(emotion.current.energy);
    const breathRate = reduced ? 0 : 1.1 + fatigue * 0.35 + energy * 0.25;
    phase.current.breath += dt * breathRate * Math.PI * 2;
    phase.current.gait += dt * (action === "run" ? 7 : 3.2 + energy * 2.2);
    audioEnergy.current *= 0.9;

    const damp = (name: string, x?: number, y?: number, z?: number, k = 7) => {
      const node = nodes[name];
      const origin = base[name];
      if (!node || !origin) return;
      if (x != null)
        node.rotation.x = THREE.MathUtils.damp(
          node.rotation.x,
          origin.rotation.x + x,
          k,
          dt,
        );
      if (y != null)
        node.rotation.y = THREE.MathUtils.damp(
          node.rotation.y,
          origin.rotation.y + y,
          k,
          dt,
        );
      if (z != null)
        node.rotation.z = THREE.MathUtils.damp(
          node.rotation.z,
          origin.rotation.z + z,
          k,
          dt,
        );
    };
    const dampPos = (name: string, x = 0, y = 0, z = 0, k = 7) => {
      const node = nodes[name];
      const origin = base[name];
      if (!node || !origin) return;
      node.position.x = THREE.MathUtils.damp(
        node.position.x,
        origin.position.x + x,
        k,
        dt,
      );
      node.position.y = THREE.MathUtils.damp(
        node.position.y,
        origin.position.y + y,
        k,
        dt,
      );
      node.position.z = THREE.MathUtils.damp(
        node.position.z,
        origin.position.z + z,
        k,
        dt,
      );
    };

    const breath = Math.sin(phase.current.breath);
    const headNoise = reduced ? 0 : Math.sin(clock * 0.73) * 0.025;
    const eyeBreak =
      semanticState.gaze === "away"
        ? -0.22
        : semanticState.gaze === "panel"
          ? 0.28
          : semanticState.gaze === "workout"
            ? 0.08
            : Math.sin(clock * 0.21) * 0.04;
    const walk =
      action === "walk" || action === "run" || action === "squat"
        ? Math.sin(phase.current.gait)
        : 0;
    const squat =
      action === "squat"
        ? (1 - Math.cos(((clock % 2.7) * Math.PI * 2) / 2.7)) / 2
        : 0;
    const point = action === "point";
    const celebrate = action === "celebrate";
    const nod = action === "nod";

    dampPos("Hips", 0, -squat * 0.18 + Math.abs(walk) * 0.015, 0);
    damp("Spine", fatigue * 0.08 - squat * 0.16, 0, breath * 0.015);
    damp("Spine1", fatigue * 0.1 - squat * 0.2, 0, breath * 0.018);
    damp("Spine2", fatigue * 0.08 - squat * 0.14, 0, breath * 0.02);
    damp(
      "Head",
      -0.02 + fatigue * 0.1 + (nod ? Math.sin(clock * 9) * 0.14 : 0),
      eyeBreak * 0.45 + headNoise,
      emotion.current.concern * 0.08,
    );
    damp("LeftEye", 0, eyeBreak, 0, 12);
    damp("RightEye", 0, eyeBreak, 0, 12);

    // The GLB's bind pose has arms out near-horizontal (a T-pose, for clean
    // skinning) -- every non-gesture state used to offset from that pose by
    // only a few hundredths of a radian, so "idle" rendered as a scarecrow
    // instead of a relaxed stance. This is the rotation (on top of that same
    // bind pose) that actually brings the arm down to the side.
    const ARMS_DOWN = 1.48;
    for (const side of ["Left", "Right"] as const) {
      const sign = side === "Left" ? 1 : -1;
      const armSwing = walk * sign * (action === "run" ? 0.92 : 0.55);
      const isPointing = point && side === "Right";
      damp(
        `${side}Arm`,
        isPointing
          ? -1.15
          : celebrate
            ? -1.55
            : speaking
              ? ARMS_DOWN - 0.3 + Math.sin(clock * 2 + sign) * 0.16
              : ARMS_DOWN + armSwing,
        isPointing ? -0.42 : 0,
        isPointing ? -0.48 : sign * (0.04 + emotion.current.energy * 0.05),
      );
      damp(
        `${side}ForeArm`,
        isPointing
          ? -0.24
          : celebrate
            ? -1.1
            : -0.22 - Math.abs(armSwing) * 0.45,
        0,
        isPointing ? -0.32 : sign * 0.04,
      );
      damp(`${side}Hand`, isPointing ? -0.28 : -fatigue * 0.12, 0, 0);
      damp(
        `${side}UpLeg`,
        walk * sign * 0.32 - squat * 0.85,
        sign * squat * 0.08,
        0,
      );
      damp(`${side}Leg`, Math.max(0, -walk * sign) * 0.55 + squat * 1.16);
      damp(`${side}Foot`, -squat * 0.28 - walk * sign * 0.08);
    }

    // EMAGE-driven body gestures: while actually speaking (and only in the
    // plain "idle" action, so a deliberate pose -- squat/point/celebrate/
    // walk -- is never fought with real gesture data), replace the bones it
    // covers with base-pose * (fresh EMAGE delta), blending smoothly in via
    // slerp from whatever the procedural pass above just set. When it stops
    // being fresh (speech ends, or the body service is behind/offline), we
    // simply stop touching those bones again -- damp() above already runs
    // for them every frame regardless, so they smoothly damp back to the
    // plain procedural target on their own; no separate transition-out
    // logic needed.
    const bodyFrame = bodyFrames.current.at(-1);
    const bodyFresh =
      speaking &&
      action === "idle" &&
      !!bodyFrame &&
      window.performance.now() - bodyFrame.timestampMs < 500;
    if (bodyFresh) {
      for (const [boneName, delta] of Object.entries(bodyFrame!.bones) as [
        string,
        [number, number, number],
      ][]) {
        const node = nodes[boneName];
        const origin = base[boneName];
        if (!node || !origin) continue;
        const target = new THREE.Quaternion()
          .setFromEuler(origin.rotation)
          .multiply(axisAngleToQuaternion(delta));
        node.quaternion.slerp(target, 1 - Math.exp(-dt * 8));
      }
    }

    const frame = faceFrames.current.at(-1);
    const speech =
      frame && window.performance.now() - frame.timestampMs < 220
        ? frame.weights
        : mouthFallback(clock, speaking, audioEnergy.current);
    const final: Record<string, number> = {};
    for (const [incoming, value] of Object.entries(speech)) {
      const mapped = audio2FaceMorphMap[incoming] ?? incoming;
      final[mapped] = clamp01((final[mapped] ?? 0) + value * 0.95);
    }
    for (const [name, value] of Object.entries(emotionMorphs(emotion.current)))
      final[name] = clamp01((final[name] ?? 0) + value * 0.55);
    if (clock > phase.current.blinkAt) {
      phase.current.blinkStart = clock;
      phase.current.blinkAt =
        clock + 2 + Math.random() * 4 - emotion.current.stress * 0.8;
    }
    const blinkAge = clock - phase.current.blinkStart;
    const blink =
      blinkAge >= 0 && blinkAge < 0.18
        ? Math.sin((blinkAge / 0.18) * Math.PI)
        : 0;
    final.eyeBlinkLeft = Math.max(final.eyeBlinkLeft ?? 0, blink);
    final.eyeBlinkRight = Math.max(final.eyeBlinkRight ?? 0, blink);

    for (const mesh of morphMeshes) {
      const dict = mesh.morphTargetDictionary;
      const influences = mesh.morphTargetInfluences;
      if (!dict || !influences) continue;
      for (const [name, index] of Object.entries(dict)) {
        influences[index] = THREE.MathUtils.damp(
          influences[index],
          final[name] ?? 0,
          18,
          dt,
        );
      }
    }

    const targetCamera =
      semanticState.camera === "exercise"
        ? new THREE.Vector3(0, 0.6, 5.2)
        : semanticState.camera === "full_body"
          ? new THREE.Vector3(0, 0.35, 4.4)
          : new THREE.Vector3(0, 0.28, 3.7);
    camera.position.lerp(targetCamera, 1 - Math.exp(-dt * 1.7));
    camera.lookAt(0, semanticState.camera === "exercise" ? 0.3 : 0.1, 0);

    if (clock > 3 && rawDt < 0.5) performance.current.push(rawDt * 1000);
    if (clock - reported.current > 5 && performance.current.length > 60) {
      const values = performance.current.splice(0).sort((a, b) => a - b);
      const p95 = values[Math.floor(values.length * 0.95)];
      onPerf(p95);
      reported.current = clock;
    }
  });

  return (
    <primitive
      object={model}
      position={[0, -1.08, 0]}
      rotation={[0, 0, 0]}
      scale={0.95}
    />
  );
}

function WorkoutHud({ active, cue }: { active: boolean; cue: string }) {
  if (!active) return null;
  return (
    <div className="avatar-workout-hud">
      <span>BARBELL SQUAT</span>
      <b>{cue}</b>
      <small>QUADS / GLUTES / CORE</small>
    </div>
  );
}

export default function Avatar({
  live,
  overlay,
  state,
  reduced,
  speaking = false,
  listening = false,
  thinking = false,
  compact = false,
}: {
  live: RefObject<TwinState | null>;
  overlay: RefObject<SimulationOverlay | null>;
  state: TwinState;
  reduced: boolean;
  speaking?: boolean;
  listening?: boolean;
  thinking?: boolean;
  compact?: boolean;
}) {
  const controls = useRef<OrbitControlsImpl>(null);
  const semantic = useRef<AvatarSemanticState>({
    ...defaultAvatarState,
    emotion: readinessEmotion(state),
  });
  const socket = useRef<WebSocket | null>(null);
  const faceFrames = useRef<FaceFrame[]>([]);
  const bodySocket = useRef<WebSocket | null>(null);
  const bodyFrames = useRef<BodyFrame[]>([]);
  const audioEnergy = useRef(0);
  const [quality, setQuality] = useState("Auto");
  const [dpr, setDpr] = useState(1.5);
  const [motion, setMotion] = useState("IDLE");
  const [workoutCue, setWorkoutCue] = useState("BRACE");
  const [, refresh] = useState(0);
  const phase = speaking
    ? "speaking"
    : listening
      ? "listening"
      : thinking
        ? "thinking"
        : "idle";

  useEffect(() => {
    // "High" targets the screen's real pixel density instead of a flat 2 --
    // a flat cap undershoots any display denser than that (common on
    // phones/newer laptops), which matters most exactly when zoomed in
    // close, where every screen pixel is showing you more of the texture.
    // Capped at 3: native retina density with a sane ceiling, not uncapped.
    const native = Math.min(window.devicePixelRatio || 1, 3);
    setDpr(quality === "Low" ? 1 : quality === "High" ? native : 1.5);
  }, [quality]);
  useEffect(() => {
    semantic.current = mergeSemantic(semantic.current, {
      emotion: readinessEmotion(state),
    });
  }, [state]);
  useEffect(
    () =>
      listenAvatarSemantic((next) => {
        semantic.current = mergeSemantic(semantic.current, next);
        refresh((n) => n + 1);
      }),
    [],
  );
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement)?.closest("input, textarea, select, [contenteditable=true]")) return;
      const next = demoStates[event.key];
      if (!next) return;
      emitAvatarSemantic(next);
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, []);
  useEffect(() => {
    if (semantic.current.action !== "squat") return;
    const cues = ["BRACE", "3", "2", "1", "HOLD", "DRIVE", "CHEST UP"];
    const started = window.performance.now();
    const id = window.setInterval(() => {
      const elapsed = (window.performance.now() - started) / 1000;
      setWorkoutCue(cues[Math.min(cues.length - 1, Math.floor(elapsed))]);
      if (elapsed > 9) {
        emitAvatarSemantic({
          action: "idle",
          gaze: "user",
          camera: "conversation",
        });
        window.clearInterval(id);
      }
    }, 250);
    return () => window.clearInterval(id);
  }, [motion]);
  useEffect(() => {
    let stopped = false;
    let retry = 0;
    let healthTimer: number | undefined;
    const connect = () => {
      if (stopped) return;
      if (socket.current?.readyState === WebSocket.OPEN) return;
      const ws = new WebSocket(faceWs);
      ws.binaryType = "arraybuffer";
      socket.current = ws;
      ws.onopen = () => {
        retry = 0;
      };
      ws.onmessage = (event) => {
        const raw =
          typeof event.data === "string" ? JSON.parse(event.data) : null;
        const frame = parseFaceFrame(raw);
        if (!frame) return;
        frame.timestampMs = window.performance.now();
        faceFrames.current.push(frame);
        if (faceFrames.current.length > 16) faceFrames.current.shift();
      };
      ws.onerror = () => {};
      ws.onclose = () => {
        if (socket.current === ws) socket.current = null;
        if (!stopped)
          window.setTimeout(connect, Math.min(5000, 1000 + retry++ * 500));
      };
    };
    const checkHealth = () => {
      fetch(`${faceHttp}/health`, { mode: "cors" })
        .then((response) => {
          if (!response.ok) throw new Error("Face service unavailable");
            connect();
        })
        .catch(() => {
            if (!stopped)
            healthTimer = window.setTimeout(checkHealth, 5000);
        });
    };
    checkHealth();

    // Body-gesture service: same audio, a separate WS/health pair, entirely
    // best-effort -- if it's offline the avatar just keeps whatever
    // procedural pose it already had (see the useFrame loop's speaking-only
    // gesture-overlay block), same graceful-degrade shape as the face
    // service but with no cycling fallback of its own.
    let bodyStopped = false;
    let bodyRetry = 0;
    let bodyHealthTimer: number | undefined;
    const connectBody = () => {
      if (bodyStopped) return;
      if (bodySocket.current?.readyState === WebSocket.OPEN) return;
      const ws = new WebSocket(bodyWs);
      bodySocket.current = ws;
      ws.onopen = () => {
        bodyRetry = 0;
      };
      ws.onmessage = (event) => {
        const raw = typeof event.data === "string" ? JSON.parse(event.data) : null;
        const frame = parseBodyFrame(raw);
        if (!frame) return;
        frame.timestampMs = window.performance.now();
        bodyFrames.current.push(frame);
        if (bodyFrames.current.length > 4) bodyFrames.current.shift();
      };
      ws.onclose = () => {
        if (bodySocket.current === ws) bodySocket.current = null;
        if (!bodyStopped)
          window.setTimeout(connectBody, Math.min(5000, 1000 + bodyRetry++ * 500));
      };
    };
    const checkBodyHealth = () => {
      fetch(`${bodyHttp}/health`, { mode: "cors" })
        .then((response) => {
          if (!response.ok) throw new Error("Body service unavailable");
          connectBody();
        })
        .catch(() => {
          if (!bodyStopped) bodyHealthTimer = window.setTimeout(checkBodyHealth, 5000);
        });
    };
    checkBodyHealth();

    const stopAudio = listenAvatarAudio(({ bytes }) => {
      audioEnergy.current = Math.min(0.75, bytes.byteLength / 18000);
      const ws = socket.current;
      if (ws?.readyState === WebSocket.OPEN) ws.send(bytes.slice(0));
      const bws = bodySocket.current;
      if (bws?.readyState === WebSocket.OPEN) bws.send(bytes.slice(0));
    });
    return () => {
      stopped = true;
      bodyStopped = true;
      stopAudio();
      if (healthTimer) window.clearTimeout(healthTimer);
      if (bodyHealthTimer) window.clearTimeout(bodyHealthTimer);
      socket.current?.close();
      bodySocket.current?.close();
    };
  }, []);

  const perf = (n: number) => {
    if (quality === "Auto" && n > 25) setDpr(1);
  };
  return (
    <div
      className={`avatar-card${compact ? " compact" : ""} avatar-phase-${phase}`}
    >
      <div className="avatar-top">
        <span className="eyebrow">YOUR DIGITAL TWIN</span>
        <span className="avatar-state">
          <i />
          {state.readiness.score == null
            ? "Awaiting data"
            : humanize(state.readiness.state)}
        </span>
      </div>
      <CanvasBoundary>
        <Canvas
          dpr={compact ? 1 : dpr}
          camera={{ position: [0, 0.28, 3.7], fov: compact ? 31 : 35 }}
          gl={{
            antialias: true,
            alpha: true,
            powerPreference: "high-performance",
          }}
          shadows
          style={{ height: "100%" }}
        >
          <ambientLight intensity={1.5} />
          <directionalLight
            position={[3, 5, 4]}
            intensity={3.2}
            color="#edfff4"
            castShadow
          />
          <directionalLight
            position={[-4, 2, -3]}
            intensity={2.4}
            color="#74c7d9"
          />
          <Suspense fallback={null}>
            {/* Lighting-only (background stays transparent, alpha canvas) --
                gives the now-glossy corneas and any specular skin/eye highlight
                something continuous to reflect instead of just two point lights. */}
            <Environment preset="apartment" environmentIntensity={0.35} />
            <Body
              live={live}
              overlay={overlay}
              reduced={reduced}
              speaking={speaking}
              listening={listening}
              thinking={thinking}
              semantic={semantic}
              faceFrames={faceFrames}
              bodyFrames={bodyFrames}
              audioEnergy={audioEnergy}
              onPerf={perf}
              onMotion={setMotion}
            />
          </Suspense>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.08, 0]}>
            <ringGeometry args={[0.64, 0.646, 96]} />
            <meshBasicMaterial
              color="#70b59f"
              transparent
              opacity={semantic.current.action === "squat" ? 0.55 : 0.28}
              side={THREE.DoubleSide}
            />
          </mesh>
          <OrbitControls
            ref={controls}
            enablePan={false}
            enableZoom
            zoomSpeed={0.6}
            minDistance={1.05}
            maxDistance={6}
            target={[0, 0.1, 0]}
            minPolarAngle={0.78}
            maxPolarAngle={1.85}
          />
        </Canvas>
      </CanvasBoundary>
      <WorkoutHud active={semantic.current.action === "squat"} cue={workoutCue} />
      <div className="avatar-caption">
        <Move size={13} />
        <span>Drag to explore your coach</span>
      </div>
      <div className="avatar-bottom">
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
      <div className="avatar-voice-status" aria-live="polite">
        <span className="avatar-voice-pulse" aria-hidden="true" />
        {phase === "speaking" && (
          <>
            <Volume2 size={12} /> Speaking
          </>
        )}
        {phase === "listening" && (
          <>
            <Mic size={12} /> Listening
          </>
        )}
        {phase === "thinking" && (
          <>
            <LoaderCircle size={12} className="spin" /> Thinking
          </>
        )}
        {phase === "idle" && "Idle"}
      </div>
      <details className="avatar-movements"><summary>Movement</summary><div>
        {[["idle", "Relax"], ["point", "Point"], ["walk", "Walk"], ["run", "Run"], ["nod", "Nod"], ["squat", "Squat"], ["celebrate", "Celebrate"]].map(([action, label]) =>
          <button key={action} onClick={() => emitAvatarSemantic({ action: action as AvatarAction, gaze: action === "point" ? "panel" : "user", camera: action === "squat" ? "exercise" : "conversation" })}>{label}</button>
        )}
      </div></details>
      {semantic.current.action === "squat" && (
        <div className="avatar-workout-icon" aria-hidden="true">
          <Dumbbell size={16} />
        </div>
      )}
    </div>
  );
}
useGLTF.preload("/assets/model.glb");
