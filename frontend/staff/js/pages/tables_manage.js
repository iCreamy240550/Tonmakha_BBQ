/**
 * frontend/staff/js/pages/tables_manage.js — จัดการโต๊ะ + QR (เจ้าของ)
 * คัดลอกจาก ui/owner/tables_manage_page.py ทุกตัวอักษร
 */

import { apiGet, apiPatch, apiPost } from '../../../shared/js/api.js';
import { DataTable } from '../../../shared/js/data-table.js';
import {
  BaseDialog,
  askTextDialog,
  confirmDialog,
} from '../../../shared/js/dialogs.js';
import { parse_int } from '../../../shared/js/format.js';
import { createStatusBadge } from '../../../shared/js/status-badge.js';

export class TablesManagePage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.tables = [];
    this.suggestedNo = 1;
    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'จัดการโต๊ะและ QR';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);

    const right = document.createElement('div');
    right.className = 'page-header-right';

    const openBtn = document.createElement('button');
    openBtn.type = 'button';
    openBtn.className = 'btn btn-ghost';
    openBtn.textContent = 'เปิดโฟลเดอร์ QR';
    openBtn.addEventListener('click', () => this.openQrFolder());

    const genAllBtn = document.createElement('button');
    genAllBtn.type = 'button';
    genAllBtn.className = 'btn btn-success';
    genAllBtn.textContent = 'สร้าง QR ทุกโต๊ะ';
    genAllBtn.addEventListener('click', () => this.generateAll());

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn-primary';
    addBtn.textContent = '+ เพิ่มโต๊ะ';
    addBtn.addEventListener('click', () => this.addTable());

    right.appendChild(openBtn);
    right.appendChild(genAllBtn);
    right.appendChild(addBtn);
    header.appendChild(left);
    header.appendChild(right);
    this.container.appendChild(header);

    const split = document.createElement('div');
    split.className = 'split-layout split-tables-manage audit-block';

    const leftWrap = document.createElement('div');
    leftWrap.style.minWidth = '0';

    this.table = new DataTable(
      leftWrap,
      [
        { key: 'table_no', title: 'เลข', weight: 1, min_width: 55, anchor: 'w' },
        { key: 'name', title: 'ชื่อโต๊ะ', weight: 3, min_width: 110, anchor: 'w' },
        {
          key: 'status',
          title: 'สถานะ',
          weight: 2,
          min_width: 95,
          anchor: 'center',
          widget: (row) => createStatusBadge(row.status_th, row.status_color),
        },
        { key: 'qr_status_text', title: 'ไฟล์ QR', weight: 2, min_width: 85, anchor: 'w' },
        {
          key: 'actions',
          title: 'จัดการ',
          weight: 6,
          min_width: 270,
          anchor: 'w',
          widget: (row) => {
            const box = document.createElement('div');
            box.className = 'table-actions';

            const bRen = document.createElement('button');
            bRen.type = 'button';
            bRen.className = 'btn btn-sm btn-info';
            bRen.textContent = 'ชื่อ';
            bRen.addEventListener('click', () => this.rename(row));

            const bRegen = document.createElement('button');
            bRegen.type = 'button';
            bRegen.className = 'btn btn-sm btn-ghost';
            bRegen.textContent = 'สุ่มรหัสใหม่';
            bRegen.addEventListener('click', () => this.regenerate(row));

            const bToggle = document.createElement('button');
            bToggle.type = 'button';
            bToggle.className = `btn btn-sm ${!row.active ? 'btn-success' : 'btn-ghost'}`;
            bToggle.textContent = !row.active ? 'เปิดใช้' : 'ปิดใช้';
            bToggle.addEventListener('click', () => this.toggleActive(row));

            box.appendChild(bRen);
            box.appendChild(bRegen);
            box.appendChild(bToggle);
            return box;
          },
        },
      ],
      {
        onSelect: () => this._showPreview(),
        emptyText: 'ยังไม่มีโต๊ะ',
      }
    );

    const rightCard = document.createElement('div');
    rightCard.className = 'card';
    rightCard.style.display = 'flex';
    rightCard.style.flexDirection = 'column';
    rightCard.style.gap = 'var(--space-2)';

    this.previewTitle = document.createElement('div');
    this.previewTitle.style.fontSize = 'var(--fs-xl)';
    this.previewTitle.style.fontWeight = '700';
    this.previewTitle.textContent = 'ตัวอย่าง QR';
    rightCard.appendChild(this.previewTitle);

    this.previewBox = document.createElement('div');
    this.previewBox.style.width = '240px';
    this.previewBox.style.height = '240px';
    this.previewBox.style.alignSelf = 'center';
    this.previewBox.style.backgroundColor = 'var(--color-row-alt)';
    this.previewBox.style.borderRadius = 'var(--radius-md)';
    this.previewBox.style.display = 'flex';
    this.previewBox.style.alignItems = 'center';
    this.previewBox.style.justifyContent = 'center';
    this.previewBox.style.textAlign = 'center';
    this.previewBox.style.color = 'var(--color-text-muted)';
    this.previewBox.style.whiteSpace = 'pre-line';
    this.previewBox.textContent = 'เลือกโต๊ะทางซ้าย';
    rightCard.appendChild(this.previewBox);

    this.urlInput = document.createElement('input');
    this.urlInput.type = 'text';
    this.urlInput.className = 'field-input';
    this.urlInput.readOnly = true;
    this.urlInput.style.fontSize = 'var(--fs-xs)';
    rightCard.appendChild(this.urlInput);

    this.warnLabel = document.createElement('div');
    this.warnLabel.style.fontSize = 'var(--fs-sm)';
    this.warnLabel.style.color = 'var(--color-danger)';
    rightCard.appendChild(this.warnLabel);

    const btnRow = document.createElement('div');
    btnRow.style.display = 'flex';
    btnRow.style.gap = 'var(--space-2)';
    btnRow.style.flexWrap = 'wrap';

    const genBtn = document.createElement('button');
    genBtn.type = 'button';
    genBtn.className = 'btn btn-sm btn-success';
    genBtn.textContent = 'สร้าง/อัปเดตรูป QR';
    genBtn.addEventListener('click', () => this.generateSelected());

    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'btn btn-sm btn-ghost';
    copyBtn.textContent = 'คัดลอกลิงก์';
    copyBtn.addEventListener('click', () => this.copyLink());

    this.dlBtn = document.createElement('a');
    this.dlBtn.className = 'btn btn-sm btn-info hidden';
    this.dlBtn.textContent = 'ดาวน์โหลด QR';

    btnRow.appendChild(genBtn);
    btnRow.appendChild(copyBtn);
    btnRow.appendChild(this.dlBtn);
    rightCard.appendChild(btnRow);

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
      const data = await apiGet('/api/owner/tables_manage');
      this.tables = data.tables || [];
      this.suggestedNo = data.suggested_no || 1;
      this.subtitleEl.textContent = data.subtitle || '';
      this.table.setRows(this.tables);
      this._showPreview();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  _selectedTable() {
    const sel = this.table.selected;
    if (!sel) return null;
    return this.tables.find((t) => t.id === sel.id) || null;
  }

  _showPreview() {
    const t = this._selectedTable();
    this.previewBox.textContent = '';
    if (!t) {
      this.previewTitle.textContent = 'ตัวอย่าง QR';
      this.previewBox.textContent = 'เลือกโต๊ะทางซ้าย';
      this.urlInput.value = '';
      this.warnLabel.textContent = '';
      this.dlBtn.classList.add('hidden');
      return;
    }

    this.previewTitle.textContent = `QR: ${t.name}`;
    this.urlInput.value = t.qr_url || '';
    this.warnLabel.textContent = t.url_is_local
      ? 'ลิงก์ยังเป็น localhost — มือถือลูกค้าสแกนแล้วเข้าไม่ได้ ตั้งค่า "ลิงก์เว็บลูกค้า" ที่หน้าตั้งค่าก่อนสร้าง QR'
      : '';

    if (t.has_qr_file) {
      const img = document.createElement('img');
      img.src = `${t.qr_image_endpoint}?t=${Date.now()}`;
      img.alt = `QR ${t.name}`;
      img.style.width = '220px';
      img.style.height = '220px';
      img.style.objectFit = 'contain';
      this.previewBox.appendChild(img);

      this.dlBtn.href = `${t.qr_image_endpoint}?download=true`;
      this.dlBtn.download = `table_${t.table_no}.png`;
      this.dlBtn.classList.remove('hidden');
    } else {
      this.previewBox.textContent = 'ยังไม่มีรูป QR\nกด "สร้าง/อัปเดตรูป QR"';
      this.dlBtn.classList.add('hidden');
    }
  }

  async generateSelected() {
    const t = this._selectedTable();
    if (!t) {
      this.app.toast('เลือกโต๊ะทางซ้ายก่อน', 'warning');
      return;
    }
    try {
      const res = await apiPost(`/api/owner/tables_manage/${t.id}/qr`, {});
      this.app.toast(res.message || `สร้าง QR โต๊ะ ${t.table_no} แล้ว`, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async generateAll() {
    const active = this.tables.filter((t) => t.active);
    if (active.length === 0) {
      this.app.toast('ยังไม่มีโต๊ะที่ใช้งาน', 'warning');
      return;
    }
    if (active.some((t) => t.url_is_local)) {
      const ok = await confirmDialog(
        'ลิงก์เว็บลูกค้ายังเป็น localhost — QR ที่สร้างจะใช้กับมือถือไม่ได้\nสร้างต่อหรือไม่?',
        {
          title: 'ลิงก์ยังเป็น localhost',
          confirmText: 'สร้างต่อ',
        }
      );
      if (!ok) return;
    }
    try {
      const res = await apiPost('/api/owner/tables_manage/qr_all', {});
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async openQrFolder() {
    try {
      const res = await apiPost('/api/owner/open_folder', { target: 'qr' });
      this.app.toast(res.message, res.opened ? 'info' : 'warning');
    } catch (err) {
      this.app.toast(err.message, 'warning');
    }
  }

  async copyLink() {
    const t = this._selectedTable();
    if (!t) {
      this.app.toast('เลือกโต๊ะทางซ้ายก่อน', 'warning');
      return;
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(t.qr_url);
      } else {
        this.urlInput.select();
        document.execCommand('copy');
      }
      this.app.toast('คัดลอกลิงก์แล้ว', 'success');
    } catch (_e) {
      this.app.toast('คัดลอกลิงก์แล้ว', 'success');
    }
  }

  async addTable() {
    const dlg = new BaseDialog('เพิ่มโต๊ะ', { width: 400 });
    const noGroup = document.createElement('div');
    noGroup.className = 'field-group';
    const noLbl = document.createElement('label');
    noLbl.className = 'field-label';
    noLbl.textContent = 'เลขโต๊ะ';
    const noInput = document.createElement('input');
    noInput.type = 'text';
    noInput.className = 'field-input num';
    noInput.value = String(this.suggestedNo);
    noGroup.appendChild(noLbl);
    noGroup.appendChild(noInput);
    dlg.body.appendChild(noGroup);

    const nameGroup = document.createElement('div');
    nameGroup.className = 'field-group';
    const nameLbl = document.createElement('label');
    nameLbl.className = 'field-label';
    nameLbl.textContent = 'ชื่อโต๊ะ (ว่าง = "โต๊ะ <เลข>")';
    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.className = 'field-input';
    nameInput.placeholder = 'เช่น โต๊ะริมสระ';
    nameGroup.appendChild(nameLbl);
    nameGroup.appendChild(nameInput);
    dlg.body.appendChild(nameGroup);

    const errEl = document.createElement('div');
    errEl.className = 'modal-error';
    dlg.body.appendChild(errEl);

    dlg.addButtons({
      confirmText: 'เพิ่มโต๊ะ',
      cancelText: 'ยกเลิก',
      variant: 'primary',
      onConfirm: () => {
        try {
          const no = parse_int(noInput.value, 'เลขโต๊ะ', { minimum: 1 });
          dlg.close({ table_no: no, name: nameInput.value.trim() });
        } catch (err) {
          errEl.textContent = err.message;
        }
      },
    });

    const data = await dlg.show();
    if (!data) return;
    try {
      const res = await apiPost('/api/owner/tables_manage', data);
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async rename(row) {
    const name = await askTextDialog(`ชื่อโต๊ะ ${row.table_no}`, {
      title: 'เปลี่ยนชื่อโต๊ะ',
      initial: row.name,
    });
    if (name === null) return;
    try {
      const res = await apiPatch(`/api/owner/tables_manage/${row.id}`, { name });
      this.app.toast(res.message || 'เปลี่ยนชื่อแล้ว', 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async toggleActive(row) {
    if (row.active) {
      const ok = await confirmDialog(
        `ปิดใช้งาน ${row.name} ?\nลูกค้าสแกน QR ของโต๊ะนี้ไม่ได้จนกว่าจะเปิดใหม่`,
        {
          title: 'ปิดใช้งานโต๊ะ',
          confirmText: 'ปิดใช้งาน',
        }
      );
      if (!ok) return;
    }
    try {
      const res = await apiPatch(`/api/owner/tables_manage/${row.id}`, {
        active: !row.active,
      });
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async regenerate(row) {
    const ok = await confirmDialog(
      `สุ่มรหัสลับใหม่ให้ ${row.name} ?\nQR เดิมที่พิมพ์ติดโต๊ะไว้จะใช้ไม่ได้ ต้องพิมพ์ QR ใหม่\n(ลูกค้าที่กำลังนั่งอยู่ไม่ได้รับผลกระทบ)`,
      {
        title: 'สุ่มรหัสลับใหม่',
        confirmText: 'สุ่มรหัสใหม่',
        danger: true,
      }
    );
    if (!ok) return;
    try {
      const res = await apiPost(
        `/api/owner/tables_manage/${row.id}/regenerate_secret`,
        {}
      );
      this.app.toast(res.message || 'เปลี่ยนรหัสลับแล้ว', 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }
}
