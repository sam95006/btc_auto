import type { ReactNode } from "react";
import { useReveal } from "../hooks/useCorporate";

/** Cinematic scroll-reveal section wrapper (reduced-motion safe, no CLS). */
export function Scene({
  id,
  className = "",
  children,
}: {
  id?: string;
  className?: string;
  children: ReactNode;
}) {
  const { ref, shown } = useReveal<HTMLElement>();
  return (
    <section
      ref={ref}
      id={id}
      className={`corp-scene ${shown ? "is-shown" : ""} ${className}`}
      data-testid={id ? `scene-${id}` : undefined}
    >
      {children}
    </section>
  );
}
