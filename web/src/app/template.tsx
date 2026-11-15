"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";

/** Page transition: every navigation remounts this template, so each new page
 *  rises in softly. Skipped under prefers-reduced-motion. */
export default function Template({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const tween = gsap.fromTo(ref.current, { opacity: 0, y: 12 },
      { opacity: 1, y: 0, duration: 0.45, ease: "power3.out", clearProps: "all" });
    return () => { tween.kill(); };
  }, []);

  return <div ref={ref}>{children}</div>;
}
