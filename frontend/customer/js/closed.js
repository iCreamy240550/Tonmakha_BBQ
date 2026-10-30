/**
 * frontend/customer/js/closed.js — หน้าทางตัน: ร้านปิด / QR ผิด / โต๊ะไม่ว่าง / ชำระแล้ว / ถูกยกเลิก / ไม่พบรอบ
 * คัดลอกจาก web/pages/closed.py ทุกตัวอักษร
 */

import { createBillCard, createMessageCard } from './components.js';

export function renderShopClosed(container) {
  container.appendChild(
    createMessageCard({
      icon: 'storefront',
      title: 'ร้านปิดอยู่',
      text: 'ขณะนี้ร้านยังไม่เปิดให้บริการ กรุณาลองใหม่อีกครั้งเมื่อร้านเปิด',
      color: 'grey',
    })
  );
}

export function renderInvalidQr(container) {
  container.appendChild(
    createMessageCard({
      icon: 'qr_code_2',
      title: 'QR ไม่ถูกต้อง',
      text: 'กรุณาสแกน QR ที่โต๊ะอีกครั้ง หรือแจ้งพนักงาน',
      color: 'negative',
    })
  );
}

export function renderTableBusy(container, message = null) {
  container.appendChild(
    createMessageCard({
      icon: 'event_seat',
      title: 'โต๊ะนี้มีลูกค้าใช้งานอยู่แล้ว',
      text: message || 'หากเป็นโต๊ะของคุณ กรุณาแจ้งพนักงาน',
      color: 'warning',
    })
  );
}

export function renderOtherTable(container, tableName) {
  const card = createMessageCard({
    icon: 'swap_horiz',
    title: `คุณกำลังใช้งาน ${tableName} อยู่`,
    text: 'หากต้องการเปลี่ยนโต๊ะ กรุณาแจ้งพนักงาน',
    color: 'warning',
  });
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn btn-primary';
  btn.style.minHeight = '44px';
  btn.textContent = 'กลับไปที่โต๊ะของฉัน';
  btn.addEventListener('click', () => {
    window.location.href = '/s';
  });
  card.appendChild(btn);
  container.appendChild(card);
}

export function renderNoSession(container) {
  container.appendChild(
    createMessageCard({
      icon: 'qr_code_scanner',
      title: 'กรุณาสแกน QR ที่โต๊ะ',
      text: 'สแกน QR บนโต๊ะของคุณด้วยกล้องมือถือเพื่อเริ่มสั่งอาหาร',
      color: 'primary',
    })
  );
}

export function renderPaid(container, snap) {
  container.appendChild(
    createMessageCard({
      icon: 'check_circle',
      title: 'ชำระเงินเรียบร้อย',
      text: 'ขอบคุณที่มาใช้บริการค่ะ',
      color: 'positive',
    })
  );
  if (snap && snap.bill) {
    container.appendChild(createBillCard(snap.bill, { paid: true }));
  }
  const hint = document.createElement('div');
  hint.className = 'cust-center-hint audit-block';
  hint.textContent = 'หากต้องการสั่งเพิ่ม กรุณาสแกน QR ที่โต๊ะใหม่อีกครั้ง';
  container.appendChild(hint);
}

export function renderCancelled(container, snap) {
  const byCustomer =
    snap && snap.session && snap.session.cancelled_by === 'customer';
  container.appendChild(
    createMessageCard({
      icon: 'cancel',
      title: byCustomer ? 'ยกเลิกคำขอแล้ว' : 'คำขอถูกยกเลิก',
      text: 'หากต้องการใช้บริการ กรุณาสแกน QR ที่โต๊ะอีกครั้ง',
      color: 'negative',
    })
  );
}
