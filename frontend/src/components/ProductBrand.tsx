/** Shared code-native product mark; decorative SVG keeps the name accessible. */
export default function ProductBrand() {
  return <span className="inline-flex items-center gap-2 text-lg font-semibold tracking-wide text-white">
    <svg aria-hidden="true" focusable="false" viewBox="0 0 32 32" className="h-7 w-7 shrink-0" fill="none">
      <path d="M16 3 27 7v9c0 6-6 11-11 13C11 27 5 22 5 16V7Z" stroke="#00c8ff" strokeWidth="2" />
      <path d="m10 17 4 4 8-10" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
    <span>Audit<span className="text-cyan">Mind</span></span>
  </span>;
}
