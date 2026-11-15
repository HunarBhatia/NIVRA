"use client";

import { useEffect, useRef } from "react";
import { animate } from "animejs";

/** A number that counts up once it scrolls into view. Renders the final
 *  value on the server so it is correct without JavaScript. */
export default function CountUp({ to, suffix = "" }: { to: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const state = { v: 0 };
    let started = false;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting || started) return;
      started = true;
      animate(state, {
        v: to, duration: 1400, ease: "outExpo",
        onUpdate: () => { el.textContent = `${Math.round(state.v)}${suffix}`; },
      });
    });
    io.observe(el);
    return () => io.disconnect();
  }, [to, suffix]);
  return <span ref={ref} className="num">{to}{suffix}</span>;
}
