/**
 * frontend/customer/js/bill.js — หน้าบิลระหว่างรอชำระ (สถานะ awaiting_payment) ลูกค้าดูอย่างเดียว
 * คัดลอกจาก web/pages/bill.py
 */

import { createBillCard, createMessageCard } from './components.js';

export function renderBill(container, snap) {
  container.appendChild(
    createMessageCard({
      icon: 'receipt_long',
      title: 'พนักงานกำลังเช็คบิลให้ที่โต๊ะ',
      text: 'กรุณาชำระเงินกับพนักงาน',
      color: 'info',
    })
  );

  const bill = snap ? snap.bill : null;
  if (!bill) {
    const empty = document.createElement('div');
    empty.className = 'cust-center-hint audit-block';
    empty.textContent = 'ยังโหลดบิลไม่ได้ กรุณาสอบถามพนักงาน';
    container.appendChild(empty);
    return;
  }

  container.appendChild(createBillCard(bill, { paid: false }));

  const hint = document.createElement('div');
  hint.className = 'cust-center-hint audit-block';
  hint.textContent = 'ยอดสุทธิอาจเปลี่ยนตามโปรโมชั่นที่พนักงานใช้ตอนชำระเงิน';
  container.appendChild(hint);
}
