/**
 * frontend/staff/js/pages/orders.js — หน้าออเดอร์: ดู/เปลี่ยนสถานะออเดอร์ตามลำดับ (เริ่มทำ -> เสิร์ฟแล้ว) และสั่งให้ลูกค้า
 * คัดลอกจาก ui/staff/orders_page.py และ ui/widgets/order_card.py
 */

import { apiGet, apiPost } from '../../../shared/js/api.js';
import { BaseDialog } from '../../../shared/js/dialogs.js';
import { baht, money } from '../../../shared/js/format.js';
import {
  ORDER_STATUS_COLORS,
  ORDER_STATUS_TH,
  createStatusBadge,
} from '../../../shared/js/status-badge.js';

export class OrdersPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.sessionId = null;
    this.onlyActive = true;
    this._sig = null;
    this._timer = null;
    this._updatingIds = new Set();
    this._usableTables = [];
    this._orderableMenu = [];

    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';

    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'ออเดอร์';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);

    const right = document.createElement('div');
    right.className = 'page-header-right';

    this.tableSelect = document.createElement('select');
    this.tableSelect.className = 'field-select';
    this.tableSelect.style.width = '150px';
    this.tableSelect.style.height = '38px';
    this.tableSelect.addEventListener('change', () => {
      const v = this.tableSelect.value;
      this.sessionId = v ? Number(v) : null;
      this._sig = null;
      this.refresh();
    });
    right.appendChild(this.tableSelect);

    const seg = document.createElement('div');
    seg.className = 'seg-group';
    this.btnActive = document.createElement('button');
    this.btnActive.type = 'button';
    this.btnActive.className = 'seg-btn is-active';
    this.btnActive.textContent = 'ยังไม่เสิร์ฟ';
    this.btnActive.addEventListener('click', () => {
      this.onlyActive = true;
      this.btnActive.classList.add('is-active');
      this.btnAll.classList.remove('is-active');
      this._sig = null;
      this.refresh();
    });
    this.btnAll = document.createElement('button');
    this.btnAll.type = 'button';
    this.btnAll.className = 'seg-btn';
    this.btnAll.textContent = 'ทั้งหมด';
    this.btnAll.addEventListener('click', () => {
      this.onlyActive = false;
      this.btnAll.classList.add('is-active');
      this.btnActive.classList.remove('is-active');
      this._sig = null;
      this.refresh();
    });
    seg.appendChild(this.btnActive);
    seg.appendChild(this.btnAll);
    right.appendChild(seg);

    const createBtn = document.createElement('button');
    createBtn.type = 'button';
    createBtn.className = 'btn btn-primary';
    createBtn.textContent = '+ สั่งให้ลูกค้า';
    createBtn.addEventListener('click', () => this.openCreateDialog());
    right.appendChild(createBtn);

    header.appendChild(left);
    header.appendChild(right);
    this.container.appendChild(header);

    this.gridEl = document.createElement('div');
    this.gridEl.className = 'orders-grid audit-block';
    this.container.appendChild(this.gridEl);

    this.emptyEl = document.createElement('div');
    this.emptyEl.className = 'card empty-state audit-block hidden';
    this.emptyEl.textContent = 'ไม่มีออเดอร์';
    this.container.appendChild(this.emptyEl);
  }

  activate(params = {}) {
    this.sessionId =
      params.session_id !== undefined ? Number(params.session_id) : null;
    this._sig = null;
    this.refresh();
    this._timer = setInterval(() => {
      if (!document.hidden && !document.querySelector('.modal-backdrop')) {
        this.refresh();
      }
    }, 4000);
  }

  deactivate() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  reload() {
    this._sig = null;
    this.refresh();
  }

  async refresh() {
    let data;
    try {
      data = await apiGet('/api/staff/orders', {
        session_id: this.sessionId || '',
        only_active: this.onlyActive ? 'true' : 'false',
      });
    } catch (_err) {
      return;
    }

    this._usableTables = data.tables || [];
    this._orderableMenu = data.orderable_menu || [];
    this.sessionId = data.selected_session_id;

    this.tableSelect.textContent = '';
    const allOpt = document.createElement('option');
    allOpt.value = '';
    allOpt.textContent = 'ทุกโต๊ะ';
    this.tableSelect.appendChild(allOpt);
    for (const t of this._usableTables) {
      const opt = document.createElement('option');
      opt.value = String(t.session_id);
      opt.textContent = t.label;
      if (t.session_id === this.sessionId) {
        opt.selected = true;
      }
      this.tableSelect.appendChild(opt);
    }

    this.subtitleEl.textContent = data.subtitle || '0 ออเดอร์';
    if (data.signature === this._sig) {
      return;
    }
    this._sig = data.signature;

    const orders = data.orders || [];
    this.gridEl.textContent = '';
    if (orders.length === 0) {
      this.gridEl.classList.add('hidden');
      this.emptyEl.classList.remove('hidden');
      return;
    }

    this.emptyEl.classList.add('hidden');
    this.gridEl.classList.remove('hidden');
    for (const o of orders) {
      this.gridEl.appendChild(this._makeOrderCard(o));
    }
  }

  _makeOrderCard(o) {
    const card = document.createElement('div');
    card.className = `order-card status-${o.status}`;

    const top = document.createElement('div');
    top.className = 'card-top';

    const head = document.createElement('div');
    head.className = 'card-head-row';
    const title = document.createElement('div');
    title.style.fontSize = 'var(--fs-2xl)';
    title.style.fontWeight = '700';
    title.textContent =
      o.table_no !== null && o.table_no !== undefined
        ? `โต๊ะ ${o.table_no}`
        : `ออเดอร์ #${o.id}`;
    head.appendChild(title);
    head.appendChild(
      createStatusBadge(
        ORDER_STATUS_TH[o.status] || o.status,
        ORDER_STATUS_COLORS[o.status] || '#868e96'
      )
    );
    top.appendChild(head);

    let subTxt = `#${o.id} · ${o.time_text || '-'}`;
    if (o.status === 'new' || o.status === 'preparing') {
      subTxt += ` · รอมา ${o.duration_text || '0 นาที'}`;
    }
    subTxt += ` · ${o.actor_text || 'ลูกค้าสั่ง'}`;
    const subEl = document.createElement('div');
    subEl.style.fontSize = 'var(--fs-xs)';
    subEl.style.color = 'var(--color-text-muted)';
    subEl.textContent = subTxt;
    top.appendChild(subEl);

    const itemsWrap = document.createElement('div');
    itemsWrap.style.display = 'flex';
    itemsWrap.style.flexDirection = 'column';
    itemsWrap.style.gap = 'var(--space-1)';
    itemsWrap.style.marginTop = 'var(--space-1)';
    for (const it of o.items || []) {
      const row = document.createElement('div');
      row.style.fontSize = 'var(--fs-md)';
      row.style.fontWeight = '700';
      if (it.status === 'served') {
        row.style.color = 'var(--color-text-muted)';
      }
      row.textContent = `${it.quantity} × ${it.name_snapshot}`;
      itemsWrap.appendChild(row);
    }
    top.appendChild(itemsWrap);

    if (o.note) {
      const noteEl = document.createElement('div');
      noteEl.style.fontSize = 'var(--fs-sm)';
      noteEl.style.color = 'var(--color-warning)';
      noteEl.textContent = `หมายเหตุ: ${o.note}`;
      top.appendChild(noteEl);
    }

    card.appendChild(top);

    const footer = document.createElement('div');
    footer.className = 'card-footer';

    // ตามข้อกำหนด: new -> 'เริ่มทำ', preparing -> 'เสิร์ฟแล้ว', served -> ไม่มีปุ่มดำเนินการซ้ำ และไม่มีปุ่มยกเลิก
    if (o.status === 'new' || o.status === 'preparing') {
      const btnRow = document.createElement('div');
      btnRow.className = 'card-btn-row';
      const btn = document.createElement('button');
      btn.type = 'button';
      if (o.status === 'new') {
        btn.className = 'btn btn-sm btn-info';
        btn.textContent = 'เริ่มทำ';
        btn.addEventListener('click', () => {
          btn.disabled = true;
          this.setStatus(o, 'preparing');
        });
      } else {
        btn.className = 'btn btn-sm btn-success';
        btn.textContent = 'เสิร์ฟแล้ว';
        btn.addEventListener('click', () => {
          btn.disabled = true;
          this.setStatus(o, 'served');
        });
      }
      btnRow.appendChild(btn);
      footer.appendChild(btnRow);
    }

    card.appendChild(footer);
    return card;
  }

  async setStatus(order, newStatus) {
    const oid = order.id;
    if (this._updatingIds.has(oid)) return;
    this._updatingIds.add(oid);
    try {
      await apiPost(`/api/staff/orders/${oid}/status`, { status: newStatus });
      this._sig = null;
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'warning');
      this._sig = null;
      await this.refresh();
    } finally {
      this._updatingIds.delete(oid);
    }
  }

  async openCreateDialog() {
    if (!this._usableTables || this._usableTables.length === 0) {
      this.app.toast('ยังไม่มีโต๊ะที่ใช้งานอยู่', 'error');
      return;
    }

    const dlg = new BaseDialog('สั่งให้ลูกค้า', { width: 520 });

    const topRow = document.createElement('div');
    topRow.style.display = 'flex';
    topRow.style.alignItems = 'center';
    topRow.style.justifyContent = 'space-between';
    topRow.style.gap = 'var(--space-2)';

    const leftSel = document.createElement('div');
    leftSel.style.display = 'flex';
    leftSel.style.alignItems = 'center';
    leftSel.style.gap = 'var(--space-2)';
    const tblLbl = document.createElement('span');
    tblLbl.style.fontWeight = '700';
    tblLbl.textContent = 'โต๊ะ';
    const tblSelect = document.createElement('select');
    tblSelect.className = 'field-select';
    tblSelect.style.width = '160px';
    for (const t of this._usableTables) {
      const opt = document.createElement('option');
      opt.value = String(t.session_id);
      opt.textContent = t.label;
      if (t.session_id === this.sessionId) opt.selected = true;
      tblSelect.appendChild(opt);
    }
    leftSel.appendChild(tblLbl);
    leftSel.appendChild(tblSelect);

    const totalLbl = document.createElement('div');
    totalLbl.style.fontWeight = '700';
    totalLbl.style.color = 'var(--color-primary)';
    totalLbl.textContent = 'รวม 0.00 บาท';

    topRow.appendChild(leftSel);
    topRow.appendChild(totalLbl);
    dlg.body.appendChild(topRow);

    const listBox = document.createElement('div');
    listBox.style.maxHeight = '280px';
    listBox.style.overflowY = 'auto';
    listBox.style.backgroundColor = 'var(--color-bg)';
    listBox.style.borderRadius = 'var(--radius-md)';
    listBox.style.padding = 'var(--space-2)';
    listBox.style.display = 'flex';
    listBox.style.flexDirection = 'column';
    listBox.style.gap = 'var(--space-1)';

    const qtyMap = {};
    const qtyEls = {};

    const updateTotal = () => {
      let sum = 0;
      for (const m of this._orderableMenu) {
        sum += Number(m.price) * (qtyMap[m.id] || 0);
      }
      totalLbl.textContent = `รวม ${baht(sum)}`;
    };

    if (this._orderableMenu.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'ไม่มีเมนูปกติที่สั่งได้';
      listBox.appendChild(empty);
    } else {
      for (const m of this._orderableMenu) {
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.justifyContent = 'space-between';
        row.style.padding = 'var(--space-1) var(--space-2)';
        row.style.backgroundColor = 'var(--color-card)';
        row.style.borderRadius = 'var(--radius-sm)';

        const nameSpan = document.createElement('span');
        nameSpan.textContent = `${m.name}  (${money(m.price)})`;

        const ctrls = document.createElement('div');
        ctrls.style.display = 'flex';
        ctrls.style.alignItems = 'center';
        ctrls.style.gap = 'var(--space-1)';

        const minus = document.createElement('button');
        minus.type = 'button';
        minus.className = 'btn btn-sm btn-ghost';
        minus.style.minWidth = '36px';
        minus.textContent = '−';

        const qLbl = document.createElement('span');
        qLbl.style.minWidth = '32px';
        qLbl.style.textAlign = 'center';
        qLbl.style.fontWeight = '700';
        qLbl.textContent = '0';
        qtyEls[m.id] = qLbl;

        const plus = document.createElement('button');
        plus.type = 'button';
        plus.className = 'btn btn-sm btn-success';
        plus.style.minWidth = '36px';
        plus.textContent = '+';

        const changeQty = (delta) => {
          const next = Math.max(0, Math.min(99, (qtyMap[m.id] || 0) + delta));
          qtyMap[m.id] = next;
          qLbl.textContent = String(next);
          updateTotal();
        };
        minus.addEventListener('click', () => changeQty(-1));
        plus.addEventListener('click', () => changeQty(1));

        ctrls.appendChild(minus);
        ctrls.appendChild(qLbl);
        ctrls.appendChild(plus);
        row.appendChild(nameSpan);
        row.appendChild(ctrls);
        listBox.appendChild(row);
      }
    }
    dlg.body.appendChild(listBox);

    const noteInput = document.createElement('input');
    noteInput.type = 'text';
    noteInput.className = 'field-input';
    noteInput.placeholder = 'หมายเหตุ (ถ้ามี)';
    dlg.body.appendChild(noteInput);

    const errEl = document.createElement('div');
    errEl.className = 'modal-error';
    dlg.body.appendChild(errEl);

    dlg.addButtons({
      confirmText: 'บันทึกออเดอร์',
      cancelText: 'ยกเลิก',
      variant: 'primary',
      onConfirm: async () => {
        const items = Object.entries(qtyMap)
          .filter(([_id, q]) => q > 0)
          .map(([id, q]) => ({ menu_item_id: Number(id), quantity: q }));
        if (items.length === 0) {
          errEl.textContent = 'ยังไม่ได้เลือกรายการ';
          return;
        }
        try {
          const res = await apiPost('/api/staff/orders', {
            session_id: Number(tblSelect.value),
            items,
            note: noteInput.value.trim() || null,
          });
          dlg.close(true);
          this.app.toast(res.message || 'บันทึกออเดอร์แล้ว', 'success');
          this._sig = null;
          await this.refresh();
        } catch (err) {
          errEl.textContent = err.message;
        }
      },
    });

    await dlg.show();
  }
}
