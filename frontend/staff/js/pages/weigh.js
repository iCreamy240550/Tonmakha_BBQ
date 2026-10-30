/**
 * frontend/staff/js/pages/weigh.js — หน้าชั่งน้ำหนัก: เลือกโต๊ะ + กรอกน้ำหนัก -> บันทึก (ชั่งครั้งแรก ≥ 1 กก.)
 * คัดลอกจาก ui/staff/weigh_page.py
 */

import { apiGet, apiPost } from '../../../shared/js/api.js';
import { DataTable } from '../../../shared/js/data-table.js';
import { askReasonDialog } from '../../../shared/js/dialogs.js';
import { baht, weight_text } from '../../../shared/js/format.js';

const UNITS = ['ขีด', 'กรัม', 'กิโลกรัม'];

export class WeighPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.sessionId = null;
    this.rate = 299.0;
    this.rateText = 'กิโลกรัมละ 299 บาท';
    this.isFirstWeigh = true;
    this.minFirstGrams = 1000;
    this.firstWeighErrorMsg = 'การชั่งครั้งแรกของโต๊ะต้องมีน้ำหนักอย่างน้อย 1 กิโลกรัม';
    this.unit = 'ขีด';
    this.saving = false;
    this._timer = null;

    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const hLeft = document.createElement('div');
    hLeft.className = 'page-header-left';
    const hTitle = document.createElement('h1');
    hTitle.className = 'page-title';
    hTitle.textContent = 'ชั่งน้ำหนัก';
    const hSub = document.createElement('div');
    hSub.className = 'page-subtitle';
    hSub.textContent =
      'เลือกโต๊ะ กรอกน้ำหนัก แล้วกดบันทึก (ชั่งครั้งแรกของแต่ละโต๊ะต้องอย่างน้อย 1 กก.)';
    hLeft.appendChild(hTitle);
    hLeft.appendChild(hSub);
    header.appendChild(hLeft);
    this.container.appendChild(header);

    const split = document.createElement('div');
    split.className = 'split-layout split-weigh audit-block';

    // ซ้าย: ฟอร์มชั่งน้ำหนัก
    const leftCard = document.createElement('div');
    leftCard.className = 'card';
    leftCard.style.display = 'flex';
    leftCard.style.flexDirection = 'column';
    leftCard.style.gap = 'var(--space-3)';

    const topRow = document.createElement('div');
    topRow.style.display = 'flex';
    topRow.style.alignItems = 'center';
    topRow.style.gap = 'var(--space-3)';
    const tblLbl = document.createElement('label');
    tblLbl.style.fontSize = 'var(--fs-lg)';
    tblLbl.style.fontWeight = '700';
    tblLbl.textContent = 'โต๊ะ';
    this.tableSelect = document.createElement('select');
    this.tableSelect.className = 'field-select';
    this.tableSelect.style.maxWidth = '240px';
    this.tableSelect.addEventListener('change', () => {
      const val = this.tableSelect.value;
      this.sessionId = val ? Number(val) : null;
      this.refresh();
    });
    topRow.appendChild(tblLbl);
    topRow.appendChild(this.tableSelect);
    leftCard.appendChild(topRow);

    const rateBox = document.createElement('div');
    rateBox.className = 'card';
    rateBox.style.backgroundColor = 'var(--color-row-alt)';
    rateBox.style.padding = 'var(--space-3)';
    const rateTitle = document.createElement('div');
    rateTitle.style.fontSize = 'var(--fs-base)';
    rateTitle.style.color = 'var(--color-text-muted)';
    rateTitle.textContent = 'อัตราราคาหมูกระทะชั่งกิโล';
    this.rateLabel = document.createElement('div');
    this.rateLabel.style.fontSize = 'var(--fs-title)';
    this.rateLabel.style.fontWeight = '700';
    this.rateLabel.style.color = 'var(--color-primary)';
    this.rateLabel.textContent = this.rateText;
    rateBox.appendChild(rateTitle);
    rateBox.appendChild(this.rateLabel);
    leftCard.appendChild(rateBox);

    const wRow = document.createElement('div');
    wRow.style.display = 'flex';
    wRow.style.alignItems = 'center';
    wRow.style.gap = 'var(--space-2)';
    wRow.style.flexWrap = 'wrap';
    const wLbl = document.createElement('label');
    wLbl.style.fontSize = 'var(--fs-lg)';
    wLbl.style.fontWeight = '700';
    wLbl.textContent = 'น้ำหนัก';
    this.weightInput = document.createElement('input');
    this.weightInput.type = 'text';
    this.weightInput.className = 'field-input num';
    this.weightInput.style.width = '150px';
    this.weightInput.style.height = '48px';
    this.weightInput.style.fontSize = 'var(--fs-page-title)';
    this.weightInput.style.fontWeight = '700';
    this.weightInput.style.textAlign = 'right';
    this.weightInput.addEventListener('input', () => this._updateCalc());
    this.weightInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        this.save();
      }
    });

    const unitGroup = document.createElement('div');
    unitGroup.className = 'seg-group';
    this.unitBtns = {};
    for (const u of UNITS) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = `seg-btn ${this.unit === u ? 'is-active' : ''}`;
      b.textContent = u;
      b.addEventListener('click', () => {
        this.unit = u;
        for (const [k, btn] of Object.entries(this.unitBtns)) {
          btn.classList.toggle('is-active', k === u);
        }
        this._updateCalc();
      });
      unitGroup.appendChild(b);
      this.unitBtns[u] = b;
    }

    wRow.appendChild(wLbl);
    wRow.appendChild(this.weightInput);
    wRow.appendChild(unitGroup);
    leftCard.appendChild(wRow);

    const quickRow = document.createElement('div');
    quickRow.style.display = 'flex';
    quickRow.style.alignItems = 'center';
    quickRow.style.gap = 'var(--space-2)';
    quickRow.style.flexWrap = 'wrap';
    for (const [label, kheed] of [
      ['+1 ขีด', 1],
      ['+2 ขีด', 2],
      ['+5 ขีด', 5],
      ['+10 ขีด', 10],
    ]) {
      const qb = document.createElement('button');
      qb.type = 'button';
      qb.className = 'btn btn-sm btn-ghost';
      qb.textContent = label;
      qb.addEventListener('click', () => this._addKheed(kheed));
      quickRow.appendChild(qb);
    }
    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'btn btn-sm btn-ghost';
    clearBtn.textContent = 'ล้าง';
    clearBtn.addEventListener('click', () => {
      this.weightInput.value = '';
      this._updateCalc();
    });
    quickRow.appendChild(clearBtn);
    leftCard.appendChild(quickRow);

    this.calcLabel = document.createElement('div');
    this.calcLabel.style.fontSize = 'var(--fs-xl)';
    this.calcLabel.style.fontWeight = '700';
    this.calcLabel.style.whiteSpace = 'pre-line';
    this.calcLabel.style.color = 'var(--color-text-muted)';
    leftCard.appendChild(this.calcLabel);

    this.saveBtn = document.createElement('button');
    this.saveBtn.type = 'button';
    this.saveBtn.className = 'btn btn-lg btn-success';
    this.saveBtn.style.alignSelf = 'flex-start';
    this.saveBtn.style.minWidth = '240px';
    this.saveBtn.textContent = 'บันทึกการชั่ง';
    this.saveBtn.addEventListener('click', () => this.save());
    leftCard.appendChild(this.saveBtn);

    // ขวา: ตารางรายการที่ชั่งแล้ว
    const rightCard = document.createElement('div');
    rightCard.className = 'card';
    rightCard.style.display = 'flex';
    rightCard.style.flexDirection = 'column';
    rightCard.style.gap = 'var(--space-2)';

    const rTitle = document.createElement('div');
    rTitle.style.fontSize = 'var(--fs-xl)';
    rTitle.style.fontWeight = '700';
    rTitle.textContent = 'รายการที่ชั่งแล้ว';
    rightCard.appendChild(rTitle);

    const tblHolder = document.createElement('div');
    tblHolder.style.flex = '1 1 auto';
    rightCard.appendChild(tblHolder);

    this.table = new DataTable(
      tblHolder,
      [
        { key: 'time', title: 'เวลา', weight: 2, min_width: 60, anchor: 'w' },
        { key: 'name', title: 'รายการ', weight: 3, min_width: 110, anchor: 'w' },
        { key: 'weight', title: 'น้ำหนัก', weight: 2, min_width: 85, anchor: 'w' },
        { key: 'amount_fmt', title: 'บาท', weight: 2, min_width: 80, anchor: 'w' },
        {
          key: 'act',
          title: 'จัดการ',
          weight: 2,
          min_width: 75,
          anchor: 'w',
          widget: (row) => {
            const wrap = document.createElement('div');
            wrap.className = 'table-actions';
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-sm btn-ghost';
            btn.textContent = 'ยกเลิก';
            btn.addEventListener('click', () => this.cancelEntry(row));
            wrap.appendChild(btn);
            return wrap;
          },
        },
      ],
      { emptyText: 'ยังไม่มีรายการชั่ง' }
    );

    this.totalLabel = document.createElement('div');
    this.totalLabel.style.fontSize = 'var(--fs-title)';
    this.totalLabel.style.fontWeight = '700';
    this.totalLabel.style.color = 'var(--color-primary)';
    this.totalLabel.style.textAlign = 'right';
    this.totalLabel.textContent = 'รวม 0.00 บาท';
    rightCard.appendChild(this.totalLabel);

    split.appendChild(leftCard);
    split.appendChild(rightCard);
    this.container.appendChild(split);
  }

  activate(params = {}) {
    if (params.session_id !== undefined) {
      this.sessionId = Number(params.session_id);
    }
    this.refresh();
    setTimeout(() => this.weightInput.focus(), 50);
    this._timer = setInterval(() => {
      if (!document.hidden && !document.querySelector('.modal-backdrop')) {
        this.refresh();
      }
    }, 6000);
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
      const data = await apiGet('/api/staff/weigh', {
        session_id: this.sessionId || '',
      });
      this.rate = Number(data.rate || 299);
      this.rateText = data.rate_text || 'กิโลกรัมละ 299 บาท';
      this.rateLabel.textContent = this.rateText;
      this.sessionId = data.selected_session_id;
      this.isFirstWeigh = Boolean(data.is_first_weigh);
      this.minFirstGrams = Number(data.min_first_weigh_grams || 1000);
      this.firstWeighErrorMsg =
        data.first_weigh_error_msg ||
        'การชั่งครั้งแรกของโต๊ะต้องมีน้ำหนักอย่างน้อย 1 กิโลกรัม';

      this.tableSelect.textContent = '';
      const tables = data.tables || [];
      if (tables.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '(ไม่มีโต๊ะที่ใช้งาน)';
        this.tableSelect.appendChild(opt);
      } else {
        for (const t of tables) {
          const opt = document.createElement('option');
          opt.value = String(t.session_id);
          opt.textContent = t.label;
          if (t.session_id === this.sessionId) {
            opt.selected = true;
          }
          this.tableSelect.appendChild(opt);
        }
      }

      this.table.setRows(data.entries || []);
      this.totalLabel.textContent = data.total_text || 'รวม 0.00 บาท';
      this._updateCalc();
    } catch (_err) {
      // ignore
    }
  }

  _grams() {
    const text = (this.weightInput.value || '').trim().replace(/,/g, '');
    if (!text) return null;
    const val = Number(text);
    if (!Number.isFinite(val) || val <= 0) return null;
    if (this.unit === 'ขีด') {
      return Math.round(val * 100);
    }
    if (this.unit === 'กิโลกรัม') {
      return Math.round(val * 1000);
    }
    return Math.round(val);
  }

  _addKheed(kheed) {
    const text = (this.weightInput.value || '').trim();
    const cur = Number(text) || 0;
    let delta = kheed;
    if (this.unit === 'กรัม') delta = kheed * 100;
    else if (this.unit === 'กิโลกรัม') delta = kheed / 10.0;
    const nextVal = Number((cur + delta).toFixed(4));
    this.weightInput.value = String(nextVal);
    this._updateCalc();
  }

  _updateCalc() {
    const grams = this._grams();
    if (grams === null) {
      const hint = this.isFirstWeigh ? ' (การชั่งครั้งแรกต้องอย่างน้อย 1 กก.)' : '';
      this.calcLabel.textContent = `อัตรา ${this.rateText} — กรอกน้ำหนักเพื่อดูราคา${hint}`;
      this.calcLabel.style.color = 'var(--color-text-muted)';
      return;
    }
    const amount = Math.round(((grams / 1000) * this.rate + Number.EPSILON) * 100) / 100;
    if (this.isFirstWeigh && grams < this.minFirstGrams) {
      this.calcLabel.textContent = `น้ำหนัก ${weight_text(grams)} (${grams.toLocaleString('en-US')} กรัม) = ${baht(amount)}\n⚠️ ${this.firstWeighErrorMsg}`;
      this.calcLabel.style.color = 'var(--color-danger)';
      return;
    }
    this.calcLabel.textContent = `น้ำหนัก ${weight_text(grams)} (${grams.toLocaleString('en-US')} กรัม)\n${this.rateText}  =  ${baht(amount)}`;
    this.calcLabel.style.color = 'var(--color-text)';
  }

  async save() {
    if (this.saving) return;
    if (!this.sessionId) {
      this.app.toast('ยังไม่ได้เลือกโต๊ะ', 'error');
      return;
    }
    const grams = this._grams();
    if (grams === null) {
      this.app.toast('กรุณากรอกน้ำหนักเป็นตัวเลขมากกว่า 0', 'error');
      return;
    }
    if (this.isFirstWeigh && grams < this.minFirstGrams) {
      this.app.toast(this.firstWeighErrorMsg, 'error');
      this._updateCalc();
      return;
    }

    this.saving = true;
    try {
      const res = await apiPost('/api/staff/weigh', {
        session_id: this.sessionId,
        weight_grams: grams,
      });
      this.app.toast(res.message, 'success');
      this.weightInput.value = '';
      await this.refresh();
      if (this.app.alertCenter) {
        this.app.alertCenter.refreshView(false);
      }
      this.weightInput.focus();
    } catch (err) {
      this.app.toast(err.message, 'error');
    } finally {
      this.saving = false;
    }
  }

  async cancelEntry(entry) {
    const reason = await askReasonDialog(
      `เหตุผลที่ยกเลิก ${entry.name_snapshot} ${weight_text(entry.weight_grams)}`,
      { title: 'ยกเลิกรายการชั่ง' }
    );
    if (reason === null) return;
    try {
      const res = await apiPost(`/api/staff/weigh/${entry.id}/cancel`, {
        reason,
      });
      this.app.toast(res.message || 'ยกเลิกรายการชั่งแล้ว', 'success');
      await this.refresh();
      if (this.app.alertCenter) {
        this.app.alertCenter.refreshView(false);
      }
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }
}
