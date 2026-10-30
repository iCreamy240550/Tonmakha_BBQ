/**
 * frontend/shared/js/toast.js — ข้อความแจ้งสั้น ๆ มุมขวาล่างของหน้าต่าง หายเองใน 3 วินาที
 * คัดลอกจาก ui/widgets/toast.py
 */

let containerEl = null;
let currentToast = null;
let hideTimer = null;

function ensureContainer() {
  if (!containerEl || !document.body.contains(containerEl)) {
    containerEl = document.createElement('div');
    containerEl.className = 'toast-container';
    containerEl.setAttribute('aria-live', 'polite');
    document.body.appendChild(containerEl);
  }
  return containerEl;
}

/**
 * แสดงข้อความ kind = 'info' | 'success' | 'error' | 'warning' (error อยู่นานกว่าปกติ 2 เท่า)
 */
export function showToast(text, kind = 'info', ms = 3000) {
  const container = ensureContainer();
  if (hideTimer) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
  if (currentToast && currentToast.parentNode) {
    currentToast.parentNode.removeChild(currentToast);
  }

  const validKind = ['info', 'success', 'error', 'warning'].includes(kind) ? kind : 'info';
  const item = document.createElement('div');
  item.className = `toast-item toast-${validKind}`;
  item.textContent = String(text || '');
  container.appendChild(item);
  currentToast = item;

  const duration = validKind === 'error' ? ms * 2 : ms;
  hideTimer = setTimeout(() => {
    if (currentToast === item && item.parentNode) {
      item.parentNode.removeChild(item);
      currentToast = null;
    }
  }, duration);
}
