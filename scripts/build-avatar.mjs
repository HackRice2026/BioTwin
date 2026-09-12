import * as THREE from "../frontend/node_modules/three/build/three.module.js";
import { GLTFExporter } from "../frontend/node_modules/three/examples/jsm/exporters/GLTFExporter.js";
import { writeFile } from "node:fs/promises";

// Original articulated, stylized adult human. No downloaded or unlicensed model/animation dependencies.
globalThis.FileReader = class {
  readAsArrayBuffer(blob) {
    blob.arrayBuffer().then((data) => {
      this.result = data;
      this.onloadend?.();
    });
  }
  readAsDataURL(blob) {
    blob.arrayBuffer().then((data) => {
      this.result = `data:${blob.type};base64,${Buffer.from(data).toString("base64")}`;
      this.onloadend?.();
    });
  }
};
const body = new THREE.MeshStandardMaterial({
  color: "#cbdcd5",
  roughness: 0.38,
  metalness: 0.32,
});
const dark = new THREE.MeshStandardMaterial({
  color: "#456960",
  roughness: 0.65,
  metalness: 0.25,
});
const light = new THREE.MeshStandardMaterial({
  color: "#9ee9cf",
  emissive: "#67d6b0",
  emissiveIntensity: 0.65,
  roughness: 0.45,
});
const root = new THREE.Group();
root.name = "Twin";
function group(name, parent, x, y, z) {
  const g = new THREE.Group();
  g.name = name;
  g.position.set(x, y, z);
  parent.add(g);
  return g;
}
function ellipsoid(
  name,
  parent,
  x,
  y,
  z,
  sx,
  sy,
  sz,
  mat = body,
  segments = 16,
) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(1, segments, 12), mat);
  m.name = name;
  m.position.set(x, y, z);
  m.scale.set(sx, sy, sz);
  parent.add(m);
  return m;
}
function capsule(name, parent, x, y, z, r, len, mat = body) {
  const m = new THREE.Mesh(new THREE.CapsuleGeometry(r, len, 4, 12), mat);
  m.name = name;
  m.position.set(x, y, z);
  parent.add(m);
  return m;
}
const hips = group("Hips", root, 0, 1.04, 0);
ellipsoid("Pelvis", hips, 0, 0, 0, 0.25, 0.18, 0.16);
const torso = group("Torso", hips, 0, 0.12, 0);
ellipsoid("Abdomen", torso, 0, 0.12, 0, 0.21, 0.25, 0.145);
ellipsoid("Ribcage", torso, 0, 0.34, 0, 0.31, 0.28, 0.18);
ellipsoid("PectoralLeft", torso, 0.135, 0.42, 0.11, 0.16, 0.13, 0.115);
ellipsoid("PectoralRight", torso, -0.135, 0.42, 0.11, 0.16, 0.13, 0.115);
ellipsoid("Heart", torso, 0.09, 0.43, 0.207, 0.034, 0.036, 0.016, light, 10);
for (const side of [-1, 1]) {
  for (let i = 0; i < 3; i++)
    ellipsoid(
      "CoreDetail",
      torso,
      side * 0.063,
      0.22 - i * 0.063,
      0.14,
      0.055,
      0.035,
      0.018,
      dark,
      8,
    );
  const arm = group(
    side < 0 ? "RightArm" : "LeftArm",
    torso,
    side * 0.325,
    0.45,
    0,
  );
  ellipsoid("Shoulder", arm, 0, -0.02, 0, 0.12, 0.14, 0.13);
  capsule("UpperArm", arm, 0, -0.18, 0, 0.084, 0.22);
  const elbow = group(
    side < 0 ? "RightForearm" : "LeftForearm",
    arm,
    0,
    -0.35,
    0,
  );
  ellipsoid("Elbow", elbow, 0, 0, 0, 0.078, 0.078, 0.078, dark, 10);
  capsule("Forearm", elbow, 0, -0.13, 0, 0.063, 0.19);
  const hand = group(side < 0 ? "RightHand" : "LeftHand", elbow, 0, -0.29, 0);
  ellipsoid("Palm", hand, 0, -0.03, 0, 0.064, 0.085, 0.028);
  for (let i = 0; i < 4; i++) {
    const finger = group(
      `Finger${side}_${i}`,
      hand,
      -0.043 + i * 0.028,
      -0.088,
      0,
    );
    capsule("FingerMesh", finger, 0, -0.04, 0, 0.011, 0.05 - i * 0.005);
  }
  const thumb = group("Thumb", hand, side * 0.065, -0.01, 0);
  thumb.rotation.z = side * 0.6;
  capsule("ThumbMesh", thumb, 0, -0.025, 0, 0.016, 0.037);
  const leg = group(
    side < 0 ? "RightThigh" : "LeftThigh",
    hips,
    side * 0.135,
    -0.1,
    0,
  );
  capsule("Thigh", leg, 0, -0.2, 0, 0.105, 0.25);
  const knee = group(side < 0 ? "RightShin" : "LeftShin", leg, 0, -0.42, 0);
  ellipsoid("Knee", knee, 0, 0, 0.018, 0.085, 0.08, 0.088, dark, 10);
  capsule("Calf", knee, 0, -0.18, -0.01, 0.075, 0.23);
  const foot = group(
    side < 0 ? "RightFoot" : "LeftFoot",
    knee,
    0,
    -0.38,
    0.035,
  );
  ellipsoid("Foot", foot, 0, -0.025, 0.06, 0.078, 0.058, 0.155);
  ellipsoid("Ankle", foot, 0, 0.027, -0.03, 0.057, 0.057, 0.06, dark, 10);
}
capsule("Neck", torso, 0, 0.66, 0, 0.068, 0.07);
const head = group("Head", torso, 0, 0.85, 0);
ellipsoid("Skull", head, 0, 0.02, 0, 0.135, 0.173, 0.13);
ellipsoid("Jaw", head, 0, -0.076, 0.035, 0.1, 0.081, 0.105);
ellipsoid("Nose", head, 0, -0.015, 0.132, 0.027, 0.045, 0.03);
for (const side of [-1, 1]) {
  ellipsoid("Ear", head, side * 0.13, -0.025, 0, 0.022, 0.045, 0.025);
  ellipsoid(
    "Eye",
    head,
    side * 0.055,
    0.026,
    0.115,
    0.029,
    0.009,
    0.013,
    dark,
    8,
  );
  ellipsoid(
    "Iris",
    head,
    side * 0.055,
    0.026,
    0.126,
    0.01,
    0.008,
    0.007,
    light,
    8,
  );
}
const mouth = ellipsoid(
  "Mouth",
  head,
  0,
  -0.069,
  0.128,
  0.035,
  0.004,
  0.006,
  dark,
  8,
);
const result = await new GLTFExporter().parseAsync(root, { binary: true });
const path = new URL("../frontend/public/assets/twin.glb", import.meta.url);
await writeFile(path, Buffer.from(result));
let triangles = 0;
root.traverse((o) => {
  if (o.isMesh) triangles += o.geometry.index.count / 3;
});
console.log(
  JSON.stringify({ asset: path.pathname, bytes: result.byteLength, triangles }),
);
