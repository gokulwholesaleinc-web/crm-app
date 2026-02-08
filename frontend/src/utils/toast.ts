import toast from 'react-hot-toast';

export function showSuccess(message: string) {
  toast.success(message);
}

export function showError(message: string) {
  toast.error(message);
}

export function showInfo(message: string) {
  toast(message, {
    icon: '\u2139\uFE0F',
  });
}
