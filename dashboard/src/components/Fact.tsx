import type { ReactNode } from "react";

export function Fact({
  name,
  mono = false,
  children,
}: Readonly<{ name: string; mono?: boolean; children: ReactNode }>) {
  return (
    <div>
      <dt>{name}</dt>
      <dd className={mono ? "mono" : undefined}>{children}</dd>
    </div>
  );
}
