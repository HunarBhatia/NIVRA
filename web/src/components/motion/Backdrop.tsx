"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";

/** Fixed ambient background: two slow-drifting aurora glows over a faint grid.
 *  Purely decorative (aria-hidden); motion stops under prefers-reduced-motion. */
export default function Backdrop() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const ctx = gsap.context(() => {
      gsap.to(".backdrop__glow--a", { x: "12vw", y: "8vh", duration: 18, ease: "sine.inOut", yoyo: true, repeat: -1 });
      gsap.to(".backdrop__glow--b", { x: "-10vw", y: "-10vh", duration: 22, ease: "sine.inOut", yoyo: true, repeat: -1 });
    }, el);
    return () => ctx.revert();
  }, []);

  return (
    <div ref={ref} className="backdrop" aria-hidden="true">
      <div className="backdrop__glow backdrop__glow--a" />
      <div className="backdrop__glow backdrop__glow--b" />
      <div className="backdrop__grid" />
    </div>
  );
}
