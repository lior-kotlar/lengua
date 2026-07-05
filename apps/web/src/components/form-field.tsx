/**
 * Labeled text input with inline validation message — the building block of the auth forms.
 * The label is associated via `htmlFor`/`id`, and the error is wired through `aria-describedby`
 * + `aria-invalid` for screen readers.
 */
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export interface FormFieldProps extends Omit<
  React.ComponentProps<'input'>,
  'id'
> {
  /** Required so the label + error can be associated with the input. */
  id: string;
  label: string;
  /** Inline validation message (rendered below the input when present). */
  error?: string | null;
}

export function FormField({
  id,
  label,
  error,
  className,
  ...props
}: FormFieldProps) {
  const hasError = error !== undefined && error !== null && error !== '';
  const errorId = hasError ? `${id}-error` : undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-body font-medium">
        {label}
      </label>
      <Input
        id={id}
        aria-invalid={hasError || undefined}
        aria-describedby={errorId}
        className={cn(hasError && 'border-destructive', className)}
        {...props}
      />
      {hasError && (
        <p id={errorId} className="text-footnote text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
