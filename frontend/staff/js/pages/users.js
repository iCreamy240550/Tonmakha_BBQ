/**
 * frontend/staff/js/pages/users.js — จัดการผู้ใช้ (เจ้าของ)
 * คัดลอกจาก ui/owner/users_page.py ทุกตัวอักษร
 */

import { apiGet, apiPatch, apiPost } from '../../../shared/js/api.js';
import { DataTable } from '../../../shared/js/data-table.js';
import { BaseDialog, confirmDialog } from '../../../shared/js/dialogs.js';
import { createStatusBadge } from '../../../shared/js/status-badge.js';

export class UsersPage {
  constructor(container, app) {
    this.container = container;
    this.app = app;
    this.minPasswordLength = 4;
    this._build();
  }

  _build() {
    const header = document.createElement('div');
    header.className = 'page-header audit-block';
    const left = document.createElement('div');
    left.className = 'page-header-left';
    const title = document.createElement('h1');
    title.className = 'page-title';
    title.textContent = 'ผู้ใช้';
    this.subtitleEl = document.createElement('div');
    this.subtitleEl.className = 'page-subtitle';
    left.appendChild(title);
    left.appendChild(this.subtitleEl);

    const right = document.createElement('div');
    right.className = 'page-header-right';
    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn-primary';
    addBtn.textContent = '+ เพิ่มผู้ใช้';
    addBtn.addEventListener('click', () => this.addUser());
    right.appendChild(addBtn);

    header.appendChild(left);
    header.appendChild(right);
    this.container.appendChild(header);

    const tblHolder = document.createElement('div');
    tblHolder.className = 'audit-block';
    this.container.appendChild(tblHolder);

    this.table = new DataTable(
      tblHolder,
      [
        { key: 'username', title: 'ชื่อผู้ใช้', weight: 3, min_width: 120, anchor: 'w' },
        { key: 'display_name', title: 'ชื่อที่แสดง', weight: 3, min_width: 120, anchor: 'w' },
        { key: 'role_th', title: 'สิทธิ์', weight: 2, min_width: 90, anchor: 'w' },
        {
          key: 'status',
          title: 'สถานะ',
          weight: 2,
          min_width: 95,
          anchor: 'center',
          widget: (row) =>
            createStatusBadge(
              row.status_text,
              row.active ? 'var(--color-success)' : 'var(--color-neutral)'
            ),
        },
        { key: 'created_at_fmt', title: 'สร้างเมื่อ', weight: 3, min_width: 120, anchor: 'w' },
        {
          key: 'actions',
          title: 'จัดการ',
          weight: 5,
          min_width: 270,
          anchor: 'w',
          widget: (row) => {
            const box = document.createElement('div');
            box.className = 'table-actions';

            const bEdit = document.createElement('button');
            bEdit.type = 'button';
            bEdit.className = 'btn btn-sm btn-info';
            bEdit.textContent = 'แก้ไข';
            bEdit.addEventListener('click', () => this.editUser(row));

            const bReset = document.createElement('button');
            bReset.type = 'button';
            bReset.className = 'btn btn-sm btn-ghost';
            bReset.textContent = 'รีเซ็ตรหัส';
            bReset.addEventListener('click', () => this.resetPassword(row));

            const bToggle = document.createElement('button');
            bToggle.type = 'button';
            bToggle.className = `btn btn-sm ${!row.active ? 'btn-success' : 'btn-ghost'}`;
            bToggle.textContent = !row.active ? 'เปิดบัญชี' : 'ปิดบัญชี';
            bToggle.addEventListener('click', () => this.toggleActive(row));

            box.appendChild(bEdit);
            box.appendChild(bReset);
            box.appendChild(bToggle);
            return box;
          },
        },
      ],
      { emptyText: 'ยังไม่มีผู้ใช้' }
    );
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
      const data = await apiGet('/api/owner/users');
      this.minPasswordLength = data.min_password_length || 4;
      this.subtitleEl.textContent = data.subtitle || '';
      this.table.setRows(data.users || []);
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async addUser() {
    const d = await openUserDialog(null, false, this.minPasswordLength);
    if (!d) return;
    try {
      const res = await apiPost('/api/owner/users', d);
      this.app.toast(res.message || `เพิ่มผู้ใช้ ${d.username} แล้ว`, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async editUser(row) {
    const d = await openUserDialog(row, Boolean(row.is_me), this.minPasswordLength);
    if (!d) return;
    if (row.is_me && d.role !== row.role) {
      this.app.toast('ลดสิทธิ์บัญชีที่กำลังล็อกอินอยู่ไม่ได้', 'error');
      return;
    }
    try {
      const res = await apiPatch(`/api/owner/users/${row.id}`, d);
      this.app.toast(res.message || 'บันทึกแล้ว', 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async resetPassword(row) {
    const dlg = new BaseDialog('รีเซ็ตรหัสผ่าน', { width: 420 });
    const head = document.createElement('div');
    head.style.fontSize = 'var(--fs-lg)';
    head.style.fontWeight = '700';
    head.textContent = `ตั้งรหัสผ่านใหม่ให้ ${row.username}`;
    dlg.body.appendChild(head);

    const pwGroup = document.createElement('div');
    pwGroup.className = 'field-group';
    const pwLbl = document.createElement('label');
    pwLbl.className = 'field-label';
    pwLbl.textContent = `รหัสผ่านใหม่ (อย่างน้อย ${this.minPasswordLength} ตัว)`;
    const pwInput = document.createElement('input');
    pwInput.type = 'password';
    pwInput.className = 'field-input';
    pwGroup.appendChild(pwLbl);
    pwGroup.appendChild(pwInput);
    dlg.body.appendChild(pwGroup);

    const pw2Group = document.createElement('div');
    pw2Group.className = 'field-group';
    const pw2Lbl = document.createElement('label');
    pw2Lbl.className = 'field-label';
    pw2Lbl.textContent = 'ยืนยันรหัสผ่านใหม่';
    const pw2Input = document.createElement('input');
    pw2Input.type = 'password';
    pw2Input.className = 'field-input';
    pw2Group.appendChild(pw2Lbl);
    pw2Group.appendChild(pw2Input);
    dlg.body.appendChild(pw2Group);

    const errEl = document.createElement('div');
    errEl.className = 'modal-error';
    dlg.body.appendChild(errEl);

    dlg.addButtons({
      confirmText: 'เปลี่ยนรหัสผ่าน',
      cancelText: 'ยกเลิก',
      variant: 'primary',
      onConfirm: () => {
        if (pwInput.value !== pw2Input.value) {
          errEl.textContent = 'รหัสผ่านทั้งสองช่องไม่ตรงกัน';
          return;
        }
        dlg.close(pwInput.value);
      },
    });

    const pw = await dlg.show();
    if (pw === null) return;
    try {
      const res = await apiPost(`/api/owner/users/${row.id}/password`, {
        password: pw,
        password_confirm: pw,
      });
      this.app.toast(res.message || `เปลี่ยนรหัสผ่านของ ${row.username} แล้ว`, 'success');
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }

  async toggleActive(row) {
    if (row.active) {
      if (row.is_me) {
        this.app.toast('ปิดบัญชีที่กำลังล็อกอินอยู่ไม่ได้', 'error');
        return;
      }
      const ok = await confirmDialog(
        `ปิดบัญชี ${row.username} ?\nผู้ใช้นี้จะล็อกอินไม่ได้ (ประวัติเดิมยังอยู่)`,
        {
          title: 'ปิดบัญชีผู้ใช้',
          confirmText: 'ปิดบัญชี',
          danger: true,
        }
      );
      if (!ok) return;
    }
    try {
      const res = await apiPatch(`/api/owner/users/${row.id}`, {
        active: !row.active,
      });
      this.app.toast(res.message, 'success');
      await this.refresh();
    } catch (err) {
      this.app.toast(err.message, 'error');
    }
  }
}

async function openUserDialog(user = null, lockRole = false, minPasswordLength = 4) {
  const dlg = new BaseDialog(user ? 'แก้ไขผู้ใช้' : 'เพิ่มผู้ใช้', {
    width: 440,
  });

  const uGroup = document.createElement('div');
  uGroup.className = 'field-group';
  const uLbl = document.createElement('label');
  uLbl.className = 'field-label';
  uLbl.textContent = 'ชื่อผู้ใช้ (สำหรับล็อกอิน)';
  const uInput = document.createElement('input');
  uInput.type = 'text';
  uInput.className = 'field-input';
  uInput.placeholder = 'เช่น staff2';
  if (user) {
    uInput.value = user.username;
    uInput.disabled = true;
  }
  uGroup.appendChild(uLbl);
  uGroup.appendChild(uInput);
  dlg.body.appendChild(uGroup);

  const dGroup = document.createElement('div');
  dGroup.className = 'field-group';
  const dLbl = document.createElement('label');
  dLbl.className = 'field-label';
  dLbl.textContent = 'ชื่อที่แสดง';
  const dInput = document.createElement('input');
  dInput.type = 'text';
  dInput.className = 'field-input';
  dInput.placeholder = 'เช่น น้องมะค่า';
  if (user) dInput.value = user.display_name;
  dGroup.appendChild(dLbl);
  dGroup.appendChild(dInput);
  dlg.body.appendChild(dGroup);

  const rGroup = document.createElement('div');
  rGroup.className = 'field-group';
  const rLbl = document.createElement('label');
  rLbl.className = 'field-label';
  rLbl.textContent = 'สิทธิ์';
  const rSelect = document.createElement('select');
  rSelect.className = 'field-select';
  for (const [k, label] of [
    ['staff', 'พนักงาน'],
    ['owner', 'เจ้าของร้าน'],
  ]) {
    const opt = document.createElement('option');
    opt.value = k;
    opt.textContent = label;
    if (user && user.role === k) opt.selected = true;
    rSelect.appendChild(opt);
  }
  if (lockRole) rSelect.disabled = true;
  rGroup.appendChild(rLbl);
  rGroup.appendChild(rSelect);
  dlg.body.appendChild(rGroup);

  let pwInput = null;
  let pw2Input = null;
  if (!user) {
    const pwGroup = document.createElement('div');
    pwGroup.className = 'field-group';
    const pwLbl = document.createElement('label');
    pwLbl.className = 'field-label';
    pwLbl.textContent = `รหัสผ่าน (อย่างน้อย ${minPasswordLength} ตัว)`;
    pwInput = document.createElement('input');
    pwInput.type = 'password';
    pwInput.className = 'field-input';
    pwGroup.appendChild(pwLbl);
    pwGroup.appendChild(pwInput);
    dlg.body.appendChild(pwGroup);

    const pw2Group = document.createElement('div');
    pw2Group.className = 'field-group';
    const pw2Lbl = document.createElement('label');
    pw2Lbl.className = 'field-label';
    pw2Lbl.textContent = 'ยืนยันรหัสผ่าน';
    pw2Input = document.createElement('input');
    pw2Input.type = 'password';
    pw2Input.className = 'field-input';
    pw2Group.appendChild(pw2Lbl);
    pw2Group.appendChild(pw2Input);
    dlg.body.appendChild(pw2Group);
  }

  const errEl = document.createElement('div');
  errEl.className = 'modal-error';
  dlg.body.appendChild(errEl);

  dlg.addButtons({
    confirmText: 'บันทึก',
    cancelText: 'ยกเลิก',
    variant: 'primary',
    onConfirm: () => {
      const display = dInput.value.trim();
      if (user) {
        dlg.close({ display_name: display, role: rSelect.value });
        return;
      }
      const username = uInput.value.trim();
      if (!username) {
        errEl.textContent = 'กรุณากรอกชื่อผู้ใช้';
        return;
      }
      if (pwInput.value !== pw2Input.value) {
        errEl.textContent = 'รหัสผ่านทั้งสองช่องไม่ตรงกัน';
        return;
      }
      dlg.close({
        username,
        display_name: display || username,
        role: rSelect.value,
        password: pwInput.value,
        password_confirm: pw2Input.value,
      });
    },
  });

  return dlg.show();
}
