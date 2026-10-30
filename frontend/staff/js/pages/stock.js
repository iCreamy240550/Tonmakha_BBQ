/**
 * frontend/staff/js/pages/stock.js — สต๊อกวัตถุดิบ/สินค้า (เจ้าของ)
 * คัดลอกจาก ui/owner/stock_page.py ทุกตัวอักษร
 */

import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
} from '../../../shared/js/api.js';
import { DataTable } from '../../../shared/js/data-table.js';
import { BaseDialog, confirmDialog } from '../../../shared/js/dialogs.js';
import { fmt_qty, parse_number } from '../../../shared/js/format.js';
import { createStatusBadge } from '../../../shared/js/status-badge.js';

export class StockPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.includeInactive = false;
    this.defaultThreshold = 5;
    this.defaultThresholdFmt = '5';
    this.deleting = false;

    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'สต๊อก';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);

    const right = document.createElement('div');
    right.className = 'page-header-right';

    const chkLabel = document.createElement('label');
    chkLabel.style.display = 'inline-flex';
    chkLabel.style.alignItems = 'center';
    chkLabel.style.gap = 'var(--space-2)';
    chkLabel.style.cursor = 'pointer';
    this.chkInactive = document.createElement('input');
    this.chkInactive.type = 'checkbox';
    this.chkInactive.addEventListener('change', () => {
      this.includeInactive = this.chkInactive.checked;
      this.refresh();
    });
    const chkSpan = document.createElement('span');
    chkSpan.textContent = 'แสดงรายการที่ปิดใช้';
    chkLabel.appendChild(this.chkInactive);
    chkLabel.appendChild(chkSpan);
    right.appendChild(chkLabel);

    this.deleteBtn = document.createElement('button');
    this.deleteBtn.type = 'button';
    this.deleteBtn.className = 'btn btn-danger';
    this.deleteBtn.textContent = 'ลบรายการสต๊อกที่เลือก';
    this.deleteBtn.disabled = true;
    this.deleteBtn.addEventListener('click', () => this.deleteSelected());
    right.appendChild(this.deleteBtn);

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn-primary';
    addBtn.textContent = '+ เพิ่มรายการ';
    addBtn.addEventListener('click', () => this.addItem());
    right.appendChild(addBtn);

    header.appendChild(left);
    header.appendChild(right);
    this.container.appendChild(header);

    const split = document.createElement('div');
    split.className = 'split-layout split-stock audit-block';

    const leftWrap = document.createElement('div');
    leftWrap.style.minWidth = '0';

    this.table = new DataTable(
      leftWrap,
      [
        { key: 'name', title: 'รายการ', weight: 3, min_width: 120, anchor: 'w' },
        { key: 'quantity_fmt', title: 'คงเหลือ', weight: 2, min_width: 85, anchor: 'w' },
        { key: 'min_qty_fmt', title: 'จุดเตือน', weight: 2, min_width: 75, anchor: 'w' },
        {
          key: 'status',
          title: 'สถานะ',
          weight: 2,
          min_width: 85,
          anchor: 'center',
          widget: (row) => {
            if (!row.active) {
              return createStatusBadge('ปิดใช้', 'var(--color-neutral)');
            }
            if (Number(row.quantity) <= 0) {
              return createStatusBadge('สินค้าหมด', 'var(--color-danger)');
            }
            if (row.is_low) {
              return createStatusBadge('ใกล้หมด', 'var(--color-warning)');
            }
            return createStatusBadge('พอ', 'var(--color-success)');
          },
        },
        {
          key: 'actions',
          title: 'จัดการสต๊อก',
          weight: 6,
          min_width: 270,
          anchor: 'w',
          widget: (row) => {
            const box = document.createElement('div');
            box.className = 'table-actions';

            const bRestock = document.createElement('button');
            bRestock.type = 'button';
            bRestock.className = 'btn btn-sm btn-success';
            bRestock.textContent = 'เติม';
            bRestock.addEventListener('click', () => this.restock(row));

            const bAdj = document.createElement('button');
            bAdj.type = 'button';
            bAdj.className = 'btn btn-sm btn-ghost';
            bAdj.textContent = 'ปรับ +/-';
            bAdj.addEventListener('click', () => this.adjust(row));

            const bEdit = document.createElement('button');
            bEdit.type = 'button';
            bEdit.className = 'btn btn-sm btn-info';
            bEdit.textContent = 'แก้ไข';
            bEdit.addEventListener('click', () => this.editItem(row));

            const bDel = document.createElement('button');
            bDel.type = 'button';
            bDel.className = 'btn btn-sm btn-danger';
            bDel.textContent = 'ลบ';
            bDel.addEventListener('click', () => this.deleteItem(row));

            box.appendChild(bRestock);
            box.appendChild(bAdj);
            box.appendChild(bEdit);
            box.appendChild(bDel);
            return box;
          },
        },
      ],
      {
        onSelect: () => this._onRowSelected(),
        emptyText: 'ยังไม่มีรายการสต๊อก',
      }
    );

    const rightCard = document.createElement('div');
    rightCard.className = 'card';
    rightCard.style.display = 'flex';
    rightCard.style.flexDirection = 'column';
    rightCard.style.gap = 'var(--space-2)';
    rightCard.style.minWidth = '0';

    this.moveTitle = document.createElement('div');
    this.moveTitle.style.fontSize = 'var(--fs-xl)';
    this.moveTitle.style.fontWeight = '700';
    this.moveTitle.textContent = 'ประวัติการเคลื่อนไหว';
    rightCard.appendChild(this.moveTitle);

    const movesWrap = document.createElement('div');
    movesWrap.style.flex = '1 1 auto';
    rightCard.appendChild(movesWrap);

    this.movesTable = new DataTable(
      movesWrap,
      [
        { key: 'created_at_fmt', title: 'เวลา', weight: 3, min_width: 110, anchor: 'w' },
        { key: 'change_qty_fmt', title: 'เปลี่ยน', weight: 2, min_width: 70, anchor: 'w' },
        { key: 'reason', title: 'เหตุผล', weight: 4, min_width: 100, anchor: 'w' },
        { key: 'user_display', title: 'โดย', weight: 2, min_width: 70, anchor: 'w' },
      ],
      { emptyText: 'เลือกรายการทางซ้ายเพื่อดูประวัติ' }
    );

    split.appendChild(leftWrap);
    split.appendChild(rightCard);
    this.container.appendChild(split);
  }

  activate() {
    this.refresh();
  }

  deactivate() {}

  reload() {
    this.refresh();
  }

  async refresh() {
    try {
      const selId = this.table.selected ? this.table.selected.id : '';
      const data = await apiGet('/api/owner/stock', {
        include_inactive: this.includeInactive ? 'true' : 'false',
        selected_id: selId,
      });
      this.defaultThreshold = data.default_low_threshold;
      this.defaultThresholdFmt = data.default_low_threshold_fmt;
      this.subtitleEl.textContent = data.subtitle || '';
      this.table.setRows(data.items || []);
      await this._onRowSelected();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async _onRowSelected() {
    const sel = this.table.selected;
    this.deleteBtn.disabled = !sel;
    if (!sel) {
      this.moveTitle.textContent = 'ประวัติการเคลื่อนไหว';
      this.movesTable.setRows([]);
      return;
    }
    this.moveTitle.textContent = `ประวัติ: ${sel.name}`;
    try {
      const res = await apiGet(`/api/owner/stock/${sel.id}/movements`);
      this.movesTable.setRows(res.movements || []);
    } catch (_err) {
      this.movesTable.setRows([]);
    }
  }

  async addItem() {
    const data = await openStockDialog(null, this.defaultThreshold, this.defaultThresholdFmt);
    if (!data) return;
    try {
      const res = await apiPost('/api/owner/stock', data);
      this.app.toast(res.message || 'เพิ่มรายการสต๊อกแล้ว', 'success');
      await this.refresh();
      if (this.app.alertCenter) this.app.alertCenter.refreshView(false);
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async editItem(row) {
    const data = await openStockDialog(row, this.defaultThreshold, this.defaultThresholdFmt);
    if (!data) return;
    try {
      const res = await apiPatch(`/api/owner/stock/${row.id}`, data);
      this.app.toast(res.message || 'บันทึกแล้ว', 'success');
      await this.refresh();
      if (this.app.alertCenter) this.app.alertCenter.refreshView(false);
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async restock(row) {
    const data = await openQuantityDialog(row, 'restock');
    if (!data) return;
    try {
      const res = await apiPost(`/api/owner/stock/${row.id}/restock`, data);
      this.app.toast(res.message, 'success');
      await this.refresh();
      if (this.app.alertCenter) this.app.alertCenter.refreshView(false);
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async adjust(row) {
    const data = await openQuantityDialog(row, 'adjust');
    if (!data) return;
    try {
      const res = await apiPost(`/api/owner/stock/${row.id}/adjust`, data);
      this.app.toast(res.message, 'success');
      await this.refresh();
      if (this.app.alertCenter) this.app.alertCenter.refreshView(false);
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  deleteSelected() {
    const sel = this.table.selected;
    if (!sel) {
      this.app.toast('กรุณาเลือกรายการสต๊อกที่ต้องการลบก่อน', 'warning');
      return;
    }
    this.deleteItem(sel);
  }

  async deleteItem(row) {
    if (this.deleting) return;
    try {
      const impact = await apiGet(`/api/owner/stock/${row.id}/delete_impact`);
      const btnLabel = impact.can_hard_delete
        ? 'ลบถาวร'
        : 'ปิดใช้งานแทนการลบ';
      const msg = `ต้องการลบรายการสต๊อก "${row.name}" (คงเหลือ ${fmt_qty(row.quantity)} ${row.unit}) ใช่หรือไม่?\n\nผลกระทบ:\n${impact.impact_text}`;
      const ok = await confirmDialog(msg, {
        title: 'ยืนยันลบรายการสต๊อก',
        confirmText: btnLabel,
        danger: true,
      });
      if (!ok) return;

      this.deleting = true;
      const res = await apiDelete(`/api/owner/stock/${row.id}`);
      this.app.toast(res.message, 'success');
      await this.refresh();
      if (this.app.alertCenter) this.app.alertCenter.refreshView(false);
    } catch (err) {
      this.app.toast(err.message, 'error');
    } finally {
      this.deleting = false;
    }
  }
}

async function openStockDialog(item, defaultThresh, defaultThreshFmt) {
  const dlg = new BaseDialog(
    item ? 'แก้ไขรายการสต๊อก' : 'เพิ่มรายการสต๊อก',
    { width: 460 }
  );

  const nameGroup = document.createElement('div');
  nameGroup.className = 'field-group';
  const nameLbl = document.createElement('label');
  nameLbl.className = 'field-label';
  nameLbl.textContent = 'ชื่อ';
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.className = 'field-input';
  nameInput.placeholder = 'เช่น หมูสามชั้น';
  nameInput.value = item ? item.name : '';
  nameGroup.appendChild(nameLbl);
  nameGroup.appendChild(nameInput);
  dlg.body.appendChild(nameGroup);

  const row = document.createElement('div');
  row.style.display = 'grid';
  row.style.gridTemplateColumns = '1fr 1fr';
  row.style.gap = 'var(--space-2)';

  const unitGroup = document.createElement('div');
  unitGroup.className = 'field-group';
  const unitLbl = document.createElement('label');
  unitLbl.className = 'field-label';
  unitLbl.textContent = 'หน่วย';
  const unitInput = document.createElement('input');
  unitInput.type = 'text';
  unitInput.className = 'field-input';
  unitInput.placeholder = 'กก. / ชิ้น / ขวด';
  unitInput.value = item ? item.unit : '';
  unitGroup.appendChild(unitLbl);
  unitGroup.appendChild(unitInput);

  const minGroup = document.createElement('div');
  minGroup.className = 'field-group';
  const minLbl = document.createElement('label');
  minLbl.className = 'field-label';
  minLbl.textContent = `จุดเตือนเมื่อเหลือไม่เกิน (เริ่มต้น ${defaultThreshFmt})`;
  const minInput = document.createElement('input');
  minInput.type = 'text';
  minInput.className = 'field-input num';
  minInput.placeholder = defaultThreshFmt;
  minInput.value = item ? fmt_qty(item.min_quantity) : defaultThreshFmt;
  minGroup.appendChild(minLbl);
  minGroup.appendChild(minInput);

  row.appendChild(unitGroup);
  row.appendChild(minGroup);
  dlg.body.appendChild(row);

  let qtyInput = null;
  let activeChk = null;
  if (!item) {
    const qtyGroup = document.createElement('div');
    qtyGroup.className = 'field-group';
    const qtyLbl = document.createElement('label');
    qtyLbl.className = 'field-label';
    qtyLbl.textContent = 'จำนวนตั้งต้น';
    qtyInput = document.createElement('input');
    qtyInput.type = 'text';
    qtyInput.className = 'field-input num';
    qtyInput.placeholder = '0';
    qtyGroup.appendChild(qtyLbl);
    qtyGroup.appendChild(qtyInput);
    dlg.body.appendChild(qtyGroup);
  } else {
    const swRow = document.createElement('label');
    swRow.style.display = 'inline-flex';
    swRow.style.alignItems = 'center';
    swRow.style.gap = 'var(--space-2)';
    swRow.style.cursor = 'pointer';
    activeChk = document.createElement('input');
    activeChk.type = 'checkbox';
    activeChk.checked = Boolean(item.active);
    const swTxt = document.createElement('span');
    swTxt.textContent = 'เปิดใช้งานรายการนี้';
    swRow.appendChild(activeChk);
    swRow.appendChild(swTxt);
    dlg.body.appendChild(swRow);
  }

  const errEl = document.createElement('div');
  errEl.className = 'modal-error';
  dlg.body.appendChild(errEl);

  dlg.addButtons({
    confirmText: 'บันทึก',
    cancelText: 'ยกเลิก',
    variant: 'primary',
    onConfirm: () => {
      try {
        const name = nameInput.value.trim();
        const unit = unitInput.value.trim();
        if (!name || !unit) {
          throw new Error('กรุณากรอกชื่อและหน่วย');
        }
        const minQuantity = parse_number(minInput.value, 'จุดเตือน', {
          minimum: 0,
          allowEmpty: true,
          defaultValue: defaultThresh,
        });
        const out = { name, unit, min_quantity: minQuantity };
        if (!item) {
          out.quantity = parse_number(qtyInput.value, 'จำนวนตั้งต้น', {
            minimum: 0,
            allowEmpty: true,
            defaultValue: 0,
          });
        } else {
          out.active = Boolean(activeChk.checked);
        }
        dlg.close(out);
      } catch (err) {
        errEl.textContent = err.message;
      }
    },
  });

  return dlg.show();
}

async function openQuantityDialog(item, mode) {
  const isRestock = mode === 'restock';
  const dlg = new BaseDialog(isRestock ? 'เติมสต๊อก' : 'ปรับสต๊อก', {
    width: 440,
  });

  const head = document.createElement('div');
  head.style.fontSize = 'var(--fs-lg)';
  head.style.fontWeight = '700';
  head.textContent = `${item.name}  (เหลือ ${fmt_qty(item.quantity)} ${item.unit})`;
  dlg.body.appendChild(head);

  const qtyGroup = document.createElement('div');
  qtyGroup.className = 'field-group';
  const qtyLbl = document.createElement('label');
  qtyLbl.className = 'field-label';
  qtyLbl.textContent = isRestock
    ? `จำนวนที่เติมเข้า (${item.unit})`
    : `จำนวนที่เปลี่ยน (${item.unit}) — ใส่ + เพิ่ม / - ลด เช่น -2.5 (ถ้าจะเติมของเข้าร้านให้ใช้ปุ่ม "เติม")`;
  const qtyInput = document.createElement('input');
  qtyInput.type = 'text';
  qtyInput.className = 'field-input num';
  qtyInput.placeholder = '0';
  qtyGroup.appendChild(qtyLbl);
  qtyGroup.appendChild(qtyInput);
  dlg.body.appendChild(qtyGroup);

  const reasonGroup = document.createElement('div');
  reasonGroup.className = 'field-group';
  const reasonLbl = document.createElement('label');
  reasonLbl.className = 'field-label';
  reasonLbl.textContent = `เหตุผล (${isRestock ? 'ไม่บังคับ' : 'บังคับ'})`;
  const reasonInput = document.createElement('input');
  reasonInput.type = 'text';
  reasonInput.className = 'field-input';
  reasonInput.placeholder = 'เช่น ซื้อเข้าร้าน / นับสต๊อกจริง / ของเสีย';
  reasonGroup.appendChild(reasonLbl);
  reasonGroup.appendChild(reasonInput);
  dlg.body.appendChild(reasonGroup);

  const errEl = document.createElement('div');
  errEl.className = 'modal-error';
  dlg.body.appendChild(errEl);

  dlg.addButtons({
    confirmText: isRestock ? 'เติมสต๊อก' : 'ปรับสต๊อก',
    cancelText: 'ยกเลิก',
    variant: 'primary',
    onConfirm: () => {
      try {
        const qty = parse_number(qtyInput.value, 'จำนวน');
        const reason = reasonInput.value.trim();
        if (isRestock) {
          if (qty <= 0) throw new Error('จำนวนที่เติมต้องมากกว่า 0');
        } else {
          if (qty === 0) throw new Error('จำนวนที่ปรับต้องไม่เป็น 0');
          if (!reason) throw new Error('กรุณากรอกเหตุผลที่ปรับสต๊อก');
        }
        dlg.close({ quantity: qty, reason });
      } catch (err) {
        errEl.textContent = err.message;
      }
    },
  });

  return dlg.show();
}
