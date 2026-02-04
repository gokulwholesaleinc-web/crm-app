import clsx from 'clsx';

export type AvatarSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

export interface AvatarProps {
  src?: string | null;
  name?: string;
  size?: AvatarSize;
  className?: string;
}

const sizeStyles: Record<AvatarSize, string> = {
  xs: 'h-6 w-6 text-xs',
  sm: 'h-8 w-8 text-sm',
  md: 'h-10 w-10 text-sm',
  lg: 'h-12 w-12 text-base',
  xl: 'h-16 w-16 text-lg',
};

const colorPalette = [
  'bg-red-500',
  'bg-orange-500',
  'bg-amber-500',
  'bg-yellow-500',
  'bg-lime-500',
  'bg-green-500',
  'bg-emerald-500',
  'bg-teal-500',
  'bg-cyan-500',
  'bg-sky-500',
  'bg-blue-500',
  'bg-indigo-500',
  'bg-violet-500',
  'bg-purple-500',
  'bg-fuchsia-500',
  'bg-pink-500',
  'bg-rose-500',
];

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) {
    return parts[0].substring(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function getColorFromName(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % colorPalette.length;
  return colorPalette[index];
}

export function Avatar({ src, name, size = 'md', className }: AvatarProps) {
  const initials = name ? getInitials(name) : '?';
  const bgColor = name ? getColorFromName(name) : 'bg-gray-400';

  if (src) {
    return (
      <img
        src={src}
        alt={name || 'Avatar'}
        className={clsx(
          'rounded-full object-cover',
          sizeStyles[size],
          className
        )}
      />
    );
  }

  return (
    <div
      className={clsx(
        'rounded-full flex items-center justify-center font-medium text-white',
        sizeStyles[size],
        bgColor,
        className
      )}
      aria-label={name || 'Avatar'}
    >
      {initials}
    </div>
  );
}

export interface AvatarGroupProps {
  avatars: Array<{ src?: string | null; name?: string }>;
  max?: number;
  size?: AvatarSize;
  className?: string;
}

export function AvatarGroup({
  avatars,
  max = 4,
  size = 'md',
  className,
}: AvatarGroupProps) {
  const visibleAvatars = avatars.slice(0, max);
  const remainingCount = avatars.length - max;

  return (
    <div className={clsx('flex -space-x-2', className)}>
      {visibleAvatars.map((avatar, index) => (
        <Avatar
          key={index}
          src={avatar.src}
          name={avatar.name}
          size={size}
          className="ring-2 ring-white"
        />
      ))}
      {remainingCount > 0 && (
        <div
          className={clsx(
            'rounded-full flex items-center justify-center font-medium bg-gray-200 text-gray-600 ring-2 ring-white',
            sizeStyles[size]
          )}
        >
          +{remainingCount}
        </div>
      )}
    </div>
  );
}
