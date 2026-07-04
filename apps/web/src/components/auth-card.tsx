/**
 * Presentational card scaffold shared by the auth screens (login / signup / forgot / reset).
 * Renders the brand wordmark + a titled card inside the centered `AuthLayout` column, entering with
 * a soft rise (CSS `animate-in`; the reduced-motion media query in index.css settles it instantly).
 */
export interface AuthCardProps {
  title: string;
  description?: string;
  children: React.ReactNode;
}

export function AuthCard({ title, description, children }: AuthCardProps) {
  return (
    <div className="animate-in fade-in-0 slide-in-from-bottom-2 rounded-2xl border bg-card p-8 text-card-foreground shadow-overlay duration-300 ease-apple">
      <div className="flex flex-col space-y-1.5">
        {/* Brand wordmark — a NON-heading element on purpose so each auth screen exposes exactly
            ONE heading (its h1); the staging specs match headings by case-insensitive substring, so
            a heading here would collide with the /log in/i, /sign up/i, … lookups. */}
        <p className="text-[1.25rem] font-bold leading-none tracking-[-0.01em]">
          Lengua
        </p>
        {/* A real <h1> (not shadcn's div-based CardTitle) so it carries the heading role. */}
        <h1 className="text-title1">{title}</h1>
        {description !== undefined && (
          <p className="text-subhead text-muted-foreground">{description}</p>
        )}
      </div>
      <div className="mt-6">{children}</div>
    </div>
  );
}
