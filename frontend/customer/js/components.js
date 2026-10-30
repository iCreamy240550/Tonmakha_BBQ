/**
 * frontend/customer/js/components.js — ชิ้นส่วน UI ที่ใช้ร่วมกันทุกหน้าของเว็บลูกค้า
 * คัดลอกจาก web/components.py ทุกตัวอักษร
 */

import { baht, fmt_datetime, money, weight_text } from '../../shared/js/format.js';
import {
  CUSTOMER_STATUS_COLORS,
  CUSTOMER_STATUS_TH,
  createStatusBadge,
} from '../../shared/js/status-badge.js';

export const APP_NAME_SHORT = 'ต้นมะค่า';
export const LOGO_URL = '/logo.png';

const ICON_GLYPHS = {
  qr_code_scanner: '📷',
  qr_code_2: '🔳',
  check_circle: '✓',
  hourglass_top: '⏳',
  restaurant_menu: '🍽',
  restaurant: '🍲',
  receipt: '🧾',
  receipt_long: '🧾',
  storefront: '🏠',
  event_seat: '🪑',
  swap_horiz: '⇄',
  cancel: '✕',
  notifications_none: '🔔',
  block: '⛔',
  campaign: '📢',
  info: 'ℹ',
};

const COLOR_MAP = {
  primary: 'var(--color-primary)',
  positive: 'var(--color-success)',
  negative: 'var(--color-danger)',
  warning: 'var(--color-warning)',
  info: 'var(--color-info)',
  grey: 'var(--color-neutral)',
};

export function createCustomerHeader(tableName, status = null) {
  const card = document.createElement('header');
  card.className = 'cust-header-card audit-block';

  const brand = document.createElement('div');
  brand.className = 'cust-header-brand';

  const img = document.createElement('img');
  img.src = LOGO_URL;
  img.alt = APP_NAME_SHORT;
  img.className = 'cust-logo';
  img.addEventListener('error', () => {
    img.style.display = 'none';
  });
  brand.appendChild(img);

  const titles = document.createElement('div');
  titles.className = 'cust-header-titles';

  const shopLbl = document.createElement('div');
  shopLbl.className = 'cust-shop-name';
  shopLbl.textContent = APP_NAME_SHORT;
  titles.appendChild(shopLbl);

  const tableLbl = document.createElement('div');
  tableLbl.className = 'cust-table-name';
  tableLbl.textContent = tableName || APP_NAME_SHORT;
  titles.appendChild(tableLbl);

  brand.appendChild(titles);
  card.appendChild(brand);

  if (status) {
    const label = CUSTOMER_STATUS_TH[status] || status;
    const color = CUSTOMER_STATUS_COLORS[status] || '#868e96';
    const badge = createStatusBadge(label, color);
    card.appendChild(badge);
  }

  return card;
}

export function createMessageCard({
  icon = 'info',
  title = '',
  text = null,
  color = 'grey',
  spinner = false,
} = {}) {
  const card = document.createElement('section');
  card.className = 'cust-msg-card audit-block';

  if (spinner) {
    const spin = document.createElement('div');
    spin.className = 'cust-spinner';
    spin.style.borderTopColor = COLOR_MAP[color] || COLOR_MAP.primary;
    card.appendChild(spin);
  } else {
    const iconBox = document.createElement('div');
    iconBox.className = 'cust-msg-icon';
    iconBox.style.color = COLOR_MAP[color] || COLOR_MAP.grey;
    iconBox.style.backgroundColor = 'var(--color-row-alt)';
    iconBox.textContent = ICON_GLYPHS[icon] || '•';
    card.appendChild(iconBox);
  }

  const titleEl = document.createElement('div');
  titleEl.className = 'cust-msg-title';
  titleEl.textContent = title;
  card.appendChild(titleEl);

  if (text) {
    const textEl = document.createElement('div');
    textEl.className = 'cust-msg-text';
    textEl.textContent = text;
    card.appendChild(textEl);
  }

  return card;
}

export function createSummaryRow(label, value, { bold = false, color = null } = {}) {
  const row = document.createElement('div');
  row.className = 'cust-summary-row';
  if (bold) row.classList.add('is-bold');
  if (color === 'primary') row.classList.add('color-primary');
  if (color === 'positive') row.classList.add('color-positive');

  const lbl = document.createElement('span');
  lbl.textContent = label;

  const val = document.createElement('span');
  val.className = 'summary-val';
  val.textContent = value;

  row.appendChild(lbl);
  row.appendChild(val);
  return row;
}

export function createSeparator() {
  const sep = document.createElement('div');
  sep.className = 'cust-separator';
  return sep;
}

export function appendLinesBlock(container, weighEntries = [], orders = []) {
  for (const w of weighEntries || []) {
    container.appendChild(
      createSummaryRow(
        `${w.name_snapshot}  ${weight_text(w.weight_grams)}`,
        money(w.amount)
      )
    );
  }
  for (const o of orders || []) {
    for (const it of o.items || []) {
      container.appendChild(
        createSummaryRow(
          `${it.name_snapshot}  x${it.quantity}`,
          money(it.line_total)
        )
      );
    }
  }
}

export function createBillCard(bill, { paid = false } = {}) {
  const card = document.createElement('section');
  card.className = 'cust-section-card audit-block';

  const heading = document.createElement('div');
  heading.className = 'cust-section-title';
  heading.textContent = paid ? 'ใบเสร็จรับเงิน' : 'รายการที่ต้องชำระ';
  card.appendChild(heading);

  appendLinesBlock(card, bill.weigh_entries || [], bill.orders || []);
  card.appendChild(createSeparator());

  card.appendChild(
    createSummaryRow('รวมเป็นเงินก่อนคิดภาษีและส่วนลด', money(bill.subtotal))
  );

  if (bill.discount) {
    const promo = bill.promo_name ? ` (${bill.promo_name})` : '';
    card.appendChild(
      createSummaryRow(`ส่วนลด${promo}`, `-${money(bill.discount)}`, {
        color: 'positive',
      })
    );
  }

  if (bill.service_charge) {
    const pct = bill.service_charge_percent;
    const scLabel = pct ? `ค่าบริการ ${Number(pct)}%` : 'ค่าบริการ';
    card.appendChild(createSummaryRow(scLabel, money(bill.service_charge)));
  }

  if (bill.vat) {
    const pct = bill.vat_percent;
    const vatLabel = pct ? `ภาษีมูลค่าเพิ่ม ${Number(pct)}%` : 'ภาษีมูลค่าเพิ่ม';
    card.appendChild(createSummaryRow(vatLabel, money(bill.vat)));
  }

  card.appendChild(createSeparator());
  card.appendChild(
    createSummaryRow('ยอดชำระสุทธิ', baht(bill.total), {
      bold: true,
      color: 'primary',
    })
  );

  if (paid) {
    if (bill.payment_method_th) {
      card.appendChild(createSummaryRow('ชำระโดย', bill.payment_method_th));
    }
    if (bill.payment_method === 'cash') {
      if (bill.amount_received !== null && bill.amount_received !== undefined) {
        card.appendChild(createSummaryRow('รับเงินมา', baht(bill.amount_received)));
      }
      card.appendChild(createSummaryRow('เงินทอน', baht(bill.change_amount || 0.0)));
    }
    if (bill.paid_at) {
      card.appendChild(createSummaryRow('เวลาชำระ', fmt_datetime(bill.paid_at, '')));
    }
  }

  return card;
}
