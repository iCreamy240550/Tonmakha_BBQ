/**
 * frontend/staff/js/pages/menu.js — เมนูและราคา + จัดการรูปภาพเมนู 1:1 + ลบรายการเมนู (เจ้าของ)
 * คัดลอกจาก ui/owner/menu_page.py ทุกตัวอักษร
 */

import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiUpload,
} from '../../../shared/js/api.js';
import { DataTable } from '../../../shared/js/data-table.js';
import {
  BaseDialog,
  askTextDialog,
  confirmDialog,
} from '../../../shared/js/dialogs.js';
import { money, parse_number } from '../../../shared/js/format.js';
import { createStatusBadge } from '../../../shared/js/status-badge.js';

const ALL_CATEGORIES = 'ทั้งหมด';
const NO_STOCK = 'ไม่ผูกสต๊อก';
const TYPE_LABELS = {
  weighed: 'ชั่งกิโล (บาท/กก.)',
  normal: 'ปกติ (บาท/หน่วย)',
};
const TYPE_SHORT = {
  weighed: 'ชั่งกิโล',
  normal: 'ปกติ',
};

export class MenuPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.categoryId = null;
    this.categories = [];
    this.stockItems = [];
    this.deleting = false;

    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'เมนูและราคา';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);

    const right = document.createElement('div');
    right.className = 'page-header-right';
    this.btnUp = document.createElement('button');
    this.btnUp.type = 'button';
    this.btnUp.className = 'btn btn-ghost';
    this.btnUp.style.minWidth = '44px';
    this.btnUp.textContent = '▲';
    this.btnUp.addEventListener('click', () => this.moveItem(-1));

    this.btnDown = document.createElement('button');
    this.btnDown.type = 'button';
    this.btnDown.className = 'btn btn-ghost';
    this.btnDown.style.minWidth = '44px';
    this.btnDown.textContent = '▼';
    this.btnDown.addEventListener('click', () => this.moveItem(1));

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn-primary';
    addBtn.textContent = '+ เพิ่มเมนู';
    addBtn.addEventListener('click', () => this.addItem());

    right.appendChild(this.btnUp);
    right.appendChild(this.btnDown);
    right.appendChild(addBtn);
    header.appendChild(left);
    header.appendChild(right);
    this.container.appendChild(header);

    const split = document.createElement('div');
    split.className = 'split-layout split-menu audit-block';

    // ซ้าย: หมวดเมนู
    const leftCard = document.createElement('div');
    leftCard.className = 'card';
    leftCard.style.display = 'flex';
    leftCard.style.flexDirection = 'column';
    leftCard.style.gap = 'var(--space-2)';

    const catTitle = document.createElement('div');
    catTitle.style.fontSize = 'var(--fs-xl)';
    catTitle.style.fontWeight = '700';
    catTitle.textContent = 'หมวดเมนู';
    leftCard.appendChild(catTitle);

    this.catArea = document.createElement('div');
    this.catArea.style.flex = '1 1 auto';
    this.catArea.style.display = 'flex';
    this.catArea.style.flexDirection = 'column';
    this.catArea.style.gap = 'var(--space-1)';
    leftCard.appendChild(this.catArea);

    const tools = document.createElement('div');
    tools.style.display = 'flex';
    tools.style.gap = 'var(--space-1)';
    tools.style.flexWrap = 'nowrap';

    const bAddCat = document.createElement('button');
    bAddCat.type = 'button';
    bAddCat.className = 'btn btn-sm btn-success';
    bAddCat.style.minWidth = '0';
    bAddCat.style.padding = 'var(--space-1) var(--space-2)';
    bAddCat.textContent = '+ หมวด';
    bAddCat.addEventListener('click', () => this.addCategory());

    const bRenCat = document.createElement('button');
    bRenCat.type = 'button';
    bRenCat.className = 'btn btn-sm btn-ghost';
    bRenCat.style.minWidth = '0';
    bRenCat.style.padding = 'var(--space-1) var(--space-2)';
    bRenCat.textContent = 'เปลี่ยนชื่อ';
    bRenCat.addEventListener('click', () => this.renameCategory());

    const bCatUp = document.createElement('button');
    bCatUp.type = 'button';
    bCatUp.className = 'btn btn-sm btn-ghost';
    bCatUp.style.minWidth = '32px';
    bCatUp.style.padding = 'var(--space-1) var(--space-1)';
    bCatUp.textContent = '▲';
    bCatUp.addEventListener('click', () => this.moveCategory(-1));

    const bCatDown = document.createElement('button');
    bCatDown.type = 'button';
    bCatDown.className = 'btn btn-sm btn-ghost';
    bCatDown.style.minWidth = '32px';
    bCatDown.style.padding = 'var(--space-1) var(--space-1)';
    bCatDown.textContent = '▼';
    bCatDown.addEventListener('click', () => this.moveCategory(1));

    tools.appendChild(bAddCat);
    tools.appendChild(bRenCat);
    tools.appendChild(bCatUp);
    tools.appendChild(bCatDown);
    leftCard.appendChild(tools);

    this.btnCatToggle = document.createElement('button');
    this.btnCatToggle.type = 'button';
    this.btnCatToggle.className = 'btn btn-sm btn-ghost btn-block';
    this.btnCatToggle.textContent = 'ซ่อนหมวดนี้';
    this.btnCatToggle.addEventListener('click', () => this.toggleCategory());
    leftCard.appendChild(this.btnCatToggle);

    // ขวา: ตารางเมนู
    const rightWrap = document.createElement('div');
    rightWrap.style.minWidth = '0';

    this.table = new DataTable(
      rightWrap,
      [
        { key: 'name', title: 'ชื่อเมนู', weight: 3, min_width: 115, anchor: 'w' },
        { key: 'category_name', title: 'หมวด', weight: 2, min_width: 80, anchor: 'w' },
        {
          key: 'item_type',
          title: 'ประเภท',
          weight: 2,
          min_width: 72,
          anchor: 'w',
          format: (v) => TYPE_SHORT[v] || v,
        },
        {
          key: 'price',
          title: 'ราคา',
          weight: 2,
          min_width: 80,
          anchor: 'w',
          format: (v, r) => money(v) + (r.item_type === 'weighed' ? ' /กก.' : ''),
        },
        {
          key: 'stock_display_name',
          title: 'สต๊อกที่ผูก',
          weight: 2,
          min_width: 85,
          anchor: 'w',
        },
        {
          key: 'has_image',
          title: 'รูปภาพ',
          weight: 1,
          min_width: 72,
          anchor: 'center',
          format: (v) => (v ? 'มีรูป' : '-'),
        },
        {
          key: 'status',
          title: 'สถานะ',
          weight: 2,
          min_width: 75,
          anchor: 'center',
          widget: (row) => {
            if (!row.active) {
              return createStatusBadge('ซ่อนอยู่', 'var(--color-neutral)');
            }
            if (row.is_sold_out) {
              return createStatusBadge('หมด', 'var(--color-danger)');
            }
            return createStatusBadge('ขายอยู่', 'var(--color-success)');
          },
        },
        {
          key: 'actions',
          title: 'จัดการ',
          weight: 6,
          min_width: 250,
          anchor: 'w',
          widget: (row) => {
            const box = document.createElement('div');
            box.className = 'table-actions';

            const bEdit = document.createElement('button');
            bEdit.type = 'button';
            bEdit.className = 'btn btn-sm btn-info';
            bEdit.textContent = 'แก้ไข';
            bEdit.addEventListener('click', () => this.editItem(row));

            const bSold = document.createElement('button');
            bSold.type = 'button';
            bSold.className = `btn btn-sm ${row.is_sold_out ? 'btn-success' : 'btn-ghost'}`;
            bSold.textContent = row.is_sold_out ? 'มีขาย' : 'ทำเป็นหมด';
            bSold.addEventListener('click', () => this.toggleSoldOut(row));

            const bAct = document.createElement('button');
            bAct.type = 'button';
            bAct.className = 'btn btn-sm btn-ghost';
            bAct.textContent = !row.active ? 'แสดง' : 'ซ่อน';
            bAct.addEventListener('click', () => this.toggleActive(row));

            const bDel = document.createElement('button');
            bDel.type = 'button';
            bDel.className = 'btn btn-sm btn-danger';
            bDel.textContent = 'ลบ';
            bDel.addEventListener('click', () => this.deleteItem(row));

            box.appendChild(bEdit);
            box.appendChild(bSold);
            box.appendChild(bAct);
            box.appendChild(bDel);
            return box;
          },
        },
      ],
      {
        onSelect: () => this._updateMoveButtons(),
        emptyText: 'ยังไม่มีเมนูในหมวดนี้',
      }
    );

    split.appendChild(leftCard);
    split.appendChild(rightWrap);
    this.container.appendChild(split);
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
      const data = await apiGet('/api/owner/menu', {
        category_id: this.categoryId || '',
      });
      this.categories = data.categories || [];
      this.categoryId = data.selected_category_id;
      this.stockItems = data.stock_items || [];
      this.subtitleEl.textContent = data.subtitle || '';
      this._drawCategories();
      this.table.setRows(data.items || []);
      this._updateMoveButtons();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  _drawCategories() {
    this.catArea.textContent = '';
    const entries = [
      { id: null, label: ALL_CATEGORIES, active: true },
      ...this.categories.map((c) => ({
        id: c.id,
        label: c.name + (c.active ? '' : ' (ซ่อน)'),
        active: c.active,
      })),
    ];

    for (const entry of entries) {
      const selected = entry.id === this.categoryId;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `btn btn-sm ${selected ? 'btn-primary' : 'btn-ghost'}`;
      btn.style.justifyContent = 'flex-start';
      btn.style.width = '100%';
      if (!selected && !entry.active) {
        btn.style.color = 'var(--color-text-muted)';
      }
      btn.textContent = entry.label;
      btn.addEventListener('click', () => {
        this.categoryId = entry.id;
        this.refresh();
      });
      this.catArea.appendChild(btn);
    }

    const curCat = this._currentCategory();
    this.btnCatToggle.textContent =
      curCat && !curCat.active ? 'แสดงหมวดนี้อีกครั้ง' : 'ซ่อนหมวดนี้';
  }

  _currentCategory() {
    return this.categories.find((c) => c.id === this.categoryId) || null;
  }

  _updateMoveButtons() {
    const enabled = this.categoryId !== null && this.table.selected !== null;
    this.btnUp.disabled = !enabled;
    this.btnDown.disabled = !enabled;
  }

  async addItem() {
    const activeCats = this.categories.filter((c) => c.active);
    if (activeCats.length === 0) {
      this.app.toast('ต้องมีหมวดที่ใช้งานอย่างน้อย 1 หมวดก่อน', 'error');
      return;
    }
    const activeStocks = this.stockItems.filter((s) => s.active);
    const data = await openItemDialog({
      categories: activeCats,
      stockItems: activeStocks,
      item: null,
      defaultCategoryId: this.categoryId,
    });
    if (!data) return;

    try {
      const res = await apiPost('/api/owner/menu/items', {
        category_id: data.category_id,
        name: data.name,
        item_type: data.item_type,
        price: data.price,
        stock_item_id: data.stock_item_id,
      });
      if (data.imageFile && res.item) {
        const fd = new FormData();
        fd.append('file', data.imageFile);
        await apiUpload(`/api/owner/menu/items/${res.item.id}/image`, fd);
      }
      this.app.toast('เพิ่มเมนูแล้ว', 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async editItem(row) {
    const linked = row.stock_item_id;
    const stocks = this.stockItems.filter((s) => s.active || s.id === linked);
    const data = await openItemDialog({
      categories: this.categories,
      stockItems: stocks,
      item: row,
    });
    if (!data) return;

    try {
      await apiPatch(`/api/owner/menu/items/${row.id}`, {
        name: data.name,
        price: data.price,
        category_id: data.category_id,
        stock_item_id: data.stock_item_id,
        clear_stock: data.stock_item_id === null,
      });
      if (data.removeImage) {
        await apiDelete(`/api/owner/menu/items/${row.id}/image`);
      } else if (data.imageFile) {
        const fd = new FormData();
        fd.append('file', data.imageFile);
        await apiUpload(`/api/owner/menu/items/${row.id}/image`, fd);
      }
      this.app.toast('บันทึกเมนูแล้ว', 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async toggleSoldOut(row) {
    try {
      const res = await apiPost(`/api/owner/menu/items/${row.id}/sold_out`, {
        sold_out: !row.is_sold_out,
      });
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async toggleActive(row) {
    if (row.active) {
      const ok = await confirmDialog(
        `ซ่อนเมนู "${row.name}" ?\nลูกค้าจะไม่เห็นเมนูนี้ (ประวัติเดิมไม่หาย)`,
        {
          title: 'ซ่อนเมนู',
          confirmText: 'ซ่อน',
        }
      );
      if (!ok) return;
    }
    try {
      const res = await apiPatch(`/api/owner/menu/items/${row.id}`, {
        active: !row.active,
      });
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async deleteItem(row) {
    if (this.deleting) return;
    try {
      const impact = await apiGet(`/api/owner/menu/items/${row.id}/delete_impact`);
      const ok = await confirmDialog(
        `ต้องการลบเมนู "${row.name}" ใช่หรือไม่?\n\n${impact.impact_text}`,
        {
          title: 'ยืนยันการลบเมนู',
          confirmText: 'ลบเมนู',
          danger: true,
        }
      );
      if (!ok) return;

      this.deleting = true;
      const res = await apiDelete(`/api/owner/menu/items/${row.id}`);
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    } finally {
      this.deleting = false;
    }
  }

  async moveItem(delta) {
    const sel = this.table.selected;
    if (this.categoryId === null || !sel) return;
    try {
      await apiPost(`/api/owner/menu/items/${sel.id}/move`, {
        category_id: this.categoryId,
        delta,
      });
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async addCategory() {
    const name = await askTextDialog('ชื่อหมวดใหม่', { title: 'เพิ่มหมวด' });
    if (!name) return;
    try {
      const res = await apiPost('/api/owner/menu/categories', { name });
      this.app.toast(res.message || 'เพิ่มหมวดแล้ว', 'success');
      if (res.category) {
        this.categoryId = res.category.id;
      }
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async renameCategory() {
    const cat = this._currentCategory();
    if (!cat) {
      this.app.toast('เลือกหมวดทางซ้ายก่อน', 'warning');
      return;
    }
    const name = await askTextDialog('ชื่อหมวด', {
      title: 'เปลี่ยนชื่อหมวด',
      initial: cat.name,
    });
    if (!name) return;
    try {
      const res = await apiPatch(`/api/owner/menu/categories/${cat.id}`, { name });
      this.app.toast(res.message || 'เปลี่ยนชื่อแล้ว', 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async toggleCategory() {
    const cat = this._currentCategory();
    if (!cat) {
      this.app.toast('เลือกหมวดทางซ้ายก่อน', 'warning');
      return;
    }
    if (cat.active) {
      const ok = await confirmDialog(
        `ซ่อนหมวด "${cat.name}" ?\nเมนูในหมวดนี้จะไม่แสดงให้ลูกค้า`,
        {
          title: 'ซ่อนหมวด',
          confirmText: 'ซ่อน',
        }
      );
      if (!ok) return;
    }
    try {
      const res = await apiPatch(`/api/owner/menu/categories/${cat.id}`, {
        active: !cat.active,
      });
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async moveCategory(delta) {
    const cat = this._currentCategory();
    if (!cat) {
      this.app.toast('เลือกหมวดทางซ้ายก่อน', 'warning');
      return;
    }
    try {
      await apiPost(`/api/owner/menu/categories/${cat.id}/move`, { delta });
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }
}

async function openItemDialog({
  categories,
  stockItems,
  item = null,
  defaultCategoryId = null,
}) {
  const dlg = new BaseDialog(item ? 'แก้ไขเมนู' : 'เพิ่มเมนู', { width: 480 });
  let itemType = item ? item.item_type : 'normal';
  let selectedFile = null;
  let removeImage = false;

  const nameGroup = document.createElement('div');
  nameGroup.className = 'field-group';
  const nameLbl = document.createElement('label');
  nameLbl.className = 'field-label';
  nameLbl.textContent = 'ชื่อเมนู';
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.className = 'field-input';
  nameInput.placeholder = 'เช่น หมูสามชั้น';
  nameInput.value = item ? item.name : '';
  nameGroup.appendChild(nameLbl);
  nameGroup.appendChild(nameInput);
  dlg.body.appendChild(nameGroup);

  const catGroup = document.createElement('div');
  catGroup.className = 'field-group';
  const catLbl = document.createElement('label');
  catLbl.className = 'field-label';
  catLbl.textContent = 'หมวด';
  const catSelect = document.createElement('select');
  catSelect.className = 'field-select';
  for (const c of categories) {
    const opt = document.createElement('option');
    opt.value = String(c.id);
    opt.textContent = c.name + (c.active ? '' : ' (ซ่อนอยู่)');
    if (
      (item && c.id === item.category_id) ||
      (!item && defaultCategoryId && c.id === defaultCategoryId)
    ) {
      opt.selected = true;
    }
    catSelect.appendChild(opt);
  }
  catGroup.appendChild(catLbl);
  catGroup.appendChild(catSelect);
  dlg.body.appendChild(catGroup);

  const typeGroup = document.createElement('div');
  typeGroup.className = 'field-group';
  const typeLbl = document.createElement('label');
  typeLbl.className = 'field-label';
  typeLbl.textContent = 'ประเภท';
  typeGroup.appendChild(typeLbl);

  const priceLbl = document.createElement('label');
  priceLbl.className = 'field-label';
  const updatePriceLabel = () => {
    priceLbl.textContent =
      itemType === 'weighed' ? 'ราคา (บาทต่อ 1 กก.)' : 'ราคา (บาทต่อหน่วย)';
  };
  updatePriceLabel();

  if (item) {
    const fixedType = document.createElement('div');
    fixedType.style.fontSize = 'var(--fs-md)';
    fixedType.textContent = `${TYPE_LABELS[itemType]}  (เปลี่ยนประเภทไม่ได้)`;
    typeGroup.appendChild(fixedType);
  } else {
    const seg = document.createElement('div');
    seg.className = 'seg-group';
    const bNormal = document.createElement('button');
    bNormal.type = 'button';
    bNormal.className = 'seg-btn is-active';
    bNormal.textContent = TYPE_LABELS.normal;
    const bWeighed = document.createElement('button');
    bWeighed.type = 'button';
    bWeighed.className = 'seg-btn';
    bWeighed.textContent = TYPE_LABELS.weighed;

    bNormal.addEventListener('click', () => {
      itemType = 'normal';
      bNormal.classList.add('is-active');
      bWeighed.classList.remove('is-active');
      updatePriceLabel();
    });
    bWeighed.addEventListener('click', () => {
      itemType = 'weighed';
      bWeighed.classList.add('is-active');
      bNormal.classList.remove('is-active');
      updatePriceLabel();
    });
    seg.appendChild(bNormal);
    seg.appendChild(bWeighed);
    typeGroup.appendChild(seg);
  }
  dlg.body.appendChild(typeGroup);

  const priceGroup = document.createElement('div');
  priceGroup.className = 'field-group';
  const priceInput = document.createElement('input');
  priceInput.type = 'text';
  priceInput.className = 'field-input num';
  priceInput.placeholder = '0.00';
  priceInput.value = item ? String(item.price) : '';
  priceGroup.appendChild(priceLbl);
  priceGroup.appendChild(priceInput);
  dlg.body.appendChild(priceGroup);

  const stockGroup = document.createElement('div');
  stockGroup.className = 'field-group';
  const stockLbl = document.createElement('label');
  stockLbl.className = 'field-label';
  stockLbl.textContent = 'ผูกกับสต๊อก (ตัดสต๊อก/หมดอัตโนมัติ)';
  const stockSelect = document.createElement('select');
  stockSelect.className = 'field-select';
  const noneOpt = document.createElement('option');
  noneOpt.value = '';
  noneOpt.textContent = NO_STOCK;
  stockSelect.appendChild(noneOpt);
  for (const s of stockItems) {
    const opt = document.createElement('option');
    opt.value = String(s.id);
    opt.textContent = `${s.name} (${s.unit})`;
    if (item && item.stock_item_id === s.id) {
      opt.selected = true;
    }
    stockSelect.appendChild(opt);
  }
  stockGroup.appendChild(stockLbl);
  stockGroup.appendChild(stockSelect);
  dlg.body.appendChild(stockGroup);

  // ส่วนจัดการรูปภาพ 1:1
  const imgBox = document.createElement('div');
  imgBox.className = 'card';
  imgBox.style.backgroundColor = 'var(--color-row-alt)';
  imgBox.style.display = 'flex';
  imgBox.style.alignItems = 'center';
  imgBox.style.gap = 'var(--space-3)';

  const previewEl = document.createElement('div');
  previewEl.style.width = '96px';
  previewEl.style.height = '96px';
  previewEl.style.borderRadius = 'var(--radius-md)';
  previewEl.style.backgroundColor = 'var(--color-today-highlight)';
  previewEl.style.display = 'flex';
  previewEl.style.alignItems = 'center';
  previewEl.style.justifyContent = 'center';
  previewEl.style.textAlign = 'center';
  previewEl.style.fontSize = 'var(--fs-sm)';
  previewEl.style.color = 'var(--color-text-muted)';
  previewEl.style.overflow = 'hidden';
  previewEl.style.flexShrink = '0';

  const imgCtrl = document.createElement('div');
  imgCtrl.style.display = 'flex';
  imgCtrl.style.flexDirection = 'column';
  imgCtrl.style.gap = 'var(--space-1)';

  const imgTitle = document.createElement('div');
  imgTitle.style.fontWeight = '700';
  imgTitle.textContent = 'รูปภาพเมนู (แสดงสัดส่วน 1:1)';

  const imgStatus = document.createElement('div');
  imgStatus.style.fontSize = 'var(--fs-xs)';
  imgStatus.style.color = 'var(--color-text-muted)';

  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp';
  fileInput.className = 'hidden';

  const btnRow = document.createElement('div');
  btnRow.style.display = 'flex';
  btnRow.style.gap = 'var(--space-2)';

  const browseBtn = document.createElement('button');
  browseBtn.type = 'button';
  browseBtn.className = 'btn btn-sm btn-info';
  browseBtn.textContent = 'เลือกรูป...';
  browseBtn.addEventListener('click', () => fileInput.click());

  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'btn btn-sm btn-danger';
  removeBtn.textContent = 'ลบรูป';

  const showPreviewUrl = (url, labelTxt) => {
    previewEl.textContent = '';
    if (url) {
      const img = document.createElement('img');
      img.src = url;
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'cover';
      previewEl.appendChild(img);
      imgStatus.textContent = labelTxt;
      imgStatus.style.color = 'var(--color-success)';
      removeBtn.disabled = false;
    } else {
      previewEl.textContent = 'ไม่มีรูป\n(1:1)';
      imgStatus.textContent =
        labelTxt || 'ยังไม่มีรูปภาพ (รองรับ JPG, PNG, WebP ≤ 5 MB)';
      imgStatus.style.color = 'var(--color-text-muted)';
      removeBtn.disabled = true;
    }
  };

  if (item && item.has_image && item.image_url) {
    showPreviewUrl(item.image_url, `ไฟล์: ${item.image_path}`);
  } else {
    showPreviewUrl(null, null);
  }

  fileInput.addEventListener('change', () => {
    const f = fileInput.files && fileInput.files[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) {
      errEl.textContent = 'ไฟล์มีขนาดใหญ่เกิน 5 MB';
      return;
    }
    errEl.textContent = '';
    selectedFile = f;
    removeImage = false;
    const objUrl = URL.createObjectURL(f);
    showPreviewUrl(objUrl, `ไฟล์: ${f.name}`);
  });

  removeBtn.addEventListener('click', () => {
    selectedFile = null;
    removeImage = true;
    showPreviewUrl(null, 'จะลบรูปภาพเมื่อกดบันทึก');
    imgStatus.style.color = 'var(--color-warning)';
  });

  btnRow.appendChild(browseBtn);
  btnRow.appendChild(removeBtn);
  imgCtrl.appendChild(imgTitle);
  imgCtrl.appendChild(imgStatus);
  imgCtrl.appendChild(btnRow);
  imgCtrl.appendChild(fileInput);
  imgBox.appendChild(previewEl);
  imgBox.appendChild(imgCtrl);
  dlg.body.appendChild(imgBox);

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
        if (!name) throw new Error('กรุณากรอกชื่อเมนู');
        const price = parse_number(priceInput.value, 'ราคา', { minimum: 0 });
        dlg.close({
          name,
          category_id: Number(catSelect.value),
          item_type: itemType,
          price,
          stock_item_id: stockSelect.value ? Number(stockSelect.value) : null,
          imageFile: selectedFile,
          removeImage,
        });
      } catch (err) {
        errEl.textContent = err.message;
      }
    },
  });

  return dlg.show();
}
