interface BrandMarkProps {
  size?: number
}

export default function BrandMark({ size = 32 }: BrandMarkProps) {
  return (
    <svg
      aria-hidden="true"
      className="brand-mark"
      height={size}
      viewBox="0 0 32 32"
      width={size}
    >
      <circle cx="10" cy="22" fill="currentColor" r="3.5" />
      <path d="M10 14a8 8 0 0 1 8 8" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="3" />
      <path d="M10 7a15 15 0 0 1 15 15" fill="none" opacity=".42" stroke="currentColor" strokeLinecap="round" strokeWidth="3" />
      <path d="m23.6 5.5.8 2.1 2.1.8-2.1.8-.8 2.1-.8-2.1-2.1-.8 2.1-.8.8-2.1Z" fill="currentColor" />
    </svg>
  )
}
