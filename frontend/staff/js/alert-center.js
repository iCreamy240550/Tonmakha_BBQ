/**
 * frontend/staff/js/alert-center.js — ศูนย์แจ้งเตือนด่วน (แถบแดงใต้แถบบน) + เสียงเตือน WebAudio 3 ครั้ง (1200Hz 250ms)
 * คัดลอกจาก ui/alert_center.py
 */

import { apiGet, apiPost } from '../../shared/js/api.js';
import { confirmDialog } from '../../shared/js/dialogs.js';
import { showToast } from '../../shared/js/toast.js';

const MAX_VISIBLE_ROWS = 5;
const SOUND_PREF_KEY = 'tonmakha_sound_enabled';

let audioCtx = null;

export function unlockAudioContext() {
  try {
    const AudioContextCls = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCls) return;
    if (!audioCtx) {
      audioCtx = new AudioContextCls();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
  } catch (_e) {
    // ignore
  }
}

export function isSoundEnabled() {
  try {
    const v = window.localStorage.getItem(SOUND_PREF_KEY);
    return v !== '0';
  } catch (_e) {
    return true;
  }
}

export function setSoundEnabled(enabled) {
  try {
    window.localStorage.setItem(SOUND_PREF_KEY, enabled ? '1' : '0');
  } catch (_e) {
    // ignore
  }
  if (enabled) {
    unlockAudioContext();
  }
}

export async function playAlertBeep() {
  if (!isSoundEnabled()) return;
  try {
    const AudioContextCls = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCls) return;
    if (!audioCtx) {
      audioCtx = new AudioContextCls();
    }
    if (audioCtx.state === 'suspended') {
      await audioCtx.resume();
    }
    // บี๊บ 3 ครั้ง (1200Hz ครั้งละ 250ms) ตาม winsound.Beep(1200, 250) เดิม
    for (let i = 0; i < 3; i += 1) {
      const startAt = audioCtx.currentTime + i * 0.35;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(1200, startAt);
      gain.gain.setValueAtTime(0.18, startAt);
      gain.gain.exponentialRampToValueAtTime(0.001, startAt + 0.25);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(startAt);
      osc.stop(startAt + 0.25);
    }
  } catch (_e) {
    // หากเบราว์เซอร์บล็อกเสียงจนกว่าผู้ใช้จะคลิก จะไม่ทำให้แอปล่ม
  }
}

export class AlertCenter {
  constructor(container, { onChange = null } = {}) {
    this.container = container;
    this.onChange = onChange;
    this.alerts = [];
    this._sig = '';
    this._timer = null;

    this.el = document.createElement('section');
    this.el.className = 'alert-center hidden';
    if (this.container) {
      this.container.appendChild(this.el);
    }
  }

  start() {
    this.tick(true);
    this.stop();
    this._timer = setInterval(() => {
      if (!document.hidden) {
        this.tick(true);
      }
    }, 30000);
  }

  stop() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  async refreshView(notify = false) {
    return this.tick(false, notify);
  }

  async tick(checkNow = true, forceNotify = false) {
    try {
      const data = await apiGet('/api/staff/alerts', {
        check: checkNow ? 'true' : 'false',
        pop_sound: 'true',
      });
      const alerts = data.alerts || [];
      const nextSig = JSON.stringify(alerts.map((a) => [a.id, a.message]));
      const changed = Boolean(data.changed) || nextSig !== this._sig || forceNotify;
      this._sig = nextSig;
      this.alerts = alerts;
      this._render();

      if (data.play_sound) {
        this.el.classList.add('is-flashing');
        setTimeout(() => this.el.classList.remove('is-flashing'), 1600);
        playAlertBeep();
      }
      if (changed && typeof this.onChange === 'function') {
        this.onChange();
      }
    } catch (_err) {
      // ignore background error
    }
  }

  _render() {
    this.el.textContent = '';
    if (!this.alerts || this.alerts.length === 0) {
      this.el.classList.add('hidden');
      return;
    }
    this.el.classList.remove('hidden');

    const stockCnt = this.alerts.filter((a) => a.is_stock_alert).length;
    const tableCnt = this.alerts.length - stockCnt;
    const parts = [];
    if (tableCnt > 0) parts.push(`โต๊ะเงียบ ${tableCnt}`);
    if (stockCnt > 0) parts.push(`สต๊อก ${stockCnt}`);
    const detailTxt = parts.length > 0 ? parts.join(' · ') : `${this.alerts.length} รายการ`;

    const head = document.createElement('div');
    head.className = 'alert-head';
    head.textContent = `แจ้งเตือนด่วน (${detailTxt})`;
    this.el.appendChild(head);

    for (const alert of this.alerts.slice(0, MAX_VISIBLE_ROWS)) {
      const row = document.createElement('div');
      row.className = 'alert-row';

      const left = document.createElement('div');
      left.className = 'alert-row-left';

      const badge = document.createElement('span');
      badge.className = 'alert-kind-badge';
      badge.style.backgroundColor =
        alert.kind === 'out_of_stock' ? '#5c0f0f' : '#e67700';
      badge.textContent = alert.kind_th || 'แจ้งเตือน';
      left.appendChild(badge);

      const msg = document.createElement('span');
      msg.className = 'alert-msg';
      msg.textContent = alert.message;
      left.appendChild(msg);
      row.appendChild(left);

      const actions = document.createElement('div');
      actions.className = 'alert-row-actions';

      if (alert.is_stock_alert) {
        actions.appendChild(
          this._makeBtn('รับทราบแล้ว', '#2f9e44', () => this._handleCheck(alert))
        );
        actions.appendChild(
          this._makeBtn('ปล่อยไว้', '#e67700', () => this._handleSnooze(alert))
        );
      } else {
        actions.appendChild(
          this._makeBtn('ไปเช็คแล้ว', '#2f9e44', () => this._handleCheck(alert))
        );
        actions.appendChild(
          this._makeBtn('ปล่อยไว้', '#e67700', () => this._handleSnooze(alert))
        );
        actions.appendChild(
          this._makeBtn('ยกเลิกโต๊ะ', '#5c0f0f', () => this._handleCancelTable(alert))
        );
      }

      row.appendChild(actions);
      this.el.appendChild(row);
    }

    if (this.alerts.length > MAX_VISIBLE_ROWS) {
      const more = document.createElement('div');
      more.className = 'alert-more';
      more.textContent = `และอีก ${this.alerts.length - MAX_VISIBLE_ROWS} รายการ`;
      this.el.appendChild(more);
    }
  }

  _makeBtn(text, bg, onClick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm';
    btn.style.backgroundColor = bg;
    btn.style.color = '#ffffff';
    btn.textContent = text;
    btn.addEventListener('click', onClick);
    return btn;
  }

  async _handleCheck(alert) {
    try {
      const res = await apiPost(`/api/staff/alerts/${alert.id}/check`, {});
      showToast(res.message, 'success');
      await this.refreshView(true);
    } catch (err) {
      showToast(err.message || 'ไม่สามารถทำรายการได้', 'error');
    }
  }

  async _handleSnooze(alert) {
    try {
      const res = await apiPost(`/api/staff/alerts/${alert.id}/snooze`, {});
      showToast(res.message, 'success');
      await this.refreshView(true);
    } catch (err) {
      showToast(err.message || 'ไม่สามารถทำรายการได้', 'error');
    }
  }

  async _handleCancelTable(alert) {
    if (alert.is_stock_alert) return;
    const ok = await confirmDialog(
      `ยกเลิกโต๊ะ ${alert.table_no} ใช่หรือไม่?\n(ใช้เมื่อไม่มีลูกค้าจริง/สแกนมั่ว)`,
      {
        title: 'ยกเลิกโต๊ะ',
        confirmText: 'ยกเลิกโต๊ะ',
        danger: true,
      }
    );
    if (!ok) return;
    try {
      const res = await apiPost(`/api/staff/alerts/${alert.id}/cancel_table`, {});
      showToast(res.message, 'success');
      await this.refreshView(true);
    } catch (err) {
      showToast(err.message || 'ไม่สามารถยกเลิกโต๊ะได้', 'error');
    }
  }
}
