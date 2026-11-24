import { type ReactNode, useId } from "react";

export function Panel({
  title,
  className = "",
  children,
}: Readonly<{ title: string; className?: string; children: ReactNode }>) {
  const id = useId();
  return (
    <section className={`panel ${className}`.trim()} aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}
