import toast from 'react-hot-toast';

export function showSuccess(message: string) {
  toast.success(message);
}

export function showError(message: string) {
  toast.error(message);
}

export function showWarning(message: string) {
  // react-hot-toast doesn't ship a built-in warning variant \u2014 use a
  // 6-second toast with a warning glyph and amber accent. Visibly
  // distinct from success/error so users notice a "your action half-
  // succeeded" message instead of dismissing a generic info toast.
  toast(message, {
    icon: '\u26A0\uFE0F',
    duration: 6000,
    style: { borderLeft: '4px solid #D4A574' },
  });
}

export function showInfo(message: string) {
  toast(message, {
    icon: '\u2139\uFE0F',
  });
}
