/**
 * frontend/staff/js/pages/log.js — ประวัติการใช้งาน (activity_log) สำหรับเจ้าของ
 * คัดลอกจาก ui/owner/log_page.py ทุกตัวอักษร (กรอง + แบ่งหน้าละ 100 รายการ)
 */

import { apiGet } from '../../../shared/js/api.js';
import { DataTable } from '../../../shared/js/data-table.js';
import { parse_date } from '../../../shared/js/format.js';

const PAGE_SIZE = 100;

export class LogPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.offset = 0;
    this.total = 0;
    this.filters = {};
    this._optionsLoaded = false;

    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'ประวัติการใช้งาน';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);
    header.appendChild(left);
    this.container.appendChild(header);

    const filtCard = document.createElement('div');
    filtCard.className = 'card audit-block';
    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.alignItems = 'flex-end';
    row.style.gap = 'var(--space-3)';
    row.style.flexWrap = 'wrap';

    const actGroup = document.createElement('div');
    actGroup.className = 'field-group';
    const actLbl = document.createElement('label');
    actLbl.className = 'field-label';
    actLbl.textContent = 'การกระทำ';
    this.actionSelect = document.createElement('select');
    this.actionSelect.className = 'field-select';
    this.actionSelect.style.width = '210px';
    const allAct = document.createElement('option');
    allAct.value = '';
    allAct.textContent = 'ทั้งหมด';
    this.actionSelect.appendChild(allAct);
    actGroup.appendChild(actLbl);
    actGroup.appendChild(this.actionSelect);
    row.appendChild(actGroup);

    const userGroup = document.createElement('div');
    userGroup.className = 'field-group';
    const userLbl = document.createElement('label');
    userLbl.className = 'field-label';
    userLbl.textContent = 'ผู้ใช้';
    this.userSelect = document.createElement('select');
    this.userSelect.className = 'field-select';
    this.userSelect.style.width = '180px';
    const allUsr = document.createElement('option');
    allUsr.value = '';
    allUsr.textContent = 'ทั้งหมด';
    this.userSelect.appendChild(allUsr);
    userGroup.appendChild(userLbl);
    userGroup.appendChild(this.userSelect);
    row.appendChild(userGroup);

    const dfGroup = document.createElement('div');
    dfGroup.className = 'field-group';
    const dfLbl = document.createElement('label');
    dfLbl.className = 'field-label';
    dfLbl.textContent = 'จากวันที่';
    this.dateFromInput = document.createElement('input');
    this.dateFromInput.type = 'text';
    this.dateFromInput.className = 'field-input';
    this.dateFromInput.style.width = '140px';
    this.dateFromInput.placeholder = 'ปี-เดือน-วัน';
    dfGroup.appendChild(dfLbl);
    dfGroup.appendChild(this.dateFromInput);
    row.appendChild(dfGroup);

    const dtGroup = document.createElement('div');
    dtGroup.className = 'field-group';
    const dtLbl = document.createElement('label');
    dtLbl.className = 'field-label';
    dtLbl.textContent = 'ถึงวันที่';
    this.dateToInput = document.createElement('input');
    this.dateToInput.type = 'text';
    this.dateToInput.className = 'field-input';
    this.dateToInput.style.width = '140px';
    this.dateToInput.placeholder = 'ปี-เดือน-วัน';
    dtGroup.appendChild(dtLbl);
    dtGroup.appendChild(this.dateToInput);
    row.appendChild(dtGroup);

    const searchBtn = document.createElement('button');
    searchBtn.type = 'button';
    searchBtn.className = 'btn btn-primary';
    searchBtn.style.height = '42px';
    searchBtn.textContent = 'ค้นหา';
    searchBtn.addEventListener('click', () => this.search());
    row.appendChild(searchBtn);

    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'btn btn-ghost';
    clearBtn.style.height = '42px';
    clearBtn.textContent = 'ล้างตัวกรอง';
    clearBtn.addEventListener('click', () => this.clearFilters());
    row.appendChild(clearBtn);

    filtCard.appendChild(row);
    this.container.appendChild(filtCard);

    const tblHolder = document.createElement('div');
    tblHolder.className = 'audit-block';
    this.container.appendChild(tblHolder);

    this.table = new DataTable(
      tblHolder,
      [
        { key: 'created_at_fmt', title: 'เวลา', weight: 3, min_width: 130, anchor: 'w' },
        { key: 'who', title: 'ผู้ทำ', weight: 2, min_width: 100, anchor: 'w' },
        { key: 'action_th', title: 'การกระทำ', weight: 3, min_width: 150, anchor: 'w' },
        { key: 'detail', title: 'รายละเอียด', weight: 7, min_width: 260, anchor: 'w' },
      ],
      { emptyText: 'ไม่พบประวัติตามเงื่อนไข' }
    );

    const pager = document.createElement('div');
    pager.className = 'audit-block';
    pager.style.display = 'flex';
    pager.style.alignItems = 'center';
    pager.style.gap = 'var(--space-3)';

    this.prevBtn = document.createElement('button');
    this.prevBtn.type = 'button';
    this.prevBtn.className = 'btn btn-sm btn-ghost';
    this.prevBtn.textContent = '◀ ใหม่กว่า';
    this.prevBtn.addEventListener('click', () => this.prevPage());

    this.pageLabel = document.createElement('span');
    this.pageLabel.style.fontSize = 'var(--fs-base)';
    this.pageLabel.style.color = 'var(--color-text-muted)';

    this.nextBtn = document.createElement('button');
    this.nextBtn.type = 'button';
    this.nextBtn.className = 'btn btn-sm btn-ghost';
    this.nextBtn.textContent = 'เก่ากว่า ▶';
    this.nextBtn.addEventListener('click', () => this.nextPage());

    pager.appendChild(this.prevBtn);
    pager.appendChild(this.pageLabel);
    pager.appendChild(this.nextBtn);
    this.container.appendChild(pager);
  }

  activate() {
    this.offset = 0;
    this.search();
  }

  deactivate() {}

  reload() {
    // ไม่รีเฟรชเองตอนแจ้งเตือนเปลี่ยน เพื่อไม่ให้หน้าที่กำลังอ่านเลื่อนหาย (ตาม ui/owner/log_page.py)
  }

  clearFilters() {
    this.actionSelect.value = '';
    this.userSelect.value = '';
    this.dateFromInput.value = '';
    this.dateToInput.value = '';
    this.search();
  }

  search() {
    try {
      const f = parse_date(this.dateFromInput.value, 'วันที่เริ่ม', true);
      const t = parse_date(this.dateToInput.value, 'วันที่สิ้นสุด', true);
      if (f && t && f > t) {
        this.app.toast('วันเริ่มต้องไม่หลังวันสิ้นสุด', 'error');
        return;
      }
      this.filters = {
        action: this.actionSelect.value || '',
        user_id: this.userSelect.value || '',
        date_from: f || '',
        date_to: t || '',
      };
      this.offset = 0;
      this._query();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async _query() {
    try {
      const data = await apiGet('/api/owner/logs', {
        ...this.filters,
        offset: this.offset,
      });
      if (!this._optionsLoaded) {
        this._populateOptions(data.action_options || [], data.user_options || []);
        this._optionsLoaded = true;
      }
      this.total = data.total || 0;
      this.offset = data.offset || 0;
      this.subtitleEl.textContent = data.subtitle || '';
      this.pageLabel.textContent = data.page_label || '';
      this.prevBtn.disabled = !data.has_prev;
      this.nextBtn.disabled = !data.has_next;
      this.table.setRows(data.rows || []);
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  _populateOptions(actions, users) {
    const curAct = this.actionSelect.value;
    this.actionSelect.textContent = '';
    const allAct = document.createElement('option');
    allAct.value = '';
    allAct.textContent = 'ทั้งหมด';
    this.actionSelect.appendChild(allAct);
    for (const a of actions) {
      const opt = document.createElement('option');
      opt.value = a.code;
      opt.textContent = a.label;
      if (a.code === curAct) opt.selected = true;
      this.actionSelect.appendChild(opt);
    }

    const curUser = this.userSelect.value;
    this.userSelect.textContent = '';
    const allUsr = document.createElement('option');
    allUsr.value = '';
    allUsr.textContent = 'ทั้งหมด';
    this.userSelect.appendChild(allUsr);
    for (const u of users) {
      const opt = document.createElement('option');
      opt.value = String(u.id);
      opt.textContent = u.label;
      if (String(u.id) === curUser) opt.selected = true;
      this.userSelect.appendChild(opt);
    }
  }

  prevPage() {
    this.offset = Math.max(0, this.offset - PAGE_SIZE);
    this._query();
  }

  nextPage() {
    if (this.offset + PAGE_SIZE < this.total) {
      this.offset += PAGE_SIZE;
      this._query();
    }
  }
}
