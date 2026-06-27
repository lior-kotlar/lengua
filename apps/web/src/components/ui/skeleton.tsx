import { cn } from '@/lib/utils';

/**
 * A pulsing placeholder block (shadcn/ui primitive). Compose several to sketch the shape of content
 * while a query loads. Coverage-excluded with the rest of `components/ui/**`.
 */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-muted', className)}
      {...props}
    />
  );
}

export { Skeleton };
