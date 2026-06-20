import { cn } from '../../lib/utils'

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
}

export function Button({
  className,
  variant = 'primary',
  size = 'md',
  loading,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all duration-200',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)] focus-visible:ring-offset-2',
        'disabled:pointer-events-none disabled:opacity-50',
        variant === 'primary' &&
          'bg-[var(--color-primary)] text-white shadow-sm hover:bg-[var(--color-primary-light)]',
        variant === 'secondary' &&
          'border border-[var(--color-border)] bg-white text-[var(--color-text)] hover:bg-[var(--color-surface-muted)]',
        variant === 'ghost' && 'text-[var(--color-text-muted)] hover:bg-black/5 hover:text-[var(--color-text)]',
        variant === 'danger' && 'bg-[var(--color-danger)] text-white hover:opacity-90',
        size === 'sm' && 'h-9 px-3 text-sm',
        size === 'md' && 'h-11 px-4 text-sm',
        size === 'lg' && 'h-12 px-6 text-base',
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? 'Please wait…' : children}
    </button>
  )
}
