import type { ReactNode } from "react";

// U11 — a lightweight hover/focus tooltip popover (multi-paragraph capable). Pure CSS show/hide,
// keyboard-accessible (focus-within). pos = above/below the trigger; align = which edge to anchor.
export default function Tip({
  tip,
  children,
  pos = "bottom",
  align = "left",
  w = 280,
}: {
  tip: ReactNode;
  children: ReactNode;
  pos?: "top" | "bottom";
  align?: "left" | "right" | "center";
  w?: number;
}) {
  return (
    <span className={`tip-wrap tip-${pos} tip-al-${align}`} tabIndex={0}>
      {children}
      <span className="tip-pop" style={{ width: w }} role="tooltip">
        {tip}
      </span>
    </span>
  );
}
