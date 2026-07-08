/**
 * Labeled text input with inline validation message — the building block of the auth forms.
 * The label is associated via `htmlFor`/`id`, and the error is wired through `aria-describedby`
 * + `aria-invalid` for screen readers.
 */
import { Input } from '@/components/ui/input';
import { PasswordInput } from '@/components/ui/password-input';
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
  type,
  ...props
}: FormFieldProps) {
  const hasError = error !== undefined && error !== null && error !== '';
  const errorId = hasError ? `${id}-error` : undefined;
  // Shared props for whichever input variant renders below — the label (`htmlFor`)/error wiring is
  // identical either way.
  const sharedProps = {
    id,
    'aria-invalid': hasError || undefined,
    'aria-describedby': errorId,
    className: cn(hasError && 'border-destructive', className),
    ...props,
  };
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-body font-medium">
        {label}
      </label>
      {/* Password fields get the reveal ("eye") affordance; PasswordInput owns the `type`. */}
      {type === 'password' ? (
        <PasswordInput {...sharedProps} />
      ) : (
        <Input type={type} {...sharedProps} />
      )}
      {hasError && (
        <p id={errorId} className="text-footnote text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
