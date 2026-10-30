/**
 * frontend/staff/js/pages/dashboard.js — แดชบอร์ดและรายงานยอดขายของเจ้าของร้าน
 * คัดลอกจาก ui/owner/dashboard_page.py (ภาพรวมวันนี้ + รายงานตามช่วงวันที่ พ.ศ. 5 แท็บ + ส่งออก CSV)
 */

import { apiGet, apiPost } from '../../../shared/js/api.js';
import { DataTable } from '../../../shared/js/data-table.js';
import { DatePickerField } from '../../../shared/js/date-picker.js';
import { baht, fmt_qty, money, parse_date } from '../../../shared/js/format.js';

const TABS = ['รายวัน', 'รายชั่วโมง', 'เมนูขายดี', 'รายการยกเลิก', 'บิล'];

function makePropBar(fraction, color = 'var(--color-primary)') {
  const track = document.createElement('div');
  track.className = 'prop-bar-track';
  const fill = document.createElement('div');
  fill.className = 'prop-bar-fill';
  const pct = Math.max(0, Math.min(100, Number(fraction || 0) * 100));
  fill.style.width = `${pct.toFixed(1)}%`;
  fill.style.backgroundColor = color;
  track.appendChild(fill);
  return track;
}

function createStatTile(title, color = 'var(--color-text)') {
  const card = document.createElement('div');
  card.className = 'stat-tile';
  const t = document.createElement('div');
  t.className = 'stat-title';
  t.textContent = title;
  const v = document.createElement('div');
  v.className = 'stat-value';
  v.style.color = color;
  v.textContent = '-';
  const h = document.createElement('div');
  h.className = 'stat-hint';
  card.appendChild(t);
  card.appendChild(v);
  card.appendChild(h);
  return {
    el: card,
    set(val, hint = '') {
      v.textContent = val;
      h.textContent = hint || '';
    },
  };
}

export class DashboardPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.currentTab = TABS[0];
    this.barMax = { daily: 1, hourly: 1, top: 1 };
    this._timer = null;

    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'แดชบอร์ดและรายงาน';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);

    const right = document.createElement('div');
    right.className = 'page-header-right';
    const openBtn = document.createElement('button');
    openBtn.type = 'button';
    openBtn.className = 'btn btn-ghost';
    openBtn.textContent = 'เปิดโฟลเดอร์ exports';
    openBtn.addEventListener('click', () => this.openExportsFolder());
    const csvBtn = document.createElement('button');
    csvBtn.type = 'button';
    csvBtn.className = 'btn btn-success';
    csvBtn.textContent = 'ส่งออก CSV';
    csvBtn.addEventListener('click', () => this.exportCsv());
    right.appendChild(openBtn);
    right.appendChild(csvBtn);

    header.appendChild(left);
    header.appendChild(right);
    this.container.appendChild(header);

    // ส่วนที่ 1: ภาพรวมสถานะร้านวันนี้
    const sec1Title = document.createElement('h2');
    sec1Title.className = 'audit-block';
    sec1Title.style.fontSize = 'var(--fs-xl)';
    sec1Title.style.fontWeight = '700';
    sec1Title.textContent = 'ภาพรวมสถานะร้านวันนี้';
    this.container.appendChild(sec1Title);

    const tilesGrid = document.createElement('div');
    tilesGrid.className = 'stat-grid audit-block';
    this.tileSales = createStatTile('ยอดขายวันนี้', 'var(--color-primary)');
    this.tileBills = createStatTile('จำนวนบิลวันนี้');
    this.tileAvg = createStatTile('เฉลี่ยต่อบิลวันนี้');
    this.tileDiscount = createStatTile('ส่วนลดวันนี้', 'var(--color-warning)');
    this.tileTables = createStatTile('โต๊ะที่ใช้งาน', 'var(--color-success)');
    this.tilePending = createStatTile('รอยืนยัน', 'var(--color-warning)');
    this.tilePay = createStatTile('รอชำระเงิน', 'var(--color-info)');
    this.tileAlerts = createStatTile('แจ้งเตือนด่วน', 'var(--color-danger)');
    for (const t of [
      this.tileSales,
      this.tileBills,
      this.tileAvg,
      this.tileDiscount,
      this.tileTables,
      this.tilePending,
      this.tilePay,
      this.tileAlerts,
    ]) {
      tilesGrid.appendChild(t.el);
    }
    this.container.appendChild(tilesGrid);

    const lowerGrid = document.createElement('div');
    lowerGrid.className = 'split-dashboard-two cards-grid audit-block';

    const lowCard = document.createElement('div');
    lowCard.className = 'card';
    lowCard.style.display = 'flex';
    lowCard.style.flexDirection = 'column';
    lowCard.style.gap = 'var(--space-2)';
    const lowHead = document.createElement('div');
    lowHead.style.display = 'flex';
    lowHead.style.alignItems = 'center';
    lowHead.style.justifyContent = 'space-between';
    const lowTitle = document.createElement('div');
    lowTitle.style.fontSize = 'var(--fs-xl)';
    lowTitle.style.fontWeight = '700';
    lowTitle.textContent = 'สต๊อกใกล้หมด';
    const goStockBtn = document.createElement('button');
    goStockBtn.type = 'button';
    goStockBtn.className = 'btn btn-sm btn-ghost';
    goStockBtn.textContent = 'ไปหน้าสต๊อก';
    goStockBtn.addEventListener('click', () => this.app.navigate('stock'));
    lowHead.appendChild(lowTitle);
    lowHead.appendChild(goStockBtn);
    lowCard.appendChild(lowHead);
    this.lowArea = document.createElement('div');
    this.lowArea.style.display = 'flex';
    this.lowArea.style.flexDirection = 'column';
    this.lowArea.style.gap = 'var(--space-1)';
    lowCard.appendChild(this.lowArea);

    const payCard = document.createElement('div');
    payCard.className = 'card';
    payCard.style.display = 'flex';
    payCard.style.flexDirection = 'column';
    payCard.style.gap = 'var(--space-2)';
    const payTitle = document.createElement('div');
    payTitle.style.fontSize = 'var(--fs-xl)';
    payTitle.style.fontWeight = '700';
    payTitle.textContent = 'ยอดขายวันนี้แยกตามช่องทางชำระ';
    payCard.appendChild(payTitle);
    this.payArea = document.createElement('div');
    this.payArea.style.display = 'flex';
    this.payArea.style.flexDirection = 'column';
    this.payArea.style.gap = 'var(--space-2)';
    payCard.appendChild(this.payArea);
    this.cancelTodayLabel = document.createElement('div');
    this.cancelTodayLabel.style.fontSize = 'var(--fs-base)';
    this.cancelTodayLabel.style.color = 'var(--color-text-muted)';
    payCard.appendChild(this.cancelTodayLabel);

    lowerGrid.appendChild(lowCard);
    lowerGrid.appendChild(payCard);
    this.container.appendChild(lowerGrid);

    // ส่วนที่ 2: รายงานยอดขายและธุรกรรมตามช่วงวันที่
    const repHead = document.createElement('div');
    repHead.className = 'audit-block';
    repHead.style.display = 'flex';
    repHead.style.alignItems = 'baseline';
    repHead.style.gap = 'var(--space-3)';
    const repTitle = document.createElement('h2');
    repTitle.style.fontSize = 'var(--fs-2xl)';
    repTitle.style.fontWeight = '700';
    repTitle.textContent = 'รายงานยอดขายและธุรกรรมตามช่วงวันที่';
    this.reportRangeLabel = document.createElement('span');
    this.reportRangeLabel.style.fontSize = 'var(--fs-base)';
    this.reportRangeLabel.style.color = 'var(--color-text-muted)';
    repHead.appendChild(repTitle);
    repHead.appendChild(this.reportRangeLabel);
    this.container.appendChild(repHead);

    const filtCard = document.createElement('div');
    filtCard.className = 'card audit-block';
    const filtRow = document.createElement('div');
    filtRow.style.display = 'flex';
    filtRow.style.alignItems = 'flex-end';
    filtRow.style.gap = 'var(--space-3)';
    filtRow.style.flexWrap = 'wrap';

    this.dateFromField = new DatePickerField({
      label: 'จากวันที่ (พ.ศ.)',
      onChange: () => this.showReport(),
    });
    this.dateToField = new DatePickerField({
      label: 'ถึงวันที่ (พ.ศ.)',
      onChange: () => this.showReport(),
    });
    filtRow.appendChild(this.dateFromField.el);
    filtRow.appendChild(this.dateToField.el);

    const showBtn = document.createElement('button');
    showBtn.type = 'button';
    showBtn.className = 'btn btn-primary';
    showBtn.style.height = '42px';
    showBtn.textContent = 'แสดงรายงาน';
    showBtn.addEventListener('click', () => this.showReport());
    filtRow.appendChild(showBtn);

    const quickGroup = document.createElement('div');
    quickGroup.style.display = 'flex';
    quickGroup.style.gap = 'var(--space-1)';
    quickGroup.style.flexWrap = 'wrap';
    for (const [lbl, k] of [
      ['วันนี้', 'today'],
      ['เมื่อวาน', 'yesterday'],
      ['7 วัน', '7days'],
      ['เดือนนี้', 'month'],
      ['เดือนที่แล้ว', 'lastmonth'],
    ]) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-sm btn-ghost';
      b.textContent = lbl;
      b.addEventListener('click', () => this.loadReport({ quick: k }));
      quickGroup.appendChild(b);
    }
    filtRow.appendChild(quickGroup);
    filtCard.appendChild(filtRow);
    this.container.appendChild(filtCard);

    const rTilesGrid = document.createElement('div');
    rTilesGrid.className = 'stat-grid audit-block';
    this.rtileTotal = createStatTile('ยอดสุทธิ (ช่วงที่เลือก)', 'var(--color-primary)');
    this.rtileBills = createStatTile('จำนวนบิล');
    this.rtileAvg = createStatTile('เฉลี่ยต่อบิล');
    this.rtilePay = createStatTile('ช่องทางชำระ', 'var(--color-info)');
    this.rtileSubtotal = createStatTile('ยอดรวมก่อนส่วนลด');
    this.rtileDiscount = createStatTile('ส่วนลด', 'var(--color-warning)');
    this.rtileService = createStatTile('ค่าบริการ');
    this.rtileVat = createStatTile('ภาษีมูลค่าเพิ่ม');
    for (const rt of [
      this.rtileTotal,
      this.rtileBills,
      this.rtileAvg,
      this.rtilePay,
      this.rtileSubtotal,
      this.rtileDiscount,
      this.rtileService,
      this.rtileVat,
    ]) {
      rTilesGrid.appendChild(rt.el);
    }
    this.container.appendChild(rTilesGrid);

    const tabSegWrap = document.createElement('div');
    tabSegWrap.className = 'audit-block';
    const tabSeg = document.createElement('div');
    tabSeg.className = 'seg-group';
    this.tabBtns = {};
    for (const tName of TABS) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = `seg-btn ${tName === this.currentTab ? 'is-active' : ''}`;
      b.textContent = tName;
      b.addEventListener('click', () => this._selectTab(tName));
      tabSeg.appendChild(b);
      this.tabBtns[tName] = b;
    }
    tabSegWrap.appendChild(tabSeg);
    this.container.appendChild(tabSegWrap);

    this.tabArea = document.createElement('div');
    this.tabArea.className = 'audit-block';
    this.container.appendChild(this.tabArea);

    this.tables = {
      รายวัน: new DataTable(
        this.tabArea,
        [
          { key: 'date_be_label', title: 'วันที่ (พ.ศ.)', weight: 2, min_width: 120, anchor: 'w' },
          { key: 'bill_count', title: 'บิล', weight: 1, min_width: 60, anchor: 'w' },
          {
            key: 'total',
            title: 'ยอดขาย (บาท)',
            weight: 2,
            min_width: 120,
            anchor: 'w',
            format: (v) => money(v),
          },
          {
            key: 'bar',
            title: 'สัดส่วน',
            weight: 4,
            min_width: 160,
            anchor: 'w',
            widget: (r) => makePropBar((r.total || 0) / (this.barMax.daily || 1)),
          },
        ],
        { emptyText: 'ไม่มีข้อมูลในช่วงวันที่เลือก' }
      ),
      รายชั่วโมง: new DataTable(
        this.tabArea,
        [
          { key: 'hour_label', title: 'ช่วงเวลา', weight: 2, min_width: 110, anchor: 'w' },
          { key: 'bill_count', title: 'บิล', weight: 1, min_width: 60, anchor: 'w' },
          {
            key: 'total',
            title: 'ยอดขาย (บาท)',
            weight: 2,
            min_width: 120,
            anchor: 'w',
            format: (v) => money(v),
          },
          {
            key: 'bar',
            title: 'สัดส่วน',
            weight: 4,
            min_width: 160,
            anchor: 'w',
            widget: (r) => makePropBar((r.total || 0) / (this.barMax.hourly || 1)),
          },
        ],
        { emptyText: 'ไม่มีข้อมูลในช่วงวันที่เลือก' }
      ),
      เมนูขายดี: new DataTable(
        this.tabArea,
        [
          { key: 'rank', title: '#', weight: 1, min_width: 45, anchor: 'w' },
          { key: 'name', title: 'เมนู', weight: 4, min_width: 140, anchor: 'w' },
          { key: 'qty_label', title: 'ขายได้', weight: 2, min_width: 100, anchor: 'w' },
          {
            key: 'amount',
            title: 'ยอดเงิน (บาท)',
            weight: 2,
            min_width: 120,
            anchor: 'w',
            format: (v) => money(v),
          },
          {
            key: 'bar',
            title: 'สัดส่วน',
            weight: 3,
            min_width: 140,
            anchor: 'w',
            widget: (r) => makePropBar((r.amount || 0) / (this.barMax.top || 1)),
          },
        ],
        { emptyText: 'ยังไม่มีรายการขายในช่วงวันที่เลือก' }
      ),
      รายการยกเลิก: new DataTable(
        this.tabArea,
        [
          { key: 'at_fmt', title: 'เวลา', weight: 3, min_width: 120, anchor: 'w' },
          { key: 'kind_th', title: 'ประเภท', weight: 2, min_width: 100, anchor: 'w' },
          { key: 'table_no', title: 'โต๊ะ', weight: 1, min_width: 55, anchor: 'w' },
          { key: 'name', title: 'รายการ', weight: 3, min_width: 120, anchor: 'w' },
          { key: 'amount_fmt', title: 'มูลค่า', weight: 2, min_width: 85, anchor: 'w' },
          { key: 'reason', title: 'เหตุผล', weight: 4, min_width: 150, anchor: 'w' },
          { key: 'by', title: 'โดย', weight: 2, min_width: 80, anchor: 'w' },
        ],
        { emptyText: 'ไม่มีรายการยกเลิกในช่วงวันที่เลือก' }
      ),
      บิล: new DataTable(
        this.tabArea,
        [
          { key: 'id', title: 'บิล', weight: 1, min_width: 50, anchor: 'w' },
          { key: 'paid_at_fmt', title: 'ชำระเมื่อ', weight: 3, min_width: 120, anchor: 'w' },
          { key: 'table_no', title: 'โต๊ะ', weight: 1, min_width: 50, anchor: 'w' },
          {
            key: 'subtotal',
            title: 'รวม',
            weight: 2,
            min_width: 80,
            anchor: 'w',
            format: (v) => money(v),
          },
          {
            key: 'discount',
            title: 'ลด',
            weight: 2,
            min_width: 70,
            anchor: 'w',
            format: (v) => (v ? money(v) : '-'),
          },
          {
            key: 'total',
            title: 'สุทธิ',
            weight: 2,
            min_width: 90,
            anchor: 'w',
            format: (v) => money(v),
          },
          { key: 'payment_method_th', title: 'ชำระด้วย', weight: 2, min_width: 95, anchor: 'w' },
          {
            key: 'cashier_name',
            title: 'ผู้รับเงิน',
            weight: 2,
            min_width: 95,
            anchor: 'w',
            format: (v) => v || '-',
          },
        ],
        { emptyText: 'ไม่มีบิลในช่วงวันที่เลือก' }
      ),
    };

    for (const [k, tbl] of Object.entries(this.tables)) {
      if (k !== this.currentTab) {
        tbl.root.classList.add('hidden');
      }
    }

    this.noteEl = document.createElement('div');
    this.noteEl.className = 'audit-block';
    this.noteEl.style.fontSize = 'var(--fs-sm)';
    this.noteEl.style.color = 'var(--color-text-muted)';
    this.container.appendChild(this.noteEl);
  }

  _selectTab(name) {
    this.currentTab = name;
    for (const [k, b] of Object.entries(this.tabBtns)) {
      b.classList.toggle('is-active', k === name);
    }
    for (const [k, tbl] of Object.entries(this.tables)) {
      tbl.root.classList.toggle('hidden', k !== name);
    }
  }

  activate() {
    this.refresh();
    this._timer = setInterval(() => {
      if (!document.hidden && !document.querySelector('.modal-backdrop')) {
        this.refreshOverview();
      }
    }, 15000);
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
    await Promise.all([
      this.refreshOverview(),
      this.loadReport({
        date_from: this.dateFromField.get(),
        date_to: this.dateToField.get(),
      }),
    ]);
  }

  async refreshOverview() {
    try {
      const data = await apiGet('/api/owner/dashboard/overview');
      const sales = data.sales;
      this.subtitleEl.textContent = data.subtitle || '';
      this.tileSales.set(baht(sales.total), `ก่อนหักส่วนลด ${money(sales.subtotal)}`);
      this.tileBills.set(
        Number(sales.bill_count || 0).toLocaleString('en-US'),
        'บิลที่ชำระแล้ว'
      );
      this.tileAvg.set(baht(sales.avg_per_bill));
      this.tileDiscount.set(baht(sales.discount));
      this.tileTables.set(
        `${data.tables_in_use} / ${data.tables_total}`,
        'โต๊ะสถานะ "ใช้งาน" / โต๊ะทั้งหมด'
      );
      this.tilePending.set(String(data.tables_pending), 'รอพนักงานยืนยัน');
      this.tilePay.set(String(data.tables_awaiting_payment), 'เช็คบิลแล้ว รอรับเงิน');
      this.tileAlerts.set(
        String(data.active_alerts),
        data.active_alerts ? 'แถบแดงที่ยังไม่จัดการ' : 'ไม่มี'
      );

      this._drawLowStock(data.low_stock || []);
      this._drawPayments(sales.by_payment || {});
      this.cancelTodayLabel.textContent = `ยกเลิกวันนี้: รายการอาหาร ${data.cancelled_items_today} รายการ, โต๊ะ ${data.cancelled_sessions_today} โต๊ะ`;
    } catch (_err) {
      // ignore
    }
  }

  _drawLowStock(low) {
    this.lowArea.textContent = '';
    if (low.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'สต๊อกทุกรายการยังพอ';
      this.lowArea.appendChild(empty);
      return;
    }
    for (const s of low.slice(0, 8)) {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.justifyContent = 'space-between';
      row.style.fontSize = 'var(--fs-md)';
      const isEmpty = Number(s.quantity) <= 0;
      const n = document.createElement('span');
      n.textContent = s.name;
      const q = document.createElement('span');
      q.style.fontWeight = '700';
      q.style.color = isEmpty ? 'var(--color-danger)' : 'var(--color-warning)';
      q.textContent = isEmpty ? 'หมด' : `เหลือ ${fmt_qty(s.quantity)} ${s.unit}`;
      row.appendChild(n);
      row.appendChild(q);
      this.lowArea.appendChild(row);
    }
    if (low.length > 8) {
      const more = document.createElement('div');
      more.style.fontSize = 'var(--fs-sm)';
      more.style.color = 'var(--color-text-muted)';
      more.textContent = `และอีก ${low.length - 8} รายการ`;
      this.lowArea.appendChild(more);
    }
  }

  _drawPayments(byPayment) {
    this.payArea.textContent = '';
    const entries = Object.entries(byPayment).filter(
      ([m, v]) => !(m === 'card' && Number(v.count) === 0)
    );
    const biggest =
      Math.max(...entries.map(([_m, v]) => Number(v.total || 0)), 0) || 1;
    for (const [_m, v] of entries) {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.alignItems = 'center';
      row.style.justifyContent = 'space-between';
      row.style.gap = 'var(--space-2)';
      const lbl = document.createElement('span');
      lbl.style.minWidth = '150px';
      lbl.textContent = `${v.method_th} (${v.count} บิล)`;
      const barEl = makePropBar(Number(v.total || 0) / biggest, 'var(--color-info)');
      const amt = document.createElement('span');
      amt.style.fontWeight = '700';
      amt.className = 'money';
      amt.textContent = baht(v.total);
      row.appendChild(lbl);
      row.appendChild(barEl);
      row.appendChild(amt);
      this.payArea.appendChild(row);
    }
  }

  async showReport() {
    try {
      const f = parse_date(this.dateFromField.get(), 'วันที่เริ่ม', false);
      const t = parse_date(this.dateToField.get(), 'วันที่สิ้นสุด', false);
      if (f > t) {
        this.app.toast('วันเริ่มต้องไม่หลังวันสิ้นสุด', 'error');
        return;
      }
      await this.loadReport({ date_from: f, date_to: t });
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async loadReport(params = {}) {
    try {
      const data = await apiGet('/api/owner/dashboard/report', params);
      this.dateFromField.set(data.date_from, false);
      this.dateToField.set(data.date_to, false);
      this.reportRangeLabel.textContent = data.range_label || '';

      const s = data.summary;
      this.rtileTotal.set(baht(s.total));
      this.rtileBills.set(Number(s.bill_count || 0).toLocaleString('en-US'));
      this.rtileAvg.set(baht(s.avg_per_bill));

      const payParts = Object.values(s.by_payment || {})
        .filter((v) => v.count > 0)
        .map((v) => `${v.method_th} ${money(v.total)}`);
      const totalPayCount = Object.values(s.by_payment || {}).reduce(
        (acc, v) => acc + Number(v.count || 0),
        0
      );
      this.rtilePay.set(
        payParts.length > 0 ? `${totalPayCount} บิล` : '-',
        payParts.join(' · ')
      );
      this.rtileSubtotal.set(baht(s.subtotal));
      this.rtileDiscount.set(baht(s.discount));
      this.rtileService.set(baht(s.service_charge));
      this.rtileVat.set(baht(s.vat));

      const daily = data.daily || [];
      const hourly = data.hourly || [];
      const top = data.top_items || [];
      this.barMax.daily = Math.max(...daily.map((d) => Number(d.total || 0)), 0) || 1;
      this.barMax.hourly = Math.max(...hourly.map((h) => Number(h.total || 0)), 0) || 1;
      this.barMax.top = Math.max(...top.map((x) => Number(x.amount || 0)), 0) || 1;

      this.tables['รายวัน'].setRows(daily);
      this.tables['รายชั่วโมง'].setRows(hourly);
      this.tables['เมนูขายดี'].setRows(top);
      this.tables['รายการยกเลิก'].setRows(data.cancellations || []);
      this.tables['บิล'].setRows(data.bills || []);
      this.noteEl.textContent = data.note || '';
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async exportCsv() {
    try {
      const f = parse_date(this.dateFromField.get(), 'วันที่เริ่ม', false);
      const t = parse_date(this.dateToField.get(), 'วันที่สิ้นสุด', false);
      const res = await apiPost('/api/owner/report/export_csv', {
        date_from: f,
        date_to: t,
      });
      this.app.toast(res.message, 'success');
      if (res.download_url) {
        const a = document.createElement('a');
        a.href = res.download_url;
        a.download = res.filename || `sales_${f}_${t}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async openExportsFolder() {
    try {
      const res = await apiPost('/api/owner/open_folder', { target: 'exports' });
      this.app.toast(res.message, res.opened ? 'info' : 'warning');
    } catch (err) {
      this.app.toast(err.message, 'warning');
    }
  }
}
