import type { ReactNode } from "react";

const base = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function Svg({ size = 18, children, className }: { size?: number; children: ReactNode; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" className={className} {...base}>
      {children}
    </svg>
  );
}

export const Logo = () => (
  <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
    <rect x="2" y="2" width="22" height="22" rx="5" fill="none" stroke="currentColor" strokeWidth="2" />
    <path d="M7 9h12M7 13h12M7 17h7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <circle cx="19.5" cy="18.5" r="2.6" fill="var(--rust)" />
  </svg>
);
export const Upload = ({ size = 40 }: { size?: number }) => (
  <Svg size={size}><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M4 14v4.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V14" /></Svg>
);
export const FileIcon = () => <Svg size={20}><path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z" /><path d="M14 3v5h5" /></Svg>;
export const Close = () => <Svg size={18}><path d="M6 6l12 12M18 6 6 18" /></Svg>;
export const Arrow = () => <Svg size={17}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>;
export const Refresh = () => <Svg size={16}><path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v4.5h-4.5" /></Svg>;
export const Book = () => <Svg size={15}><path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5z" /><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19" /></Svg>;
export const Check = () => <Svg size={16}><path d="M4.5 12.5 9.5 17.5 19.5 6.5" /></Svg>;
export const Alert = () => <Svg size={16}><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5v.01" /></Svg>;
export const Bulb = () => <Svg size={16}><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.6.5 1.1 1.3 1.1 2.2h5c0-.9.5-1.7 1.1-2.2A6 6 0 0 0 12 3z" /></Svg>;
export const Trash = () => <Svg size={16}><path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13" /></Svg>;
export const Spinner = () => <Svg size={16} className="spin"><path d="M12 3a9 9 0 1 0 9 9" /></Svg>;
export const Chevron = ({ open }: { open: boolean }) => (
  <Svg size={15}><path d={open ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} /></Svg>
);
