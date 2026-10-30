/**
 * frontend/staff/js/pages/tables.js — หน้าโต๊ะ: ดูสถานะทุกโต๊ะ ยืนยัน/ยกเลิกโต๊ะที่สแกนเข้ามา ไปชั่ง/ออเดอร์/เช็คบิล/ส่งข้อความ
 * คัดลอกจาก ui/staff/tables_page.py (รีเฟรชทุก 4 วินาที)
 */

import { apiGet, apiPost } from '../../../shared/js/api.js';
import {
  askReasonDialog,
  askTextDialog,
  confirmDialog,
} from '../../../shared/js/dialogs.js';
import { baht } from '../../../shared/js/format.js';
import {
  SESSION_STATUS_TH,
  createStatusBadge,
  statusColor,
} from '../../../shared/js/status-badge.js';

export class TablesPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this._sig = null;
    this._timer = null;
    this._build();
  }

  _build() {
    this.headerEl = document.createElement('div');
    this.headerEl.className = 'page-header audit-block';

    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'สถานะโต๊ะ';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);

    const right = document.createElement('div');
    right.className = 'page-header-right';
    for (const st of ['free', 'pending', 'open', 'awaiting_payment']) {
      right.appendChild(
        createStatusBadge(SESSION_STATUS_TH[st], statusColor(st))
      );
    }

    this.headerEl.appendChild(left);
    this.headerEl.appendChild(right);
    this.container.appendChild(this.headerEl);

    this.gridEl = document.createElement('div');
    this.gridEl.className = 'tables-grid audit-block';
    this.container.appendChild(this.gridEl);
  }

  activate() {
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
      data = await apiGet('/api/staff/tables');
    } catch (_err) {
      return;
    }

    this.subtitleEl.textContent = data.subtitle || '';
    if (data.signature === this._sig) {
      return;
    }
    this._sig = data.signature;

    this.gridEl.textContent = '';
    for (const t of data.tables || []) {
      this.gridEl.appendChild(this._makeCard(t));
    }
  }

  _makeCard(t) {
    const status = t.status;
    const card = document.createElement('div');
    card.className = `table-card status-${status}`;

    const top = document.createElement('div');
    top.className = 'card-top';

    const head = document.createElement('div');
    head.className = 'card-head-row';
    const tblNo = document.createElement('div');
    tblNo.style.fontSize = 'var(--fs-title)';
    tblNo.style.fontWeight = '700';
    tblNo.textContent = `โต๊ะ ${t.table_no}`;
    head.appendChild(tblNo);
    head.appendChild(createStatusBadge(t.status_th, t.status_color));
    top.appendChild(head);

    if (t.name && t.name !== String(t.table_no) && t.name !== `โต๊ะ ${t.table_no}`) {
      const subName = document.createElement('div');
      subName.style.fontSize = 'var(--fs-sm)';
      subName.style.color = 'var(--color-text-muted)';
      subName.textContent = t.name;
      top.appendChild(subName);
    }

    if (status === 'free') {
      const freeTxt = document.createElement('div');
      freeTxt.style.fontSize = 'var(--fs-md)';
      freeTxt.style.color = 'var(--color-text-muted)';
      freeTxt.textContent = 'ว่าง';
      top.appendChild(freeTxt);
      card.appendChild(top);

      const footer = document.createElement('div');
      footer.className = 'card-footer';
      card.appendChild(footer);
      return card;
    }

    const durEl = document.createElement('div');
    durEl.style.fontSize = 'var(--fs-base)';
    durEl.style.color = 'var(--color-text-muted)';
    durEl.textContent = `นั่งมาแล้ว ${t.duration_text || '0 นาที'}`;
    top.appendChild(durEl);

    if (status === 'open' || status === 'awaiting_payment') {
      const totalEl = document.createElement('div');
      totalEl.style.fontSize = 'var(--fs-2xl)';
      totalEl.style.fontWeight = '700';
      totalEl.style.color = 'var(--color-primary)';
      totalEl.className = 'money';
      totalEl.textContent = baht(t.total);
      top.appendChild(totalEl);
    }

    card.appendChild(top);

    const footer = document.createElement('div');
    footer.className = 'card-footer';
    const sid = t.session_id;

    if (status === 'pending') {
      const row1 = document.createElement('div');
      row1.className = 'card-btn-row';
      row1.appendChild(
        this._btn('ยืนยัน', 'success', () => this.confirmSession(sid))
      );
      row1.appendChild(
        this._btn('ยกเลิก', 'danger', () => this.cancelSession(t))
      );
      footer.appendChild(row1);
    } else if (status === 'open') {
      const row1 = document.createElement('div');
      row1.className = 'card-btn-row';
      row1.appendChild(
        this._btn('ชั่ง', 'primary', () =>
          this.app.navigate('weigh', { session_id: sid })
        )
      );
      row1.appendChild(
        this._btn('ออเดอร์', 'info', () =>
          this.app.navigate('orders', { session_id: sid })
        )
      );
      row1.appendChild(
        this._btn('เช็คบิล', 'success', () =>
          this.app.navigate('checkout', { session_id: sid })
        )
      );
      footer.appendChild(row1);

      const row2 = document.createElement('div');
      row2.className = 'card-btn-row';
      row2.appendChild(
        this._btn('ส่งข้อความ', 'ghost', () => this.sendMessage(t))
      );
      row2.appendChild(
        this._btn('ยกเลิกโต๊ะ', 'ghost', () => this.cancelSession(t))
      );
      footer.appendChild(row2);
    } else if (status === 'awaiting_payment') {
      const row1 = document.createElement('div');
      row1.className = 'card-btn-row';
      row1.appendChild(
        this._btn('ไปชำระเงิน', 'info', () =>
          this.app.navigate('checkout', { session_id: sid })
        )
      );
      footer.appendChild(row1);
    }

    card.appendChild(footer);
    return card;
  }

  _btn(text, variant, onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `btn btn-sm btn-${variant}`;
    b.textContent = text;
    b.addEventListener('click', onClick);
    return b;
  }

  async _afterChange() {
    this._sig = null;
    await this.refresh();
    if (this.app.alertCenter) {
      this.app.alertCenter.refreshView(false);
    }
  }

  async confirmSession(sessionId) {
    try {
      const res = await apiPost(`/api/staff/tables/${sessionId}/confirm`, {});
      this.app.toast(res.message || 'ยืนยันโต๊ะแล้ว ลูกค้าสั่งอาหารได้', 'success');
      await this._afterChange();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async cancelSession(t) {
    let reason = 'ไม่มีลูกค้าจริง/สแกนมั่ว';
    if (t.status === 'pending') {
      const ok = await confirmDialog(
        `ยกเลิกโต๊ะ ${t.table_no} ใช่หรือไม่?\n(ใช้เมื่อไม่มีลูกค้าจริง/สแกนมั่ว)`,
        {
          title: 'ยกเลิกโต๊ะ',
          confirmText: 'ยกเลิกโต๊ะ',
          danger: true,
        }
      );
      if (!ok) return;
    } else {
      reason = await askReasonDialog(`เหตุผลที่ยกเลิกโต๊ะ ${t.table_no}`, {
        title: 'ยกเลิกโต๊ะ',
      });
      if (reason === null) return;
    }

    try {
      const res = await apiPost(`/api/staff/tables/${t.session_id}/cancel`, {
        reason,
      });
      this.app.toast(res.message || `ยกเลิกโต๊ะ ${t.table_no} แล้ว`, 'success');
      await this._afterChange();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async sendMessage(t) {
    const msg = await askTextDialog(`ข้อความถึงลูกค้าโต๊ะ ${t.table_no}`, {
      title: 'ส่งข้อความ',
      confirmText: 'ส่ง',
    });
    if (!msg) return;
    try {
      const res = await apiPost(`/api/staff/tables/${t.session_id}/notice`, {
        message: msg,
      });
      this.app.toast(res.message || 'ส่งข้อความแล้ว', 'success');
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }
}
