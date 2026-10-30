/**
 * frontend/customer/js/enter.js — หน้าเข้าจาก QR: /t/<เลขโต๊ะ>?k=<รหัสลับ>
 * สแกนจริงด้วย POST หลังโหลดหน้า เพื่อกันบอตพรีวิวลิงก์ (LINE/Facebook) สร้างรอบหลอก
 * ล้าง ?k= ออกจาก URL ทันที และเมื่อสำเร็จพาไป /s ด้วย location.replace('/s')
 */

import { apiPost } from '../../shared/js/api.js';
import { APP_NAME_SHORT, createCustomerHeader, createMessageCard } from './components.js';
import {
  renderInvalidQr,
  renderOtherTable,
  renderShopClosed,
  renderTableBusy,
} from './closed.js';

export async function runEnterPage(container, tableNo, secretKey) {
  // ล้าง ?k= ออกจาก URL/ประวัติทันทีเพื่อไม่ให้รหัสลับโต๊ะค้างในแถบที่อยู่
  try {
    window.history.replaceState(null, '', window.location.pathname);
  } catch (_e) {
    // ignore
  }

  container.textContent = '';
  container.appendChild(createCustomerHeader(APP_NAME_SHORT));
  container.appendChild(
    createMessageCard({
      icon: 'qr_code_scanner',
      title: 'กำลังตรวจสอบ QR...',
      color: 'primary',
      spinner: true,
    })
  );

  let outcome;
  try {
    outcome = await apiPost('/api/customer/scan', {
      table_no: Number(tableNo),
      k: String(secretKey || ''),
    });
  } catch (_err) {
    container.textContent = '';
    container.appendChild(createCustomerHeader(APP_NAME_SHORT));
    renderInvalidQr(container);
    return;
  }

  container.textContent = '';
  container.appendChild(
    createCustomerHeader(outcome.table_name || APP_NAME_SHORT)
  );

  if (outcome.kind === 'ok') {
    const okCard = createMessageCard({
      icon: 'check_circle',
      title: 'ส่งคำขอแล้ว',
      text: 'กำลังพาไปหน้าสั่งอาหาร...',
      color: 'positive',
    });
    const link = document.createElement('a');
    link.href = '/s';
    link.className = 'btn btn-ghost';
    link.style.minHeight = '44px';
    link.textContent = 'ถ้าหน้าไม่เปลี่ยน กดที่นี่';
    okCard.appendChild(link);
    container.appendChild(okCard);

    setTimeout(() => {
      window.location.replace('/s');
    }, 250);
  } else if (outcome.kind === 'other_table') {
    renderOtherTable(container, outcome.table_name);
  } else if (outcome.code === 'shop_closed') {
    renderShopClosed(container);
  } else if (outcome.code === 'table_busy') {
    renderTableBusy(container, outcome.message);
  } else {
    renderInvalidQr(container);
  }
}
