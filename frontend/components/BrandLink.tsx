import Link from "next/link";

export function BrandLink() {
  return (
    <Link className="wordmark" href="/" aria-label="SkyOffer 首页">
      <span className="wordmark-mark" aria-hidden="true">
        <svg viewBox="0 0 36 36" role="presentation">
          <path d="M8.5 25.5c4.8-.8 7.2-3.7 9.3-7.1 2.2-3.5 4.6-6.1 9.7-8" />
          <path d="m22.5 9.5 5.5.6-1.4 5.3" />
          <circle cx="8.5" cy="25.5" r="1.7" />
        </svg>
      </span>
      <span>SkyOffer</span>
    </Link>
  );
}
