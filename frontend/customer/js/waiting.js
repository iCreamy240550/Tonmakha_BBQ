/**
 * frontend/customer/js/waiting.js — หน้ารอพนักงานยืนยัน (สถานะ pending) + ปุ่มยกเลิกคำขอ
 * คัดลอกจาก web/pages/waiting.py
 */

import { apiPost } from '../../shared/js/api.js';
import { BaseDialog } from '../../shared/js/dialogs.js';
import { showToast } from '../../shared/js/toast.js';
import { createMessageCard } from './components.js';

export function renderWaiting(container, onChange) {
  const card = createMessageCard({
    icon: 'hourglass_top',
    title: 'ส่งคำขอแล้ว กรุณารอพนักงานยืนยัน',
    text: 'พนักงานจะยืนยันโต๊ะของคุณสักครู่ เมื่อยืนยันแล้วจะสั่งอาหารได้ทันที',
    color: 'warning',
    spinner: true,
  });

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'btn btn-danger';
  cancelBtn.style.minHeight = '44px';
  cancelBtn.textContent = 'ยกเลิกคำขอ';
  cancelBtn.addEventListener('click', () => openCancelConfirm(onChange));
  card.appendChild(cancelBtn);

  container.appendChild(card);
}

async function openCancelConfirm(onChange) {
  const dlg = new BaseDialog('ยกเลิกคำขอใช้โต๊ะ?', { width: 400 });
  const msg = document.createElement('div');
  msg.style.fontSize = 'var(--fs-lg)';
  msg.style.color = 'var(--color-text-muted)';
  msg.textContent = 'ถ้ายกเลิก ต้องสแกน QR ใหม่หากต้องการใช้บริการ';
  dlg.body.appendChild(msg);

  dlg.addButtons({
    confirmText: 'ยืนยันยกเลิก',
    cancelText: 'ไม่ยกเลิก',
    variant: 'danger',
    onConfirm: async () => {
      try {
        await apiPost('/api/customer/cancel', {});
      } catch (err) {
        showToast(err.message || 'ไม่สามารถยกเลิกคำขอได้', 'warning');
      }
      dlg.close(true);
      if (typeof onChange === 'function') {
        onChange();
      }
    },
  });

  await dlg.show();
}
