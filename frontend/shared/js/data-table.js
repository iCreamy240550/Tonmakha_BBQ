/**
 * frontend/shared/js/data-table.js — คอมโพเนนต์ตารางกลางตัวเดียว (PLAN §4.3)
 * - ใช้ <table> เดียว (หัวและเนื้อหาอยู่ตารางเดียวกัน; thead แบบ position: sticky)
 * - table-layout: fixed + <colgroup> ที่สร้างจากรายการคอลัมน์ (key, title, weight, min_width, anchor, header_anchor, format, widget)
 * - ทุกคอลัมน์ชิดซ้าย ('w') ยกเว้นคอลัมน์ที่กำหนด 'center' (เช่น รูปภาพ, สถานะ) หรือ 'e'
 * - MAX_ROWS = 300
 */

export const MAX_ROWS = 300;

export class DataTable {
  constructor(
    container,
    columns,
    {
      onSelect = null,
      rowHeight = 48,
      emptyText = 'ไม่มีข้อมูล',
      maxHeight = null,
    } = {}
  ) {
    this.container = container;
    this.columns = columns || [];
    this.onSelect = onSelect;
    this.rowHeight = rowHeight;
    this.emptyText = emptyText;
    this.rows = [];
    this.selected = null;
    this._rowEls = [];

    this.root = document.createElement('div');
    this.root.className = 'data-table-card';
    if (maxHeight) {
      this.root.style.maxHeight = typeof maxHeight === 'number' ? `${maxHeight}px` : maxHeight;
    }

    this.scrollWrap = document.createElement('div');
    this.scrollWrap.className = 'data-table-scroll';

    this.table = document.createElement('table');
    this.table.className = 'data-table';

    this.colgroup = document.createElement('colgroup');
    this._buildColgroup();
    this.table.appendChild(this.colgroup);

    this.thead = document.createElement('thead');
    this._buildHeader();
    this.table.appendChild(this.thead);

    this.tbody = document.createElement('tbody');
    this.table.appendChild(this.tbody);

    this.scrollWrap.appendChild(this.table);
    this.root.appendChild(this.scrollWrap);

    this.emptyEl = document.createElement('div');
    this.emptyEl.className = 'data-table-empty hidden';
    this.emptyEl.textContent = this.emptyText;
    this.root.appendChild(this.emptyEl);

    this.footerNoteEl = document.createElement('div');
    this.footerNoteEl.className = 'data-table-footer-note hidden';
    this.root.appendChild(this.footerNoteEl);

    if (this.container) {
      this.container.appendChild(this.root);
    }
  }

  _buildColgroup() {
    this.colgroup.textContent = '';
    const effWeights = this.columns.map((col) => {
      const titleLen = String(col.title || '').length;
      const headerMin = titleLen * 9 + 20;
      const mw = Math.max(Number(col.min_width) || 45, headerMin);
      return mw;
    });
    const totalWeight = effWeights.reduce((acc, v) => acc + v, 0) || 1;
    this.table.style.minWidth = `${Math.round(totalWeight * 0.76)}px`;
    this.columns.forEach((_col, idx) => {
      const colEl = document.createElement('col');
      const pct = ((effWeights[idx] / totalWeight) * 100).toFixed(4);
      colEl.style.width = `${pct}%`;
      this.colgroup.appendChild(colEl);
    });
  }

  _buildHeader() {
    this.thead.textContent = '';
    const tr = document.createElement('tr');
    for (const col of this.columns) {
      const th = document.createElement('th');
      const anchor = col.header_anchor || col.anchor || 'w';
      th.className = `align-${anchor}`;
      th.dataset.colKey = col.key || '';
      th.dataset.anchor = anchor;
      th.textContent = col.title || '';
      tr.appendChild(th);
    }
    this.thead.appendChild(tr);
  }

  setRows(rows) {
    const prevId = this.selected && this.selected.id !== undefined ? this.selected.id : null;
    this.tbody.textContent = '';
    this._rowEls = [];
    this.rows = Array.isArray(rows) ? [...rows] : [];
    this.selected = null;

    if (this.rows.length === 0) {
      this.emptyEl.textContent = this.emptyText;
      this.emptyEl.classList.remove('hidden');
      this.footerNoteEl.classList.add('hidden');
      return;
    }

    this.emptyEl.classList.add('hidden');
    const slice = this.rows.slice(0, MAX_ROWS);

    slice.forEach((row, idx) => {
      const tr = document.createElement('tr');
      if (idx % 2 === 1) {
        tr.classList.add('row-alt');
      }
      if (this.rowHeight >= 60) {
        tr.classList.add('row-tall');
      }
      if (this.onSelect) {
        tr.style.cursor = 'pointer';
      }

      for (const col of this.columns) {
        const td = document.createElement('td');
        const anchor = col.anchor || 'w';
        td.className = `align-${anchor} ${col.wrap ? 'cell-wrap' : 'cell-nowrap'}`;
        td.dataset.colKey = col.key || '';
        td.dataset.anchor = anchor;

        if (typeof col.widget === 'function') {
          const widgetNode = col.widget(row, td);
          if (widgetNode instanceof Node) {
            td.appendChild(widgetNode);
          }
        } else {
          const rawVal = row[col.key];
          const text =
            typeof col.format === 'function'
              ? col.format(rawVal, row)
              : rawVal === null || rawVal === undefined
              ? ''
              : String(rawVal);
          td.textContent = text;
          td.title = text;
        }
        tr.appendChild(td);
      }

      tr.addEventListener('click', (e) => {
        if (e.target.closest('button, a, input, select')) {
          return;
        }
        this._clickRow(row, true);
      });

      this.tbody.appendChild(tr);
      this._rowEls.push({ row, tr });

      if (prevId !== null && row.id === prevId) {
        this._clickRow(row, false);
      }
    });

    if (this.rows.length > MAX_ROWS) {
      this.footerNoteEl.textContent = `แสดง ${MAX_ROWS} จาก ${this.rows.length} รายการ — กรองข้อมูลเพื่อดูเพิ่ม`;
      this.footerNoteEl.classList.remove('hidden');
    } else {
      this.footerNoteEl.classList.add('hidden');
    }
  }

  _clickRow(row, notify = true) {
    this.selected = row;
    for (const item of this._rowEls) {
      if (item.row === row) {
        item.tr.classList.add('row-selected');
      } else {
        item.tr.classList.remove('row-selected');
      }
    }
    if (notify && typeof this.onSelect === 'function') {
      this.onSelect(row);
    }
  }

  clearSelection() {
    this.selected = null;
    for (const item of this._rowEls) {
      item.tr.classList.remove('row-selected');
    }
  }
}
