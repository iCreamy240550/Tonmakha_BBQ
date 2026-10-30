/**
 * frontend/shared/js/status-badge.js — ป้ายสีสถานะโต๊ะและออเดอร์สำหรับพนักงานและลูกค้า
 * คัดลอกจาก config.py, ui/theme.py, ui/widgets/order_card.py, และ web/components.py
 */

export const SESSION_STATUS_TH = {
  free: 'ว่าง',
  pending: 'รอยืนยัน',
  open: 'กำลังนั่ง',
  awaiting_payment: 'รอชำระเงิน',
  closed: 'ปิดบิลแล้ว',
  cancelled: 'ยกเลิก',
};

export const STATUS_COLORS = {
  free: '#868e96',
  pending: '#f08c00',
  open: '#2f9e44',
  awaiting_payment: '#1c7ed6',
  closed: '#495057',
  cancelled: '#e03131',
};

export const ORDER_STATUS_TH = {
  new: 'ใหม่',
  preparing: 'กำลังทำ',
  served: 'เสิร์ฟแล้ว',
  cancelled: 'ยกเลิก',
};

export const ORDER_STATUS_COLORS = {
  new: '#e03131',
  preparing: '#f08c00',
  served: '#2f9e44',
  cancelled: '#868e96',
};

export const CUSTOMER_STATUS_TH = {
  pending: 'รอพนักงานยืนยัน',
  open: 'สั่งอาหารได้',
  awaiting_payment: 'รอชำระเงิน',
  closed: 'ชำระแล้ว',
  cancelled: 'ยกเลิกแล้ว',
};

export const CUSTOMER_STATUS_COLORS = {
  pending: '#f08c00',
  open: '#2f9e44',
  awaiting_payment: '#1c7ed6',
  closed: '#868e96',
  cancelled: '#e03131',
};

export const ORDER_STATUS_CUSTOMER_TH = {
  new: 'รับออเดอร์แล้ว',
  preparing: 'กำลังทำ',
  served: 'เสิร์ฟแล้ว',
  cancelled: 'ยกเลิก',
};

export const ORDER_STATUS_CUSTOMER_COLORS = {
  new: '#1c7ed6',
  preparing: '#f08c00',
  served: '#2f9e44',
  cancelled: '#868e96',
};

export function statusColor(status) {
  return STATUS_COLORS[status] || '#868e96';
}

export function statusText(status) {
  return SESSION_STATUS_TH[status] || status;
}

export function createStatusBadge(text, color = '#868e96') {
  const span = document.createElement('span');
  span.className = 'status-badge';
  span.textContent = text;
  if (color) {
    span.style.backgroundColor = color;
  }
  return span;
}
