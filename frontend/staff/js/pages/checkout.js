/**
 * frontend/staff/js/pages/checkout.js — หน้าเช็คเอาท์: เช็คบิล -> เลือกโปร/ช่องทางชำระ (เงินสด หรือ โอน/PromptPay) -> ชำระเงิน -> ใบเสร็จ PDF/TXT
 * คัดลอกจาก ui/staff/checkout_page.py ทุกตัวอักษร
 */

import { apiGet, apiPost } from '../../../shared/js/api.js';
import { BaseDialog, confirmDialog } from '../../../shared/js/dialogs.js';
import { baht, money, weight_text } from '../../../shared/js/format.js';
import { createStatusBadge } from '../../../shared/js/status-badge.js';

const NO_PROMO = 'ไม่ใช้โปรโมชั่น';
const LABEL_CASH = 'เงินสด';
const LABEL_PROMPTPAY = 'โอน/PromptPay';

export class CheckoutPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.sessionId = null;
    this.promoId = null;
    this.method = 'cash';
    this.bill = null;
    this.promptpay = null;
    this.submitting = false;
    this._timer = null;

    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'เช็คเอาท์';
    const sub = document.createElement('div');
    sub.className = 'page-subtitle';
    sub.textContent = 'เลือกโต๊ะทางซ้าย เพื่อดูบิล ตรวจสอบยอดเงิน และรับชำระเงิน';
    left.appendChild(title);
    left.appendChild(sub);
    header.appendChild(left);
    this.container.appendChild(header);

    const split = document.createElement('div');
    split.className = 'split-layout split-checkout audit-block';

    // ซ้าย: รายการโต๊ะที่ใช้งาน/รอชำระ
    this.listCard = document.createElement('div');
    this.listCard.className = 'card';
    this.listCard.style.display = 'flex';
    this.listCard.style.flexDirection = 'column';
    this.listCard.style.gap = 'var(--space-2)';

    // ขวา: รายละเอียดบิลและตัวควบคุม
    this.rightCard = document.createElement('div');
    this.rightCard.className = 'card';
    this.rightCard.style.display = 'flex';
    this.rightCard.style.flexDirection = 'column';
    this.rightCard.style.gap = 'var(--space-3)';

    this.titleLabel = document.createElement('div');
    this.titleLabel.style.fontSize = 'var(--fs-title)';
    this.titleLabel.style.fontWeight = '700';
    this.titleLabel.textContent = 'ยังไม่ได้เลือกโต๊ะ';
    this.rightCard.appendChild(this.titleLabel);

    this.itemsArea = document.createElement('div');
    this.itemsArea.style.flex = '1 1 auto';
    this.itemsArea.style.display = 'flex';
    this.itemsArea.style.flexDirection = 'column';
    this.itemsArea.style.gap = 'var(--space-1)';
    this.rightCard.appendChild(this.itemsArea);

    this.totalsArea = document.createElement('div');
    this.totalsArea.style.display = 'flex';
    this.totalsArea.style.flexDirection = 'column';
    this.totalsArea.style.gap = 'var(--space-1)';
    this.rightCard.appendChild(this.totalsArea);

    this.controlsEl = document.createElement('div');
    this.controlsEl.className = 'hidden';
    this.controlsEl.style.display = 'flex';
    this.controlsEl.style.flexDirection = 'column';
    this.controlsEl.style.gap = 'var(--space-3)';

    const row1 = document.createElement('div');
    row1.style.display = 'flex';
    row1.style.alignItems = 'center';
    row1.style.justifyContent = 'space-between';
    row1.style.gap = 'var(--space-2)';
    row1.style.flexWrap = 'wrap';

    const promoBox = document.createElement('div');
    promoBox.style.display = 'flex';
    promoBox.style.alignItems = 'center';
    promoBox.style.gap = 'var(--space-2)';
    const promoLbl = document.createElement('span');
    promoLbl.textContent = 'โปรโมชั่น';
    this.promoSelect = document.createElement('select');
    this.promoSelect.className = 'field-select';
    this.promoSelect.style.width = '240px';
    this.promoSelect.addEventListener('change', () => {
      const val = this.promoSelect.value;
      this.promoId = val ? Number(val) : null;
      this.refresh();
    });
    promoBox.appendChild(promoLbl);
    promoBox.appendChild(this.promoSelect);

    const methodSeg = document.createElement('div');
    methodSeg.className = 'seg-group';
    this.btnCash = document.createElement('button');
    this.btnCash.type = 'button';
    this.btnCash.className = 'seg-btn is-active';
    this.btnCash.textContent = LABEL_CASH;
    this.btnCash.addEventListener('click', () => {
      this.method = 'cash';
      this.btnCash.classList.add('is-active');
      this.btnPromptPay.classList.remove('is-active');
      this._updateControls();
    });
    this.btnPromptPay = document.createElement('button');
    this.btnPromptPay.type = 'button';
    this.btnPromptPay.className = 'seg-btn';
    this.btnPromptPay.textContent = LABEL_PROMPTPAY;
    this.btnPromptPay.addEventListener('click', () => {
      this.method = 'transfer';
      this.btnPromptPay.classList.add('is-active');
      this.btnCash.classList.remove('is-active');
      this._updateControls();
    });
    methodSeg.appendChild(this.btnCash);
    methodSeg.appendChild(this.btnPromptPay);

    row1.appendChild(promoBox);
    row1.appendChild(methodSeg);
    this.controlsEl.appendChild(row1);

    // แถวเงินสด
    this.cashRow = document.createElement('div');
    this.cashRow.style.display = 'flex';
    this.cashRow.style.alignItems = 'center';
    this.cashRow.style.gap = 'var(--space-2)';
    this.cashRow.style.flexWrap = 'wrap';
    const cashLbl = document.createElement('span');
    cashLbl.style.fontWeight = '700';
    cashLbl.textContent = 'รับเงินสดมา (บาท)';
    this.cashInput = document.createElement('input');
    this.cashInput.type = 'text';
    this.cashInput.className = 'field-input num';
    this.cashInput.style.width = '150px';
    this.cashInput.style.textAlign = 'right';
    this.cashInput.placeholder = '0.00';
    this.cashInput.addEventListener('input', () => this._updateChange());
    this.changeLabel = document.createElement('span');
    this.changeLabel.style.fontWeight = '700';
    this.cashRow.appendChild(cashLbl);
    this.cashRow.appendChild(this.cashInput);
    this.cashRow.appendChild(this.changeLabel);
    this.controlsEl.appendChild(this.cashRow);

    // กรอบ QR PromptPay
    this.qrFrame = document.createElement('div');
    this.qrFrame.className = 'card hidden';
    this.qrFrame.style.backgroundColor = 'var(--color-row-alt)';
    this.qrFrame.style.display = 'flex';
    this.qrFrame.style.alignItems = 'center';
    this.qrFrame.style.gap = 'var(--space-3)';

    this.qrImgBox = document.createElement('div');
    this.qrImgBox.style.width = '150px';
    this.qrImgBox.style.height = '150px';
    this.qrImgBox.style.backgroundColor = '#ffffff';
    this.qrImgBox.style.borderRadius = 'var(--radius-md)';
    this.qrImgBox.style.display = 'flex';
    this.qrImgBox.style.alignItems = 'center';
    this.qrImgBox.style.justifyContent = 'center';
    this.qrImgBox.style.flexShrink = '0';

    const qrInfo = document.createElement('div');
    qrInfo.style.display = 'flex';
    qrInfo.style.flexDirection = 'column';
    qrInfo.style.gap = 'var(--space-1)';
    this.qrStatusBadge = createStatusBadge('สถานะ: รอตรวจสอบการโอน', 'var(--color-warning)');
    this.qrStatusBadge.style.alignSelf = 'flex-start';
    this.qrAmountLabel = document.createElement('div');
    this.qrAmountLabel.style.fontSize = 'var(--fs-xl)';
    this.qrAmountLabel.style.fontWeight = '700';
    this.qrAmountLabel.style.color = 'var(--color-primary)';
    this.qrAccountLabel = document.createElement('div');
    this.qrAccountLabel.style.fontSize = 'var(--fs-base)';
    this.qrAccountLabel.style.fontWeight = '700';
    this.qrAccountLabel.style.whiteSpace = 'pre-line';
    const qrHint = document.createElement('div');
    qrHint.style.fontSize = 'var(--fs-xs)';
    qrHint.style.color = 'var(--color-text-muted)';
    qrHint.textContent =
      'การแสดง QR ไม่ได้ยืนยันว่าเงินเข้าแล้ว กรุณาตรวจสลิป/ยอดเงินเข้าแอปธนาคารของร้านก่อนกดยืนยันชำระเงิน';

    qrInfo.appendChild(this.qrStatusBadge);
    qrInfo.appendChild(this.qrAmountLabel);
    qrInfo.appendChild(this.qrAccountLabel);
    qrInfo.appendChild(qrHint);
    this.qrFrame.appendChild(this.qrImgBox);
    this.qrFrame.appendChild(qrInfo);
    this.controlsEl.appendChild(this.qrFrame);

    this.actionBtn = document.createElement('button');
    this.actionBtn.type = 'button';
    this.actionBtn.className = 'btn btn-lg btn-success';
    this.actionBtn.style.alignSelf = 'flex-end';
    this.actionBtn.style.minWidth = '280px';
    this.actionBtn.addEventListener('click', () => this._onAction());
    this.controlsEl.appendChild(this.actionBtn);

    this.rightCard.appendChild(this.controlsEl);
    split.appendChild(this.listCard);
    split.appendChild(this.rightCard);
    this.container.appendChild(split);
  }

  activate(params = {}) {
    if (params.session_id !== undefined) {
      this.sessionId = Number(params.session_id);
    }
    this.refresh();
    this._timer = setInterval(() => {
      if (!document.hidden && !document.querySelector('.modal-backdrop')) {
        this.refresh();
      }
    }, 5000);
  }

  deactivate() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  reload() {
    this.refresh();
  }

  async refresh() {
    try {
      const data = await apiGet('/api/staff/checkout', {
        session_id: this.sessionId || '',
        promo_id: this.promoId || '',
      });
      this.sessionId = data.selected_session_id;
      this.promoId = data.selected_promo_id;
      this.bill = data.bill;
      this.promptpay = data.promptpay;

      this._renderTableList(data.tables || []);
      this._renderPromos(data.available_promos || []);
      this._renderBill();
    } catch (_err) {
      // ignore
    }
  }

  _renderTableList(tables) {
    this.listCard.textContent = '';
    if (tables.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'ไม่มีโต๊ะที่ต้องเช็คบิล';
      this.listCard.appendChild(empty);
      return;
    }

    for (const t of tables) {
      const selected = t.session_id === this.sessionId;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `btn ${selected ? 'btn-primary' : 'btn-ghost'}`;
      btn.style.justifyContent = 'flex-start';
      btn.style.width = '100%';
      btn.style.height = '48px';
      if (!selected) {
        btn.style.backgroundColor = 'var(--color-today-highlight)';
      }
      btn.textContent = `โต๊ะ ${t.table_no}   ·   ${t.status_th}`;
      btn.addEventListener('click', () => {
        this.sessionId = t.session_id;
        this.promoId = null;
        this.cashInput.value = '';
        this.refresh();
      });
      this.listCard.appendChild(btn);
    }
  }

  _renderPromos(promos) {
    this.promoSelect.textContent = '';
    const noneOpt = document.createElement('option');
    noneOpt.value = '';
    noneOpt.textContent = NO_PROMO;
    this.promoSelect.appendChild(noneOpt);
    for (const p of promos) {
      const opt = document.createElement('option');
      opt.value = String(p.id);
      opt.textContent = p.display_label;
      if (p.id === this.promoId) {
        opt.selected = true;
      }
      this.promoSelect.appendChild(opt);
    }
  }

  _renderBill() {
    this.itemsArea.textContent = '';
    this.totalsArea.textContent = '';

    if (!this.bill) {
      this.titleLabel.textContent = 'ยังไม่ได้เลือกโต๊ะ';
      this.controlsEl.classList.add('hidden');
      return;
    }

    const bill = this.bill;
    this.titleLabel.textContent = `โต๊ะ ${bill.table_no}  ·  ${bill.status_th}`;
    this.controlsEl.classList.remove('hidden');

    const addLine = (leftTxt, rightTxt, { bold = false, muted = false } = {}) => {
      const r = document.createElement('div');
      r.style.display = 'flex';
      r.style.justifyContent = 'space-between';
      r.style.fontSize = 'var(--fs-md)';
      if (bold) r.style.fontWeight = '700';
      if (muted) r.style.color = 'var(--color-text-muted)';
      const l = document.createElement('span');
      l.textContent = leftTxt;
      const rt = document.createElement('span');
      rt.className = 'money';
      rt.textContent = rightTxt;
      r.appendChild(l);
      r.appendChild(rt);
      this.itemsArea.appendChild(r);
    };

    if (bill.weigh_entries && bill.weigh_entries.length > 0) {
      addLine('รายการชั่งกิโล', '', { bold: true });
      for (const e of bill.weigh_entries) {
        addLine(`  ${e.name_snapshot}  ${weight_text(e.weight_grams)}`, money(e.amount));
      }
    }

    const orderLines = [];
    for (const o of bill.orders || []) {
      for (const it of o.items || []) {
        orderLines.push(it);
      }
    }
    if (orderLines.length > 0) {
      addLine('รายการสั่งอาหาร', '', { bold: true });
      for (const it of orderLines) {
        addLine(
          `  ${it.name_snapshot} × ${it.quantity}`,
          money(Number(it.unit_price) * Number(it.quantity))
        );
      }
    }

    if (
      (!bill.weigh_entries || bill.weigh_entries.length === 0) &&
      orderLines.length === 0
    ) {
      addLine('ยังไม่มีรายการ', '', { muted: true });
    }

    const sep = document.createElement('div');
    sep.style.height = '1px';
    sep.style.backgroundColor = 'var(--color-card-border)';
    this.totalsArea.appendChild(sep);

    const addTotalRow = (label, value, big = false) => {
      const r = document.createElement('div');
      r.style.display = 'flex';
      r.style.justifyContent = 'space-between';
      r.style.alignItems = 'baseline';
      r.style.fontSize = big ? 'var(--fs-2xl)' : 'var(--fs-base)';
      if (big) r.style.fontWeight = '700';
      const l = document.createElement('span');
      l.textContent = label;
      const v = document.createElement('span');
      v.className = 'money';
      if (big) {
        v.style.fontSize = 'var(--fs-page-title)';
        v.style.color = 'var(--color-primary)';
      }
      v.textContent = value;
      r.appendChild(l);
      r.appendChild(v);
      this.totalsArea.appendChild(r);
    };

    addTotalRow('รวมเป็นเงินก่อนคิดภาษีและส่วนลด', money(bill.subtotal));
    if (bill.discount) {
      addTotalRow(
        `ส่วนลด ${bill.promo_name || ''}`.trim(),
        `-${money(bill.discount)}`
      );
    }
    if (bill.service_charge) {
      addTotalRow(
        `ค่าบริการ ${Number(bill.service_charge_percent)}%`,
        money(bill.service_charge)
      );
    }
    if (bill.vat) {
      addTotalRow(
        `ภาษีมูลค่าเพิ่ม ${Number(bill.vat_percent)}%`,
        money(bill.vat)
      );
    }
    addTotalRow('ยอดที่ต้องชำระ', baht(bill.total), true);

    this._updateControls();
  }

  _updateControls() {
    if (!this.bill) return;
    const awaiting = this.bill.status === 'awaiting_payment';
    const isCash = this.method === 'cash';
    const isPromptPay = this.method === 'transfer';

    this.promoSelect.disabled = !awaiting;
    this.btnCash.disabled = !awaiting;
    this.btnPromptPay.disabled = !awaiting;
    this.cashInput.disabled = !(awaiting && isCash);

    if (isCash) {
      this.cashRow.classList.remove('hidden');
      this.qrFrame.classList.add('hidden');
    } else {
      this.cashRow.classList.add('hidden');
      if (awaiting) {
        this.qrFrame.classList.remove('hidden');
        this._renderPromptPayBox();
      } else {
        this.qrFrame.classList.add('hidden');
      }
    }

    if (awaiting) {
      this.actionBtn.textContent = isPromptPay
        ? 'ยืนยันรับเงินโอนแล้ว (ปิดโต๊ะ)'
        : 'ชำระเงินแล้ว (ปิดโต๊ะ)';
      this.actionBtn.className = 'btn btn-lg btn-success';
    } else {
      this.actionBtn.textContent = 'เริ่มเช็คบิล';
      this.actionBtn.className = 'btn btn-lg btn-info';
      this.actionBtn.disabled = false;
    }

    this._updateChange();
  }

  _renderPromptPayBox() {
    this.qrImgBox.textContent = '';
    const pp = this.promptpay;
    if (pp && pp.valid && pp.data_url) {
      const img = document.createElement('img');
      img.src = pp.data_url;
      img.alt = 'PromptPay QR';
      img.style.width = '142px';
      img.style.height = '142px';
      this.qrImgBox.appendChild(img);
      this.qrStatusBadge.textContent = `สถานะ: ${pp.status_th}`;
      this.qrStatusBadge.style.backgroundColor = 'var(--color-warning)';
      this.qrAmountLabel.textContent = `สแกนชำระ: ${baht(pp.amount)}`;
      this.qrAccountLabel.textContent = `พร้อมเพย์: ${pp.promptpay_id}\nชื่อบัญชี: ${pp.promptpay_name}`;
    } else {
      this.qrImgBox.textContent = 'สร้าง QR ไม่ได้';
      this.qrStatusBadge.textContent = 'ข้อมูล PromptPay ไม่ถูกต้อง';
      this.qrStatusBadge.style.backgroundColor = 'var(--color-danger)';
      this.qrAmountLabel.textContent = (pp && pp.error) || '';
      this.qrAccountLabel.textContent = 'กรุณาตรวจสอบหมายเลข PromptPay ที่หน้าตั้งค่า';
    }
  }

  _parseCashStatus() {
    if (!this.bill) return { ok: false, rec: null, chg: null, msg: '' };
    const totalCents = Math.round(Number(this.bill.total) * 100);
    const totalVal = totalCents / 100;
    const raw = (this.cashInput.value || '').trim().replace(/,/g, '');
    if (!raw) {
      return {
        ok: false,
        rec: null,
        chg: null,
        msg: `กรุณากรอกเงินสดที่รับ (อย่างน้อย ${baht(totalVal)})`,
      };
    }
    const num = Number(raw);
    if (!Number.isFinite(num) || Number.isNaN(num)) {
      return {
        ok: false,
        rec: null,
        chg: null,
        msg: 'กรุณากรอกจำนวนเงินเป็นตัวเลขที่ถูกต้อง',
      };
    }
    if (num < 0) {
      return {
        ok: false,
        rec: null,
        chg: null,
        msg: 'ห้ามกรอกจำนวนเงินติดลบ',
      };
    }
    const recCents = Math.round(num * 100);
    const recVal = recCents / 100;
    if (recCents < totalCents) {
      const diffVal = (totalCents - recCents) / 100;
      return {
        ok: false,
        rec: recVal,
        chg: null,
        msg: `เงินสดรับไม่พอ (ยังขาด ${baht(diffVal)})`,
      };
    }
    const chgVal = (recCents - totalCents) / 100;
    return {
      ok: true,
      rec: recVal,
      chg: chgVal,
      msg: `เงินทอน ${baht(chgVal)}`,
    };
  }

  _updateChange() {
    if (!this.bill) {
      this.changeLabel.textContent = '';
      return;
    }
    const awaiting = this.bill.status === 'awaiting_payment';
    if (!awaiting) {
      this.changeLabel.textContent = '';
      this.actionBtn.disabled = false;
      return;
    }
    if (this.method !== 'cash') {
      this.changeLabel.textContent = '';
      this.actionBtn.disabled = !(this.promptpay && this.promptpay.valid);
      return;
    }
    const st = this._parseCashStatus();
    this.changeLabel.textContent = st.msg;
    this.changeLabel.style.color = st.ok
      ? 'var(--color-info)'
      : 'var(--color-danger)';
    this.actionBtn.disabled = !st.ok;
  }

  async _onAction() {
    if (this.submitting || !this.bill || !this.sessionId) return;
    if (this.bill.status === 'open') {
      await this.startCheckout();
    } else {
      await this.pay();
    }
  }

  async startCheckout() {
    const tNo = this.bill.table_no;
    const ok = await confirmDialog(
      `เริ่มเช็คบิลโต๊ะ ${tNo} ใช่หรือไม่?\nหลังเช็คบิลแล้วโต๊ะนี้จะสั่ง/ชั่งเพิ่มไม่ได้ (ย้อนกลับไม่ได้)`,
      {
        title: 'เริ่มเช็คบิล',
        confirmText: 'เริ่มเช็คบิล',
      }
    );
    if (!ok) return;
    try {
      const res = await apiPost(`/api/staff/checkout/${this.sessionId}/start`, {});
      this.app.toast(res.message || `เช็คบิลโต๊ะ ${tNo} แล้ว`, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async pay() {
    if (this.submitting || !this.bill || !this.sessionId) return;
    let amountReceived;
    let summaryText;

    if (this.method === 'cash') {
      const st = this._parseCashStatus();
      if (!st.ok || st.rec === null || st.chg === null) {
        this.app.toast(st.msg || 'กรุณาตรวจสอบจำนวนเงินสดที่รับ', 'error');
        return;
      }
      amountReceived = st.rec;
      summaryText =
        `สรุปการรับชำระเงิน โต๊ะ ${this.bill.table_no}\n` +
        `• ยอดที่ต้องชำระ: ${baht(this.bill.total)}\n` +
        `• ช่องทางการชำระ: เงินสด\n` +
        `• รับเงินมา: ${baht(st.rec)}\n` +
        `• เงินทอน: ${baht(st.chg)}\n\n` +
        'ยืนยันการบันทึกบิลและปิดโต๊ะใช่หรือไม่?';
    } else {
      if (!this.promptpay || !this.promptpay.valid) {
        this.app.toast('ไม่สามารถยืนยันได้เนื่องจากข้อมูล PromptPay ไม่ถูกต้อง', 'error');
        return;
      }
      amountReceived = Number(this.bill.total);
      summaryText =
        `สรุปการรับชำระเงิน โต๊ะ ${this.bill.table_no}\n` +
        `• ยอดที่ต้องชำระ: ${baht(this.bill.total)}\n` +
        `• ช่องทางการชำระ: โอน/PromptPay\n` +
        '(กรุณาตรวจสอบว่ามีเงินโอนเข้าบัญชีร้านจริงแล้วก่อนกดยืนยัน)\n\n' +
        'ยืนยันว่าตรวจสอบยอดเงินเรียบร้อยและต้องการปิดโต๊ะใช่หรือไม่?';
    }

    let force = false;
    if (this.bill.unserved_orders > 0) {
      const forceOk = await confirmDialog(
        `ยังมีออเดอร์ที่ยังไม่เสิร์ฟ ${this.bill.unserved_orders} รายการ\nปิดบิลต่อเลย (ระบบจะตั้งเป็นเสิร์ฟแล้ว) ใช่หรือไม่?`,
        {
          title: 'มีออเดอร์ค้าง',
          confirmText: 'ปิดบิลต่อ',
          danger: true,
        }
      );
      if (!forceOk) return;
      force = true;
    }

    const confirmPay = await confirmDialog(summaryText, {
      title: 'ยืนยันชำระเงิน',
      confirmText: 'ยืนยันชำระเงิน',
    });
    if (!confirmPay) return;

    this.submitting = true;
    try {
      const res = await apiPost(`/api/staff/checkout/${this.sessionId}/pay`, {
        payment_method: this.method,
        promo_id: this.promoId,
        amount_received: amountReceived,
        force,
      });
      const paidSessionId = this.sessionId;
      this.sessionId = null;
      this.promoId = null;
      this.cashInput.value = '';
      await this.refresh();
      if (this.app.alertCenter) {
        this.app.alertCenter.refreshView(false);
      }
      await openReceiptDialog(paidSessionId, res.bill, res.receipt_info);
    } catch (err) {
      this.app.toast(err.message, 'error');
      await this.refresh();
    } finally {
      this.submitting = false;
    }
  }
}

async function openReceiptDialog(sessionId, bill, info) {
  const dlg = new BaseDialog('ชำระเงินเรียบร้อย — ใบเสร็จรับเงิน', { width: 560 });
  const shop = info.shop || {};

  const topNotice = document.createElement('div');
  topNotice.style.fontSize = 'var(--fs-xl)';
  topNotice.style.fontWeight = '700';
  topNotice.style.color = 'var(--color-success)';
  topNotice.textContent = `โต๊ะ ${bill.table_no} ชำระเงินเรียบร้อยแล้ว (${info.method_th})`;
  dlg.body.appendChild(topNotice);

  const paper = document.createElement('div');
  paper.className = 'receipt-paper';

  const addCenter = (txt, sizePx = 13, bold = false) => {
    const el = document.createElement('div');
    el.className = 'receipt-center';
    el.style.fontSize = `${sizePx}px`;
    if (bold) el.style.fontWeight = '700';
    el.textContent = txt;
    paper.appendChild(el);
  };

  const addDivider = () => {
    const d = document.createElement('div');
    d.className = 'receipt-divider';
    paper.appendChild(d);
  };

  const addMeta = (lbl, val) => {
    const r = document.createElement('div');
    r.className = 'receipt-meta-row';
    const l = document.createElement('span');
    l.style.fontWeight = '700';
    l.textContent = lbl;
    const v = document.createElement('span');
    v.textContent = val;
    r.appendChild(l);
    r.appendChild(v);
    paper.appendChild(r);
  };

  const addSumRow = (lbl, val, { bold = false, highlight = false } = {}) => {
    const r = document.createElement('div');
    r.className = 'receipt-sum-row';
    if (bold || highlight) r.style.fontWeight = '700';
    if (highlight) {
      r.style.color = 'var(--color-primary)';
      r.style.fontSize = 'var(--fs-md)';
    }
    const l = document.createElement('span');
    l.textContent = lbl;
    const v = document.createElement('span');
    v.className = 'receipt-sum-val';
    v.textContent = val;
    r.appendChild(l);
    r.appendChild(v);
    paper.appendChild(r);
  };

  addCenter(shop.shop_name || 'ร้านหมูกระทะต้นมะค่า', 16, true);
  if (shop.shop_tax_id_enabled && shop.shop_tax_id) {
    addCenter(`เลขผู้เสียภาษี ${shop.shop_tax_id}`, 13, false);
  }
  addCenter('ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน', 13, true);
  if (shop.address_line1) addCenter(shop.address_line1, 12, false);
  if (shop.address_line2) addCenter(shop.address_line2, 12, false);
  if (shop.phone_line) addCenter(shop.phone_line, 12, false);

  addDivider();
  addMeta('พนักงานขาย', info.cashier);
  addMeta('วันที่', info.date_str);
  addMeta('เวลา', info.time_str);
  addDivider();

  const headRow = document.createElement('div');
  headRow.className = 'receipt-line-row';
  headRow.style.fontWeight = '700';
  const h1 = document.createElement('span');
  h1.style.textAlign = 'center';
  h1.textContent = 'จำนวน';
  const h2 = document.createElement('span');
  h2.textContent = 'รายการ';
  const h3 = document.createElement('span');
  h3.style.textAlign = 'right';
  h3.textContent = 'จำนวนเงิน';
  headRow.appendChild(h1);
  headRow.appendChild(h2);
  headRow.appendChild(h3);
  paper.appendChild(headRow);
  addDivider();

  for (const ln of info.lines || []) {
    const r = document.createElement('div');
    r.className = 'receipt-line-row';
    const c1 = document.createElement('span');
    c1.style.textAlign = 'center';
    c1.textContent = ln.qty_str;
    const c2 = document.createElement('span');
    c2.textContent = ln.name;
    const c3 = document.createElement('span');
    c3.style.textAlign = 'right';
    c3.className = 'money';
    c3.textContent = ln.amount_str;
    r.appendChild(c1);
    r.appendChild(c2);
    r.appendChild(c3);
    paper.appendChild(r);
  }

  addDivider();
  const qtyTotal = document.createElement('div');
  qtyTotal.style.fontSize = 'var(--fs-sm)';
  qtyTotal.style.fontWeight = '700';
  qtyTotal.textContent = `จำนวนรวม   ${info.total_qty_count}`;
  paper.appendChild(qtyTotal);

  const promoSuffix = info.promo_name ? ` (${info.promo_name})` : '';
  addSumRow('รวมเป็นเงิน', money(info.subtotal));
  addSumRow(`ส่วนลด${promoSuffix}`, money(info.discount));
  addSumRow('จำนวนเงินหลังหักส่วนลด', money(info.after_discount));
  if (info.service_charge > 0) {
    const pct = info.service_charge_percent;
    const scLbl = pct ? `ค่าบริการ (${Number(pct)}%)` : 'ค่าบริการ';
    addSumRow(scLbl, money(info.service_charge));
  }
  addSumRow('ราคาไม่รวมภาษีมูลค่าเพิ่ม', money(info.pre_vat));
  addSumRow('ภาษีมูลค่าเพิ่ม 7%', money(info.vat));
  addSumRow('รวมทั้งสิ้น', baht(info.total), { bold: true, highlight: true });

  addDivider();
  const payRow = document.createElement('div');
  payRow.style.fontSize = 'var(--fs-sm)';
  payRow.style.fontWeight = '700';
  payRow.textContent = `ช่องทางการชำระ :   ${info.method_th}`;
  paper.appendChild(payRow);

  if (info.method === 'cash') {
    const recRow = document.createElement('div');
    recRow.style.display = 'flex';
    recRow.style.justifyContent = 'space-between';
    recRow.style.fontSize = 'var(--fs-sm)';
    const rl = document.createElement('span');
    rl.textContent = 'รับเงินมา';
    const rv = document.createElement('span');
    rv.textContent = money(info.received);
    recRow.appendChild(rl);
    recRow.appendChild(rv);
    paper.appendChild(recRow);

    const chgRow = document.createElement('div');
    chgRow.style.display = 'flex';
    chgRow.style.justifyContent = 'space-between';
    chgRow.style.fontSize = 'var(--fs-sm)';
    chgRow.style.fontWeight = '700';
    const cl = document.createElement('span');
    cl.textContent = 'เงินทอน';
    const cv = document.createElement('span');
    cv.textContent = money(info.change);
    chgRow.appendChild(cl);
    chgRow.appendChild(cv);
    paper.appendChild(chgRow);
  }

  addDivider();
  addCenter(shop.shop_name || 'ร้านหมูกระทะต้นมะค่า', 14, true);
  addCenter('ขอบคุณที่ใช้บริการ', 13, false);
  dlg.body.appendChild(paper);

  const savedLbl = document.createElement('div');
  savedLbl.style.fontSize = 'var(--fs-sm)';
  savedLbl.style.color = 'var(--color-text-muted)';
  savedLbl.textContent = 'เลือกส่งออกใบเสร็จเป็นไฟล์ PDF หรือ TXT ด้านล่าง';
  dlg.body.appendChild(savedLbl);

  const exportFile = async (fmt) => {
    try {
      const res = await apiPost(`/api/staff/checkout/${sessionId}/export/${fmt}`, {});
      savedLbl.textContent = res.message;
      savedLbl.style.color = 'var(--color-success)';
      if (res.download_url) {
        const a = document.createElement('a');
        a.href = res.download_url;
        a.download = res.filename || `receipt.${fmt}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }
    } catch (err) {
      savedLbl.textContent = err.message;
      savedLbl.style.color = 'var(--color-danger)';
    }
  };

  dlg.footer.textContent = '';
  const leftBtns = document.createElement('div');
  leftBtns.style.display = 'flex';
  leftBtns.style.gap = 'var(--space-2)';
  leftBtns.style.marginRight = 'auto';

  const pdfBtn = document.createElement('button');
  pdfBtn.type = 'button';
  pdfBtn.className = 'btn btn-sm btn-primary';
  pdfBtn.textContent = 'บันทึก PDF (.pdf)';
  pdfBtn.addEventListener('click', () => exportFile('pdf'));

  const txtBtn = document.createElement('button');
  txtBtn.type = 'button';
  txtBtn.className = 'btn btn-sm btn-ghost';
  txtBtn.textContent = 'บันทึก TXT (.txt)';
  txtBtn.addEventListener('click', () => exportFile('txt'));

  const printBtn = document.createElement('button');
  printBtn.type = 'button';
  printBtn.className = 'btn btn-sm btn-info';
  printBtn.textContent = 'พิมพ์';
  printBtn.addEventListener('click', () => window.print());

  leftBtns.appendChild(pdfBtn);
  leftBtns.appendChild(txtBtn);
  leftBtns.appendChild(printBtn);
  dlg.footer.appendChild(leftBtns);

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'btn btn-primary';
  closeBtn.textContent = 'ปิด';
  closeBtn.addEventListener('click', () => dlg.close(true));
  dlg.footer.appendChild(closeBtn);

  await dlg.show();
}
