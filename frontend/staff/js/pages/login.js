/**
 * frontend/staff/js/pages/login.js — หน้าล็อกอินของพนักงาน/เจ้าของร้าน
 * คัดลอกจาก ui/login_page.py ทุกตัวอักษร
 */

import { apiPost } from '../../../shared/js/api.js';
import { unlockAudioContext } from '../alert-center.js';

export function renderLoginPage(container, onSuccess) {
  container.textContent = '';

  const screen = document.createElement('div');
  screen.className = 'login-screen';

  const card = document.createElement('div');
  card.className = 'login-card card';

  const logo = document.createElement('img');
  logo.src = '/logo.png';
  logo.alt = 'ต้นมะค่า';
  logo.className = 'login-logo';
  logo.addEventListener('error', () => {
    logo.style.display = 'none';
  });
  card.appendChild(logo);

  const brand = document.createElement('div');
  brand.className = 'login-brand';
  brand.textContent = 'ต้นมะค่า';
  card.appendChild(brand);

  const sub = document.createElement('div');
  sub.className = 'login-sub';
  sub.textContent = 'เข้าสู่ระบบพนักงาน / เจ้าของร้าน';
  card.appendChild(sub);

  const form = document.createElement('form');
  form.className = 'login-form';
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    submit();
  });

  const userGroup = document.createElement('div');
  userGroup.className = 'field-group';
  const userLbl = document.createElement('label');
  userLbl.className = 'field-label';
  userLbl.textContent = 'ชื่อผู้ใช้';
  const userInput = document.createElement('input');
  userInput.type = 'text';
  userInput.className = 'field-input';
  userInput.autocomplete = 'username';
  userGroup.appendChild(userLbl);
  userGroup.appendChild(userInput);
  form.appendChild(userGroup);

  const passGroup = document.createElement('div');
  passGroup.className = 'field-group';
  const passLbl = document.createElement('label');
  passLbl.className = 'field-label';
  passLbl.textContent = 'รหัสผ่าน';
  const passInput = document.createElement('input');
  passInput.type = 'password';
  passInput.className = 'field-input';
  passInput.autocomplete = 'current-password';
  passGroup.appendChild(passLbl);
  passGroup.appendChild(passInput);
  form.appendChild(passGroup);

  const errorEl = document.createElement('div');
  errorEl.className = 'login-error';
  form.appendChild(errorEl);

  const submitBtn = document.createElement('button');
  submitBtn.type = 'submit';
  submitBtn.className = 'btn btn-lg btn-primary btn-block';
  submitBtn.textContent = 'เข้าสู่ระบบ';
  form.appendChild(submitBtn);

  card.appendChild(form);
  screen.appendChild(card);
  container.appendChild(screen);

  setTimeout(() => userInput.focus(), 50);

  async function submit() {
    unlockAudioContext();
    const username = userInput.value.trim();
    const password = passInput.value;
    if (!username || !password) {
      errorEl.textContent = 'กรุณากรอกชื่อผู้ใช้และรหัสผ่าน';
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'กำลังตรวจสอบ...';
    errorEl.textContent = '';

    try {
      const res = await apiPost(
        '/api/staff/login',
        { username, password },
        { ignoreAuth: true }
      );
      if (res && res.user && typeof onSuccess === 'function') {
        onSuccess(res.user);
      }
    } catch (err) {
      errorEl.textContent = err.message || 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง';
      passInput.value = '';
      submitBtn.disabled = false;
      submitBtn.textContent = 'เข้าสู่ระบบ';
      passInput.focus();
    }
  }
}
