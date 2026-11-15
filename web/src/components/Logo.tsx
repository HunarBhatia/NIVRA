/** Nivra mark: fingerprint-like arcs that resolve into a shield-shaped "N". */
export default function Logo() {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="nv-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--teal)" />
          <stop offset="1" stopColor="var(--violet)" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="9" stroke="url(#nv-grad)" strokeOpacity=".5" />
      <path d="M10 22V10l12 12V10" stroke="url(#nv-grad)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6.5 16a9.5 9.5 0 0 1 19 0" stroke="url(#nv-grad)" strokeOpacity=".45" strokeLinecap="round" />
    </svg>
  );
}
