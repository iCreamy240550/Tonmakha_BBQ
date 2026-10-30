/**
 * frontend/staff/js/pages/takeaway.js — หน้าสั่งกลับบ้าน (Takeaway POS) สำหรับพนักงานและเจ้าของร้าน
 *
 * ฟีเจอร์ตามข้อกำหนด:
 * - ลูกค้าสามารถสั่งกลับบ้านโดยไม่ต้องสแกนเข้าโต๊ะ พนักงาน/เจ้าของร้านเป็นผู้บันทึกรายการทั้งหมด
 * - ฝั่งซ้าย: รายการและสิ่งที่ลูกค้าสั่งซื้อ มีรายการและยอดรวม จำนวนทั้งหมด/ราคา มีหน่วยของตัวเอง
 *   รายการชั่งกิโลเมื่อกดเพิ่มซ้ำจะนำไปรวมกันในหัวข้อเดียวกันฝั่งซ้าย
 * - ฝั่งขวา: แบ่งเป็น 2 ส่วนหลัก
 *   1. กรอกส่วนชั่งกิโล: แถบยาวให้พนักงานกรอกจำนวนน้ำหนักที่ลูกค้าสั่ง (ต้องซื้อเนื้อขั้นต่ำรวม 1 กก. ขึ้นไป) คำนวณราคาแล้วเอาไว้ฝั่งซ้าย
 *   2. กรอกส่วนของอื่นๆ: ผัก เครื่องดื่ม ของทานเล่น จัดหมวดหมู่กดเลือกดูได้ หรือพิมพ์ค้นหาสินค้าด้วยชื่อได้ ดูที่เหลือในสต๊อกได้ และกด add เลือกจำนวนได้
 * - เมื่อครบแล้วไปส่วนชำระเงินแบบปกติ ชำระด้วย เงินสด หรือ พร้อมเพย์ ก็ได้ บันทึกเข้ารายรับ มีสลิปใบเสร็จ และบันทึกประวัติการทำงาน (activity_log)
 */

import { apiGet, apiPost } from '../../../shared/js/api.js';
import { BaseDialog, confirmDialog } from '../../../shared/js/dialogs.js';
import { baht, fmt_qty, money, weight_text } from '../../../shared/js/format.js';
import { createStatusBadge } from '../../../shared/js/status-badge.js';

const UNITS = ['ขีด', 'กรัม', 'กิโลกรัม'];
const NO_PROMO = 'ไม่ใช้โปรโมชั่น';
const LABEL_CASH = 'เงินสด';
const LABEL_PROMPTPAY = 'โอน/PromptPay';

export class TakeawayPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;

    // ข้อมูลเมนูและอัตราจากเซิร์ฟเวอร์
    this.rate = 299.0;
    this.rateText = 'กิโลกรัมละ 299 บาท';
    this.minWeighGrams = 1000;
    this.defaultWeighedItem = { id: 1, name: 'หมูกระทะชั่งกิโล', price: 299, unit: 'กก.' };
    this.categories = [];
    this.normalItems = [];
    this.rates = {
      service_charge_enabled: false,
      service_charge_percent: 0,
      vat_enabled: false,
      vat_percent: 0,
    };

    // สถานะรายการที่ลูกค้าสั่งซื้อ (ฝั่งซ้าย)
    this.weighGramsTotal = 0; // น้ำหนักชั่งกิโลรวมทั้งหมดในหัวข้อเดียวกัน (กรัม)
    this.cartMap = {};        // menu_item_id -> quantity (จำนวนของเสริม)
    this.promoId = null;
    this.availablePromos = [];
    this.previewData = null;

    // สถานะฝั่งขวา
    this.unit = 'ขีด';
    this.selectedCatId = 'all';
    this.searchQuery = '';
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
    hTitle.textContent = 'สั่งกลับบ้าน';
    const hSub = document.createElement('div');
    hSub.className = 'page-subtitle';
    hSub.textContent =
      'บันทึกรายการสั่งกลับบ้านโดยไม่ต้องสแกนโต๊ะ — เนื้อชั่งกิโลขั้นต่ำ 1 กก. ขึ้นไป ส่วนของเสริมซื้อเท่าไหร่ก็ได้';
    hLeft.appendChild(hTitle);
    hLeft.appendChild(hSub);

    const hRight = document.createElement('div');
    hRight.className = 'page-header-right';
    const clearAllBtn = document.createElement('button');
    clearAllBtn.type = 'button';
    clearAllBtn.className = 'btn btn-ghost';
    clearAllBtn.textContent = 'ล้างรายการทั้งหมด';
    clearAllBtn.addEventListener('click', () => this.clearAll());
    hRight.appendChild(clearAllBtn);

    header.appendChild(hLeft);
    header.appendChild(hRight);
    this.container.appendChild(header);

    const split = document.createElement('div');
    split.className = 'split-layout split-takeaway audit-block';

    // ==================== ฝั่งซ้าย: รายการและสิ่งที่ลูกค้าสั่งซื้อ ====================
    this.leftCard = document.createElement('div');
    this.leftCard.className = 'card takeaway-left-card';
    this.leftCard.style.display = 'flex';
    this.leftCard.style.flexDirection = 'column';
    this.leftCard.style.gap = 'var(--space-3)';

    const leftHead = document.createElement('div');
    leftHead.style.display = 'flex';
    leftHead.style.alignItems = 'center';
    leftHead.style.justifyContent = 'space-between';
    leftHead.style.gap = 'var(--space-2)';
    const leftTitle = document.createElement('div');
    leftTitle.style.fontSize = 'var(--fs-xl)';
    leftTitle.style.fontWeight = '700';
    leftTitle.textContent = 'รายการที่ลูกค้าสั่งซื้อ';
    this.weighStatusBadge = createStatusBadge('รอชั่งเนื้อ (ขั้นต่ำ 1 กก.)', 'var(--color-warning)');
    leftHead.appendChild(leftTitle);
    leftHead.appendChild(this.weighStatusBadge);
    this.leftCard.appendChild(leftHead);

    // ตารางหัวข้อรายการฝั่งซ้าย
    const listHeader = document.createElement('div');
    listHeader.className = 'takeaway-cart-head';
    const lh1 = document.createElement('span');
    lh1.textContent = 'รายการ';
    const lh2 = document.createElement('span');
    lh2.style.textAlign = 'center';
    lh2.textContent = 'จำนวน / หน่วย';
    const lh3 = document.createElement('span');
    lh3.style.textAlign = 'right';
    lh3.textContent = 'ราคา (บาท)';
    listHeader.appendChild(lh1);
    listHeader.appendChild(lh2);
    listHeader.appendChild(lh3);
    this.leftCard.appendChild(listHeader);

    this.cartListEl = document.createElement('div');
    this.cartListEl.className = 'takeaway-cart-list';
    this.leftCard.appendChild(this.cartListEl);

    // สรุปจำนวนและยอดรวมฝั่งซ้าย
    this.summaryBox = document.createElement('div');
    this.summaryBox.className = 'takeaway-summary-box';
    this.leftCard.appendChild(this.summaryBox);

    this.checkoutBtn = document.createElement('button');
    this.checkoutBtn.type = 'button';
    this.checkoutBtn.className = 'btn btn-lg btn-success btn-block';
    this.checkoutBtn.textContent = 'ชำระเงิน (เงินสด / พร้อมเพย์)';
    this.checkoutBtn.disabled = true;
    this.checkoutBtn.addEventListener('click', () => this.openPaymentDialog());
    this.leftCard.appendChild(this.checkoutBtn);

    // ==================== ฝั่งขวา: 1. กรอกส่วนชั่งกิโล + 2. กรอกส่วนของอื่นๆ ====================
    const rightCol = document.createElement('div');
    rightCol.style.display = 'flex';
    rightCol.style.flexDirection = 'column';
    rightCol.style.gap = 'var(--space-3)';
    rightCol.style.minWidth = '0';

    // --- ส่วนที่ 1: กรอกส่วนชั่งกิโล (แถบยาวด้านบน) ---
    const weighCard = document.createElement('div');
    weighCard.className = 'card';
    weighCard.style.display = 'flex';
    weighCard.style.flexDirection = 'column';
    weighCard.style.gap = 'var(--space-2)';

    const wHeadRow = document.createElement('div');
    wHeadRow.style.display = 'flex';
    wHeadRow.style.alignItems = 'center';
    wHeadRow.style.justifyContent = 'space-between';
    wHeadRow.style.gap = 'var(--space-2)';
    wHeadRow.style.flexWrap = 'wrap';

    const wTitle = document.createElement('div');
    wTitle.style.fontSize = 'var(--fs-xl)';
    wTitle.style.fontWeight = '700';
    wTitle.textContent = '1. กรอกส่วนชั่งกิโล (เนื้อสัตว์ขั้นต่ำ 1 กก. ขึ้นไป)';

    this.rateBadge = document.createElement('div');
    this.rateBadge.style.fontSize = 'var(--fs-md)';
    this.rateBadge.style.fontWeight = '700';
    this.rateBadge.style.color = 'var(--color-primary)';
    this.rateBadge.textContent = this.rateText;

    wHeadRow.appendChild(wTitle);
    wHeadRow.appendChild(this.rateBadge);
    weighCard.appendChild(wHeadRow);

    // แถบยาวกรอกน้ำหนัก + เลือกหน่วย + ปุ่มกดเพิ่มเข้าฝั่งซ้าย
    const wBar = document.createElement('div');
    wBar.className = 'takeaway-weigh-bar';

    const wLbl = document.createElement('label');
    wLbl.style.fontWeight = '700';
    wLbl.style.fontSize = 'var(--fs-md)';
    wLbl.textContent = 'น้ำหนัก:';

    this.weightInput = document.createElement('input');
    this.weightInput.type = 'text';
    this.weightInput.className = 'field-input num takeaway-weight-input';
    this.weightInput.placeholder = 'กรอกน้ำหนัก...';
    this.weightInput.addEventListener('input', () => this._updateWeighCalc());
    this.weightInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        this.addWeighToCart();
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
        this._updateWeighCalc();
      });
      unitGroup.appendChild(b);
      this.unitBtns[u] = b;
    }

    this.addWeighBtn = document.createElement('button');
    this.addWeighBtn.type = 'button';
    this.addWeighBtn.className = 'btn btn-primary';
    this.addWeighBtn.style.height = '38px';
    this.addWeighBtn.style.flexShrink = '0';
    this.addWeighBtn.textContent = '+ เพิ่มน้ำหนัก';
    this.addWeighBtn.addEventListener('click', () => this.addWeighToCart());

    wBar.appendChild(wLbl);
    wBar.appendChild(this.weightInput);
    wBar.appendChild(unitGroup);
    wBar.appendChild(this.addWeighBtn);
    weighCard.appendChild(wBar);

    // ปุ่มลัดเพิ่มขีด + แสดงราคาที่คำนวณก่อนกดเพิ่ม
    const wQuickRow = document.createElement('div');
    wQuickRow.style.display = 'flex';
    wQuickRow.style.alignItems = 'center';
    wQuickRow.style.justifyContent = 'space-between';
    wQuickRow.style.gap = 'var(--space-2)';
    wQuickRow.style.flexWrap = 'wrap';

    const qBtnsWrap = document.createElement('div');
    qBtnsWrap.style.display = 'flex';
    qBtnsWrap.style.alignItems = 'center';
    qBtnsWrap.style.gap = 'var(--space-1)';
    qBtnsWrap.style.flexWrap = 'wrap';
    for (const [label, kheed] of [
      ['+1 ขีด', 1],
      ['+2 ขีด', 2],
      ['+5 ขีด', 5],
      ['+10 ขีด (1 กก.)', 10],
    ]) {
      const qb = document.createElement('button');
      qb.type = 'button';
      qb.className = 'btn btn-sm btn-ghost';
      qb.textContent = label;
      qb.addEventListener('click', () => this._addQuickKheed(kheed));
      qBtnsWrap.appendChild(qb);
    }
    const clearWBtn = document.createElement('button');
    clearWBtn.type = 'button';
    clearWBtn.className = 'btn btn-sm btn-ghost';
    clearWBtn.textContent = 'ล้างช่องกรอก';
    clearWBtn.addEventListener('click', () => {
      this.weightInput.value = '';
      this._updateWeighCalc();
    });
    qBtnsWrap.appendChild(clearWBtn);

    this.weighCalcLabel = document.createElement('div');
    this.weighCalcLabel.style.fontSize = 'var(--fs-base)';
    this.weighCalcLabel.style.fontWeight = '700';
    this.weighCalcLabel.style.color = 'var(--color-text-muted)';

    wQuickRow.appendChild(qBtnsWrap);
    wQuickRow.appendChild(this.weighCalcLabel);
    weighCard.appendChild(wQuickRow);

    rightCol.appendChild(weighCard);

    // --- ส่วนที่ 2: กรอกส่วนของอื่นๆ (หมวดหมู่ + ค้นหาด้วยชื่อ + ดูสต๊อก + กด add เลือกจำนวน) ---
    const otherCard = document.createElement('div');
    otherCard.className = 'card';
    otherCard.style.display = 'flex';
    otherCard.style.flexDirection = 'column';
    otherCard.style.gap = 'var(--space-3)';
    otherCard.style.flex = '1 1 auto';

    const oHeadRow = document.createElement('div');
    oHeadRow.style.display = 'flex';
    oHeadRow.style.alignItems = 'center';
    oHeadRow.style.justifyContent = 'space-between';
    oHeadRow.style.gap = 'var(--space-2)';
    oHeadRow.style.flexWrap = 'wrap';

    const oTitle = document.createElement('div');
    oTitle.style.fontSize = 'var(--fs-xl)';
    oTitle.style.fontWeight = '700';
    oTitle.textContent = '2. กรอกส่วนของอื่นๆ (ผัก / เครื่องดื่ม / ของกินเล่น)';

    // ช่องพิมพ์ค้นหาสินค้าด้วยชื่อ
    const searchWrap = document.createElement('div');
    searchWrap.style.display = 'flex';
    searchWrap.style.alignItems = 'center';
    searchWrap.style.gap = 'var(--space-2)';
    this.searchInput = document.createElement('input');
    this.searchInput.type = 'text';
    this.searchInput.className = 'field-input';
    this.searchInput.style.width = '240px';
    this.searchInput.placeholder = 'ค้นหาสินค้าด้วยชื่อ...';
    this.searchInput.addEventListener('input', () => {
      this.searchQuery = (this.searchInput.value || '').trim();
      this._renderOtherItems();
    });
    const clearSearchBtn = document.createElement('button');
    clearSearchBtn.type = 'button';
    clearSearchBtn.className = 'btn btn-sm btn-ghost';
    clearSearchBtn.textContent = 'ล้างค้นหา';
    clearSearchBtn.addEventListener('click', () => {
      this.searchInput.value = '';
      this.searchQuery = '';
      this._renderOtherItems();
    });
    searchWrap.appendChild(this.searchInput);
    searchWrap.appendChild(clearSearchBtn);

    oHeadRow.appendChild(oTitle);
    oHeadRow.appendChild(searchWrap);
    otherCard.appendChild(oHeadRow);

    // แถบหมวดหมู่กดเลือกดูได้
    this.catTabsEl = document.createElement('div');
    this.catTabsEl.className = 'takeaway-cat-tabs';
    otherCard.appendChild(this.catTabsEl);

    // กริดแสดงรายการสินค้าของอื่นๆ พร้อมสต๊อกคงเหลือและปุ่ม Add / เลือกจำนวน
    this.otherGridEl = document.createElement('div');
    this.otherGridEl.className = 'takeaway-items-grid';
    otherCard.appendChild(this.otherGridEl);

    rightCol.appendChild(otherCard);

    split.appendChild(this.leftCard);
    split.appendChild(rightCol);
    this.container.appendChild(split);
  }

  activate() {
    this.refreshCatalog();
    setTimeout(() => this.weightInput.focus(), 50);
    this._timer = setInterval(() => {
      if (!document.hidden && !document.querySelector('.modal-backdrop')) {
        this.refreshCatalog(true);
      }
    }, 8000);
  }

  deactivate() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  reload() {
    this.refreshCatalog(true);
  }

  async refreshCatalog(silent = false) {
    try {
      const data = await apiGet('/api/staff/takeaway');
      this.rate = Number(data.rate || 299);
      this.rateText = data.rate_text || 'กิโลกรัมละ 299 บาท';
      this.rateBadge.textContent = this.rateText;
      this.minWeighGrams = Number(data.min_weigh_grams || 1000);
      if (data.default_weighed_item) {
        this.defaultWeighedItem = data.default_weighed_item;
      }
      this.categories = data.categories || [];
      this.normalItems = data.normal_items || [];
      if (data.rates) {
        this.rates = data.rates;
      }

      // ตรวจสอบจำนวนในตะกร้าไม่ให้เกินสต๊อกปัจจุบัน
      for (const [midStr, q] of Object.entries(this.cartMap)) {
        const it = this.normalItems.find((x) => x.id === Number(midStr));
        if (!it || it.is_sold_out) {
          delete this.cartMap[midStr];
        } else if (it.stock_item_id !== null && it.stock_quantity !== null) {
          const maxStock = Math.max(0, Math.floor(Number(it.stock_quantity)));
          if (maxStock <= 0) {
            delete this.cartMap[midStr];
          } else if (q > maxStock) {
            this.cartMap[midStr] = maxStock;
          }
        }
      }

      this._renderCategoryTabs();
      this._renderOtherItems();
      this._updateWeighCalc();
      this._renderLeftCart();
    } catch (err) {
      if (!silent) {
        this.app.toast(err.message || 'โหลดข้อมูลไม่สำเร็จ', 'error');
      }
    }
  }

  _inputGrams() {
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

  _addQuickKheed(kheed) {
    const text = (this.weightInput.value || '').trim();
    const cur = Number(text) || 0;
    let delta = kheed;
    if (this.unit === 'กรัม') delta = kheed * 100;
    else if (this.unit === 'กิโลกรัม') delta = kheed / 10.0;
    const nextVal = Number((cur + delta).toFixed(4));
    this.weightInput.value = String(nextVal);
    this._updateWeighCalc();
  }

  _calcWeighPrice(grams) {
    if (!grams || grams <= 0) return 0;
    return Math.round(((grams / 1000) * this.rate + Number.EPSILON) * 100) / 100;
  }

  _updateWeighCalc() {
    const grams = this._inputGrams();
    if (grams === null) {
      this.weighCalcLabel.textContent = `กรอกน้ำหนักแล้วกด "+ เพิ่มน้ำหนักเข้าบิล" (หากกดเพิ่มซ้ำจะนำไปรวมในหัวข้อเดียวกันฝั่งซ้าย)`;
      this.weighCalcLabel.style.color = 'var(--color-text-muted)';
      return;
    }
    const amt = this._calcWeighPrice(grams);
    const nextTotalGrams = this.weighGramsTotal + grams;
    const nextTotalAmt = this._calcWeighPrice(nextTotalGrams);
    if (this.weighGramsTotal > 0) {
      this.weighCalcLabel.textContent = `รอบนี้ ${weight_text(grams)} = ${baht(amt)} (รวมเป็น ${weight_text(nextTotalGrams)} = ${baht(nextTotalAmt)})`;
    } else {
      this.weighCalcLabel.textContent = `น้ำหนัก ${weight_text(grams)} (${grams.toLocaleString('en-US')} กรัม) = ${baht(amt)}`;
    }
    this.weighCalcLabel.style.color = 'var(--color-primary)';
  }

  addWeighToCart() {
    const grams = this._inputGrams();
    if (grams === null || grams <= 0) {
      this.app.toast('กรุณากรอกน้ำหนักที่ชั่งเป็นตัวเลขมากกว่า 0', 'error');
      this.weightInput.focus();
      return;
    }
    if (this.weighGramsTotal + grams > 50000) {
      this.app.toast('น้ำหนักรวมเกิน 50 กิโลกรัม กรุณาตรวจสอบอีกครั้ง', 'error');
      return;
    }
    // นำไปรวมกันในหัวข้อเดียวกันอยู่ฝั่งซ้ายตามข้อกำหนด
    this.weighGramsTotal += grams;
    this.weightInput.value = '';
    this._updateWeighCalc();
    this._renderLeftCart();
    this.app.toast(
      `เพิ่มน้ำหนักชั่งกิโลแล้ว (รวม ${weight_text(this.weighGramsTotal)})`,
      'success'
    );
    this.weightInput.focus();
  }

  clearWeighTotal() {
    this.weighGramsTotal = 0;
    this._updateWeighCalc();
    this._renderLeftCart();
  }

  clearAll() {
    this.weighGramsTotal = 0;
    this.cartMap = {};
    this.promoId = null;
    this.weightInput.value = '';
    this._updateWeighCalc();
    this._renderOtherItems();
    this._renderLeftCart();
  }

  _renderCategoryTabs() {
    this.catTabsEl.textContent = '';
    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = `btn btn-sm ${this.selectedCatId === 'all' ? 'btn-primary' : 'btn-ghost'}`;
    allBtn.textContent = 'ทั้งหมด';
    allBtn.addEventListener('click', () => {
      this.selectedCatId = 'all';
      this._renderCategoryTabs();
      this._renderOtherItems();
    });
    this.catTabsEl.appendChild(allBtn);

    for (const c of this.categories) {
      const btn = document.createElement('button');
      btn.type = 'button';
      const active = this.selectedCatId === c.id;
      btn.className = `btn btn-sm ${active ? 'btn-primary' : 'btn-ghost'}`;
      btn.textContent = c.name;
      btn.addEventListener('click', () => {
        this.selectedCatId = c.id;
        this._renderCategoryTabs();
        this._renderOtherItems();
      });
      this.catTabsEl.appendChild(btn);
    }
  }

  _stockUnitOf(item) {
    return (item.stock_unit || '').trim() || 'ชิ้น';
  }

  _maxOrderableQty(item) {
    if (item.is_sold_out) return 0;
    if (item.stock_item_id !== null && item.stock_quantity !== null && item.stock_quantity !== undefined) {
      return Math.max(0, Math.min(99, Math.floor(Number(item.stock_quantity))));
    }
    return 99;
  }

  _changeItemQty(item, delta) {
    const cur = Number(this.cartMap[item.id] || 0);
    const maxQ = this._maxOrderableQty(item);
    if (delta > 0 && cur >= maxQ) {
      const unit = this._stockUnitOf(item);
      if (maxQ <= 0) {
        this.app.toast(`${item.name} สินค้าหมดแล้ว`, 'warning');
      } else {
        this.app.toast(`${item.name} คงเหลือในสต๊อก ${maxQ} ${unit}`, 'warning');
      }
      return;
    }
    const next = Math.max(0, Math.min(maxQ, cur + delta));
    if (next <= 0) {
      delete this.cartMap[item.id];
    } else {
      this.cartMap[item.id] = next;
    }
    this._renderOtherItems();
    this._renderLeftCart();
  }

  _setItemQty(item, newQty) {
    const maxQ = this._maxOrderableQty(item);
    const parsed = Math.floor(Number(newQty) || 0);
    if (parsed <= 0) {
      delete this.cartMap[item.id];
    } else if (parsed > maxQ) {
      const unit = this._stockUnitOf(item);
      this.app.toast(`${item.name} สั่งได้สูงสุด ${maxQ} ${unit}`, 'warning');
      if (maxQ > 0) this.cartMap[item.id] = maxQ;
      else delete this.cartMap[item.id];
    } else {
      this.cartMap[item.id] = parsed;
    }
    this._renderOtherItems();
    this._renderLeftCart();
  }

  _renderOtherItems() {
    this.otherGridEl.textContent = '';
    const q = (this.searchQuery || '').toLowerCase();
    const filtered = this.normalItems.filter((it) => {
      if (this.selectedCatId !== 'all' && it.category_id !== this.selectedCatId) {
        return false;
      }
      if (q && !String(it.name || '').toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.style.gridColumn = '1 / -1';
      empty.textContent = q
        ? `ไม่พบสินค้าที่ตรงกับ "${this.searchQuery}"`
        : 'ไม่มีสินค้าในหมวดหมู่นี้';
      this.otherGridEl.appendChild(empty);
      return;
    }

    for (const it of filtered) {
      const card = document.createElement('div');
      card.className = 'takeaway-item-card';

      const top = document.createElement('div');
      top.className = 'card-top';

      const head = document.createElement('div');
      head.className = 'card-head-row';
      const nameEl = document.createElement('div');
      nameEl.style.fontSize = 'var(--fs-lg)';
      nameEl.style.fontWeight = '700';
      nameEl.textContent = it.name;

      const unit = this._stockUnitOf(it);
      const priceEl = document.createElement('div');
      priceEl.style.fontSize = 'var(--fs-md)';
      priceEl.style.fontWeight = '700';
      priceEl.style.color = 'var(--color-primary)';
      priceEl.className = 'money';
      priceEl.textContent = `${money(it.price)} ฿/${unit}`;

      head.appendChild(nameEl);
      head.appendChild(priceEl);
      top.appendChild(head);

      const metaRow = document.createElement('div');
      metaRow.style.display = 'flex';
      metaRow.style.alignItems = 'center';
      metaRow.style.justifyContent = 'space-between';
      metaRow.style.gap = 'var(--space-1)';

      const catSpan = document.createElement('span');
      catSpan.style.fontSize = 'var(--fs-xs)';
      catSpan.style.color = 'var(--color-text-muted)';
      catSpan.textContent = it.category_name || '';

      const stockSpan = document.createElement('span');
      stockSpan.style.fontSize = 'var(--fs-xs)';
      stockSpan.style.fontWeight = '700';
      const maxQ = this._maxOrderableQty(it);
      if (it.is_sold_out || maxQ <= 0) {
        stockSpan.style.color = 'var(--color-danger)';
        stockSpan.textContent = `สินค้าหมด (0 ${unit})`;
      } else if (it.stock_item_id !== null && it.stock_quantity !== null) {
        stockSpan.style.color = 'var(--color-success)';
        stockSpan.textContent = `สต๊อกคงเหลือ ${fmt_qty(it.stock_quantity)} ${unit}`;
      } else {
        stockSpan.style.color = 'var(--color-info)';
        stockSpan.textContent = `พร้อมจำหน่าย (${unit})`;
      }

      metaRow.appendChild(catSpan);
      metaRow.appendChild(stockSpan);
      top.appendChild(metaRow);
      card.appendChild(top);

      // ส่วนปุ่มกด Add / เลือกจำนวน
      const footer = document.createElement('div');
      footer.className = 'card-footer';
      const curQ = Number(this.cartMap[it.id] || 0);

      if (it.is_sold_out || maxQ <= 0) {
        const outBtn = document.createElement('button');
        outBtn.type = 'button';
        outBtn.className = 'btn btn-sm btn-ghost btn-block';
        outBtn.disabled = true;
        outBtn.textContent = 'สินค้าหมด';
        footer.appendChild(outBtn);
      } else if (curQ <= 0) {
        const addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.className = 'btn btn-sm btn-primary btn-block';
        addBtn.textContent = `+ เพิ่ม (${unit})`;
        addBtn.addEventListener('click', () => this._changeItemQty(it, 1));
        footer.appendChild(addBtn);
      } else {
        const ctrlRow = document.createElement('div');
        ctrlRow.style.display = 'flex';
        ctrlRow.style.alignItems = 'center';
        ctrlRow.style.justifyContent = 'space-between';
        ctrlRow.style.gap = 'var(--space-1)';

        const minusBtn = document.createElement('button');
        minusBtn.type = 'button';
        minusBtn.className = 'btn btn-sm btn-ghost';
        minusBtn.style.minWidth = '38px';
        minusBtn.textContent = '−';
        minusBtn.addEventListener('click', () => this._changeItemQty(it, -1));

        const qtyInput = document.createElement('input');
        qtyInput.type = 'text';
        qtyInput.className = 'field-input num';
        qtyInput.style.width = '64px';
        qtyInput.style.height = '32px';
        qtyInput.style.textAlign = 'center';
        qtyInput.style.fontWeight = '700';
        qtyInput.value = String(curQ);
        qtyInput.addEventListener('change', () => this._setItemQty(it, qtyInput.value));

        const plusBtn = document.createElement('button');
        plusBtn.type = 'button';
        plusBtn.className = 'btn btn-sm btn-success';
        plusBtn.style.minWidth = '38px';
        plusBtn.textContent = '+';
        plusBtn.disabled = curQ >= maxQ;
        plusBtn.addEventListener('click', () => this._changeItemQty(it, 1));

        ctrlRow.appendChild(minusBtn);
        ctrlRow.appendChild(qtyInput);
        ctrlRow.appendChild(plusBtn);
        footer.appendChild(ctrlRow);
      }

      card.appendChild(footer);
      this.otherGridEl.appendChild(card);
    }
  }

  _renderLeftCart() {
    this.cartListEl.textContent = '';
    this.summaryBox.textContent = '';

    const weighOk = this.weighGramsTotal >= this.minWeighGrams;
    if (this.weighGramsTotal <= 0) {
      this.weighStatusBadge.textContent = 'รอชั่งเนื้อ (ขั้นต่ำ 1 กก.)';
      this.weighStatusBadge.style.backgroundColor = 'var(--color-warning)';
    } else if (!weighOk) {
      const lackGrams = this.minWeighGrams - this.weighGramsTotal;
      this.weighStatusBadge.textContent = `เนื้อยังไม่ถึง 1 กก. (ขาดอีก ${weight_text(lackGrams)})`;
      this.weighStatusBadge.style.backgroundColor = 'var(--color-danger)';
    } else {
      this.weighStatusBadge.textContent = `เนื้อครบขั้นต่ำแล้ว (${weight_text(this.weighGramsTotal)})`;
      this.weighStatusBadge.style.backgroundColor = 'var(--color-success)';
    }

    const activeOtherItems = [];
    for (const [midStr, q] of Object.entries(this.cartMap)) {
      if (q <= 0) continue;
      const it = this.normalItems.find((x) => x.id === Number(midStr));
      if (it) {
        activeOtherItems.push({ item: it, quantity: q });
      }
    }

    if (this.weighGramsTotal <= 0 && activeOtherItems.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'ยังไม่มีรายการที่เลือก — กรุณากรอกน้ำหนักชั่งกิโลหรือเลือกสินค้าทางขวา';
      this.cartListEl.appendChild(empty);
    } else {
      // 1) แถวรายการชั่งกิโล (รวมกันในหัวข้อเดียวกัน)
      if (this.weighGramsTotal > 0) {
        const wAmt = this._calcWeighPrice(this.weighGramsTotal);
        const wRow = document.createElement('div');
        wRow.className = 'takeaway-cart-row takeaway-cart-row-weigh';

        const colName = document.createElement('div');
        colName.style.display = 'flex';
        colName.style.flexDirection = 'column';
        const nTitle = document.createElement('span');
        nTitle.style.fontWeight = '700';
        nTitle.textContent = this.defaultWeighedItem.name || 'หมูกระทะชั่งกิโล';
        const nSub = document.createElement('span');
        nSub.style.fontSize = 'var(--fs-xs)';
        nSub.style.color = 'var(--color-text-muted)';
        nSub.textContent = `อัตรา ${money(this.rate)} บาท/กก. (รวมน้ำหนักทุกครั้งที่เพิ่ม)`;
        colName.appendChild(nTitle);
        colName.appendChild(nSub);

        const colQty = document.createElement('div');
        colQty.style.display = 'flex';
        colQty.style.flexDirection = 'column';
        colQty.style.alignItems = 'center';
        const qTxt = document.createElement('span');
        qTxt.style.fontWeight = '700';
        qTxt.textContent = `${(this.weighGramsTotal / 1000).toFixed(2).replace(/\.?0+$/, '')} กก.`;
        const kTxt = document.createElement('span');
        kTxt.style.fontSize = 'var(--fs-xs)';
        kTxt.style.color = 'var(--color-text-muted)';
        kTxt.textContent = `(${weight_text(this.weighGramsTotal)} / ${this.weighGramsTotal.toLocaleString('en-US')} กรัม)`;
        colQty.appendChild(qTxt);
        colQty.appendChild(kTxt);

        const colPrice = document.createElement('div');
        colPrice.style.display = 'flex';
        colPrice.style.alignItems = 'center';
        colPrice.style.justifyContent = 'flex-end';
        colPrice.style.gap = 'var(--space-2)';
        const pTxt = document.createElement('span');
        pTxt.style.fontWeight = '700';
        pTxt.className = 'money';
        pTxt.textContent = money(wAmt);
        const delWBtn = document.createElement('button');
        delWBtn.type = 'button';
        delWBtn.className = 'btn btn-sm btn-ghost';
        delWBtn.style.minWidth = '32px';
        delWBtn.style.padding = 'var(--space-1)';
        delWBtn.textContent = '✕';
        delWBtn.title = 'ล้างน้ำหนักชั่งกิโล';
        delWBtn.addEventListener('click', () => this.clearWeighTotal());
        colPrice.appendChild(pTxt);
        colPrice.appendChild(delWBtn);

        wRow.appendChild(colName);
        wRow.appendChild(colQty);
        wRow.appendChild(colPrice);
        this.cartListEl.appendChild(wRow);
      }

      // 2) แถวรายการของเสริม
      for (const { item, quantity } of activeOtherItems) {
        const unit = this._stockUnitOf(item);
        const lineAmt = Math.round(Number(item.price) * quantity * 100) / 100;
        const row = document.createElement('div');
        row.className = 'takeaway-cart-row';

        const colName = document.createElement('div');
        colName.style.display = 'flex';
        colName.style.flexDirection = 'column';
        const nTitle = document.createElement('span');
        nTitle.style.fontWeight = '700';
        nTitle.textContent = item.name;
        const nSub = document.createElement('span');
        nSub.style.fontSize = 'var(--fs-xs)';
        nSub.style.color = 'var(--color-text-muted)';
        nSub.textContent = `${money(item.price)} บาท/${unit}`;
        colName.appendChild(nTitle);
        colName.appendChild(nSub);

        const colQty = document.createElement('div');
        colQty.style.display = 'flex';
        colQty.style.alignItems = 'center';
        colQty.style.justifyContent = 'center';
        colQty.style.gap = 'var(--space-1)';

        const mBtn = document.createElement('button');
        mBtn.type = 'button';
        mBtn.className = 'btn btn-sm btn-ghost';
        mBtn.style.minWidth = '28px';
        mBtn.style.height = '28px';
        mBtn.style.padding = '0';
        mBtn.textContent = '−';
        mBtn.addEventListener('click', () => this._changeItemQty(item, -1));

        const qSpan = document.createElement('span');
        qSpan.style.fontWeight = '700';
        qSpan.style.minWidth = '54px';
        qSpan.style.textAlign = 'center';
        qSpan.textContent = `${quantity} ${unit}`;

        const pBtn = document.createElement('button');
        pBtn.type = 'button';
        pBtn.className = 'btn btn-sm btn-ghost';
        pBtn.style.minWidth = '28px';
        pBtn.style.height = '28px';
        pBtn.style.padding = '0';
        pBtn.textContent = '+';
        pBtn.addEventListener('click', () => this._changeItemQty(item, 1));

        colQty.appendChild(mBtn);
        colQty.appendChild(qSpan);
        colQty.appendChild(pBtn);

        const colPrice = document.createElement('div');
        colPrice.style.display = 'flex';
        colPrice.style.alignItems = 'center';
        colPrice.style.justifyContent = 'flex-end';
        colPrice.style.gap = 'var(--space-2)';
        const pTxt = document.createElement('span');
        pTxt.style.fontWeight = '700';
        pTxt.className = 'money';
        pTxt.textContent = money(lineAmt);
        const delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'btn btn-sm btn-ghost';
        delBtn.style.minWidth = '32px';
        delBtn.style.padding = 'var(--space-1)';
        delBtn.textContent = '✕';
        delBtn.title = 'ลบรายการนี้';
        delBtn.addEventListener('click', () => {
          delete this.cartMap[item.id];
          this._renderOtherItems();
          this._renderLeftCart();
        });
        colPrice.appendChild(pTxt);
        colPrice.appendChild(delBtn);

        row.appendChild(colName);
        row.appendChild(colQty);
        row.appendChild(colPrice);
        this.cartListEl.appendChild(row);
      }
    }

    // คำนวณยอดรวมทั้งหมด
    const weighSubtotal = this._calcWeighPrice(this.weighGramsTotal);
    let otherSubtotal = 0;
    let otherCount = 0;
    for (const { item, quantity } of activeOtherItems) {
      otherSubtotal += Math.round(Number(item.price) * quantity * 100) / 100;
      otherCount += quantity;
    }
    const subtotal = Math.round((weighSubtotal + otherSubtotal) * 100) / 100;
    const totalLineCount = (this.weighGramsTotal > 0 ? 1 : 0) + otherCount;

    const addSummaryRow = (label, value, { bold = false, highlight = false, danger = false } = {}) => {
      const r = document.createElement('div');
      r.style.display = 'flex';
      r.style.justifyContent = 'space-between';
      r.style.alignItems = 'baseline';
      r.style.fontSize = highlight ? 'var(--fs-2xl)' : 'var(--fs-base)';
      if (bold || highlight) r.style.fontWeight = '700';
      if (danger) r.style.color = 'var(--color-danger)';
      const l = document.createElement('span');
      l.textContent = label;
      const v = document.createElement('span');
      v.className = 'money';
      if (highlight) {
        v.style.fontSize = 'var(--fs-page-title)';
        v.style.color = 'var(--color-primary)';
      }
      v.textContent = value;
      r.appendChild(l);
      r.appendChild(v);
      this.summaryBox.appendChild(r);
    };

    addSummaryRow(
      'น้ำหนักเนื้อชั่งกิโลรวม',
      this.weighGramsTotal > 0
        ? `${weight_text(this.weighGramsTotal)} (${baht(weighSubtotal)})`
        : '0 กก. (ขั้นต่ำ 1 กก.)',
      { bold: true, danger: !weighOk }
    );
    addSummaryRow(
      'รายการของเสริมรวม',
      `${otherCount} ชิ้น/หน่วย (${baht(otherSubtotal)})`
    );
    addSummaryRow('จำนวนรายการทั้งหมด', `${totalLineCount} รายการ`);
    addSummaryRow('ยอดรวมค่าสินค้า', baht(subtotal), { bold: true, highlight: true });

    if (!weighOk) {
      const warn = document.createElement('div');
      warn.style.fontSize = 'var(--fs-sm)';
      warn.style.fontWeight = '700';
      warn.style.color = 'var(--color-danger)';
      warn.textContent =
        '⚠️ ลูกค้าต้องซื้อเนื้อชั่งกิโลขั้นต่ำ 1 กิโลกรัม (10 ขีด / 1,000 กรัม) ขึ้นไป จึงจะไปส่วนชำระเงินได้';
      this.summaryBox.appendChild(warn);
    }

    this.checkoutBtn.disabled = !weighOk;
  }

  _buildItemsPayload() {
    const out = [];
    for (const [midStr, q] of Object.entries(this.cartMap)) {
      if (q > 0) {
        out.push({ menu_item_id: Number(midStr), quantity: Number(q) });
      }
    }
    return out;
  }

  async openPaymentDialog() {
    if (this.weighGramsTotal < this.minWeighGrams) {
      this.app.toast(
        'ลูกค้าต้องซื้อพวกเนื้อชั่งกิโลขั้นต่ำ 1 กิโลกรัมขึ้นไป',
        'error'
      );
      return;
    }

    let preview;
    try {
      preview = await apiPost('/api/staff/takeaway/preview', {
        weigh_grams: this.weighGramsTotal,
        items: this._buildItemsPayload(),
        promo_id: this.promoId,
      });
    } catch (err) {
      this.app.toast(err.message, 'error');
      return;
    }

    const dlg = new BaseDialog('ชำระเงินสั่งกลับบ้าน', { width: 560 });
    let method = 'cash';
    let selectedPromoId = preview.promo_id || null;
    let currentPreview = preview;
    let submitting = false;

    // สรุปยอดในหน้าต่างชำระเงิน
    const totalsBox = document.createElement('div');
    totalsBox.className = 'card';
    totalsBox.style.backgroundColor = 'var(--color-row-alt)';
    totalsBox.style.display = 'flex';
    totalsBox.style.flexDirection = 'column';
    totalsBox.style.gap = 'var(--space-1)';
    dlg.body.appendChild(totalsBox);

    // แถวเลือกโปรโมชั่น + ช่องทางชำระเงิน (เงินสด / พร้อมเพย์)
    const ctrlRow = document.createElement('div');
    ctrlRow.style.display = 'flex';
    ctrlRow.style.alignItems = 'center';
    ctrlRow.style.justifyContent = 'space-between';
    ctrlRow.style.gap = 'var(--space-2)';
    ctrlRow.style.flexWrap = 'wrap';

    const promoBox = document.createElement('div');
    promoBox.style.display = 'flex';
    promoBox.style.alignItems = 'center';
    promoBox.style.gap = 'var(--space-2)';
    const promoLbl = document.createElement('span');
    promoLbl.style.fontWeight = '700';
    promoLbl.textContent = 'โปรโมชั่น';
    const promoSelect = document.createElement('select');
    promoSelect.className = 'field-select';
    promoSelect.style.width = '220px';
    promoBox.appendChild(promoLbl);
    promoBox.appendChild(promoSelect);

    const methodSeg = document.createElement('div');
    methodSeg.className = 'seg-group';
    const btnCash = document.createElement('button');
    btnCash.type = 'button';
    btnCash.className = 'seg-btn is-active';
    btnCash.textContent = LABEL_CASH;
    const btnPromptPay = document.createElement('button');
    btnPromptPay.type = 'button';
    btnPromptPay.className = 'seg-btn';
    btnPromptPay.textContent = LABEL_PROMPTPAY;
    methodSeg.appendChild(btnCash);
    methodSeg.appendChild(btnPromptPay);

    ctrlRow.appendChild(promoBox);
    ctrlRow.appendChild(methodSeg);
    dlg.body.appendChild(ctrlRow);

    // แถวรับเงินสด
    const cashRow = document.createElement('div');
    cashRow.style.display = 'flex';
    cashRow.style.alignItems = 'center';
    cashRow.style.gap = 'var(--space-2)';
    cashRow.style.flexWrap = 'wrap';
    const cashLbl = document.createElement('span');
    cashLbl.style.fontWeight = '700';
    cashLbl.textContent = 'รับเงินสดมา (บาท)';
    const cashInput = document.createElement('input');
    cashInput.type = 'text';
    cashInput.className = 'field-input num';
    cashInput.style.width = '150px';
    cashInput.style.textAlign = 'right';
    cashInput.placeholder = '0.00';
    const changeLabel = document.createElement('span');
    changeLabel.style.fontWeight = '700';
    cashRow.appendChild(cashLbl);
    cashRow.appendChild(cashInput);
    cashRow.appendChild(changeLabel);
    dlg.body.appendChild(cashRow);

    // กรอบ QR PromptPay
    const qrFrame = document.createElement('div');
    qrFrame.className = 'card hidden';
    qrFrame.style.backgroundColor = 'var(--color-row-alt)';
    qrFrame.style.display = 'flex';
    qrFrame.style.alignItems = 'center';
    qrFrame.style.gap = 'var(--space-3)';

    const qrImgBox = document.createElement('div');
    qrImgBox.style.width = '148px';
    qrImgBox.style.height = '148px';
    qrImgBox.style.backgroundColor = '#ffffff';
    qrImgBox.style.borderRadius = 'var(--radius-md)';
    qrImgBox.style.display = 'flex';
    qrImgBox.style.alignItems = 'center';
    qrImgBox.style.justifyContent = 'center';
    qrImgBox.style.flexShrink = '0';

    const qrInfo = document.createElement('div');
    qrInfo.style.display = 'flex';
    qrInfo.style.flexDirection = 'column';
    qrInfo.style.gap = 'var(--space-1)';
    const qrStatusBadge = createStatusBadge('สถานะ: รอตรวจสอบการโอน', 'var(--color-warning)');
    qrStatusBadge.style.alignSelf = 'flex-start';
    const qrAmountLabel = document.createElement('div');
    qrAmountLabel.style.fontSize = 'var(--fs-xl)';
    qrAmountLabel.style.fontWeight = '700';
    qrAmountLabel.style.color = 'var(--color-primary)';
    const qrAccountLabel = document.createElement('div');
    qrAccountLabel.style.fontSize = 'var(--fs-base)';
    qrAccountLabel.style.fontWeight = '700';
    qrAccountLabel.style.whiteSpace = 'pre-line';
    const qrHint = document.createElement('div');
    qrHint.style.fontSize = 'var(--fs-xs)';
    qrHint.style.color = 'var(--color-text-muted)';
    qrHint.textContent =
      'กรุณาตรวจสลิป/ยอดเงินเข้าแอปธนาคารของร้านก่อนกดยืนยันชำระเงิน';

    qrInfo.appendChild(qrStatusBadge);
    qrInfo.appendChild(qrAmountLabel);
    qrInfo.appendChild(qrAccountLabel);
    qrInfo.appendChild(qrHint);
    qrFrame.appendChild(qrImgBox);
    qrFrame.appendChild(qrInfo);
    dlg.body.appendChild(qrFrame);

    const errEl = document.createElement('div');
    errEl.className = 'modal-error';
    dlg.body.appendChild(errEl);

    const parseCashStatus = () => {
      const totalCents = Math.round(Number(currentPreview.total) * 100);
      const totalVal = totalCents / 100;
      const raw = (cashInput.value || '').trim().replace(/,/g, '');
      if (!raw) {
        return {
          ok: false,
          rec: null,
          chg: null,
          msg: `กรุณากรอกเงินสดที่รับ (อย่างน้อย ${baht(totalVal)})`,
        };
      }
      const num = Number(raw);
      if (!Number.isFinite(num) || Number.isNaN(num)) {
        return {
          ok: false,
          rec: null,
          chg: null,
          msg: 'กรุณากรอกจำนวนเงินเป็นตัวเลขที่ถูกต้อง',
        };
      }
      if (num < 0) {
        return {
          ok: false,
          rec: null,
          chg: null,
          msg: 'ห้ามกรอกจำนวนเงินติดลบ',
        };
      }
      const recCents = Math.round(num * 100);
      const recVal = recCents / 100;
      if (recCents < totalCents) {
        const diffVal = (totalCents - recCents) / 100;
        return {
          ok: false,
          rec: recVal,
          chg: null,
          msg: `เงินสดรับไม่พอ (ยังขาด ${baht(diffVal)})`,
        };
      }
      const chgVal = (recCents - totalCents) / 100;
      return {
        ok: true,
        rec: recVal,
        chg: chgVal,
        msg: `เงินทอน ${baht(chgVal)}`,
      };
    };

    const renderTotalsAndControls = () => {
      totalsBox.textContent = '';
      const addTRow = (lbl, val, big = false) => {
        const r = document.createElement('div');
        r.style.display = 'flex';
        r.style.justifyContent = 'space-between';
        r.style.alignItems = 'baseline';
        r.style.fontSize = big ? 'var(--fs-xl)' : 'var(--fs-base)';
        if (big) r.style.fontWeight = '700';
        const l = document.createElement('span');
        l.textContent = lbl;
        const v = document.createElement('span');
        v.className = 'money';
        if (big) v.style.color = 'var(--color-primary)';
        v.textContent = val;
        r.appendChild(l);
        r.appendChild(v);
        totalsBox.appendChild(r);
      };

      addTRow(
        `เนื้อชั่งกิโล (${weight_text(currentPreview.weigh_grams)})`,
        money(currentPreview.weigh_total)
      );
      if (currentPreview.order_lines && currentPreview.order_lines.length > 0) {
        addTRow(
          `รายการของเสริม (${currentPreview.order_lines.length} รายการ)`,
          money(currentPreview.order_total)
        );
      }
      addTRow('รวมเป็นเงินก่อนคิดภาษีและส่วนลด', money(currentPreview.subtotal));
      if (currentPreview.discount > 0) {
        addTRow(
          `ส่วนลด ${currentPreview.promo_name || ''}`.trim(),
          `-${money(currentPreview.discount)}`
        );
      }
      if (currentPreview.service_charge > 0) {
        addTRow(
          `ค่าบริการ ${Number(currentPreview.service_charge_percent)}%`,
          money(currentPreview.service_charge)
        );
      }
      if (currentPreview.vat > 0) {
        addTRow(
          `ภาษีมูลค่าเพิ่ม ${Number(currentPreview.vat_percent)}%`,
          money(currentPreview.vat)
        );
      }
      addTRow('ยอดที่ต้องชำระสุทธิ', baht(currentPreview.total), true);

      // โปรโมชั่น
      promoSelect.textContent = '';
      const noneOpt = document.createElement('option');
      noneOpt.value = '';
      noneOpt.textContent = NO_PROMO;
      promoSelect.appendChild(noneOpt);
      for (const p of currentPreview.available_promos || []) {
        const opt = document.createElement('option');
        opt.value = String(p.id);
        opt.textContent = p.display_label;
        if (p.id === selectedPromoId) opt.selected = true;
        promoSelect.appendChild(opt);
      }

      if (method === 'cash') {
        cashRow.classList.remove('hidden');
        qrFrame.classList.add('hidden');
        const st = parseCashStatus();
        changeLabel.textContent = st.msg;
        changeLabel.style.color = st.ok ? 'var(--color-info)' : 'var(--color-danger)';
        if (dlg.confirmBtn) {
          dlg.confirmBtn.textContent = 'ยืนยันรับเงินสด & ออกสลิป';
          dlg.confirmBtn.disabled = !st.ok || submitting;
        }
      } else {
        cashRow.classList.add('hidden');
        qrFrame.classList.remove('hidden');
        qrImgBox.textContent = '';
        const pp = currentPreview.promptpay;
        if (pp && pp.valid && pp.data_url) {
          const img = document.createElement('img');
          img.src = pp.data_url;
          img.alt = 'PromptPay QR';
          img.style.width = '140px';
          img.style.height = '140px';
          qrImgBox.appendChild(img);
          qrStatusBadge.textContent = `สถานะ: ${pp.status_th}`;
          qrStatusBadge.style.backgroundColor = 'var(--color-warning)';
          qrAmountLabel.textContent = `สแกนชำระ: ${baht(pp.amount)}`;
          qrAccountLabel.textContent = `พร้อมเพย์: ${pp.promptpay_id}\nชื่อบัญชี: ${pp.promptpay_name}`;
        } else {
          qrImgBox.textContent = 'สร้าง QR ไม่ได้';
          qrStatusBadge.textContent = 'ข้อมูล PromptPay ไม่ถูกต้อง';
          qrStatusBadge.style.backgroundColor = 'var(--color-danger)';
          qrAmountLabel.textContent = (pp && pp.error) || '';
          qrAccountLabel.textContent = 'กรุณาตรวจสอบหมายเลข PromptPay ที่หน้าตั้งค่า';
        }
        if (dlg.confirmBtn) {
          dlg.confirmBtn.textContent = 'ยืนยันรับเงินโอน & ออกสลิป';
          dlg.confirmBtn.disabled = !(pp && pp.valid) || submitting;
        }
      }
    };

    promoSelect.addEventListener('change', async () => {
      const val = promoSelect.value;
      selectedPromoId = val ? Number(val) : null;
      this.promoId = selectedPromoId;
      try {
        currentPreview = await apiPost('/api/staff/takeaway/preview', {
          weigh_grams: this.weighGramsTotal,
          items: this._buildItemsPayload(),
          promo_id: selectedPromoId,
        });
        renderTotalsAndControls();
      } catch (err) {
        errEl.textContent = err.message;
      }
    });

    btnCash.addEventListener('click', () => {
      method = 'cash';
      btnCash.classList.add('is-active');
      btnPromptPay.classList.remove('is-active');
      errEl.textContent = '';
      renderTotalsAndControls();
    });

    btnPromptPay.addEventListener('click', () => {
      method = 'transfer';
      btnPromptPay.classList.add('is-active');
      btnCash.classList.remove('is-active');
      errEl.textContent = '';
      renderTotalsAndControls();
    });

    cashInput.addEventListener('input', () => {
      errEl.textContent = '';
      renderTotalsAndControls();
    });

    dlg.addButtons({
      confirmText: 'ยืนยันรับเงินสด & ออกสลิป',
      cancelText: 'กลับไปแก้ไขรายการ',
      variant: 'success',
      onConfirm: async () => {
        if (submitting) return;
        let amountReceived;
        if (method === 'cash') {
          const st = parseCashStatus();
          if (!st.ok || st.rec === null) {
            errEl.textContent = st.msg || 'กรุณาตรวจสอบจำนวนเงินสดที่รับ';
            return;
          }
          amountReceived = st.rec;
        } else {
          if (!currentPreview.promptpay || !currentPreview.promptpay.valid) {
            errEl.textContent = 'ข้อมูล PromptPay ไม่ถูกต้อง';
            return;
          }
          amountReceived = Number(currentPreview.total);
        }

        submitting = true;
        dlg.confirmBtn.disabled = true;
        errEl.textContent = '';
        try {
          const res = await apiPost('/api/staff/takeaway/pay', {
            weigh_grams: this.weighGramsTotal,
            items: this._buildItemsPayload(),
            payment_method: method,
            promo_id: selectedPromoId,
            amount_received: amountReceived,
          });
          dlg.close(true);
          this.app.toast(
            res.message || 'บันทึกสั่งกลับบ้านและชำระเงินเรียบร้อยแล้ว',
            'success'
          );
          this.clearAll();
          await this.refreshCatalog(true);
          if (this.app.alertCenter) {
            this.app.alertCenter.refreshView(false);
          }
          await openTakeawayReceiptDialog(res.session_id, res.bill, res.receipt_info);
        } catch (err) {
          errEl.textContent = err.message;
          submitting = false;
          renderTotalsAndControls();
        }
      },
    });

    renderTotalsAndControls();
    setTimeout(() => cashInput.focus(), 60);
    await dlg.show();
  }
}

async function openTakeawayReceiptDialog(sessionId, bill, info) {
  const dlg = new BaseDialog('ชำระเงินสั่งกลับบ้านเรียบร้อย — ใบเสร็จรับเงิน', {
    width: 560,
  });
  const shop = info.shop || {};

  const topNotice = document.createElement('div');
  topNotice.style.fontSize = 'var(--fs-xl)';
  topNotice.style.fontWeight = '700';
  topNotice.style.color = 'var(--color-success)';
  topNotice.textContent = `สั่งกลับบ้าน (บิล #${info.bill_no}) ชำระเงินเรียบร้อยแล้ว (${info.method_th})`;
  dlg.body.appendChild(topNotice);

  const paper = document.createElement('div');
  paper.className = 'receipt-paper';

  const addCenter = (txt, sizePx = 13, bold = false) => {
    const el = document.createElement('div');
    el.className = 'receipt-center';
    el.style.fontSize = `${sizePx}px`;
    if (bold) el.style.fontWeight = '700';
    el.textContent = txt;
    paper.appendChild(el);
  };

  const addDivider = () => {
    const d = document.createElement('div');
    d.className = 'receipt-divider';
    paper.appendChild(d);
  };

  const addMeta = (lbl, val) => {
    const r = document.createElement('div');
    r.className = 'receipt-meta-row';
    const l = document.createElement('span');
    l.style.fontWeight = '700';
    l.textContent = lbl;
    const v = document.createElement('span');
    v.textContent = val;
    r.appendChild(l);
    r.appendChild(v);
    paper.appendChild(r);
  };

  const addSumRow = (lbl, val, { bold = false, highlight = false } = {}) => {
    const r = document.createElement('div');
    r.className = 'receipt-sum-row';
    if (bold || highlight) r.style.fontWeight = '700';
    if (highlight) {
      r.style.color = 'var(--color-primary)';
      r.style.fontSize = 'var(--fs-md)';
    }
    const l = document.createElement('span');
    l.textContent = lbl;
    const v = document.createElement('span');
    v.className = 'receipt-sum-val';
    v.textContent = val;
    r.appendChild(l);
    r.appendChild(v);
    paper.appendChild(r);
  };

  addCenter(shop.shop_name || 'ร้านหมูกระทะต้นมะค่า', 16, true);
  if (shop.shop_tax_id_enabled && shop.shop_tax_id) {
    addCenter(`เลขผู้เสียภาษี ${shop.shop_tax_id}`, 13, false);
  }
  addCenter('ใบกำกับภาษีอย่างย่อ/ใบเสร็จรับเงิน', 13, true);
  if (shop.address_line1) addCenter(shop.address_line1, 12, false);
  if (shop.address_line2) addCenter(shop.address_line2, 12, false);
  if (shop.phone_line) addCenter(shop.phone_line, 12, false);

  addDivider();
  addMeta('พนักงานขาย', info.cashier);
  addMeta('วันที่', info.date_str);
  addMeta('เวลา', info.time_str);
  addMeta('ประเภท', `สั่งกลับบ้าน (บิล #${info.bill_no})`);
  addDivider();

  const headRow = document.createElement('div');
  headRow.className = 'receipt-line-row';
  headRow.style.fontWeight = '700';
  const h1 = document.createElement('span');
  h1.style.textAlign = 'center';
  h1.textContent = 'จำนวน';
  const h2 = document.createElement('span');
  h2.textContent = 'รายการ';
  const h3 = document.createElement('span');
  h3.style.textAlign = 'right';
  h3.textContent = 'จำนวนเงิน';
  headRow.appendChild(h1);
  headRow.appendChild(h2);
  headRow.appendChild(h3);
  paper.appendChild(headRow);
  addDivider();

  for (const ln of info.lines || []) {
    const r = document.createElement('div');
    r.className = 'receipt-line-row';
    const c1 = document.createElement('span');
    c1.style.textAlign = 'center';
    c1.textContent = ln.qty_str;
    const c2 = document.createElement('span');
    c2.textContent = ln.name;
    const c3 = document.createElement('span');
    c3.style.textAlign = 'right';
    c3.className = 'money';
    c3.textContent = ln.amount_str;
    r.appendChild(c1);
    r.appendChild(c2);
    r.appendChild(c3);
    paper.appendChild(r);
  }

  addDivider();
  const qtyTotal = document.createElement('div');
  qtyTotal.style.fontSize = 'var(--fs-sm)';
  qtyTotal.style.fontWeight = '700';
  qtyTotal.textContent = `จำนวนรวม   ${info.total_qty_count}`;
  paper.appendChild(qtyTotal);

  const promoSuffix = info.promo_name ? ` (${info.promo_name})` : '';
  addSumRow('รวมเป็นเงิน', money(info.subtotal));
  addSumRow(`ส่วนลด${promoSuffix}`, money(info.discount));
  addSumRow('จำนวนเงินหลังหักส่วนลด', money(info.after_discount));
  if (info.service_charge > 0) {
    const pct = info.service_charge_percent;
    const scLbl = pct ? `ค่าบริการ (${Number(pct)}%)` : 'ค่าบริการ';
    addSumRow(scLbl, money(info.service_charge));
  }
  addSumRow('ราคาไม่รวมภาษีมูลค่าเพิ่ม', money(info.pre_vat));
  addSumRow('ภาษีมูลค่าเพิ่ม 7%', money(info.vat));
  addSumRow('รวมทั้งสิ้น', baht(info.total), { bold: true, highlight: true });

  addDivider();
  const payRow = document.createElement('div');
  payRow.style.fontSize = 'var(--fs-sm)';
  payRow.style.fontWeight = '700';
  payRow.textContent = `ช่องทางการชำระ :   ${info.method_th}`;
  paper.appendChild(payRow);

  if (info.method === 'cash') {
    const recRow = document.createElement('div');
    recRow.style.display = 'flex';
    recRow.style.justifyContent = 'space-between';
    recRow.style.fontSize = 'var(--fs-sm)';
    const rl = document.createElement('span');
    rl.textContent = 'รับเงินมา';
    const rv = document.createElement('span');
    rv.textContent = money(info.received);
    recRow.appendChild(rl);
    recRow.appendChild(rv);
    paper.appendChild(recRow);

    const chgRow = document.createElement('div');
    chgRow.style.display = 'flex';
    chgRow.style.justifyContent = 'space-between';
    chgRow.style.fontSize = 'var(--fs-sm)';
    chgRow.style.fontWeight = '700';
    const cl = document.createElement('span');
    cl.textContent = 'เงินทอน';
    const cv = document.createElement('span');
    cv.textContent = money(info.change);
    chgRow.appendChild(cl);
    chgRow.appendChild(cv);
    paper.appendChild(chgRow);
  }

  addDivider();
  addCenter(shop.shop_name || 'ร้านหมูกระทะต้นมะค่า', 14, true);
  addCenter('ขอบคุณที่ใช้บริการ', 13, false);
  dlg.body.appendChild(paper);

  const savedLbl = document.createElement('div');
  savedLbl.style.fontSize = 'var(--fs-sm)';
  savedLbl.style.color = 'var(--color-text-muted)';
  savedLbl.textContent = 'เลือกส่งออกใบเสร็จเป็นไฟล์ PDF หรือ TXT ด้านล่าง';
  dlg.body.appendChild(savedLbl);

  const exportFile = async (fmt) => {
    try {
      const res = await apiPost(`/api/staff/checkout/${sessionId}/export/${fmt}`, {});
      savedLbl.textContent = res.message;
      savedLbl.style.color = 'var(--color-success)';
      if (res.download_url) {
        const a = document.createElement('a');
        a.href = res.download_url;
        a.download = res.filename || `receipt.${fmt}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }
    } catch (err) {
      savedLbl.textContent = err.message;
      savedLbl.style.color = 'var(--color-danger)';
    }
  };

  dlg.footer.textContent = '';
  const leftBtns = document.createElement('div');
  leftBtns.style.display = 'flex';
  leftBtns.style.gap = 'var(--space-2)';
  leftBtns.style.marginRight = 'auto';

  const pdfBtn = document.createElement('button');
  pdfBtn.type = 'button';
  pdfBtn.className = 'btn btn-sm btn-primary';
  pdfBtn.textContent = 'บันทึก PDF (.pdf)';
  pdfBtn.addEventListener('click', () => exportFile('pdf'));

  const txtBtn = document.createElement('button');
  txtBtn.type = 'button';
  txtBtn.className = 'btn btn-sm btn-ghost';
  txtBtn.textContent = 'บันทึก TXT (.txt)';
  txtBtn.addEventListener('click', () => exportFile('txt'));

  const printBtn = document.createElement('button');
  printBtn.type = 'button';
  printBtn.className = 'btn btn-sm btn-info';
  printBtn.textContent = 'พิมพ์';
  printBtn.addEventListener('click', () => window.print());

  leftBtns.appendChild(pdfBtn);
  leftBtns.appendChild(txtBtn);
  leftBtns.appendChild(printBtn);
  dlg.footer.appendChild(leftBtns);

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'btn btn-primary';
  closeBtn.textContent = 'ปิด';
  closeBtn.addEventListener('click', () => dlg.close(true));
  dlg.footer.appendChild(closeBtn);

  await dlg.show();
}
