export function Banner({
  kind = "error",
  children,
}: {
  kind?: "error" | "warning" | "info";
  children: React.ReactNode;
}) {
  const style = {
    error: "border-danger/40 bg-danger/10 text-danger",
    warning: "border-warning/40 bg-warning/10 text-warning",
    info: "border-accent/40 bg-accent/10 text-accent",
  }[kind];

  return (
    <div className={`rounded border p-3 text-sm leading-relaxed ${style}`}>
      {children}
    </div>
  );
}
