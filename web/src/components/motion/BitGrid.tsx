"use client";

import { useEffect, useRef } from "react";
import { animate, stagger } from "animejs";

/** A 64-bit perceptual hash drawn as an 8x8 grid. `bits` is 16 hex chars
 *  (or null while unknown). `diff` (also hex) marks bits that differ from
 *  another hash in coral. New values ripple in with anime.js. */
export function hexToBits(hex: string | null | undefined): number[] {
  if (!hex || !/^[0-9a-f]{16}$/i.test(hex)) return Array(64).fill(0);
  return [...hex].flatMap((c) => {
    const n = parseInt(c, 16);
    return [3, 2, 1, 0].map((i) => (n >> i) & 1);
  });
}

export default function BitGrid({ bits, diff, label, animateIn = true }: {
  bits: string | null | undefined;
  diff?: string | null;
  label?: string;
  animateIn?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const on = hexToBits(bits);
  const off = diff ? hexToBits(diff) : null;

  useEffect(() => {
    const el = ref.current;
    if (!el || !bits || !animateIn || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const a = animate(el.querySelectorAll("span"), {
      scale: [0.2, 1],
      opacity: [0, 1],
      delay: stagger(9, { grid: [8, 8], from: "center" }),
      duration: 420,
      ease: "outExpo",
    });
    return () => { a.revert(); };
  }, [bits, diff, animateIn]);

  return (
    <div ref={ref} className="bits" role="img" aria-label={label ?? (bits ? `Fingerprint ${bits}` : "Fingerprint not computed yet")}>
      {on.map((b, i) => (
        <span key={i} data-on={b} data-diff={off?.[i] ?? 0} />
      ))}
    </div>
  );
}
