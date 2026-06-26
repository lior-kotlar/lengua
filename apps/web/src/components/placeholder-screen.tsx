/**
 * Lightweight stub used by the authenticated screens until later Phase-4 groups build them out.
 * Renders a real heading (so routing tests and the app shell are meaningful) plus a short note.
 */
export interface PlaceholderScreenProps {
  title: string;
  description?: string;
}

export function PlaceholderScreen({
  title,
  description,
}: PlaceholderScreenProps) {
  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      <p className="text-sm text-muted-foreground">
        {description ?? 'Coming soon.'}
      </p>
    </section>
  );
}
