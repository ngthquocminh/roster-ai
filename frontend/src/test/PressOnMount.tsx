import { useEffect, useRef, type ReactNode } from "react";

/** Presses a real control after mount, so a transient state (the inline discard
 * confirmation) is rendered by the SHIPPED component, never by a lookalike. */
export function PressOnMount({ name, children }: Readonly<{ name: string; children: ReactNode }>) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const target = Array.from(ref.current?.querySelectorAll("button") ?? [])
      .find((node) => node.textContent === name);
    target?.click();
  }, [name]);
  return <div ref={ref}>{children}</div>;
}
