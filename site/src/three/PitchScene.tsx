import { Html, Line } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { memo, useEffect, useMemo, useRef } from "react";
import type { MutableRefObject } from "react";
import * as THREE from "three";
import { deriveFrame } from "../data/derive";
import type { DrawnTrack } from "../data/derive";
import { FOCUS, PITCH, positionAt, samplesBetween } from "../data/scene";
import type { Vec2 } from "../data/scene";
import type { StoryState, ViewName } from "../story";
import { effectiveView } from "../story";
import { COLORS } from "./colors";


export interface CameraOffsets {
  az: number;
  pol: number;
}

const w = (p: Vec2, h = 0): [number, number, number] => [p[0], h, -p[1]];

/* ----------------------------------------------------------------- pitch */

function Stripe() {
  const texture = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = 512;
    c.height = 8;
    const ctx = c.getContext("2d")!;
    const bands = 14;
    for (let i = 0; i < bands; i++) {
      ctx.fillStyle = i % 2 ? COLORS.grassA : COLORS.grassB;
      ctx.fillRect((i * c.width) / bands, 0, c.width / bands + 1, c.height);
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 4;
    return t;
  }, []);
  return (
    <mesh position={[0, 0, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[PITCH.length, PITCH.width]} />
      <meshStandardMaterial map={texture} roughness={0.95} />
    </mesh>
  );
}

function Seg({ a, b, width = 0.14 }: { a: Vec2; b: Vec2; width?: number }) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  return (
    <mesh position={[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.02]} rotation={[0, 0, Math.atan2(dy, dx)]}>
      <planeGeometry args={[len + width, width]} />
      <meshBasicMaterial color={COLORS.line} transparent opacity={0.82} />
    </mesh>
  );
}

function Arc({ c, r, start = 0, length = Math.PI * 2, width = 0.14 }: { c: Vec2; r: number; start?: number; length?: number; width?: number }) {
  return (
    <mesh position={[c[0], c[1], 0.02]}>
      <ringGeometry args={[r - width / 2, r + width / 2, 96, 1, start, length]} />
      <meshBasicMaterial color={COLORS.line} transparent opacity={0.82} />
    </mesh>
  );
}

function Rect({ x0, x1, y0, y1 }: { x0: number; x1: number; y0: number; y1: number }) {
  return (
    <>
      <Seg a={[x0, y0]} b={[x1, y0]} />
      <Seg a={[x1, y0]} b={[x1, y1]} />
      <Seg a={[x1, y1]} b={[x0, y1]} />
      <Seg a={[x0, y1]} b={[x0, y0]} />
    </>
  );
}

const Markings = memo(function Markings() {
  const L = PITCH.length / 2;
  const W = PITCH.width / 2;
  const arcAngle = Math.acos((16.5 - 11) / 9.15);
  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      <Rect x0={-L} x1={L} y0={-W} y1={W} />
      <Seg a={[0, -W]} b={[0, W]} />
      <Arc c={[0, 0]} r={9.15} />
      <Arc c={[0, 0]} r={0.2} width={0.4} />
      {[-1, 1].map((s) => (
        <group key={s}>
          <Rect x0={s * L} x1={s * (L - 16.5)} y0={-20.16} y1={20.16} />
          <Rect x0={s * L} x1={s * (L - 5.5)} y0={-9.16} y1={9.16} />
          <Arc c={[s * (L - 11), 0]} r={0.2} width={0.4} />
          <Arc c={[s * (L - 11), 0]} r={9.15} start={s > 0 ? Math.PI - arcAngle : -arcAngle} length={2 * arcAngle} />
          <Arc c={[s * L, -W]} r={1} start={s > 0 ? Math.PI / 2 : 0} length={Math.PI / 2} />
          <Arc c={[s * L, W]} r={1} start={s > 0 ? Math.PI : -Math.PI / 2} length={Math.PI / 2} />
        </group>
      ))}
    </group>
  );
});

function Goal({ side }: { side: 1 | -1 }) {
  const x = side * (PITCH.length / 2);
  const depth = side * 1.8;
  const mat = <meshStandardMaterial color="#f4f4f0" roughness={0.4} />;
  return (
    <group>
      {[-3.66, 3.66].map((z) => (
        <mesh key={z} position={[x, 1.22, z]}>
          <cylinderGeometry args={[0.1, 0.1, 2.44, 10]} />
          {mat}
        </mesh>
      ))}
      <mesh position={[x, 2.44, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.1, 0.1, 7.52, 10]} />
        {mat}
      </mesh>
      <mesh position={[x + depth / 2, 1.22, 0]}>
        <boxGeometry args={[Math.abs(depth), 2.44, 7.32]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.07} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
    </group>
  );
}

const Surroundings = memo(function Surroundings() {
  const tiers = [0, 1, 2, 3];
  const sideLen = PITCH.length + 30;
  const endLen = PITCH.width + 26;
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]}>
        <planeGeometry args={[PITCH.length + 14, PITCH.width + 12]} />
        <meshStandardMaterial color={COLORS.runoff} roughness={1} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]}>
        <planeGeometry args={[520, 520]} />
        <meshStandardMaterial color="#0c0e0f" roughness={1} />
      </mesh>
      {tiers.map((i) => {
        const h = 1.4 + i * 2.1;
        const off = 4 + i * 3.4;
        return (
          <group key={i}>
            {[-1, 1].map((s) => (
              <mesh key={`s${s}`} position={[0, h / 2, s * (PITCH.width / 2 + 6 + off)]}>
                <boxGeometry args={[sideLen + i * 7, h, 3.4]} />
                <meshStandardMaterial color={i % 2 ? "#1a1e21" : "#1e2326"} roughness={0.9} />
              </mesh>
            ))}
            {[-1, 1].map((s) => (
              <mesh key={`e${s}`} position={[s * (PITCH.length / 2 + 7 + off), h / 2, 0]}>
                <boxGeometry args={[3.4, h, endLen + i * 7]} />
                <meshStandardMaterial color={i % 2 ? "#1a1e21" : "#1e2326"} roughness={0.9} />
              </mesh>
            ))}
          </group>
        );
      })}
    </group>
  );
});

/* ---------------------------------------------------------------- tokens */

function Token({ d, emphasis }: { d: DrawnTrack; emphasis: boolean }) {
  const frozen = d.state === "frozen";
  const opacity = frozen ? 0.32 : 1;
  const pos = w(d.position);
  if (d.track.team === "ball") {
    return (
      <group position={pos}>
        <mesh position={[0, 0.65, 0]}>
          <sphereGeometry args={[0.65, 24, 16]} />
          <meshStandardMaterial color="#ffffff" roughness={0.35} transparent opacity={opacity} emissive="#ffffff" emissiveIntensity={0.25} />
        </mesh>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
          <circleGeometry args={[0.9, 24]} />
          <meshBasicMaterial color="#000000" transparent opacity={0.3 * opacity} depthWrite={false} />
        </mesh>
        {d.state === "future-input" && <FutureHalo r={1.35} />}
      </group>
    );
  }
  const isTarget = d.track.team === "target";
  return (
    <group position={pos}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
        <circleGeometry args={[1.45, 28]} />
        <meshBasicMaterial color="#000000" transparent opacity={0.28 * opacity} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0.35, 0]}>
        <cylinderGeometry args={[0.95, 1.05, 0.7, 32]} />
        <meshStandardMaterial
          color={isTarget ? COLORS.target : COLORS.opponent}
          roughness={0.55}
          transparent={frozen}
          opacity={opacity}
        />
      </mesh>
      {!isTarget && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.71, 0]}>
          <ringGeometry args={[0.62, 0.92, 32]} />
          <meshBasicMaterial color={COLORS.opponentRim} transparent opacity={opacity} />
        </mesh>
      )}
      {d.state === "future-input" && <FutureHalo r={1.55} />}
      {emphasis && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.04, 0]}>
          <ringGeometry args={[1.9, 2.15, 48]} />
          <meshBasicMaterial color={COLORS.target} transparent opacity={0.9} />
        </mesh>
      )}
    </group>
  );
}

function FutureHalo({ r }: { r: number }) {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
      <ringGeometry args={[r, r + 0.28, 40]} />
      <meshBasicMaterial color={COLORS.future} />
    </mesh>
  );
}

function Trail({ pts, color, width, opacity = 1, dashed = false, h = 0.08 }: { pts: Vec2[]; color: string; width: number; opacity?: number; dashed?: boolean; h?: number }) {
  if (pts.length < 2) return null;
  return (
    <Line
      points={pts.map((p) => w(p, h))}
      color={color}
      lineWidth={width}
      transparent
      opacity={opacity}
      dashed={dashed}
      dashSize={0.9}
      gapSize={0.7}
      depthWrite={false}
    />
  );
}

/* ------------------------------------------------- absolute vs displacement */

function Arrow({ from, to, color, active, width }: { from: Vec2; to: Vec2; color: string; active: boolean; width: number }) {
  const dir = new THREE.Vector3(to[0] - from[0], 0, -(to[1] - from[1])).normalize();
  const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
  const tip = w(to, 0.25);
  const back: Vec2 = [to[0] - dir.x * 1.6, to[1] + dir.z * 1.6];
  const opacity = active ? 1 : 0.28;
  return (
    <group>
      <Line points={[w(from, 0.25), w(back, 0.25)]} color={color} lineWidth={width} transparent opacity={opacity} depthWrite={false} />
      <mesh position={[tip[0] - dir.x * 0.8, 0.25, tip[2] - dir.z * 0.8]} quaternion={quat}>
        <coneGeometry args={[0.75, 1.6, 20]} />
        <meshBasicMaterial color={color} transparent opacity={opacity} />
      </mesh>
    </group>
  );
}

function Label({ at, children, tone = "plain" }: { at: [number, number, number]; children: React.ReactNode; tone?: "plain" | "abs" | "disp" | "muted" }) {
  return (
    <Html position={at} center zIndexRange={[5, 0]} style={{ pointerEvents: "none" }}>
      <div className={`scene-label scene-label--${tone}`} aria-hidden="true">
        {children}
      </div>
    </Html>
  );
}

function EncodingOverlay({ representation }: { representation: StoryState["representation"] }) {
  const o = positionAt(FOCUS, 0);
  const f = positionAt(FOCUS, 3);
  const path = samplesBetween(FOCUS, 0, 3);
  const isAbs = representation === "absolute_xy";
  const dx = f[0] - o[0];
  const dy = f[1] - o[1];
  const sign = (v: number) => `${v < 0 ? "−" : "+"}${Math.abs(v).toFixed(1)}`;
  return (
    <group>
      <Line points={[w([-6, 0], 0.12), w([6, 0], 0.12)]} color={COLORS.line} lineWidth={1.5} transparent opacity={0.9} />
      <Line points={[w([0, -6], 0.12), w([0, 6], 0.12)]} color={COLORS.line} lineWidth={1.5} transparent opacity={0.9} />
      <Label at={w([0, -2.5], 0.5)} tone="muted">
        (0, 0) centre spot
      </Label>
      <Trail pts={path} color={COLORS.target} width={2} opacity={0.75} dashed />
      <Arrow from={[0, 0]} to={f} color={COLORS.absolute} active={isAbs} width={isAbs ? 4 : 2} />
      <Arrow from={o} to={f} color={COLORS.displacement} active={!isAbs} width={!isAbs ? 4 : 2} />
      <mesh position={w(f, 0.06)} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.0, 1.25, 40]} />
        <meshBasicMaterial color={COLORS.target} />
      </mesh>
      {isAbs ? (
        <Label at={w([f[0] / 2, f[1] / 2 - 3], 0.6)} tone="abs">
          absolute target (x, y) = ({f[0].toFixed(1)}, {f[1].toFixed(1)}) m
        </Label>
      ) : (
        <Label at={w([(o[0] + f[0]) / 2 - 3, (o[1] + f[1]) / 2 - 3.5], 0.6)} tone="disp">
          displacement (Δx, Δy) = ({sign(dx)}, {sign(dy)}) m
        </Label>
      )}
      <Label at={w([f[0] + 2, f[1] - 4.5], 0.6)} tone="plain">
        position at t + 3 s
      </Label>
      <Label at={w([o[0] - 2, o[1] + 3.8], 0.6)} tone="plain">
        at t = 0
      </Label>
    </group>
  );
}

/* ---------------------------------------------------------------- camera */

interface Preset {
  target: [number, number, number];
  az: number;
  pol: number;
  rad: number;
}

export interface Insets {
  left: number;
  top: number;
  bottom: number;
}

interface Frame {
  tanV: number; // tangent of the half vertical angle covering the free region
  tanH: number;
  portrait: boolean;
}

const fit = (f: Frame, horiz: number, vert: number) => Math.max(vert / 2 / f.tanV, horiz / 2 / f.tanH);

function preset(view: ViewName, f: Frame): Preset {
  const p = f.portrait;
  const L = PITCH.length;
  const W = PITCH.width;
  if (view === "tactical") {
    const [h, v] = p ? [W + 6, L + 6] : [L + 6, W + 6];
    return { target: [0, 0, 0], az: p ? -Math.PI / 2 : 0, pol: 0.02, rad: fit(f, h, v) };
  }
  if (view === "focus") {
    const o = positionAt(FOCUS, 0);
    const e = positionAt(FOCUS, 3);
    const cx = (Math.min(0, o[0], e[0]) + Math.max(o[0], e[0])) / 2;
    const cy = (Math.min(0, o[1], e[1]) + Math.max(0, o[1], e[1])) / 2;
    const [h, v] = p ? [36, 58] : [62, 34];
    return { target: w([cx, cy]), az: p ? -Math.PI / 2 + 0.15 : -0.12, pol: 0.42, rad: fit(f, h, v) * 1.05 };
  }
  if (view === "hero") {
    return p
      ? { target: [6, 0, 0], az: -Math.PI / 2 + 0.38, pol: 1.0, rad: fit(f, W + 30, L * 0.5) }
      : { target: [0, 0, 4], az: 0.06, pol: 1.0, rad: fit(f, L + 14, W * 0.62) };
  }
  return p
    ? { target: [6, 0, 0], az: -Math.PI / 2 + 0.25, pol: 0.88, rad: fit(f, W + 20, L * 0.62) }
    : { target: [3, 0, 2], az: -0.26, pol: 0.9, rad: fit(f, L + 8, W * 0.72) };
}

function CameraRig({
  view,
  offsets,
  reducedMotion,
  insets,
}: {
  view: ViewName;
  offsets: MutableRefObject<CameraOffsets>;
  reducedMotion: boolean;
  insets: Insets;
}) {
  const { camera, size, invalidate, scene } = useThree();
  const cam = camera as THREE.PerspectiveCamera;
  const current = useRef<Preset | null>(null);
  const tmp = useMemo(() => new THREE.Vector3(), []);

  const frame = useRef<Frame>({ tanV: 0.27, tanH: 0.4, portrait: false });
  useEffect(() => {
    // Centre the projection on the part of the screen not covered by text or controls.
    const fw = Math.max(0.2, (size.width - insets.left) / size.width);
    const fh = Math.max(0.2, (size.height - insets.top - insets.bottom) / size.height);
    cam.setViewOffset(size.width, size.height, -insets.left / 2, (insets.bottom - insets.top) / 2, size.width, size.height);
    cam.updateProjectionMatrix();
    const tan = Math.tan(THREE.MathUtils.degToRad(cam.fov / 2));
    const aspect = size.width / size.height;
    frame.current = { tanV: tan * fh, tanH: tan * aspect * fw, portrait: (aspect * fw) / fh < 0.95 };
    invalidate();
  }, [cam, size.width, size.height, insets.left, insets.top, insets.bottom, invalidate]);

  useEffect(() => invalidate(), [view, invalidate]);

  useFrame((_, dt) => {
    const goal = preset(view, frame.current);
    const desired: Preset = {
      target: goal.target,
      az: goal.az + offsets.current.az,
      pol: THREE.MathUtils.clamp(goal.pol + offsets.current.pol, 0.02, 1.32),
      rad: goal.rad,
    };
    if (!current.current || reducedMotion) current.current = { ...desired, target: [...desired.target] };
    const c = current.current;
    const k = 1 - Math.exp(-Math.min(dt, 0.1) * 3.4);
    c.az += (desired.az - c.az) * k;
    c.pol += (desired.pol - c.pol) * k;
    c.rad += (desired.rad - c.rad) * k;
    for (let i = 0; i < 3; i++) c.target[i] += (desired.target[i] - c.target[i]) * k;
    const [tx, ty, tz] = c.target;
    cam.position.set(
      tx + c.rad * Math.sin(c.pol) * Math.sin(c.az),
      ty + c.rad * Math.cos(c.pol),
      tz + c.rad * Math.sin(c.pol) * Math.cos(c.az),
    );
    cam.lookAt(tmp.set(tx, ty, tz));
    if (scene.fog instanceof THREE.Fog) {
      // Keep the pitch crisp at any framing distance; only the far surroundings fade.
      scene.fog.near = c.rad + 40;
      scene.fog.far = c.rad + 260;
    }
    const err =
      Math.abs(desired.az - c.az) +
      Math.abs(desired.pol - c.pol) +
      Math.abs(desired.rad - c.rad) / 50 +
      Math.abs(desired.target[0] - c.target[0]) / 50 +
      Math.abs(desired.target[2] - c.target[2]) / 50;
    if (err > 0.0005) invalidate();
  });
  return null;
}

/* ----------------------------------------------------------------- scene */

function Players({ state }: { state: StoryState }) {
  const view = effectiveView(state);
  const focusMode = CHAPTER_IS_ENCODING(state);
  const frame = useMemo(
    () => (focusMode ? deriveFrame("history_only", 0, false) : deriveFrame(state.regime, state.tau, state.showTarget)),
    [focusMode, state.regime, state.tau, state.showTarget],
  );
  const showTrails = state.chapter > 0 || view !== "hero";
  return (
    <group>
      {frame.map((d) => (
        <group key={d.track.id}>
          {showTrails && (
            <Trail
              pts={d.history}
              color={d.track.team === "opponent" ? COLORS.historyOpp : COLORS.history}
              width={d.track.team === "ball" ? 2.2 : 1.8}
              opacity={focusMode ? 0.25 : d.track.team === "ball" ? 0.95 : 0.6}
            />
          )}
          <Trail pts={d.future} color={COLORS.future} width={d.track.team === "ball" ? 3.4 : 2.6} />
          <Trail pts={d.withheld} color={COLORS.target} width={1.8} opacity={0.7} dashed />
          {d.withheld.length > 1 && (
            <mesh position={w(positionAt(d.track, state.tau), 0.05)} rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[0.85, 1.05, 32]} />
              <meshBasicMaterial color={COLORS.target} transparent opacity={0.85} />
            </mesh>
          )}
          <Token d={d} emphasis={focusMode && d.track.id === FOCUS.id} />
        </group>
      ))}
    </group>
  );
}

const CHAPTER_IS_ENCODING = (s: StoryState) => s.chapter >= 5;

function InvalidateBridge({ target }: { target: MutableRefObject<() => void> }) {
  const { invalidate } = useThree();
  useEffect(() => {
    target.current = () => invalidate();
  }, [invalidate, target]);
  return null;
}

export default function PitchScene({
  state,
  offsets,
  reducedMotion,
  insets,
  invalidateRef,
}: {
  state: StoryState;
  offsets: MutableRefObject<CameraOffsets>;
  reducedMotion: boolean;
  insets: Insets;
  invalidateRef: MutableRefObject<() => void>;
}) {
  const view = effectiveView(state);
  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 1.75]}
      camera={{ fov: 30, near: 1, far: 900, position: [0, 80, 110] }}
      gl={{ antialias: true, powerPreference: "high-performance", alpha: false }}
      onCreated={({ gl, scene }) => {
        gl.setClearColor(COLORS.bg);
        scene.fog = new THREE.Fog(COLORS.bg, 170, 420);
      }}
      aria-hidden="true"
    >
      <hemisphereLight args={["#dfe8ff", "#0a0c0d", 1.15]} />
      <directionalLight position={[-40, 90, 60]} intensity={1.6} />
      <directionalLight position={[60, 40, -50]} intensity={0.35} color="#ffe2b8" />
      <Surroundings />
      <Stripe />
      <Markings />
      <Goal side={1} />
      <Goal side={-1} />
      <Players state={state} />
      {CHAPTER_IS_ENCODING(state) && <EncodingOverlay representation={state.representation} />}
      <InvalidateBridge target={invalidateRef} />
      <CameraRig view={view} offsets={offsets} reducedMotion={reducedMotion} insets={insets} />
    </Canvas>
  );
}
