/**
 * frontend/staff/js/pages/backup.js — สำรอง/กู้คืนข้อมูล (เจ้าของ)
 * คัดลอกจาก ui/owner/backup_page.py ทุกตัวอักษร
 */

import { apiDelete, apiGet, apiPost } from '../../../shared/js/api.js';
import { DataTable } from '../../../shared/js/data-table.js';
import {
  askTextDialog,
  confirmDialog,
  showInfoDialog,
} from '../../../shared/js/dialogs.js';
import { createStatusBadge } from '../../../shared/js/status-badge.js';

const CONFIRM_WORD = 'กู้คืน';
const KIND_COLORS = {
  manual: 'var(--color-info)',
  auto: 'var(--color-neutral)',
  prerestore: 'var(--color-warning)',
};

export class BackupPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.canRestore = false;
    this.restoreBlocker = null;

    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'สำรองข้อมูล';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);

    const right = document.createElement('div');
    right.className = 'page-header-right';
    const openBtn = document.createElement('button');
    openBtn.type = 'button';
    openBtn.className = 'btn btn-ghost';
    openBtn.textContent = 'เปิดโฟลเดอร์สำรอง';
    openBtn.addEventListener('click', () => this.openFolder());

    const backupBtn = document.createElement('button');
    backupBtn.type = 'button';
    backupBtn.className = 'btn btn-success';
    backupBtn.textContent = 'สำรองตอนนี้';
    backupBtn.addEventListener('click', () => this.backupNow());

    right.appendChild(openBtn);
    right.appendChild(backupBtn);
    header.appendChild(left);
    header.appendChild(right);
    this.container.appendChild(header);

    const infoCard = document.createElement('div');
    infoCard.className = 'card audit-block';
    infoCard.style.display = 'flex';
    infoCard.style.flexDirection = 'column';
    infoCard.style.gap = 'var(--space-1)';

    this.shopLabel = document.createElement('div');
    this.shopLabel.style.fontSize = 'var(--fs-md)';
    this.shopLabel.style.fontWeight = '700';

    const desc = document.createElement('div');
    desc.style.fontSize = 'var(--fs-sm)';
    desc.style.color = 'var(--color-text-muted)';
    desc.textContent =
      'ระบบสำรองอัตโนมัติวันละครั้งตอนเปิดแอป (เก็บ 14 ไฟล์ล่าสุด) · ไฟล์สำรองคือฐานข้อมูลทั้งหมดของร้าน เก็บสำเนาไว้นอกเครื่อง (เช่น USB/คลาวด์) เป็นระยะเพื่อกันเครื่องเสีย';

    infoCard.appendChild(this.shopLabel);
    infoCard.appendChild(desc);
    this.container.appendChild(infoCard);

    const tblHolder = document.createElement('div');
    tblHolder.className = 'audit-block';
    this.container.appendChild(tblHolder);

    this.table = new DataTable(
      tblHolder,
      [
        { key: 'created_at_fmt', title: 'สร้างเมื่อ', weight: 3, min_width: 130, anchor: 'w' },
        {
          key: 'kind',
          title: 'ชนิด',
          weight: 3,
          min_width: 130,
          anchor: 'w',
          widget: (row) =>
            createStatusBadge(
              row.kind_th,
              KIND_COLORS[row.kind] || 'var(--color-neutral)'
            ),
        },
        { key: 'filename', title: 'ชื่อไฟล์', weight: 6, min_width: 260, anchor: 'w' },
        { key: 'size_text', title: 'ขนาด', weight: 2, min_width: 85, anchor: 'w' },
        {
          key: 'actions',
          title: 'จัดการ',
          weight: 3,
          min_width: 170,
          anchor: 'w',
          widget: (row) => {
            const box = document.createElement('div');
            box.className = 'table-actions';

            const bRestore = document.createElement('button');
            bRestore.type = 'button';
            bRestore.className = 'btn btn-sm btn-danger';
            bRestore.textContent = 'กู้คืน';
            bRestore.addEventListener('click', () => this.restore(row));

            const bDel = document.createElement('button');
            bDel.type = 'button';
            bDel.className = 'btn btn-sm btn-ghost';
            bDel.textContent = 'ลบไฟล์';
            bDel.addEventListener('click', () => this.deleteFile(row));

            const bDl = document.createElement('a');
            bDl.className = 'btn btn-sm btn-info';
            bDl.href = row.download_url;
            bDl.download = row.filename;
            bDl.textContent = 'ดาวน์โหลด';

            box.appendChild(bRestore);
            box.appendChild(bDel);
            box.appendChild(bDl);
            return box;
          },
        },
      ],
      { emptyText: 'ยังไม่มีไฟล์สำรอง — กด "สำรองตอนนี้"' }
    );
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
      const data = await apiGet('/api/owner/backups');
      this.canRestore = Boolean(data.can_restore);
      this.restoreBlocker = data.restore_blocker;
      this.subtitleEl.textContent = data.subtitle || '';
      this.shopLabel.textContent = data.restore_status_text || '';
      this.shopLabel.style.color = this.canRestore
        ? 'var(--color-success)'
        : 'var(--color-warning)';
      this.table.setRows(data.backups || []);
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async openFolder() {
    try {
      const res = await apiPost('/api/owner/open_folder', { target: 'backups' });
      this.app.toast(res.message, res.opened ? 'info' : 'warning');
    } catch (err) {
      this.app.toast(err.message, 'warning');
    }
  }

  async backupNow() {
    try {
      const res = await apiPost('/api/owner/backups', {});
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async deleteFile(row) {
    const ok = await confirmDialog(
      `ลบไฟล์สำรอง\n${row.filename} ?\nลบแล้วเอากลับมาไม่ได้`,
      {
        title: 'ลบไฟล์สำรอง',
        confirmText: 'ลบไฟล์',
        danger: true,
      }
    );
    if (!ok) return;
    try {
      const res = await apiDelete(`/api/owner/backups/${row.filename}`);
      this.app.toast(res.message || 'ลบไฟล์สำรองแล้ว', 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async restore(row) {
    await this.refresh();
    if (!this.canRestore && this.restoreBlocker) {
      this.app.toast(`กู้คืนไม่ได้: ${this.restoreBlocker}`, 'error');
      return;
    }

    const ok = await confirmDialog(
      `กู้คืนข้อมูลจากไฟล์\n${row.filename}\n(สร้างเมื่อ ${row.created_at_fmt})\n\nข้อมูลปัจจุบันทั้งหมดจะถูกแทนที่ด้วยข้อมูลในไฟล์นี้ — ระบบจะสำรองข้อมูลปัจจุบันไว้ให้ก่อน`,
      {
        title: 'กู้คืนข้อมูล',
        confirmText: 'ดำเนินการต่อ',
        danger: true,
      }
    );
    if (!ok) return;

    const typed = await askTextDialog(
      `เพื่อความปลอดภัย พิมพ์คำว่า ${CONFIRM_WORD} เพื่อยืนยัน`,
      {
        title: 'ยืนยันการกู้คืน',
        confirmText: 'กู้คืนเดี๋ยวนี้',
        danger: true,
      }
    );
    if (typed === null) return;
    if (typed !== CONFIRM_WORD) {
      this.app.toast(`พิมพ์ไม่ตรง (${CONFIRM_WORD}) — ยกเลิกการกู้คืน`, 'error');
      return;
    }

    try {
      const res = await apiPost(`/api/owner/backups/${row.filename}/restore`, {
        confirm_text: typed,
      });
      await showInfoDialog(res.message, { title: 'กู้คืนสำเร็จ' });
      this.app.showLogin();
    } catch (err) {
      this.app.toast(err.message, 'error');
      await this.refresh();
    }
  }
}
