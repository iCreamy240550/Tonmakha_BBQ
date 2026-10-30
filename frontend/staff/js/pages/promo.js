/**
 * frontend/staff/js/pages/promo.js — โปรโมชั่น/ส่วนลด (เจ้าของร้าน)
 * แบ่งเป็น 2 ฝั่ง:
 * - ฝั่งซ้าย: โปรโมชั่นสำหรับคนทั่วไป (target = 'general')
 * - ฝั่งขวา: โปรโมชั่นสำหรับสมาชิก (target = 'member') + ปุ่มกดดูสมาชิก
 *   (แสดงเฉพาะ ชื่อ, อีเมล, เบอร์โทร และสถานะ "กำลังใช้งาน" เรียงขึ้นบนสุดเมื่อกำลังทานอยู่ที่ร้าน)
 */

import { apiGet, apiPatch, apiPost } from '../../../shared/js/api.js';
import { DataTable } from '../../../shared/js/data-table.js';
import { BaseDialog, confirmDialog } from '../../../shared/js/dialogs.js';
import { money, parse_date, parse_number } from '../../../shared/js/format.js';
import { createStatusBadge } from '../../../shared/js/status-badge.js';

export class PromoPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'โปรโมชั่น';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);

    const right = document.createElement('div');
    right.className = 'page-header-right';
    this.topMembersBtn = document.createElement('button');
    this.topMembersBtn.type = 'button';
    this.topMembersBtn.className = 'btn btn-info';
    this.topMembersBtn.dataset.testid = 'btn-view-members-top';
    this.topMembersBtn.textContent = '👥 ดูสมาชิก';
    this.topMembersBtn.addEventListener('click', () => this.openMembersModal());
    right.appendChild(this.topMembersBtn);

    header.appendChild(left);
    header.appendChild(right);
    this.container.appendChild(header);

    // แบ่งหน้าโปรโมชั่นเป็น 2 ฝั่ง: ซ้าย (คนทั่วไป) | ขวา (สมาชิก)
    const split = document.createElement('div');
    split.className = 'split-layout split-promo audit-block';

    // ==================== ฝั่งซ้าย: โปรโมชั่นสำหรับคนทั่วไป ====================
    const leftCard = document.createElement('div');
    leftCard.className = 'card promo-side-card';
    leftCard.dataset.testid = 'promo-left-general';

    const leftHead = document.createElement('div');
    leftHead.className = 'promo-side-header';
    const leftTitleWrap = document.createElement('div');
    const leftTitle = document.createElement('div');
    leftTitle.className = 'promo-side-title';
    leftTitle.textContent = 'โปรโมชั่นสำหรับคนทั่วไป';
    this.generalSubEl = document.createElement('div');
    this.generalSubEl.className = 'promo-side-subtitle';
    this.generalSubEl.textContent = 'ใช้ลดราคาได้ทุกโต๊ะโดยไม่ต้องสมัครสมาชิก';
    leftTitleWrap.appendChild(leftTitle);
    leftTitleWrap.appendChild(this.generalSubEl);

    const leftActions = document.createElement('div');
    leftActions.className = 'promo-side-actions';
    const addGeneralBtn = document.createElement('button');
    addGeneralBtn.type = 'button';
    addGeneralBtn.className = 'btn btn-sm btn-primary';
    addGeneralBtn.dataset.testid = 'btn-add-general-promo';
    addGeneralBtn.textContent = '+ เพิ่มโปรคนทั่วไป';
    addGeneralBtn.addEventListener('click', () => this.addPromo('general'));
    leftActions.appendChild(addGeneralBtn);

    leftHead.appendChild(leftTitleWrap);
    leftHead.appendChild(leftActions);
    leftCard.appendChild(leftHead);

    const leftTblHolder = document.createElement('div');
    leftCard.appendChild(leftTblHolder);

    this.generalTable = new DataTable(
      leftTblHolder,
      this._buildColumns('general'),
      { emptyText: 'ยังไม่มีโปรโมชั่นสำหรับคนทั่วไป' }
    );
    // คง this.table ไว้เพื่อความเข้ากันได้กับโครงสร้างเดิม
    this.table = this.generalTable;

    // ==================== ฝั่งขวา: โปรโมชั่นสำหรับสมาชิก ====================
    const rightCard = document.createElement('div');
    rightCard.className = 'card promo-side-card';
    rightCard.dataset.testid = 'promo-right-member';

    const rightHead = document.createElement('div');
    rightHead.className = 'promo-side-header';
    const rightTitleWrap = document.createElement('div');
    const rightTitle = document.createElement('div');
    rightTitle.className = 'promo-side-title';
    rightTitle.textContent = '🎁 โปรโมชั่นสำหรับสมาชิก';
    this.memberSubEl = document.createElement('div');
    this.memberSubEl.className = 'promo-side-subtitle';
    this.memberSubEl.textContent = 'สำหรับสมาชิกกดเก็บโค้ดและใช้ลดราคาหน้าสั่งอาหาร';
    rightTitleWrap.appendChild(rightTitle);
    rightTitleWrap.appendChild(this.memberSubEl);

    const rightActions = document.createElement('div');
    rightActions.className = 'promo-side-actions';

    this.viewMembersBtn = document.createElement('button');
    this.viewMembersBtn.type = 'button';
    this.viewMembersBtn.className = 'btn btn-sm btn-ghost';
    this.viewMembersBtn.dataset.testid = 'btn-view-members';
    this.viewMembersBtn.textContent = '👥 ดูสมาชิก';
    this.viewMembersBtn.addEventListener('click', () => this.openMembersModal());

    const addMemberBtn = document.createElement('button');
    addMemberBtn.type = 'button';
    addMemberBtn.className = 'btn btn-sm btn-primary';
    addMemberBtn.dataset.testid = 'btn-add-member-promo';
    addMemberBtn.textContent = '+ เพิ่มโปรสมาชิก';
    addMemberBtn.addEventListener('click', () => this.addPromo('member'));

    rightActions.appendChild(this.viewMembersBtn);
    rightActions.appendChild(addMemberBtn);

    rightHead.appendChild(rightTitleWrap);
    rightHead.appendChild(rightActions);
    rightCard.appendChild(rightHead);

    const rightTblHolder = document.createElement('div');
    rightCard.appendChild(rightTblHolder);

    this.memberTable = new DataTable(
      rightTblHolder,
      this._buildColumns('member'),
      { emptyText: 'ยังไม่มีโปรโมชั่นสำหรับสมาชิก' }
    );

    split.appendChild(leftCard);
    split.appendChild(rightCard);
    this.container.appendChild(split);
  }

  _buildColumns(target) {
    const isMember = target === 'member';
    return [
      {
        key: 'name',
        title: isMember ? 'ชื่อโปร (โค้ด)' : 'ชื่อโปร',
        weight: 4,
        min_width: isMember ? 105 : 95,
        anchor: 'w',
        format: (v, row) => (isMember && row.code ? `${v} [${row.code}]` : String(v || '')),
      },
      { key: 'label', title: 'ส่วนลด', weight: 2, min_width: 58, anchor: 'w' },
      {
        key: 'min_amount',
        title: 'ขั้นต่ำ',
        weight: 2,
        min_width: 58,
        anchor: 'w',
        format: (v) => (v ? money(v) : '-'),
      },
      {
        key: 'status',
        title: 'สถานะ',
        weight: 2,
        min_width: 72,
        anchor: 'center',
        widget: (row) => {
          const colorMap = {
            neutral: 'var(--color-neutral)',
            warning: 'var(--color-warning)',
            success: 'var(--color-success)',
          };
          return createStatusBadge(
            row.status_text || '',
            colorMap[row.status_kind] || 'var(--color-neutral)'
          );
        },
      },
      {
        key: 'actions',
        title: 'จัดการ',
        weight: 3,
        min_width: 115,
        anchor: 'w',
        widget: (row) => {
          const box = document.createElement('div');
          box.className = 'table-actions';

          const bEdit = document.createElement('button');
          bEdit.type = 'button';
          bEdit.className = 'btn btn-sm btn-info';
          bEdit.textContent = 'แก้ไข';
          bEdit.addEventListener('click', () => this.editPromo(row));

          const bToggle = document.createElement('button');
          bToggle.type = 'button';
          bToggle.className = `btn btn-sm ${!row.active ? 'btn-success' : 'btn-ghost'}`;
          bToggle.textContent = !row.active ? 'เปิดใช้' : 'ปิดใช้';
          bToggle.addEventListener('click', () => this.toggleActive(row));

          box.appendChild(bEdit);
          box.appendChild(bToggle);
          return box;
        },
      },
    ];
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
      const data = await apiGet('/api/owner/promos');
      this.subtitleEl.textContent = data.subtitle || '';
      const allPromos = data.promos || [];
      const generalPromos =
        data.general_promos || allPromos.filter((p) => p.target !== 'member');
      const memberPromos =
        data.member_promos || allPromos.filter((p) => p.target === 'member');

      if (data.general_subtitle) {
        this.generalSubEl.textContent = data.general_subtitle;
      }
      if (data.member_subtitle) {
        this.memberSubEl.textContent = data.member_subtitle;
      }
      if (typeof data.member_count === 'number') {
        const activeCnt = Number(data.active_member_count || 0);
        this.topMembersBtn.textContent =
          activeCnt > 0
            ? `👥 ดูสมาชิก (${data.member_count} คน · กำลังใช้งาน ${activeCnt})`
            : `👥 ดูสมาชิก (${data.member_count} คน)`;
      }

      this.generalTable.setRows(generalPromos);
      this.memberTable.setRows(memberPromos);
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async addPromo(defaultTarget = 'general') {
    const d = await openPromoDialog(null, defaultTarget);
    if (!d) return;
    try {
      const res = await apiPost('/api/owner/promos', d);
      this.app.toast(res.message || 'เพิ่มโปรแล้ว', 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async editPromo(row) {
    const d = await openPromoDialog(row, row.target || 'general');
    if (!d) return;
    try {
      const res = await apiPatch(`/api/owner/promos/${row.id}`, d);
      this.app.toast(
        res.message || 'บันทึกโปรแล้ว (บิลที่ปิดไปแล้วไม่เปลี่ยน)',
        'success'
      );
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async toggleActive(row) {
    if (row.active) {
      const ok = await confirmDialog(
        `ปิดใช้งานโปร "${row.name}" ?\nจะไม่สามารถเลือกใช้โปรนี้ได้จนกว่าจะเปิดใหม่`,
        {
          title: 'ปิดโปรโมชั่น',
          confirmText: 'ปิดใช้งาน',
        }
      );
      if (!ok) return;
    }
    try {
      const res = await apiPost(`/api/owner/promos/${row.id}/toggle`, {
        active: !row.active,
      });
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async openMembersModal() {
    try {
      const data = await apiGet('/api/owner/members');
      await showMembersDialog(data);
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }
}

async function showMembersDialog(data) {
  const members = (data && data.members) || [];
  const dlg = new BaseDialog('รายชื่อสมาชิกทั้งหมด', { width: 680 });

  const summaryBar = document.createElement('div');
  summaryBar.className = 'members-modal-summary';
  summaryBar.textContent =
    data.subtitle ||
    `สมาชิกทั้งหมด ${members.length} คน (สมาชิกที่กำลังทานอยู่ในร้านจะแสดงสถานะ "กำลังใช้งาน" อยู่ด้านบนสุด)`;
  dlg.body.appendChild(summaryBar);

  const tblWrap = document.createElement('div');
  tblWrap.dataset.testid = 'owner-members-table';
  dlg.body.appendChild(tblWrap);

  const memberTable = new DataTable(
    tblWrap,
    [
      { key: 'name', title: 'ชื่อสมาชิก', weight: 3, min_width: 140, anchor: 'w' },
      { key: 'email', title: 'อีเมล', weight: 3, min_width: 165, anchor: 'w' },
      { key: 'phone', title: 'เบอร์โทรศัพท์', weight: 2, min_width: 110, anchor: 'w' },
      {
        key: 'status_text',
        title: 'สถานะ',
        weight: 2,
        min_width: 120,
        anchor: 'center',
        widget: (row) => {
          const isDining = Boolean(row.is_active_dining);
          return createStatusBadge(
            row.status_text || (isDining ? 'กำลังใช้งาน' : 'ไม่ได้ใช้งาน'),
            isDining ? 'var(--color-success)' : 'var(--color-neutral)'
          );
        },
      },
    ],
    { emptyText: 'ยังไม่มีข้อมูลสมาชิก', maxHeight: 380 }
  );
  memberTable.setRows(members);

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'btn btn-primary';
  closeBtn.textContent = 'ปิดหน้าต่าง';
  closeBtn.addEventListener('click', () => dlg.close(true));
  dlg.footer.appendChild(closeBtn);

  return dlg.show();
}

async function openPromoDialog(promo = null, defaultTarget = 'general') {
  let promoTarget = promo ? promo.target || defaultTarget : defaultTarget;
  const isMemberInitial = promoTarget === 'member';
  const dlg = new BaseDialog(
    promo
      ? `แก้ไขโปรโมชั่น (${isMemberInitial ? 'สมาชิก' : 'คนทั่วไป'})`
      : `เพิ่มโปรโมชั่น (${isMemberInitial ? 'สำหรับสมาชิก' : 'สำหรับคนทั่วไป'})`,
    { width: 480 }
  );
  let promoType = promo ? promo.promo_type : 'percent';

  // เลือกกลุ่มเป้าหมาย (คนทั่วไป / สมาชิก)
  const targetGroup = document.createElement('div');
  targetGroup.className = 'field-group';
  const targetLbl = document.createElement('label');
  targetLbl.className = 'field-label';
  targetLbl.textContent = 'ประเภทโปรโมชั่น';
  const targetSeg = document.createElement('div');
  targetSeg.className = 'seg-group';
  const bGen = document.createElement('button');
  bGen.type = 'button';
  bGen.className = `seg-btn ${promoTarget !== 'member' ? 'is-active' : ''}`;
  bGen.textContent = 'สำหรับคนทั่วไป';
  const bMem = document.createElement('button');
  bMem.type = 'button';
  bMem.className = `seg-btn ${promoTarget === 'member' ? 'is-active' : ''}`;
  bMem.textContent = '🎁 สำหรับสมาชิก';
  targetSeg.appendChild(bGen);
  targetSeg.appendChild(bMem);
  targetGroup.appendChild(targetLbl);
  targetGroup.appendChild(targetSeg);
  dlg.body.appendChild(targetGroup);

  const nameGroup = document.createElement('div');
  nameGroup.className = 'field-group';
  const nameLbl = document.createElement('label');
  nameLbl.className = 'field-label';
  nameLbl.textContent = 'ชื่อโปรโมชั่น';
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.className = 'field-input';
  nameInput.dataset.testid = 'promo-name-input';
  nameInput.placeholder =
    promoTarget === 'member' ? 'เช่น ส่วนลดต้อนรับสมาชิกใหม่ 50฿' : 'เช่น ลด 10% วันพุธ';
  nameInput.value = promo ? promo.name : '';
  nameGroup.appendChild(nameLbl);
  nameGroup.appendChild(nameInput);
  dlg.body.appendChild(nameGroup);

  // เฉพาะโปรสมาชิก: รหัสโค้ดส่วนลด + รายละเอียด
  const memberFieldsWrap = document.createElement('div');
  memberFieldsWrap.style.display = promoTarget === 'member' ? 'flex' : 'none';
  memberFieldsWrap.style.flexDirection = 'column';
  memberFieldsWrap.style.gap = 'var(--space-2)';

  const codeGroup = document.createElement('div');
  codeGroup.className = 'field-group';
  const codeLbl = document.createElement('label');
  codeLbl.className = 'field-label';
  codeLbl.textContent = 'รหัสโค้ดส่วนลดสำหรับสมาชิก (เช่น TONMAKHA50)';
  const codeInput = document.createElement('input');
  codeInput.type = 'text';
  codeInput.className = 'field-input';
  codeInput.dataset.testid = 'promo-code-input';
  codeInput.placeholder = 'เช่น VIP100 (เว้นว่างให้ระบบสร้างอัตโนมัติได้)';
  codeInput.value = promo && promo.code ? promo.code : '';
  codeGroup.appendChild(codeLbl);
  codeGroup.appendChild(codeInput);

  const descGroup = document.createElement('div');
  descGroup.className = 'field-group';
  const descLbl = document.createElement('label');
  descLbl.className = 'field-label';
  descLbl.textContent = 'รายละเอียดเงื่อนไขโปรสมาชิก';
  const descInput = document.createElement('input');
  descInput.type = 'text';
  descInput.className = 'field-input';
  descInput.dataset.testid = 'promo-desc-input';
  descInput.placeholder = 'เช่น ใช้ลดท้ายบิลเมื่อทานครบตามยอดขั้นต่ำ';
  descInput.value = promo && promo.description ? promo.description : '';
  descGroup.appendChild(descLbl);
  descGroup.appendChild(descInput);

  memberFieldsWrap.appendChild(codeGroup);
  memberFieldsWrap.appendChild(descGroup);
  dlg.body.appendChild(memberFieldsWrap);

  bGen.addEventListener('click', () => {
    promoTarget = 'general';
    bGen.classList.add('is-active');
    bMem.classList.remove('is-active');
    memberFieldsWrap.style.display = 'none';
  });
  bMem.addEventListener('click', () => {
    promoTarget = 'member';
    bMem.classList.add('is-active');
    bGen.classList.remove('is-active');
    memberFieldsWrap.style.display = 'flex';
  });

  const typeGroup = document.createElement('div');
  typeGroup.className = 'field-group';
  const typeLbl = document.createElement('label');
  typeLbl.className = 'field-label';
  typeLbl.textContent = 'ชนิดส่วนลด';
  const seg = document.createElement('div');
  seg.className = 'seg-group';
  const bPct = document.createElement('button');
  bPct.type = 'button';
  bPct.className = `seg-btn ${promoType === 'percent' ? 'is-active' : ''}`;
  bPct.textContent = 'ลดเป็น %';
  const bFix = document.createElement('button');
  bFix.type = 'button';
  bFix.className = `seg-btn ${promoType === 'fixed' ? 'is-active' : ''}`;
  bFix.textContent = 'ลดเป็นบาท';
  seg.appendChild(bPct);
  seg.appendChild(bFix);
  typeGroup.appendChild(typeLbl);
  typeGroup.appendChild(seg);
  dlg.body.appendChild(typeGroup);

  const row1 = document.createElement('div');
  row1.style.display = 'grid';
  row1.style.gridTemplateColumns = '1fr 1fr';
  row1.style.gap = 'var(--space-2)';

  const valGroup = document.createElement('div');
  valGroup.className = 'field-group';
  const valLbl = document.createElement('label');
  valLbl.className = 'field-label';
  const updateValLbl = () => {
    valLbl.textContent = promoType === 'percent' ? 'ลดกี่ % (1-100)' : 'ลดกี่บาท';
  };
  updateValLbl();
  bPct.addEventListener('click', () => {
    promoType = 'percent';
    bPct.classList.add('is-active');
    bFix.classList.remove('is-active');
    updateValLbl();
  });
  bFix.addEventListener('click', () => {
    promoType = 'fixed';
    bFix.classList.add('is-active');
    bPct.classList.remove('is-active');
    updateValLbl();
  });

  const valInput = document.createElement('input');
  valInput.type = 'text';
  valInput.className = 'field-input num';
  valInput.dataset.testid = 'promo-value-input';
  valInput.placeholder = '0';
  valInput.value = promo ? String(promo.value) : '';
  valGroup.appendChild(valLbl);
  valGroup.appendChild(valInput);

  const minGroup = document.createElement('div');
  minGroup.className = 'field-group';
  const minLbl = document.createElement('label');
  minLbl.className = 'field-label';
  minLbl.textContent = 'ยอดขั้นต่ำ (บาท)';
  const minInput = document.createElement('input');
  minInput.type = 'text';
  minInput.className = 'field-input num';
  minInput.dataset.testid = 'promo-min-input';
  minInput.placeholder = '0';
  minInput.value = promo ? String(promo.min_amount) : '';
  minGroup.appendChild(minLbl);
  minGroup.appendChild(minInput);

  row1.appendChild(valGroup);
  row1.appendChild(minGroup);
  dlg.body.appendChild(row1);

  const row2 = document.createElement('div');
  row2.style.display = 'grid';
  row2.style.gridTemplateColumns = '1fr 1fr';
  row2.style.gap = 'var(--space-2)';

  const startGroup = document.createElement('div');
  startGroup.className = 'field-group';
  const startLbl = document.createElement('label');
  startLbl.className = 'field-label';
  startLbl.textContent = 'เริ่มวันที่ (ว่าง = ทันที)';
  const startInput = document.createElement('input');
  startInput.type = 'text';
  startInput.className = 'field-input';
  startInput.placeholder = '2026-10-01';
  startInput.value = promo && promo.start_at ? promo.start_at.slice(0, 10) : '';
  startGroup.appendChild(startLbl);
  startGroup.appendChild(startInput);

  const endGroup = document.createElement('div');
  endGroup.className = 'field-group';
  const endLbl = document.createElement('label');
  endLbl.className = 'field-label';
  endLbl.textContent = 'ถึงวันที่ (ว่าง = ไม่จำกัด)';
  const endInput = document.createElement('input');
  endInput.type = 'text';
  endInput.className = 'field-input';
  endInput.placeholder = '2026-10-31';
  endInput.value = promo && promo.end_at ? promo.end_at.slice(0, 10) : '';
  endGroup.appendChild(endLbl);
  endGroup.appendChild(endInput);

  row2.appendChild(startGroup);
  row2.appendChild(endGroup);
  dlg.body.appendChild(row2);

  const swRow = document.createElement('label');
  swRow.style.display = 'inline-flex';
  swRow.style.alignItems = 'center';
  swRow.style.gap = 'var(--space-2)';
  swRow.style.cursor = 'pointer';
  const activeChk = document.createElement('input');
  activeChk.type = 'checkbox';
  activeChk.checked = promo ? Boolean(promo.active) : true;
  const swTxt = document.createElement('span');
  swTxt.textContent = 'เปิดใช้งานโปรนี้';
  swRow.appendChild(activeChk);
  swRow.appendChild(swTxt);
  dlg.body.appendChild(swRow);

  const errEl = document.createElement('div');
  errEl.className = 'modal-error';
  dlg.body.appendChild(errEl);

  dlg.addButtons({
    confirmText: 'บันทึก',
    cancelText: 'ยกเลิก',
    variant: 'primary',
    onConfirm: () => {
      try {
        const name = nameInput.value.trim();
        if (!name) throw new Error('กรุณาใส่ชื่อโปรโมชั่น');
        const value = parse_number(valInput.value, 'ค่าส่วนลด', { minimum: 0 });
        if (value <= 0) throw new Error('ค่าส่วนลดต้องมากกว่า 0');
        if (promoType === 'percent' && value > 100) {
          throw new Error('ส่วนลดเปอร์เซ็นต์ต้องไม่เกิน 100');
        }
        const minAmount = parse_number(minInput.value, 'ยอดขั้นต่ำ', {
          minimum: 0,
          allowEmpty: true,
          defaultValue: 0,
        });
        const start = parse_date(startInput.value, 'วันเริ่ม', true);
        const end = parse_date(endInput.value, 'วันสิ้นสุด', true);
        if (start && end && start > end) {
          throw new Error('วันเริ่มต้องไม่หลังวันสิ้นสุด');
        }
        dlg.close({
          name,
          promo_type: promoType,
          value,
          min_amount: minAmount,
          start_at: start,
          end_at: end,
          active: Boolean(activeChk.checked),
          target: promoTarget,
          code: promoTarget === 'member' ? codeInput.value.trim().toUpperCase() : null,
          description: promoTarget === 'member' ? descInput.value.trim() : null,
        });
      } catch (err) {
        errEl.textContent = err.message;
      }
    },
  });

  return dlg.show();
}
