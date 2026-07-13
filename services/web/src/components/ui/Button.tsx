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
        'inline-flex items-center justify-center gap-2 rounded-[var(--radius-xl)] font-semibold transition-all duration-300',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)]',
        'disabled:pointer-events-none disabled:opacity-50',
        'active:scale-95',
        variant === 'primary' &&
          'bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-primary-light)] text-white shadow-glow hover:scale-105 hover:shadow-card',
        variant === 'secondary' &&
          'border border-[var(--color-border)] bg-[rgba(255,255,255,0.03)] backdrop-blur-md text-[var(--color-text)] hover:bg-[rgba(255,255,255,0.08)] hover:scale-105 shadow-soft',
        variant === 'ghost' && 'text-[var(--color-text-muted)] hover:bg-[rgba(255,255,255,0.05)] hover:text-[var(--color-text)]',
        variant === 'danger' && 'bg-gradient-to-r from-[var(--color-danger)] to-red-600 text-white shadow-soft hover:scale-105 hover:shadow-card',
        size === 'sm' && 'h-9 px-4 text-sm',
        size === 'md' && 'h-11 px-6 text-sm',
        size === 'lg' && 'h-14 px-8 text-base rounded-[var(--radius-2xl)]',
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? 'Please wait…' : children}
    </button>
  )
}
