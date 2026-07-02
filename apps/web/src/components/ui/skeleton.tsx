import { cn } from '@/lib/utils';

/**
 * A shimmering placeholder block. Compose several to sketch the shape of content while a query
 * loads. The sheen is a gradient sweep (`animation-shimmer`, tailwind.config.ts) instead of the
 * stock opacity pulse. Coverage-excluded with the rest of `components/ui/**`.
 */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-md bg-muted after:absolute after:inset-0 after:-translate-x-full after:animate-shimmer after:bg-gradient-to-r after:from-transparent after:via-white/40 after:to-transparent dark:after:via-white/[0.06]',
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };
