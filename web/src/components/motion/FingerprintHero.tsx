"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

/** The landing hero's signature: a fingerprint made of ~14k light points,
 *  with a scan wave that sweeps outward through the ridges, the way Nivra
 *  reads an image into a fingerprint. Decorative only (aria-hidden).
 *  Under prefers-reduced-motion it renders a single still frame. */

const VERT = /* glsl */ `
  uniform float uTime;
  uniform float uScan;
  uniform float uPixelRatio;
  attribute float aRadius;
  attribute float aSeed;
  varying float vGlow;
  varying float vMix;
  void main() {
    vec3 p = position;
    float wave = exp(-pow((aRadius - uScan) * 7.0, 2.0));
    p.z += wave * 0.18 + sin(uTime * 0.8 + aSeed * 6.28) * 0.012;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    vGlow = wave;
    vMix = aRadius;
    gl_PointSize = (2.4 + wave * 4.0 + aSeed * 1.2) * uPixelRatio * (3.2 / -mv.z);
  }
`;

const FRAG = /* glsl */ `
  uniform vec3 uTeal;
  uniform vec3 uViolet;
  varying float vGlow;
  varying float vMix;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5) discard;
    float a = smoothstep(0.5, 0.0, d);
    vec3 col = mix(uTeal, uViolet, smoothstep(0.15, 1.0, vMix));
    col = mix(col, vec3(1.0), vGlow * 0.55);
    gl_FragColor = vec4(col, a * (0.6 + vGlow * 0.4));
  }
`;

function buildRidges() {
  const pos: number[] = [];
  const radius: number[] = [];
  const seed: number[] = [];
  const rings = 34;
  for (let r = 1; r <= rings; r++) {
    const base = (r / rings) * 1.25;
    const steps = Math.floor(70 + r * 14);
    // Each ridge has a couple of natural breaks, like a real print.
    const breakAt = Math.random() * Math.PI * 2;
    const breakLen = 0.15 + Math.random() * 0.35;
    for (let i = 0; i < steps; i++) {
      const t = (i / steps) * Math.PI * 2;
      let dt = Math.abs(t - breakAt);
      dt = Math.min(dt, Math.PI * 2 - dt);
      if (dt < breakLen && r > 3) continue;
      const wob = 1 + 0.06 * Math.sin(3 * t + r * 0.45) + 0.03 * Math.sin(7 * t - r * 0.2);
      const rr = base * wob;
      // Elongated, slightly tilted loop: a whorl rather than a target.
      const x = Math.cos(t) * rr * 0.82 + Math.sin(r * 0.3) * 0.02;
      const y = Math.sin(t) * rr * 1.08 - (r / rings) * 0.12;
      const z = -(rr * rr) * 0.22;
      pos.push(x, y, z);
      radius.push(rr / 1.35);
      seed.push(Math.random());
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("aRadius", new THREE.Float32BufferAttribute(radius, 1));
  g.setAttribute("aSeed", new THREE.Float32BufferAttribute(seed, 1));
  return g;
}

export default function FingerprintHero() {
  const mount = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = mount.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    } catch {
      return; // no WebGL: the page reads fine without the visual
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 50);
    camera.position.set(0, 0, 4.2);
    const ratio = Math.min(window.devicePixelRatio, 2);
    renderer.setPixelRatio(ratio);
    el.appendChild(renderer.domElement);

    const css = getComputedStyle(document.documentElement);
    const uniforms = {
      uTime: { value: 0 },
      uScan: { value: 0.4 },
      uPixelRatio: { value: ratio },
      uTeal: { value: new THREE.Color(css.getPropertyValue("--teal").trim() || "#3ef0c8") },
      uViolet: { value: new THREE.Color(css.getPropertyValue("--violet").trim() || "#8a7dff") },
    };
    const geometry = buildRidges();
    const material = new THREE.ShaderMaterial({
      uniforms, vertexShader: VERT, fragmentShader: FRAG,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const print = new THREE.Points(geometry, material);
    const group = new THREE.Group();
    group.add(print);
    scene.add(group);

    const layout = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
      // Desktop: sit to the right of the headline. Narrow: centred, behind.
      const wide = w > 900;
      group.position.set(wide ? 1.35 : 0, wide ? 0 : 0.2, wide ? 0 : -1.2);
    };
    layout();
    const ro = new ResizeObserver(layout);
    ro.observe(el);

    const target = { x: 0, y: 0 };
    const onMove = (e: PointerEvent) => {
      target.x = (e.clientX / window.innerWidth - 0.5) * 0.5;
      target.y = (e.clientY / window.innerHeight - 0.5) * 0.4;
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    let raf = 0;
    let visible = true;
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
    io.observe(el);
    const t0 = performance.now();
    const frame = () => {
      raf = requestAnimationFrame(frame);
      if (!visible) return;
      const t = (performance.now() - t0) / 1000;
      uniforms.uTime.value = t;
      uniforms.uScan.value = ((t * 0.28) % 1.4) - 0.1;
      group.rotation.y += (target.x + Math.sin(t * 0.25) * 0.12 - group.rotation.y) * 0.04;
      group.rotation.x += (target.y - 0.12 - group.rotation.x) * 0.04;
      renderer.render(scene, camera);
    };
    if (reduce) {
      group.rotation.set(-0.12, -0.2, 0);
      renderer.render(scene, camera);
    } else {
      frame();
    }

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      window.removeEventListener("pointermove", onMove);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div ref={mount} className="hero__canvas" aria-hidden="true" />;
}
