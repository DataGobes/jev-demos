import type { IconId } from "@/lib/dimensions";

interface IconProps {
  className?: string;
}

/**
 * Small hand-drawn line icon set, one per judgment dimension. Deliberately
 * not an emoji or a generic icon-library glyph — plain stroked shapes that
 * match the editorial look, sized to inherit `currentColor`.
 */
function Trophy({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M7 4h10v4a5 5 0 0 1-5 5 5 5 0 0 1-5-5V4Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M7 5H4v1a4 4 0 0 0 4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M17 5h3v1a4 4 0 0 1-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M12 13v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M8.5 20h7l-1-2.5h-5L8.5 20Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function Hook({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M9 4v9a4 4 0 0 0 8 0v-1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="9" cy="4" r="1.6" stroke="currentColor" strokeWidth="1.5" />
      <path d="M17 10.5c1.1.4 1.8 1.3 1.8 2.5 0 1.6-1.5 3-3.3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function CrackedHeart({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M12 20s-7-4.6-9-9.2C1.6 7.4 3.4 4.5 6.6 4.1c1.9-.2 3.6.8 4.4 2.3.8-1.5 2.5-2.5 4.4-2.3 3.2.4 5 3.3 3.6 6.7C17 15.4 12 20 12 20Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M11 7.5 9.3 11l2.4 1.6-1.4 3.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Hash({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M9.5 3.5 7 20.5M17 3.5l-2.5 17M4 9h16M3 15h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function StackedLines({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M4 6h16M4 11h11M4 16h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function Megaphone({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M4 10v4h3l6 4V6L7 10H4Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M15 8.5a4 4 0 0 1 0 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M18 6a7.5 7.5 0 0 1 0 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M6 14v3.5a1.5 1.5 0 0 0 3 0V14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function Pacifier({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.5" />
      <path d="M9.5 11 7 13.5a2.5 2.5 0 1 0 3.5 3.5L13 14.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="16.5" cy="17.5" r="2" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function AlarmClock({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="12" cy="13" r="7" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 9.5V13l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 4 2.5 6.5M19 4l2.5 2.5M9 3.5h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

const ICONS: Record<IconId, (props: IconProps) => React.JSX.Element> = {
  brag: Trophy,
  bait: Hook,
  trauma: CrackedHeart,
  buzzword: Hash,
  broetry: StackedLines,
  opener: Megaphone,
  lesson: Pacifier,
  hustle: AlarmClock,
};

export function DimensionIcon({ icon, className }: { icon: IconId; className?: string }) {
  const Component = ICONS[icon];
  return <Component className={className} />;
}
