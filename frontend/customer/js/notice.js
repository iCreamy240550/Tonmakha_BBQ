/**
 * frontend/customer/js/notice.js — ข้อความแจ้งลูกค้า (เมนูหมด / ยกเลิกรายการ / พนักงานส่งข้อความ)
 * คัดลอกจาก web/pages/notice.py
 */

import { apiPost } from '../../shared/js/api.js';
import { fmt_time } from '../../shared/js/format.js';
import { showToast } from '../../shared/js/toast.js';
import { createMessageCard } from './components.js';

const NOTICE_ICONS = {
  sold_out: '⛔',
  item_cancelled: '✕',
  staff_message: '📢',
  info: 'ℹ',
};

const NOTICE_KINDS = {
  sold_out: 'warning',
  item_cancelled: 'error',
  staff_message: 'info',
  info: 'info',
};

const shownUnreadIds = new Set();

export async function showUnreadNotices(snap) {
  if (!snap || !Array.isArray(snap.unread) || snap.unread.length === 0) {
    return 0;
  }
  const toMark = [];
  for (const n of snap.unread) {
    if (!shownUnreadIds.has(n.id)) {
      shownUnreadIds.add(n.id);
      const toastKind = NOTICE_KINDS[n.kind] || 'info';
      showToast(n.message, toastKind, 6000);
    }
    toMark.push(n.id);
  }
  if (toMark.length > 0) {
    try {
      await apiPost('/api/customer/notices/read', { notice_ids: toMark });
    } catch (_e) {
      // ignore
    }
  }
  return toMark.length;
}

export function renderNotices(container, snap) {
  const notices = (snap && snap.notices) || [];
  if (notices.length === 0) {
    container.appendChild(
      createMessageCard({
        icon: 'notifications_none',
        title: 'ยังไม่มีข้อความ',
        text: 'ข้อความจากร้าน เช่น เมนูหมด จะแสดงที่นี่',
        color: 'grey',
      })
    );
    return;
  }

  for (const n of notices) {
    const card = document.createElement('div');
    card.className = 'cust-section-card audit-block';
    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.alignItems = 'flex-start';
    row.style.gap = 'var(--space-3)';

    const iconEl = document.createElement('div');
    iconEl.style.fontSize = 'var(--fs-title)';
    iconEl.textContent = NOTICE_ICONS[n.kind] || 'ℹ';
    row.appendChild(iconEl);

    const col = document.createElement('div');
    col.style.display = 'flex';
    col.style.flexDirection = 'column';
    col.style.gap = 'var(--space-1)';

    const msgEl = document.createElement('div');
    msgEl.style.fontSize = 'var(--fs-lg)';
    msgEl.textContent = n.message;

    const timeEl = document.createElement('div');
    timeEl.style.fontSize = 'var(--fs-xs)';
    timeEl.style.color = 'var(--color-text-muted)';
    timeEl.textContent = fmt_time(n.created_at, '');

    col.appendChild(msgEl);
    col.appendChild(timeEl);
    row.appendChild(col);
    card.appendChild(row);
    container.appendChild(card);
  }
}
