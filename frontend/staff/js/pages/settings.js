/**
 * frontend/staff/js/pages/settings.js — ตั้งค่าร้าน (เจ้าของ)
 * คัดลอกจาก ui/owner/settings_page.py ทุกตัวอักษร
 */

import { apiGet, apiPut } from '../../../shared/js/api.js';
import { showInfoDialog } from '../../../shared/js/dialogs.js';

function createField(label, placeholder = '') {
  const group = document.createElement('div');
  group.className = 'field-group';
  const lbl = document.createElement('label');
  lbl.className = 'field-label';
  lbl.textContent = label;
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'field-input';
  input.placeholder = placeholder;
  group.appendChild(lbl);
  group.appendChild(input);
  return { el: group, input };
}

function createSectionCard(title, hint) {
  const card = document.createElement('section');
  card.className = 'card audit-block';
  card.style.display = 'flex';
  card.style.flexDirection = 'column';
  card.style.gap = 'var(--space-3)';

  const head = document.createElement('div');
  head.style.display = 'flex';
  head.style.flexDirection = 'column';
  head.style.gap = 'var(--space-1)';
  const t = document.createElement('h2');
  t.style.fontSize = 'var(--fs-xl)';
  t.style.fontWeight = '700';
  t.textContent = title;
  const h = document.createElement('div');
  h.style.fontSize = 'var(--fs-sm)';
  h.style.color = 'var(--color-text-muted)';
  h.textContent = hint;
  head.appendChild(t);
  head.appendChild(h);
  card.appendChild(head);
  return card;
}

export class SettingsPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.lanUrl = null;
    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'ตั้งค่า';
    const sub = document.createElement('div');
    sub.className = 'page-subtitle';
    sub.textContent =
      'ค่าที่ปรับได้ของร้าน — กด "บันทึกการตั้งค่า" ด้านล่างเมื่อแก้เสร็จ';
    left.appendChild(title);
    left.appendChild(sub);
    header.appendChild(left);
    this.container.appendChild(header);

    // 1. ข้อมูลร้านและใบเสร็จรับเงิน
    const cardShop = createSectionCard(
      'ข้อมูลร้านและใบเสร็จรับเงิน',
      'กำหนดชื่อร้าน เลขประจำตัวผู้เสียภาษี (เลือกเปิด/ปิดการแสดงผลบนใบเสร็จได้) ที่อยู่ และเบอร์โทรศัพท์ที่จะพิมพ์บนใบเสร็จรับเงิน'
    );
    const shopRow1 = document.createElement('div');
    shopRow1.style.display = 'grid';
    shopRow1.style.gridTemplateColumns = 'repeat(3, 1fr)';
    shopRow1.style.gap = 'var(--space-3)';
    this.shopName = createField('ชื่อร้าน', 'ร้านหมูกระทะต้นมะค่า');
    this.shopTaxId = createField(
      'เลขประจำตัวผู้เสียภาษี (13 หลัก)',
      'เว้นว่างได้หากไม่มี'
    );
    this.shopPhone = createField('เบอร์โทรศัพท์ร้าน', 'เช่น 012-345-6789');
    shopRow1.appendChild(this.shopName.el);
    shopRow1.appendChild(this.shopTaxId.el);
    shopRow1.appendChild(this.shopPhone.el);
    cardShop.appendChild(shopRow1);

    const taxSwRow = document.createElement('label');
    taxSwRow.style.display = 'inline-flex';
    taxSwRow.style.alignItems = 'center';
    taxSwRow.style.gap = 'var(--space-2)';
    taxSwRow.style.cursor = 'pointer';
    taxSwRow.style.fontWeight = '700';
    this.shopTaxIdSwitch = document.createElement('input');
    this.shopTaxIdSwitch.type = 'checkbox';
    const taxSwTxt = document.createElement('span');
    taxSwTxt.textContent = 'แสดงเลขประจำตัวผู้เสียภาษีในใบเสร็จรับเงิน';
    taxSwRow.appendChild(this.shopTaxIdSwitch);
    taxSwRow.appendChild(taxSwTxt);
    cardShop.appendChild(taxSwRow);

    const shopRow2 = document.createElement('div');
    shopRow2.style.display = 'grid';
    shopRow2.style.gridTemplateColumns = '2fr 1fr 1fr';
    shopRow2.style.gap = 'var(--space-3)';
    this.shopAddress = createField(
      'ที่อยู่ร้าน (บ้านเลขที่ / หมู่ที่ / ถนน)',
      'เช่น 99 หมู่ที่ 1'
    );
    this.shopSubdistrict = createField('ตำบล / แขวง', 'วังตะเฆ่');
    this.shopDistrict = createField('อำเภอ / เขต', 'หนองบัวระเหว');
    shopRow2.appendChild(this.shopAddress.el);
    shopRow2.appendChild(this.shopSubdistrict.el);
    shopRow2.appendChild(this.shopDistrict.el);
    cardShop.appendChild(shopRow2);

    const shopRow3 = document.createElement('div');
    shopRow3.style.display = 'grid';
    shopRow3.style.gridTemplateColumns = 'repeat(3, 1fr)';
    shopRow3.style.gap = 'var(--space-3)';
    this.shopProvince = createField('จังหวัด', 'ชัยภูมิ');
    this.shopPostalCode = createField('รหัสไปรษณีย์ (5 หลัก)', '36250');
    shopRow3.appendChild(this.shopProvince.el);
    shopRow3.appendChild(this.shopPostalCode.el);
    cardShop.appendChild(shopRow3);
    this.container.appendChild(cardShop);

    // 2. ลิงก์เว็บลูกค้า (QR โต๊ะ)
    const cardUrl = createSectionCard(
      'ลิงก์เว็บลูกค้า (QR โต๊ะ)',
      'ที่อยู่ที่ลูกค้าเปิดจากมือถือหลังสแกน QR เช่น http://192.168.1.50:8080 (ใช้ IP เครื่องร้านใน Wi-Fi เดียวกัน)'
    );
    this.baseUrl = createField('ลิงก์เว็บลูกค้า', 'http://192.168.1.50:8080');
    cardUrl.appendChild(this.baseUrl.el);

    const lanRow = document.createElement('div');
    lanRow.style.display = 'flex';
    lanRow.style.alignItems = 'center';
    lanRow.style.gap = 'var(--space-2)';
    this.lanLabel = document.createElement('span');
    this.lanLabel.style.fontSize = 'var(--fs-sm)';
    this.lanLabel.style.color = 'var(--color-text-muted)';
    this.lanBtn = document.createElement('button');
    this.lanBtn.type = 'button';
    this.lanBtn.className = 'btn btn-sm btn-ghost hidden';
    this.lanBtn.textContent = 'ใช้ค่านี้';
    this.lanBtn.addEventListener('click', () => {
      if (this.lanUrl) {
        this.baseUrl.input.value = this.lanUrl;
      }
    });
    lanRow.appendChild(this.lanLabel);
    lanRow.appendChild(this.lanBtn);
    cardUrl.appendChild(lanRow);
    this.container.appendChild(cardUrl);

    // 3. การรับชำระเงิน PromptPay และอัตราราคาชั่งกิโล
    const cardPp = createSectionCard(
      'การรับชำระเงิน PromptPay และอัตราราคาชั่งกิโล',
      'ข้อมูลบัญชีสำหรับสร้าง QR รับเงินตามยอดสุทธิอัตโนมัติในหน้าชำระเงิน และราคาหมูกระทะชั่งกิโล (ค่าเริ่มต้น 299 บาท/กก.)'
    );
    const ppRow = document.createElement('div');
    ppRow.style.display = 'grid';
    ppRow.style.gridTemplateColumns = 'repeat(3, 1fr)';
    ppRow.style.gap = 'var(--space-3)';
    this.promptpayId = createField(
      'หมายเลข PromptPay (เบอร์ 10 หลัก / บัตร 13 หลัก)',
      '0123456789'
    );
    this.promptpayName = createField(
      'ชื่อบัญชีเจ้าของร้าน (แสดงให้พนักงานตรวจสอบ)',
      'นาย สมชาย ใจดี (ร้านหมูกระทะต้นมะค่า)'
    );
    this.weighPrice = createField(
      'ราคาชั่งกิโล (บาท/กก. · ค่าเริ่มต้น 299)',
      '299'
    );
    ppRow.appendChild(this.promptpayId.el);
    ppRow.appendChild(this.promptpayName.el);
    ppRow.appendChild(this.weighPrice.el);
    cardPp.appendChild(ppRow);
    this.container.appendChild(cardPp);

    // 4. แจ้งเตือนโต๊ะเงียบ และ เกณฑ์สต๊อกใกล้หมด
    const cardAlert = createSectionCard(
      'แจ้งเตือนโต๊ะเงียบ และ เกณฑ์สต๊อกใกล้หมด',
      'ระบบตรวจทุก 30 วินาที แล้วขึ้นแถบแจ้งเตือนให้พนักงาน — เกณฑ์สต๊อกใกล้หมดมีค่าเริ่มต้น 5 หน่วย (แก้ไขได้)'
    );
    const alertRow = document.createElement('div');
    alertRow.style.display = 'grid';
    alertRow.style.gridTemplateColumns = 'repeat(4, 1fr)';
    alertRow.style.gap = 'var(--space-3)';
    this.pendingMin = createField('โต๊ะรอยืนยันนานเกิน (นาที)');
    this.idleMin = createField('โต๊ะเปิดแล้วเงียบเกิน (นาที)');
    this.snoozeMin = createField('เตือนซ้ำหลังกด "ปล่อยไว้" (นาที)');
    this.stockThreshold = createField('เกณฑ์สต๊อกใกล้หมดเริ่มต้น (ค่าเริ่มต้น 5 หน่วย)');
    alertRow.appendChild(this.pendingMin.el);
    alertRow.appendChild(this.idleMin.el);
    alertRow.appendChild(this.snoozeMin.el);
    alertRow.appendChild(this.stockThreshold.el);
    cardAlert.appendChild(alertRow);
    this.container.appendChild(cardAlert);

    // 5. ค่าบริการและภาษีมูลค่าเพิ่ม
    const cardTax = createSectionCard(
      'ค่าบริการและภาษีมูลค่าเพิ่ม',
      'ค่าบริการคิดจากยอดหลังหักส่วนลด ; ภาษีมูลค่าเพิ่มคิดจาก (ยอดหลังหักส่วนลด + ค่าบริการ) — มีผลกับบิลถัดไป'
    );

    const makeSwitchPercentRow = (switchText) => {
      const r = document.createElement('div');
      r.style.display = 'flex';
      r.style.alignItems = 'flex-end';
      r.style.gap = 'var(--space-5)';
      const swLbl = document.createElement('label');
      swLbl.style.display = 'inline-flex';
      swLbl.style.alignItems = 'center';
      swLbl.style.gap = 'var(--space-2)';
      swLbl.style.minWidth = '190px';
      swLbl.style.height = 'var(--input-h)';
      swLbl.style.cursor = 'pointer';
      swLbl.style.fontWeight = '700';
      const chk = document.createElement('input');
      chk.type = 'checkbox';
      const txt = document.createElement('span');
      txt.textContent = switchText;
      swLbl.appendChild(chk);
      swLbl.appendChild(txt);

      const pctField = createField('อัตรา (%)');
      pctField.el.style.width = '140px';
      r.appendChild(swLbl);
      r.appendChild(pctField.el);
      return { row: r, chk, input: pctField.input };
    };

    this.serviceCtrl = makeSwitchPercentRow('เก็บค่าบริการ');
    this.vatCtrl = makeSwitchPercentRow('คิดภาษีมูลค่าเพิ่ม');
    cardTax.appendChild(this.serviceCtrl.row);
    cardTax.appendChild(this.vatCtrl.row);
    this.container.appendChild(cardTax);

    // แถบปุ่มบันทึกด้านล่าง
    const bottomRow = document.createElement('div');
    bottomRow.className = 'audit-block';
    bottomRow.style.display = 'flex';
    bottomRow.style.justifyContent = 'flex-end';
    bottomRow.style.gap = 'var(--space-2)';

    const resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.className = 'btn btn-lg btn-ghost';
    resetBtn.textContent = 'ยกเลิกการแก้ไข (โหลดค่าเดิม)';
    resetBtn.addEventListener('click', () => this.refresh());

    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'btn btn-lg btn-success';
    saveBtn.textContent = 'บันทึกการตั้งค่า';
    saveBtn.addEventListener('click', () => this.save());

    bottomRow.appendChild(resetBtn);
    bottomRow.appendChild(saveBtn);
    this.container.appendChild(bottomRow);
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
      const data = await apiGet('/api/owner/settings');
      const shop = data.shop || {};
      this.shopName.input.value = shop.shop_name || '';
      this.shopTaxId.input.value = shop.shop_tax_id || '';
      this.shopTaxIdSwitch.checked = Boolean(shop.shop_tax_id_enabled);
      this.shopAddress.input.value = shop.shop_address || '';
      this.shopSubdistrict.input.value = shop.shop_subdistrict || '';
      this.shopDistrict.input.value = shop.shop_district || '';
      this.shopProvince.input.value = shop.shop_province || '';
      this.shopPostalCode.input.value = shop.shop_postal_code || '';
      this.shopPhone.input.value = shop.shop_phone || '';

      this.baseUrl.input.value = data.public_base_url || '';
      this.lanUrl = data.lan_url;
      if (this.lanUrl) {
        this.lanLabel.textContent = `IP ของเครื่องนี้ในเครือข่าย: ${this.lanUrl}  (มือถือต้องต่อ Wi-Fi เดียวกัน)`;
        this.lanBtn.classList.remove('hidden');
      } else {
        this.lanLabel.textContent =
          'หา IP ของเครื่องนี้ไม่ได้ — ตรวจว่าต่อเครือข่ายอยู่ แล้วกรอกเอง';
        this.lanBtn.classList.add('hidden');
      }

      this.promptpayId.input.value = data.promptpay_id || '';
      this.promptpayName.input.value = data.promptpay_name || '';
      this.weighPrice.input.value = data.weigh_price_per_kg || '';
      this.pendingMin.input.value = data.alert_pending_minutes || '';
      this.idleMin.input.value = data.alert_idle_open_minutes || '';
      this.snoozeMin.input.value = data.alert_snooze_minutes || '';
      this.stockThreshold.input.value = data.stock_low_threshold || '';

      this.serviceCtrl.chk.checked = Boolean(data.service_charge_enabled);
      this.serviceCtrl.input.value = data.service_charge_percent || '';
      this.vatCtrl.chk.checked = Boolean(data.vat_enabled);
      this.vatCtrl.input.value = data.vat_percent || '';
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async save() {
    try {
      const payload = {
        shop_name: this.shopName.input.value,
        shop_tax_id: this.shopTaxId.input.value,
        shop_tax_id_enabled: this.shopTaxIdSwitch.checked,
        shop_address: this.shopAddress.input.value,
        shop_subdistrict: this.shopSubdistrict.input.value,
        shop_district: this.shopDistrict.input.value,
        shop_province: this.shopProvince.input.value,
        shop_postal_code: this.shopPostalCode.input.value,
        shop_phone: this.shopPhone.input.value,
        public_base_url: this.baseUrl.input.value,
        promptpay_id: this.promptpayId.input.value,
        promptpay_name: this.promptpayName.input.value,
        weigh_price_per_kg: this.weighPrice.input.value,
        alert_pending_minutes: this.pendingMin.input.value,
        alert_idle_open_minutes: this.idleMin.input.value,
        alert_snooze_minutes: this.snoozeMin.input.value,
        stock_low_threshold: this.stockThreshold.input.value,
        service_charge_enabled: this.serviceCtrl.chk.checked,
        service_charge_percent: this.serviceCtrl.input.value,
        vat_enabled: this.vatCtrl.chk.checked,
        vat_percent: this.vatCtrl.input.value,
      };
      const res = await apiPut('/api/owner/settings', payload);
      this.app.toast(res.message || 'บันทึกการตั้งค่าแล้ว', 'success');
      if (res.url_changed && res.url_changed_notice) {
        await showInfoDialog(res.url_changed_notice, {
          title: 'ต้องสร้าง QR ใหม่',
        });
      }
      await this.refresh();
      if (this.app.alertCenter) {
        this.app.alertCenter.refreshView(false);
      }
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }
}
