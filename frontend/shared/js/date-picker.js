/**
 * frontend/shared/js/date-picker.js — ปฏิทินเลือกวันที่ พ.ศ. (ThaiDatePickerDialog & DatePickerField)
 * คัดลอกจาก ui/owner/_common.py (เลือกปี พ.ศ., เดือน, วันที่ แบบปฏิทิน ไม่ต้องพิมพ์เอง)
 */

import { BaseDialog } from './dialogs.js';
import {
  THAI_MONTHS,
  THAI_WEEKDAYS,
  ce_to_be_year,
  be_to_ce_year,
  format_thai_date,
  parse_date,
} from './format.js';

function todayIso() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function parseIsoParts(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || '').trim());
  if (!m) {
    const t = new Date();
    return { year: t.getFullYear(), month: t.getMonth() + 1, day: t.getDate() };
  }
  return {
    year: Number(m[1]),
    month: Number(m[2]),
    day: Number(m[3]),
  };
}

function makeIso(year, month, day) {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

export class ThaiDatePickerDialog extends BaseDialog {
  constructor({ initialIso = null, title = 'เลือกวันที่' } = {}) {
    super(title, { width: 420 });
    const tIso = todayIso();
    let initIso = tIso;
    if (initialIso) {
      try {
        const parsed = parse_date(initialIso, 'วันที่', true);
        if (parsed) initIso = parsed;
      } catch (_e) {
        initIso = tIso;
      }
    }

    const initParts = parseIsoParts(initIso);
    const todayParts = parseIsoParts(tIso);
    this.selectedIso = initIso;
    this.viewCeYear = initParts.year;
    this.viewMonth = initParts.month;

    const minCe = Math.min(todayParts.year - 10, this.viewCeYear - 2);
    const maxCe = Math.max(todayParts.year + 5, this.viewCeYear + 2);
    this.yearList = [];
    for (let y = maxCe; y >= minCe; y -= 1) {
      this.yearList.push(y);
    }

    this._buildCalendarUI();
    this._renderCalendar();
  }

  _buildCalendarUI() {
    const nav = document.createElement('div');
    nav.className = 'cal-nav';

    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'btn btn-sm btn-ghost';
    prevBtn.style.minWidth = '36px';
    prevBtn.textContent = '◀';
    prevBtn.addEventListener('click', () => this._prevMonth());

    const navCenter = document.createElement('div');
    navCenter.className = 'cal-nav-center';

    this.monthSelect = document.createElement('select');
    this.monthSelect.className = 'field-select';
    THAI_MONTHS.forEach((mName, idx) => {
      const opt = document.createElement('option');
      opt.value = String(idx + 1);
      opt.textContent = mName;
      this.monthSelect.appendChild(opt);
    });
    this.monthSelect.value = String(this.viewMonth);
    this.monthSelect.addEventListener('change', () => {
      this.viewMonth = Number(this.monthSelect.value);
      this._renderCalendar();
    });

    this.yearSelect = document.createElement('select');
    this.yearSelect.className = 'field-select';
    this._populateYearOptions();
    this.yearSelect.value = String(this.viewCeYear);
    this.yearSelect.addEventListener('change', () => {
      this.viewCeYear = be_to_ce_year(Number(this.yearSelect.value));
      this._renderCalendar();
    });

    navCenter.appendChild(this.monthSelect);
    navCenter.appendChild(this.yearSelect);

    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'btn btn-sm btn-ghost';
    nextBtn.style.minWidth = '36px';
    nextBtn.textContent = '▶';
    nextBtn.addEventListener('click', () => this._nextMonth());

    nav.appendChild(prevBtn);
    nav.appendChild(navCenter);
    nav.appendChild(nextBtn);
    this.body.appendChild(nav);

    const wkRow = document.createElement('div');
    wkRow.className = 'cal-weekdays';
    for (const wd of THAI_WEEKDAYS) {
      const cell = document.createElement('div');
      cell.textContent = wd;
      wkRow.appendChild(cell);
    }
    this.body.appendChild(wkRow);

    this.daysGrid = document.createElement('div');
    this.daysGrid.className = 'cal-days-grid';
    this.body.appendChild(this.daysGrid);

    const footInfo = document.createElement('div');
    footInfo.className = 'cal-foot-info';
    this.selectedLabel = document.createElement('div');
    this.selectedLabel.className = 'cal-selected-label';
    const todayBtn = document.createElement('button');
    todayBtn.type = 'button';
    todayBtn.className = 'btn btn-sm btn-ghost';
    todayBtn.textContent = 'วันนี้';
    todayBtn.addEventListener('click', () => this._pickToday());
    footInfo.appendChild(this.selectedLabel);
    footInfo.appendChild(todayBtn);
    this.body.appendChild(footInfo);

    this.addButtons({
      confirmText: 'ตกลง',
      cancelText: 'ยกเลิก',
      variant: 'primary',
      onConfirm: () => this.close(this.selectedIso),
    });
  }

  _populateYearOptions() {
    this.yearSelect.textContent = '';
    if (!this.yearList.includes(this.viewCeYear)) {
      this.yearList.push(this.viewCeYear);
      this.yearList.sort((a, b) => b - a);
    }
    for (const ceY of this.yearList) {
      const opt = document.createElement('option');
      opt.value = String(ceY);
      opt.textContent = `พ.ศ. ${ce_to_be_year(ceY)}`;
      this.yearSelect.appendChild(opt);
    }
  }

  _syncMenus() {
    this.monthSelect.value = String(this.viewMonth);
    this._populateYearOptions();
    this.yearSelect.value = String(this.viewCeYear);
  }

  _prevMonth() {
    if (this.viewMonth === 1) {
      this.viewMonth = 12;
      this.viewCeYear -= 1;
    } else {
      this.viewMonth -= 1;
    }
    this._syncMenus();
    this._renderCalendar();
  }

  _nextMonth() {
    if (this.viewMonth === 12) {
      this.viewMonth = 1;
      this.viewCeYear += 1;
    } else {
      this.viewMonth += 1;
    }
    this._syncMenus();
    this._renderCalendar();
  }

  _pickToday() {
    const tIso = todayIso();
    const parts = parseIsoParts(tIso);
    this.selectedIso = tIso;
    this.viewCeYear = parts.year;
    this.viewMonth = parts.month;
    this._syncMenus();
    this._renderCalendar();
  }

  _pickDay(dayNum) {
    this.selectedIso = makeIso(this.viewCeYear, this.viewMonth, dayNum);
    this.close(this.selectedIso);
  }

  _renderCalendar() {
    this.daysGrid.textContent = '';
    const firstDay = new Date(this.viewCeYear, this.viewMonth - 1, 1);
    // วันจันทร์เป็นวันแรก (0..6)
    const startOffset = (firstDay.getDay() + 6) % 7;
    const daysInMonth = new Date(this.viewCeYear, this.viewMonth, 0).getDate();
    const tIso = todayIso();

    for (let i = 0; i < startOffset; i += 1) {
      const empty = document.createElement('div');
      empty.className = 'cal-day-empty';
      this.daysGrid.appendChild(empty);
    }

    for (let d = 1; d <= daysInMonth; d += 1) {
      const curIso = makeIso(this.viewCeYear, this.viewMonth, d);
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'cal-day-btn';
      if (curIso === this.selectedIso) {
        btn.classList.add('is-selected');
      } else if (curIso === tIso) {
        btn.classList.add('is-today');
      }
      btn.textContent = String(d);
      btn.addEventListener('click', () => this._pickDay(d));
      this.daysGrid.appendChild(btn);
    }

    this.selectedLabel.textContent = `เลือก: ${format_thai_date(this.selectedIso, true)}`;
  }
}

export class DatePickerField {
  constructor({
    label = 'วันที่',
    initialIso = null,
    allowEmpty = false,
    onChange = null,
  } = {}) {
    this.labelText = label;
    this.allowEmpty = allowEmpty;
    this.onChange = onChange;
    this._isoValue = '';

    this.el = document.createElement('div');
    this.el.className = 'field-group';

    if (label) {
      this.labelEl = document.createElement('label');
      this.labelEl.className = 'field-label';
      this.labelEl.textContent = label;
      this.el.appendChild(this.labelEl);
    }

    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.alignItems = 'center';
    row.style.gap = 'var(--space-1)';

    this.button = document.createElement('button');
    this.button.type = 'button';
    this.button.className = 'date-picker-btn';
    this.button.addEventListener('click', () => this.openPicker());
    row.appendChild(this.button);

    if (allowEmpty) {
      this.clearBtn = document.createElement('button');
      this.clearBtn.type = 'button';
      this.clearBtn.className = 'btn btn-sm btn-ghost';
      this.clearBtn.style.minWidth = '36px';
      this.clearBtn.style.height = 'var(--input-h)';
      this.clearBtn.textContent = '✕';
      this.clearBtn.title = 'ล้างวันที่';
      this.clearBtn.addEventListener('click', () => this.clear(true));
      row.appendChild(this.clearBtn);
    }

    this.el.appendChild(row);

    if (initialIso) {
      this.set(initialIso, false);
    } else if (!allowEmpty) {
      this.set(todayIso(), false);
    } else {
      this._updateDisplay();
    }
  }

  _updateDisplay() {
    if (!this._isoValue) {
      this.button.textContent = '📅 เลือกวันที่ (พ.ศ.)';
      this.button.classList.add('is-empty');
    } else {
      this.button.textContent = `📅 ${format_thai_date(this._isoValue, true)}`;
      this.button.classList.remove('is-empty');
    }
  }

  async openPicker() {
    const dlg = new ThaiDatePickerDialog({
      initialIso: this._isoValue || todayIso(),
      title: `เลือก${this.labelText}`,
    });
    const chosen = await dlg.show();
    if (chosen) {
      this.set(chosen, true);
    }
  }

  get() {
    return this._isoValue;
  }

  getThaiText() {
    return this._isoValue ? format_thai_date(this._isoValue, false) : '';
  }

  set(value, notify = false) {
    if (value === null || value === undefined || String(value).trim() === '') {
      this._isoValue = this.allowEmpty ? '' : todayIso();
    } else {
      this._isoValue = parse_date(String(value), this.labelText, this.allowEmpty);
    }
    this._updateDisplay();
    if (notify && typeof this.onChange === 'function') {
      this.onChange(this._isoValue);
    }
  }

  clear(notify = false) {
    this.set(this.allowEmpty ? '' : todayIso(), notify);
  }
}
