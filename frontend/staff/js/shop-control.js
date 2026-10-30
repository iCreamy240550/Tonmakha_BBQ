/**
 * frontend/staff/js/shop-control.js — สวิตช์เปิด/ปิดร้านที่แถบบน (รีเฟรชทุก 15 วินาที)
 * คัดลอกจาก ui/staff/shop_control.py
 */

import { apiGet, apiPost } from '../../shared/js/api.js';
import { confirmDialog } from '../../shared/js/dialogs.js';
import { createStatusBadge } from '../../shared/js/status-badge.js';
import { showToast } from '../../shared/js/toast.js';

export class ShopControl {
  constructor(container, { onStatusChange = null } = {}) {
    this.container = container;
    this.onStatusChange = onStatusChange;
    this.isOpen = false;
    this._timer = null;

    this.el = document.createElement('div');
    this.el.className = 'shop-control-wrap';

    this.badge = createStatusBadge('ร้านปิด', 'var(--color-neutral)');
    this.el.appendChild(this.badge);

    this.button = document.createElement('button');
    this.button.type = 'button';
    this.button.className = 'btn btn-sm btn-success';
    this.button.style.height = '36px';
    this.button.style.minWidth = '110px';
    this.button.textContent = 'เปิดร้าน';
    this.button.addEventListener('click', () => this.toggle());
    this.el.appendChild(this.button);

    if (this.container) {
      this.container.appendChild(this.el);
    }
  }

  start() {
    this.refresh();
    this.stop();
    this._timer = setInterval(() => {
      if (!document.hidden) {
        this.refresh();
      }
    }, 15000);
  }

  stop() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  async refresh() {
    try {
      const data = await apiGet('/api/staff/shop');
      this._applyState(Boolean(data.is_open));
    } catch (_err) {
      // ignore background poll error
    }
  }

  _applyState(opened) {
    this.isOpen = opened;
    this.badge.textContent = opened ? 'ร้านเปิด' : 'ร้านปิด';
    this.badge.style.backgroundColor = opened
      ? 'var(--color-success)'
      : 'var(--color-neutral)';
    this.button.textContent = opened ? 'ปิดร้าน' : 'เปิดร้าน';
    this.button.className = `btn btn-sm ${opened ? 'btn-danger' : 'btn-success'}`;
    this.button.style.height = '36px';
    this.button.style.minWidth = '110px';
  }

  async toggle() {
    try {
      if (!this.isOpen) {
        const res = await apiPost('/api/staff/shop/open', {});
        showToast(res.message || 'เปิดร้านแล้ว ลูกค้าสแกน QR เข้าโต๊ะได้', 'success');
        this._applyState(true);
      } else {
        const ok = await confirmDialog(
          'ปิดร้านใช่หรือไม่?\nลูกค้าจะสแกน QR เข้าโต๊ะไม่ได้',
          {
            title: 'ปิดร้าน',
            confirmText: 'ปิดร้าน',
            danger: true,
          }
        );
        if (!ok) return;

        try {
          const res = await apiPost('/api/staff/shop/close', { force: false });
          showToast(res.message || 'ปิดร้านแล้ว', 'success');
          this._applyState(false);
        } catch (err) {
          if (err.status === 400) {
            const forceOk = await confirmDialog(
              `${err.message}\n\nต้องการปิดร้านทั้งที่ยังมีโต๊ะค้างหรือไม่?`,
              {
                title: 'มีโต๊ะค้างอยู่',
                confirmText: 'ปิดร้านเลย',
                danger: true,
              }
            );
            if (!forceOk) return;
            const res2 = await apiPost('/api/staff/shop/close', { force: true });
            showToast(res2.message || 'ปิดร้านแล้ว', 'success');
            this._applyState(false);
          } else {
            throw err;
          }
        }
      }
      if (typeof this.onStatusChange === 'function') {
        this.onStatusChange();
      }
    } catch (err) {
      showToast(err.message || 'ไม่สามารถเปลี่ยนสถานะร้านได้', 'error');
    }
  }
}
