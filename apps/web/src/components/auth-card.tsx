/**
 * Presentational card scaffold shared by the auth screens (login / signup / forgot / reset).
 * Renders a titled card inside the centered `AuthLayout` column.
 */
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from '@/components/ui/card';

export interface AuthCardProps {
  title: string;
  description?: string;
  children: React.ReactNode;
}

export function AuthCard({ title, description, children }: AuthCardProps) {
  return (
    <Card>
      <CardHeader>
        {/* A real <h1> (not shadcn's div-based CardTitle) so it carries the heading role. */}
        <h1 className="text-2xl font-semibold leading-none tracking-tight">
          {title}
        </h1>
        {description !== undefined && (
          <CardDescription>{description}</CardDescription>
        )}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
