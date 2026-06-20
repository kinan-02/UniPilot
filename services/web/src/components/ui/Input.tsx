import { cn } from '../../lib/utils'

type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string
  error?: string
}

export function Input({ label, error, className, id, ...props }: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')
  return (
    <label className="block space-y-1.5" htmlFor={inputId}>
      {label ? (
        <span className="text-sm font-medium text-[var(--color-text)]">{label}</span>
      ) : null}
      <input
        id={inputId}
        className={cn(
          'h-11 w-full rounded-xl border border-[var(--color-border)] bg-white px-3.5 text-sm',
          'placeholder:text-[var(--color-text-muted)]/70',
          'transition-colors focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15',
          error && 'border-[var(--color-danger)]',
          className,
        )}
        {...props}
      />
      {error ? <span className="text-xs text-[var(--color-danger)]">{error}</span> : null}
    </label>
  )
}

type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & {
  label?: string
  error?: string
}

export function Select({ label, error, className, id, children, ...props }: SelectProps) {
  const selectId = id ?? label?.toLowerCase().replace(/\s+/g, '-')
  return (
    <label className="block space-y-1.5" htmlFor={selectId}>
      {label ? (
        <span className="text-sm font-medium text-[var(--color-text)]">{label}</span>
      ) : null}
      <select
        id={selectId}
        className={cn(
          'h-11 w-full rounded-xl border border-[var(--color-border)] bg-white px-3.5 text-sm',
          'focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15',
          error && 'border-[var(--color-danger)]',
          className,
        )}
        {...props}
      >
        {children}
      </select>
      {error ? <span className="text-xs text-[var(--color-danger)]">{error}</span> : null}
    </label>
  )
}
