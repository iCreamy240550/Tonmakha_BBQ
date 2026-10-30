/**
 * frontend/customer/js/order.js — หน้าสั่งอาหาร (สถานะ open):
 * แถบสมาชิก + หน้าเข้าสู่ระบบ / สมัครสมาชิก 2 ขั้น (OTP ทางอีเมลจริง) / ลืมรหัสผ่าน 2 ขั้น
 * + แท็บเมนู / 🎁 โปรโมชันสมาชิก / รายการของฉัน / ข้อความ / 🕒 ประวัติทำรายการ
 */

import { apiPost } from '../../shared/js/api.js';
import { BaseDialog } from '../../shared/js/dialogs.js';
import { baht, fmt_datetime, fmt_time, money, weight_text } from '../../shared/js/format.js';
import {
  ORDER_STATUS_CUSTOMER_COLORS,
  ORDER_STATUS_CUSTOMER_TH,
  createStatusBadge,
} from '../../shared/js/status-badge.js';
import { showToast } from '../../shared/js/toast.js';
import {
  createBillCard,
  createMessageCard,
  createSeparator,
  createSummaryRow,
} from './components.js';
import { renderNotices } from './notice.js';

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PHONE_DIGITS_PATTERN = /^0[2345689]\d{7,8}$/;

function getOrderTabs(member) {
  const tabs = [
    { key: 'menu', label: 'เมนู', dataTab: 'menu' },
    { key: 'promo', label: '🎁 โปรโมชันสมาชิก', dataTab: 'promo' },
    { key: 'mine', label: 'รายการของฉัน', dataTab: 'my_orders' },
    { key: 'notice', label: 'ข้อความ', dataTab: 'notices' },
  ];
  if (member) {
    tabs.push({ key: 'history', label: '🕒 ประวัติทำรายการ', dataTab: 'history' });
  }
  return tabs;
}

function maskEmailLocal(email) {
  const clean = String(email || '').trim().toLowerCase();
  if (!clean.includes('@')) return '***';
  const [local, domain] = clean.split('@');
  const prefix = local.length <= 1 ? `${local.slice(0, 1)}***` : `${local.slice(0, 2)}***`;
  return `${prefix}@${domain}`;
}

function validatePasswordClient(pw, email) {
  const val = String(pw || '');
  if (val.length < 8) {
    return 'รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร';
  }
  const byteLen = new TextEncoder().encode(val).length;
  if (byteLen > 72) {
    return 'รหัสผ่านต้องมีความยาวไม่เกิน 72 ไบต์';
  }
  const cleanEmail = String(email || '').trim().toLowerCase();
  if (cleanEmail && val.trim().toLowerCase() === cleanEmail) {
    return 'รหัสผ่านต้องไม่ซ้ำกับอีเมลของคุณ';
  }
  return '';
}

function validateThaiPhoneClient(phone) {
  const raw = String(phone || '').trim();
  if (!raw) return 'กรุณากรอกเบอร์โทรศัพท์';
  let norm = raw.replace(/[\s\-()]/g, '');
  if (norm.startsWith('+66')) {
    norm = '0' + norm.slice(3);
  } else if (norm.startsWith('66') && (norm.length === 10 || norm.length === 11)) {
    norm = '0' + norm.slice(2);
  }
  if (!PHONE_DIGITS_PATTERN.test(norm)) {
    return 'กรุณากรอกเบอร์โทรศัพท์ไทย 9–10 หลัก (เช่น 081-234-5678)';
  }
  return '';
}

function createPasswordFieldWithToggle({
  label,
  placeholder,
  autocomplete,
  testId,
  toggleTestId,
  initialValue = '',
}) {
  const group = document.createElement('div');
  group.className = 'field-group';

  const lbl = document.createElement('label');
  lbl.className = 'field-label';
  lbl.textContent = label;

  const wrap = document.createElement('div');
  wrap.className = 'cust-pw-wrap';

  const input = document.createElement('input');
  input.type = 'password';
  input.className = 'field-input cust-pw-input';
  input.placeholder = placeholder;
  input.autocomplete = autocomplete;
  input.value = initialValue;
  if (testId) {
    input.dataset.testid = testId;
  }

  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.className = 'btn btn-ghost cust-pw-toggle-btn';
  if (toggleTestId) {
    toggleBtn.dataset.testid = toggleTestId;
  }
  toggleBtn.textContent = 'แสดง';
  toggleBtn.setAttribute('aria-label', 'แสดงหรือซ่อนรหัสผ่าน');
  toggleBtn.addEventListener('click', () => {
    const isHidden = input.type === 'password';
    input.type = isHidden ? 'text' : 'password';
    toggleBtn.textContent = isHidden ? 'ซ่อน' : 'แสดง';
  });

  wrap.appendChild(input);
  wrap.appendChild(toggleBtn);
  group.appendChild(lbl);
  group.appendChild(wrap);

  return { group, input, toggleBtn };
}

function createStepIndicator(currentStep, totalSteps, stepLabel) {
  const bar = document.createElement('div');
  bar.className = 'cust-step-indicator';

  const badge = document.createElement('span');
  badge.className = 'cust-step-badge';
  badge.textContent = `ขั้นที่ ${currentStep}/${totalSteps}`;

  const text = document.createElement('span');
  text.className = 'cust-step-label';
  text.textContent = stepLabel;

  bar.appendChild(badge);
  bar.appendChild(text);
  return bar;
}

function createOtpNoticeBlock() {
  const box = document.createElement('div');
  box.className = 'cust-otp-guidance';

  const line1 = document.createElement('div');
  line1.className = 'cust-otp-guidance-item';
  line1.textContent = '• หากไม่พบอีเมล กรุณาตรวจสอบในโฟลเดอร์จดหมายขยะ (Spam)';

  const line2 = document.createElement('div');
  line2.className = 'cust-otp-guidance-item';
  line2.textContent = '• ใช้รหัสจากอีเมลฉบับล่าสุดที่ขอเท่านั้น';

  box.appendChild(line1);
  box.appendChild(line2);
  return box;
}

function attachCooldownTimer(uiState, buttonEl, getCooldownUntil) {
  if (uiState.countdownTimer) {
    clearInterval(uiState.countdownTimer);
    uiState.countdownTimer = null;
  }

  const updateBtn = () => {
    const until = Number(getCooldownUntil() || 0);
    const remain = Math.max(0, Math.ceil((until - Date.now()) / 1000));
    if (remain > 0) {
      buttonEl.disabled = true;
      buttonEl.textContent = `ส่งรหัสอีกครั้ง (${remain} วินาที)`;
    } else {
      buttonEl.disabled = false;
      buttonEl.textContent = 'ส่งรหัสอีกครั้ง';
      if (uiState.countdownTimer) {
        clearInterval(uiState.countdownTimer);
        uiState.countdownTimer = null;
      }
    }
  };

  updateBtn();
  uiState.countdownTimer = setInterval(updateBtn, 1000);
}

function renderMemberBanner(container, statePayload, uiState, onRefresh) {
  const banner = document.createElement('section');
  const member = statePayload.member || null;
  const appliedPromoCode = statePayload.applied_promo_code || null;
  banner.className = `cust-member-banner audit-block ${member ? 'is-logged-in' : ''}`;

  if (!member) {
    const top = document.createElement('div');
    top.className = 'cust-member-top';

    const titleCol = document.createElement('div');
    titleCol.className = 'cust-member-welcome';

    const title = document.createElement('div');
    title.className = 'cust-member-title';
    title.textContent = '🎁 สมาชิกร้านต้นมะค่า';

    const sub = document.createElement('div');
    sub.className = 'cust-member-sub';
    sub.textContent =
      'สั่งอาหารได้เลยโดยไม่ต้องสมัคร สมัครสมาชิกเพื่อรับโค้ดส่วนลดและดูประวัติ';

    titleCol.appendChild(title);
    titleCol.appendChild(sub);
    top.appendChild(titleCol);
    banner.appendChild(top);

    const actions = document.createElement('div');
    actions.className = 'cust-member-actions';

    const loginBtn = document.createElement('button');
    loginBtn.type = 'button';
    loginBtn.className = 'btn btn-primary';
    loginBtn.dataset.testid = 'btn-open-login';
    loginBtn.textContent = 'เข้าสู่ระบบ';
    loginBtn.addEventListener('click', () => {
      uiState.authPage = 'login';
      uiState.authSuccessMessage = '';
      onRefresh(false);
    });

    const signupBtn = document.createElement('button');
    signupBtn.type = 'button';
    signupBtn.className = 'btn btn-ghost cust-btn-secondary-outline';
    signupBtn.dataset.testid = 'btn-open-signup';
    signupBtn.textContent = 'สมัครสมาชิก';
    signupBtn.addEventListener('click', () => {
      uiState.authPage = 'signup';
      uiState.signupStep = 1;
      uiState.authSuccessMessage = '';
      onRefresh(false);
    });

    actions.appendChild(loginBtn);
    actions.appendChild(signupBtn);
    banner.appendChild(actions);
  } else {
    const top = document.createElement('div');
    top.className = 'cust-member-top';

    const info = document.createElement('div');
    info.className = 'cust-member-info';

    const avatar = document.createElement('div');
    avatar.className = 'cust-member-avatar';
    avatar.textContent = (member.name || 'M').charAt(0).toUpperCase();
    info.appendChild(avatar);

    const textCol = document.createElement('div');
    textCol.className = 'cust-member-welcome';

    const nameRow = document.createElement('div');
    nameRow.className = 'cust-member-title';
    nameRow.textContent = `สมาชิก: ${member.name}`;

    const metaRow = document.createElement('div');
    metaRow.className = 'cust-member-sub';
    metaRow.textContent = `${member.email} · โทร ${member.phone || '-'}`;

    textCol.appendChild(nameRow);
    textCol.appendChild(metaRow);
    info.appendChild(textCol);
    top.appendChild(info);

    const logoutBtn = document.createElement('button');
    logoutBtn.type = 'button';
    logoutBtn.className = 'btn btn-ghost cust-btn-touch';
    logoutBtn.dataset.testid = 'btn-member-logout';
    logoutBtn.textContent = 'ออกจากระบบ';
    logoutBtn.addEventListener('click', async () => {
      logoutBtn.disabled = true;
      try {
        const res = await apiPost('/api/customer/member/logout', {});
        if (uiState.tab === 'history') {
          uiState.tab = 'menu';
        }
        showToast(res.message || 'ออกจากระบบสมาชิกแล้ว สามารถสั่งอาหารต่อได้ตามปกติ', 'info');
        onRefresh(true, res);
      } catch (err) {
        logoutBtn.disabled = false;
        showToast(err.message || 'ไม่สามารถออกจากระบบได้', 'warning');
      }
    });
    top.appendChild(logoutBtn);
    banner.appendChild(top);

    if (appliedPromoCode) {
      const activePromoBar = document.createElement('div');
      activePromoBar.className = 'cust-active-promo-bar';

      const pTxt = document.createElement('span');
      pTxt.className = 'cust-active-promo-text';
      pTxt.textContent = `✓ ใช้โค้ดส่วนลดอยู่: ${appliedPromoCode}`;

      const clearBtn = document.createElement('button');
      clearBtn.type = 'button';
      clearBtn.className = 'btn btn-ghost cust-clear-promo-btn';
      clearBtn.textContent = 'ยกเลิกโค้ด';
      clearBtn.addEventListener('click', async () => {
        try {
          const res = await apiPost('/api/customer/member/promo/apply', { code: null });
          showToast(res.message || 'ยกเลิกการใช้โค้ดส่วนลดแล้ว', 'info');
          onRefresh(true, res);
        } catch (err) {
          showToast(err.message || 'ไม่สามารถยกเลิกโค้ดได้', 'warning');
        }
      });

      activePromoBar.appendChild(pTxt);
      activePromoBar.appendChild(clearBtn);
      banner.appendChild(activePromoBar);
    }

    const quickRow = document.createElement('div');
    quickRow.className = 'cust-member-actions';

    const promoBtn = document.createElement('button');
    promoBtn.type = 'button';
    promoBtn.className = 'btn btn-primary';
    promoBtn.textContent = '🎁 รับ/ใช้โค้ดโปรโมชัน';
    promoBtn.addEventListener('click', () => {
      uiState.tab = 'promo';
      onRefresh(false);
    });

    const histCount = Array.isArray(member.history) ? member.history.length : 0;
    const histBtn = document.createElement('button');
    histBtn.type = 'button';
    histBtn.className = 'btn btn-ghost cust-btn-secondary-outline';
    histBtn.textContent = `🕒 ประวัติทำรายการ (${histCount})`;
    histBtn.addEventListener('click', () => {
      uiState.tab = 'history';
      onRefresh(false);
    });

    quickRow.appendChild(promoBtn);
    quickRow.appendChild(histBtn);
    banner.appendChild(quickRow);
  }

  container.appendChild(banner);
}

function renderLoginPage(container, uiState, onRefresh) {
  const backBtn = document.createElement('button');
  backBtn.type = 'button';
  backBtn.className = 'btn btn-ghost cust-back-btn';
  backBtn.textContent = '← กลับไปหน้าสั่งอาหาร';
  backBtn.addEventListener('click', () => {
    uiState.authPage = null;
    uiState.authSuccessMessage = '';
    onRefresh(false);
  });
  container.appendChild(backBtn);

  const card = document.createElement('section');
  card.className = 'cust-auth-card audit-block';

  const title = document.createElement('h2');
  title.className = 'cust-section-title cust-auth-heading';
  title.textContent = 'เข้าสู่ระบบสมาชิก';
  card.appendChild(title);

  const sub = document.createElement('div');
  sub.className = 'cust-note-hint';
  sub.textContent = 'กรอกอีเมลและรหัสผ่านของคุณเพื่อรับโค้ดส่วนลดสมาชิกและดูประวัติใบเสร็จย้อนหลัง';
  card.appendChild(sub);

  if (uiState.authSuccessMessage) {
    const okBanner = document.createElement('div');
    okBanner.className = 'cust-form-success';
    okBanner.dataset.testid = 'login-success';
    okBanner.setAttribute('role', 'status');
    okBanner.setAttribute('aria-live', 'polite');
    okBanner.textContent = uiState.authSuccessMessage;
    card.appendChild(okBanner);
  }

  const emailGroup = document.createElement('div');
  emailGroup.className = 'field-group';
  const emailLbl = document.createElement('label');
  emailLbl.className = 'field-label';
  emailLbl.textContent = 'อีเมล';
  const emailInput = document.createElement('input');
  emailInput.type = 'email';
  emailInput.autocomplete = 'email';
  emailInput.className = 'field-input';
  emailInput.dataset.testid = 'login-id';
  emailInput.placeholder = 'yourname@example.com';
  emailGroup.appendChild(emailLbl);
  emailGroup.appendChild(emailInput);
  card.appendChild(emailGroup);

  const pwField = createPasswordFieldWithToggle({
    label: 'รหัสผ่าน',
    placeholder: 'กรอกรหัสผ่านของคุณ',
    autocomplete: 'current-password',
    testId: 'login-pw',
    toggleTestId: 'btn-toggle-login-pw',
  });
  card.appendChild(pwField.group);

  const forgotRow = document.createElement('div');
  forgotRow.className = 'cust-forgot-row';
  const forgotBtn = document.createElement('button');
  forgotBtn.type = 'button';
  forgotBtn.className = 'cust-link-btn';
  forgotBtn.dataset.testid = 'btn-open-reset';
  forgotBtn.textContent = 'ลืมรหัสผ่าน?';
  forgotBtn.addEventListener('click', () => {
    uiState.authPage = 'reset';
    uiState.resetStep = 1;
    uiState.authSuccessMessage = '';
    onRefresh(false);
  });
  forgotRow.appendChild(forgotBtn);
  card.appendChild(forgotRow);

  const errorBox = document.createElement('div');
  errorBox.className = 'cust-form-error hidden';
  errorBox.dataset.testid = 'login-error';
  errorBox.setAttribute('role', 'alert');
  errorBox.setAttribute('aria-live', 'polite');
  card.appendChild(errorBox);

  const setError = (msg) => {
    errorBox.textContent = msg || '';
    errorBox.classList.toggle('hidden', !msg);
  };

  const submitBtn = document.createElement('button');
  submitBtn.type = 'button';
  submitBtn.className = 'btn btn-primary cust-btn-touch';
  submitBtn.dataset.testid = 'btn-submit-login';
  submitBtn.textContent = 'เข้าสู่ระบบ';

  let submitting = false;
  const doLogin = async () => {
    if (submitting) return;
    setError('');
    const identifier = emailInput.value.trim().toLowerCase();
    const password = pwField.input.value;
    if (!identifier || !password) {
      setError('กรุณากรอกอีเมลและรหัสผ่านให้ครบถ้วน');
      return;
    }
    if (!EMAIL_PATTERN.test(identifier)) {
      setError('กรุณากรอกอีเมลให้ถูกต้อง (เช่น example@email.com)');
      return;
    }
    submitting = true;
    submitBtn.disabled = true;
    submitBtn.textContent = 'กำลังเข้าสู่ระบบ...';
    try {
      const res = await apiPost('/api/customer/member/login', {
        identifier,
        password,
      });
      uiState.authPage = null;
      uiState.authSuccessMessage = '';
      showToast(res.message || 'เข้าสู่ระบบสำเร็จ', 'success');
      onRefresh(true, res);
    } catch (err) {
      const msg = err.message || 'อีเมลหรือรหัสผ่านไม่ถูกต้อง';
      setError(msg);
      showToast(msg, 'error');
    } finally {
      submitting = false;
      submitBtn.disabled = false;
      submitBtn.textContent = 'เข้าสู่ระบบ';
    }
  };

  submitBtn.addEventListener('click', doLogin);
  pwField.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      doLogin();
    }
  });
  card.appendChild(submitBtn);

  const switchRow = document.createElement('div');
  switchRow.className = 'cust-auth-switch-row';
  const swText = document.createElement('span');
  swText.textContent = 'ยังไม่มีบัญชีสมาชิกใช่ไหม? ';
  const toSignupBtn = document.createElement('button');
  toSignupBtn.type = 'button';
  toSignupBtn.className = 'cust-link-btn';
  toSignupBtn.dataset.testid = 'link-to-signup';
  toSignupBtn.textContent = 'สมัครสมาชิกใหม่';
  toSignupBtn.addEventListener('click', () => {
    uiState.authPage = 'signup';
    uiState.signupStep = 1;
    uiState.authSuccessMessage = '';
    onRefresh(false);
  });
  switchRow.appendChild(swText);
  switchRow.appendChild(toSignupBtn);
  card.appendChild(switchRow);

  container.appendChild(card);
}

function renderSignupPage(container, uiState, onRefresh) {
  if (!uiState.signupDraft) {
    uiState.signupDraft = {
      name: '',
      email: '',
      maskedEmail: '',
      phone: '',
      password: '',
      passwordConfirm: '',
      cooldownUntil: 0,
    };
  }
  const draft = uiState.signupDraft;
  const step = uiState.signupStep === 2 ? 2 : 1;

  const backBtn = document.createElement('button');
  backBtn.type = 'button';
  backBtn.className = 'btn btn-ghost cust-back-btn';
  backBtn.textContent = '← กลับไปหน้าสั่งอาหาร';
  backBtn.addEventListener('click', () => {
    uiState.authPage = null;
    onRefresh(false);
  });
  container.appendChild(backBtn);

  const card = document.createElement('section');
  card.className = 'cust-auth-card audit-block';

  const title = document.createElement('h2');
  title.className = 'cust-section-title cust-auth-heading';
  title.textContent = 'สมัครสมาชิกใหม่';
  card.appendChild(title);

  card.appendChild(
    createStepIndicator(
      step,
      2,
      step === 1 ? 'กรอกข้อมูลสมาชิก' : 'ยืนยันรหัส OTP ทางอีเมล'
    )
  );

  const errorBox = document.createElement('div');
  errorBox.className = 'cust-form-error hidden';
  errorBox.dataset.testid = 'signup-error';
  errorBox.setAttribute('role', 'alert');
  errorBox.setAttribute('aria-live', 'polite');

  const setError = (msg) => {
    errorBox.textContent = msg || '';
    errorBox.classList.toggle('hidden', !msg);
  };

  if (step === 1) {
    const nameGroup = document.createElement('div');
    nameGroup.className = 'field-group';
    const nameLbl = document.createElement('label');
    nameLbl.className = 'field-label';
    nameLbl.textContent = 'ชื่อ - นามสกุล หรือ ชื่อที่ใช้แสดง';
    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.autocomplete = 'name';
    nameInput.className = 'field-input';
    nameInput.dataset.testid = 'signup-name';
    nameInput.placeholder = 'เช่น สมศรี มีสุข';
    nameInput.value = draft.name || '';
    nameGroup.appendChild(nameLbl);
    nameGroup.appendChild(nameInput);
    card.appendChild(nameGroup);

    const emailGroup = document.createElement('div');
    emailGroup.className = 'field-group';
    const emailLbl = document.createElement('label');
    emailLbl.className = 'field-label';
    emailLbl.textContent = 'อีเมล (สำหรับรับรหัส OTP ยืนยัน)';
    const emailInput = document.createElement('input');
    emailInput.type = 'email';
    emailInput.autocomplete = 'email';
    emailInput.className = 'field-input';
    emailInput.dataset.testid = 'signup-email';
    emailInput.placeholder = 'example@email.com';
    emailInput.value = draft.email || '';
    emailGroup.appendChild(emailLbl);
    emailGroup.appendChild(emailInput);
    card.appendChild(emailGroup);

    const phoneGroup = document.createElement('div');
    phoneGroup.className = 'field-group';
    const phoneLbl = document.createElement('label');
    phoneLbl.className = 'field-label';
    phoneLbl.textContent = 'เบอร์โทรศัพท์';
    const phoneInput = document.createElement('input');
    phoneInput.type = 'tel';
    phoneInput.autocomplete = 'tel';
    phoneInput.className = 'field-input';
    phoneInput.dataset.testid = 'signup-phone';
    phoneInput.placeholder = 'เช่น 081-234-5678';
    phoneInput.value = draft.phone || '';
    phoneGroup.appendChild(phoneLbl);
    phoneGroup.appendChild(phoneInput);
    card.appendChild(phoneGroup);

    const pwField = createPasswordFieldWithToggle({
      label: 'รหัสผ่าน',
      placeholder: 'อย่างน้อย 8 ตัวอักษร',
      autocomplete: 'new-password',
      testId: 'signup-pw',
      toggleTestId: 'btn-toggle-signup-pw',
      initialValue: draft.password || '',
    });
    card.appendChild(pwField.group);

    const pwHint = document.createElement('div');
    pwHint.className = 'cust-pw-hint';
    pwHint.dataset.testid = 'signup-pw-hint';
    pwHint.setAttribute('aria-live', 'polite');
    pwHint.textContent = 'คำแนะนำ: รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร (ไม่เกิน 72 ไบต์) และไม่ซ้ำกับอีเมล';
    card.appendChild(pwHint);

    const confirmField = createPasswordFieldWithToggle({
      label: 'ยืนยันรหัสผ่าน',
      placeholder: 'กรอกรหัสผ่านอีกครั้งให้ตรงกัน',
      autocomplete: 'new-password',
      testId: 'signup-pw-confirm',
      toggleTestId: 'btn-toggle-signup-pw-confirm',
      initialValue: draft.passwordConfirm || '',
    });
    card.appendChild(confirmField.group);

    const updateLiveValidation = () => {
      const pwVal = pwField.input.value;
      const confVal = confirmField.input.value;
      const emVal = emailInput.value.trim();
      if (!pwVal) {
        pwHint.className = 'cust-pw-hint';
        pwHint.textContent = 'คำแนะนำ: รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร (ไม่เกิน 72 ไบต์) และไม่ซ้ำกับอีเมล';
        return;
      }
      const pwErr = validatePasswordClient(pwVal, emVal);
      if (pwErr) {
        pwHint.className = 'cust-pw-hint is-invalid';
        pwHint.textContent = pwErr;
      } else if (confVal && pwVal !== confVal) {
        pwHint.className = 'cust-pw-hint is-invalid';
        pwHint.textContent = 'รหัสผ่านและยืนยันรหัสผ่านยังไม่ตรงกัน';
      } else {
        pwHint.className = 'cust-pw-hint is-valid';
        pwHint.textContent = '✓ รูปแบบรหัสผ่านถูกต้อง';
      }
    };

    pwField.input.addEventListener('input', updateLiveValidation);
    confirmField.input.addEventListener('input', updateLiveValidation);
    emailInput.addEventListener('input', updateLiveValidation);

    card.appendChild(errorBox);

    const reqOtpBtn = document.createElement('button');
    reqOtpBtn.type = 'button';
    reqOtpBtn.className = 'btn btn-primary cust-btn-touch';
    reqOtpBtn.dataset.testid = 'btn-request-signup-otp';
    reqOtpBtn.textContent = 'รับรหัส OTP ทางอีเมล';

    let requesting = false;
    reqOtpBtn.addEventListener('click', async () => {
      if (requesting) return;
      setError('');
      const nameVal = nameInput.value.trim();
      const emailVal = emailInput.value.trim().toLowerCase();
      const phoneVal = phoneInput.value.trim();
      const pwVal = pwField.input.value;
      const confVal = confirmField.input.value;

      if (!nameVal || !emailVal || !phoneVal || !pwVal || !confVal) {
        setError('กรุณากรอกข้อมูลชื่อ อีเมล เบอร์โทร และรหัสผ่านให้ครบทุกช่อง');
        return;
      }
      if (!EMAIL_PATTERN.test(emailVal)) {
        setError('กรุณากรอกอีเมลให้ถูกต้อง');
        return;
      }
      const phoneErr = validateThaiPhoneClient(phoneVal);
      if (phoneErr) {
        setError(phoneErr);
        return;
      }
      const pwErr = validatePasswordClient(pwVal, emailVal);
      if (pwErr) {
        setError(pwErr);
        return;
      }
      if (pwVal !== confVal) {
        setError('รหัสผ่านและยืนยันรหัสผ่านไม่ตรงกัน');
        return;
      }

      requesting = true;
      reqOtpBtn.disabled = true;
      reqOtpBtn.textContent = 'กำลังส่งรหัส OTP...';
      try {
        const res = await apiPost('/api/customer/member/otp', { email: emailVal });
        draft.name = nameVal;
        draft.email = emailVal;
        draft.maskedEmail = res.email || maskEmailLocal(emailVal);
        draft.phone = phoneVal;
        draft.password = pwVal;
        draft.passwordConfirm = confVal;
        const cdSec = Number(res.cooldown_seconds || 60);
        draft.cooldownUntil = Date.now() + cdSec * 1000;
        uiState.signupStep = 2;
        showToast(res.message || 'ส่งรหัส OTP ไปยังอีเมลของคุณแล้ว', 'info');
        onRefresh(false);
      } catch (err) {
        const msg = err.message || 'ส่งรหัส OTP ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง';
        setError(msg);
        showToast(msg, 'error');
      } finally {
        requesting = false;
        reqOtpBtn.disabled = false;
        reqOtpBtn.textContent = 'รับรหัส OTP ทางอีเมล';
      }
    });
    card.appendChild(reqOtpBtn);
  } else {
    const summaryBox = document.createElement('div');
    summaryBox.className = 'cust-email-summary-box';

    const emailText = document.createElement('div');
    emailText.className = 'cust-email-summary-text';
    emailText.textContent = `ส่งรหัสยืนยัน 6 หลักไปที่ ${draft.maskedEmail || maskEmailLocal(draft.email)} แล้ว`;

    const editEmailBtn = document.createElement('button');
    editEmailBtn.type = 'button';
    editEmailBtn.className = 'cust-link-btn';
    editEmailBtn.dataset.testid = 'btn-edit-signup-email';
    editEmailBtn.textContent = 'แก้ไขอีเมล';
    editEmailBtn.addEventListener('click', () => {
      uiState.signupStep = 1;
      onRefresh(false);
    });

    summaryBox.appendChild(emailText);
    summaryBox.appendChild(editEmailBtn);
    card.appendChild(summaryBox);

    const otpGroup = document.createElement('div');
    otpGroup.className = 'field-group';
    const otpLbl = document.createElement('label');
    otpLbl.className = 'field-label';
    otpLbl.textContent = 'รหัส OTP 6 หลักจากอีเมล';
    const otpInput = document.createElement('input');
    otpInput.type = 'text';
    otpInput.inputMode = 'numeric';
    otpInput.autocomplete = 'one-time-code';
    otpInput.maxLength = 6;
    otpInput.className = 'field-input cust-otp-input';
    otpInput.dataset.testid = 'signup-otp';
    otpInput.placeholder = 'กรอกตัวเลข 6 หลัก';
    otpInput.addEventListener('input', () => {
      otpInput.value = otpInput.value.replace(/\D+/g, '').slice(0, 6);
    });
    otpGroup.appendChild(otpLbl);
    otpGroup.appendChild(otpInput);
    card.appendChild(otpGroup);

    card.appendChild(createOtpNoticeBlock());
    card.appendChild(errorBox);

    const submitBtn = document.createElement('button');
    submitBtn.type = 'button';
    submitBtn.className = 'btn btn-primary cust-btn-touch';
    submitBtn.dataset.testid = 'btn-submit-signup';
    submitBtn.textContent = 'ยืนยันและสมัครสมาชิก';

    let submitting = false;
    submitBtn.addEventListener('click', async () => {
      if (submitting) return;
      setError('');
      const otpVal = otpInput.value.trim();
      if (!/^\d{6}$/.test(otpVal)) {
        setError('กรุณากรอกรหัส OTP ตัวเลข 6 หลักให้ครบถ้วน');
        return;
      }
      submitting = true;
      submitBtn.disabled = true;
      submitBtn.textContent = 'กำลังยืนยันและสมัครสมาชิก...';
      try {
        const res = await apiPost('/api/customer/member/signup', {
          name: draft.name,
          email: draft.email,
          phone: draft.phone,
          password: draft.password,
          password_confirm: draft.passwordConfirm,
          otp_code: otpVal,
        });
        uiState.signupDraft = {
          name: '',
          email: '',
          maskedEmail: '',
          phone: '',
          password: '',
          passwordConfirm: '',
          cooldownUntil: 0,
        };
        uiState.signupStep = 1;
        uiState.authPage = null;
        uiState.tab = 'promo';
        showToast(res.message || 'สมัครสมาชิกสำเร็จ!', 'success');
        onRefresh(true, res);
      } catch (err) {
        const msg = err.message || 'สมัครสมาชิกไม่สำเร็จ';
        setError(msg);
        showToast(msg, 'error');
      } finally {
        submitting = false;
        submitBtn.disabled = false;
        submitBtn.textContent = 'ยืนยันและสมัครสมาชิก';
      }
    });
    card.appendChild(submitBtn);

    const resendBtn = document.createElement('button');
    resendBtn.type = 'button';
    resendBtn.className = 'btn btn-ghost cust-btn-secondary-outline cust-btn-touch';
    resendBtn.dataset.testid = 'btn-resend-signup-otp';
    resendBtn.addEventListener('click', async () => {
      if (resendBtn.disabled) return;
      setError('');
      resendBtn.disabled = true;
      resendBtn.textContent = 'กำลังส่งรหัสใหม่...';
      try {
        const res = await apiPost('/api/customer/member/otp', { email: draft.email });
        const cdSec = Number(res.cooldown_seconds || 60);
        draft.cooldownUntil = Date.now() + cdSec * 1000;
        attachCooldownTimer(uiState, resendBtn, () => draft.cooldownUntil);
        showToast(res.message || 'ส่งรหัส OTP ใหม่แล้ว', 'info');
      } catch (err) {
        const msg = err.message || 'ไม่สามารถส่งรหัสใหม่ได้';
        setError(msg);
        showToast(msg, 'error');
        attachCooldownTimer(uiState, resendBtn, () => draft.cooldownUntil);
      }
    });
    card.appendChild(resendBtn);
    attachCooldownTimer(uiState, resendBtn, () => draft.cooldownUntil);
  }

  const switchRow = document.createElement('div');
  switchRow.className = 'cust-auth-switch-row';
  const swText = document.createElement('span');
  swText.textContent = 'มีบัญชีสมาชิกอยู่แล้ว? ';
  const toLoginBtn = document.createElement('button');
  toLoginBtn.type = 'button';
  toLoginBtn.className = 'cust-link-btn';
  toLoginBtn.dataset.testid = 'link-to-login';
  toLoginBtn.textContent = 'เข้าสู่ระบบ';
  toLoginBtn.addEventListener('click', () => {
    uiState.authPage = 'login';
    onRefresh(false);
  });
  switchRow.appendChild(swText);
  switchRow.appendChild(toLoginBtn);
  card.appendChild(switchRow);

  container.appendChild(card);
}

function renderResetPasswordPage(container, uiState, onRefresh) {
  if (!uiState.resetDraft) {
    uiState.resetDraft = {
      email: '',
      maskedEmail: '',
      cooldownUntil: 0,
    };
  }
  const draft = uiState.resetDraft;
  const step = uiState.resetStep === 2 ? 2 : 1;

  const backBtn = document.createElement('button');
  backBtn.type = 'button';
  backBtn.className = 'btn btn-ghost cust-back-btn';
  backBtn.textContent = '← กลับไปหน้าเข้าสู่ระบบ';
  backBtn.addEventListener('click', () => {
    uiState.authPage = 'login';
    onRefresh(false);
  });
  container.appendChild(backBtn);

  const card = document.createElement('section');
  card.className = 'cust-auth-card audit-block';

  const title = document.createElement('h2');
  title.className = 'cust-section-title cust-auth-heading';
  title.textContent = 'ลืมรหัสผ่าน / ตั้งรหัสผ่านใหม่';
  card.appendChild(title);

  card.appendChild(
    createStepIndicator(
      step,
      2,
      step === 1 ? 'ระบุอีเมลที่ใช้สมัครสมาชิก' : 'กรอกรหัส OTP และตั้งรหัสผ่านใหม่'
    )
  );

  const errorBox = document.createElement('div');
  errorBox.className = 'cust-form-error hidden';
  errorBox.dataset.testid = 'reset-error';
  errorBox.setAttribute('role', 'alert');
  errorBox.setAttribute('aria-live', 'polite');

  const setError = (msg) => {
    errorBox.textContent = msg || '';
    errorBox.classList.toggle('hidden', !msg);
  };

  if (step === 1) {
    const desc = document.createElement('div');
    desc.className = 'cust-note-hint';
    desc.textContent = 'กรอกอีเมลของคุณเพื่อรับรหัส OTP 6 หลักสำหรับยืนยันตัวตนและตั้งรหัสผ่านใหม่';
    card.appendChild(desc);

    const emailGroup = document.createElement('div');
    emailGroup.className = 'field-group';
    const emailLbl = document.createElement('label');
    emailLbl.className = 'field-label';
    emailLbl.textContent = 'อีเมลสมาชิก';
    const emailInput = document.createElement('input');
    emailInput.type = 'email';
    emailInput.autocomplete = 'email';
    emailInput.className = 'field-input';
    emailInput.dataset.testid = 'reset-email';
    emailInput.placeholder = 'yourname@example.com';
    emailInput.value = draft.email || '';
    emailGroup.appendChild(emailLbl);
    emailGroup.appendChild(emailInput);
    card.appendChild(emailGroup);

    card.appendChild(errorBox);

    const reqBtn = document.createElement('button');
    reqBtn.type = 'button';
    reqBtn.className = 'btn btn-primary cust-btn-touch';
    reqBtn.dataset.testid = 'btn-request-reset-otp';
    reqBtn.textContent = 'รับรหัส OTP ทางอีเมล';

    let requesting = false;
    reqBtn.addEventListener('click', async () => {
      if (requesting) return;
      setError('');
      const emailVal = emailInput.value.trim().toLowerCase();
      if (!emailVal || !EMAIL_PATTERN.test(emailVal)) {
        setError('กรุณากรอกอีเมลให้ถูกต้อง');
        return;
      }
      requesting = true;
      reqBtn.disabled = true;
      reqBtn.textContent = 'กำลังส่งรหัส OTP...';
      try {
        const res = await apiPost('/api/customer/member/reset/start', { email: emailVal });
        draft.email = emailVal;
        draft.maskedEmail = res.email || maskEmailLocal(emailVal);
        const cdSec = Number(res.cooldown_seconds || 60);
        draft.cooldownUntil = Date.now() + cdSec * 1000;
        uiState.resetStep = 2;
        showToast(res.message || 'ส่งรหัส OTP สำหรับตั้งรหัสผ่านใหม่แล้ว', 'info');
        onRefresh(false);
      } catch (err) {
        const msg = err.message || 'ไม่สามารถส่งรหัส OTP ได้ กรุณาลองใหม่อีกครั้ง';
        setError(msg);
        showToast(msg, 'error');
      } finally {
        requesting = false;
        reqBtn.disabled = false;
        reqBtn.textContent = 'รับรหัส OTP ทางอีเมล';
      }
    });
    card.appendChild(reqBtn);
  } else {
    const summaryBox = document.createElement('div');
    summaryBox.className = 'cust-email-summary-box';

    const emailText = document.createElement('div');
    emailText.className = 'cust-email-summary-text';
    emailText.textContent = `อีเมลที่ทำรายการ: ${draft.maskedEmail || maskEmailLocal(draft.email)}`;

    const editEmailBtn = document.createElement('button');
    editEmailBtn.type = 'button';
    editEmailBtn.className = 'cust-link-btn';
    editEmailBtn.dataset.testid = 'btn-edit-reset-email';
    editEmailBtn.textContent = 'แก้ไขอีเมล';
    editEmailBtn.addEventListener('click', () => {
      uiState.resetStep = 1;
      onRefresh(false);
    });

    summaryBox.appendChild(emailText);
    summaryBox.appendChild(editEmailBtn);
    card.appendChild(summaryBox);

    const otpGroup = document.createElement('div');
    otpGroup.className = 'field-group';
    const otpLbl = document.createElement('label');
    otpLbl.className = 'field-label';
    otpLbl.textContent = 'รหัส OTP 6 หลักจากอีเมล';
    const otpInput = document.createElement('input');
    otpInput.type = 'text';
    otpInput.inputMode = 'numeric';
    otpInput.autocomplete = 'one-time-code';
    otpInput.maxLength = 6;
    otpInput.className = 'field-input cust-otp-input';
    otpInput.dataset.testid = 'reset-otp';
    otpInput.placeholder = 'กรอกตัวเลข 6 หลัก';
    otpInput.addEventListener('input', () => {
      otpInput.value = otpInput.value.replace(/\D+/g, '').slice(0, 6);
    });
    otpGroup.appendChild(otpLbl);
    otpGroup.appendChild(otpInput);
    card.appendChild(otpGroup);

    card.appendChild(createOtpNoticeBlock());

    const pwField = createPasswordFieldWithToggle({
      label: 'รหัสผ่านใหม่',
      placeholder: 'อย่างน้อย 8 ตัวอักษร',
      autocomplete: 'new-password',
      testId: 'reset-pw',
      toggleTestId: 'btn-toggle-reset-pw',
    });
    card.appendChild(pwField.group);

    const pwHint = document.createElement('div');
    pwHint.className = 'cust-pw-hint';
    pwHint.setAttribute('aria-live', 'polite');
    pwHint.textContent = 'คำแนะนำ: รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร (ไม่เกิน 72 ไบต์) และไม่ซ้ำกับอีเมล';
    card.appendChild(pwHint);

    const confirmField = createPasswordFieldWithToggle({
      label: 'ยืนยันรหัสผ่านใหม่',
      placeholder: 'กรอกรหัสผ่านใหม่อีกครั้งให้ตรงกัน',
      autocomplete: 'new-password',
      testId: 'reset-pw-confirm',
      toggleTestId: 'btn-toggle-reset-pw-confirm',
    });
    card.appendChild(confirmField.group);

    const updateResetPwValidation = () => {
      const pwVal = pwField.input.value;
      const confVal = confirmField.input.value;
      if (!pwVal) {
        pwHint.className = 'cust-pw-hint';
        pwHint.textContent = 'คำแนะนำ: รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร (ไม่เกิน 72 ไบต์) และไม่ซ้ำกับอีเมล';
        return;
      }
      const pwErr = validatePasswordClient(pwVal, draft.email);
      if (pwErr) {
        pwHint.className = 'cust-pw-hint is-invalid';
        pwHint.textContent = pwErr;
      } else if (confVal && pwVal !== confVal) {
        pwHint.className = 'cust-pw-hint is-invalid';
        pwHint.textContent = 'รหัสผ่านใหม่และยืนยันรหัสผ่านยังไม่ตรงกัน';
      } else {
        pwHint.className = 'cust-pw-hint is-valid';
        pwHint.textContent = '✓ รูปแบบรหัสผ่านใหม่ถูกต้อง';
      }
    };
    pwField.input.addEventListener('input', updateResetPwValidation);
    confirmField.input.addEventListener('input', updateResetPwValidation);

    card.appendChild(errorBox);

    const submitBtn = document.createElement('button');
    submitBtn.type = 'button';
    submitBtn.className = 'btn btn-primary cust-btn-touch';
    submitBtn.dataset.testid = 'btn-submit-reset';
    submitBtn.textContent = 'ตั้งรหัสผ่านใหม่';

    let submitting = false;
    submitBtn.addEventListener('click', async () => {
      if (submitting) return;
      setError('');
      const otpVal = otpInput.value.trim();
      const pwVal = pwField.input.value;
      const confVal = confirmField.input.value;

      if (!/^\d{6}$/.test(otpVal)) {
        setError('กรุณากรอกรหัส OTP ตัวเลข 6 หลักให้ครบถ้วน');
        return;
      }
      const pwErr = validatePasswordClient(pwVal, draft.email);
      if (pwErr) {
        setError(pwErr);
        return;
      }
      if (pwVal !== confVal) {
        setError('รหัสผ่านใหม่และยืนยันรหัสผ่านไม่ตรงกัน');
        return;
      }

      submitting = true;
      submitBtn.disabled = true;
      submitBtn.textContent = 'กำลังบันทึกรหัสผ่านใหม่...';
      try {
        const res = await apiPost('/api/customer/member/reset/verify', {
          email: draft.email,
          otp_code: otpVal,
          new_password: pwVal,
          new_password_confirm: confVal,
        });
        uiState.resetDraft = { email: '', maskedEmail: '', cooldownUntil: 0 };
        uiState.resetStep = 1;
        uiState.authPage = 'login';
        uiState.authSuccessMessage =
          res.message || 'ตั้งรหัสผ่านใหม่สำเร็จ กรุณาเข้าสู่ระบบด้วยรหัสผ่านใหม่ของคุณ';
        showToast(uiState.authSuccessMessage, 'success');
        onRefresh(false);
      } catch (err) {
        const msg = err.message || 'ไม่สามารถตั้งรหัสผ่านใหม่ได้';
        setError(msg);
        showToast(msg, 'error');
      } finally {
        submitting = false;
        submitBtn.disabled = false;
        submitBtn.textContent = 'ตั้งรหัสผ่านใหม่';
      }
    });
    card.appendChild(submitBtn);

    const resendBtn = document.createElement('button');
    resendBtn.type = 'button';
    resendBtn.className = 'btn btn-ghost cust-btn-secondary-outline cust-btn-touch';
    resendBtn.dataset.testid = 'btn-resend-reset-otp';
    resendBtn.addEventListener('click', async () => {
      if (resendBtn.disabled) return;
      setError('');
      resendBtn.disabled = true;
      resendBtn.textContent = 'กำลังส่งรหัสใหม่...';
      try {
        const res = await apiPost('/api/customer/member/reset/start', { email: draft.email });
        const cdSec = Number(res.cooldown_seconds || 60);
        draft.cooldownUntil = Date.now() + cdSec * 1000;
        attachCooldownTimer(uiState, resendBtn, () => draft.cooldownUntil);
        showToast(res.message || 'ส่งรหัส OTP ใหม่แล้ว', 'info');
      } catch (err) {
        const msg = err.message || 'ไม่สามารถส่งรหัสใหม่ได้';
        setError(msg);
        showToast(msg, 'error');
        attachCooldownTimer(uiState, resendBtn, () => draft.cooldownUntil);
      }
    });
    card.appendChild(resendBtn);
    attachCooldownTimer(uiState, resendBtn, () => draft.cooldownUntil);
  }

  container.appendChild(card);
}

function renderPromoTab(container, statePayload, uiState, onRefresh) {
  const member = statePayload.member || null;
  const snap = statePayload.snapshot;
  const subtotal = Number((snap && snap.subtotal) || 0);
  const appliedPromoCode = statePayload.applied_promo_code || null;
  const promos = statePayload.member_promotions || [];

  if (!member) {
    const lockCard = createMessageCard({
      icon: 'block',
      title: 'เฉพาะสมาชิกเท่านั้น',
      text: 'ลูกค้าที่ไม่ได้สมัครสมาชิกยังสามารถสั่งอาหารได้ตามปกติ แต่หากต้องการรับโค้ดส่วนลดพิเศษ กรุณาเข้าสู่ระบบหรือสมัครสมาชิกก่อนค่ะ',
      color: 'warning',
    });

    const btnRow = document.createElement('div');
    btnRow.className = 'cust-member-actions';
    btnRow.style.marginTop = 'var(--space-2)';

    const loginBtn = document.createElement('button');
    loginBtn.type = 'button';
    loginBtn.className = 'btn btn-primary';
    loginBtn.dataset.testid = 'btn-open-login';
    loginBtn.textContent = 'เข้าสู่ระบบ';
    loginBtn.addEventListener('click', () => {
      uiState.authPage = 'login';
      onRefresh(false);
    });

    const signupBtn = document.createElement('button');
    signupBtn.type = 'button';
    signupBtn.className = 'btn btn-ghost cust-btn-secondary-outline';
    signupBtn.dataset.testid = 'btn-open-signup';
    signupBtn.textContent = 'สมัครสมาชิก';
    signupBtn.addEventListener('click', () => {
      uiState.authPage = 'signup';
      uiState.signupStep = 1;
      onRefresh(false);
    });

    btnRow.appendChild(loginBtn);
    btnRow.appendChild(signupBtn);
    lockCard.appendChild(btnRow);
    container.appendChild(lockCard);
    return;
  }

  const introCard = document.createElement('section');
  introCard.className = 'cust-section-card audit-block';
  const introTitle = document.createElement('div');
  introTitle.className = 'cust-section-title';
  introTitle.textContent = '🎁 โปรโมชันสำหรับสมาชิก';
  const introSub = document.createElement('div');
  introSub.className = 'cust-note-hint';
  introSub.textContent = `ยอดสั่งอาหารปัจจุบันของโต๊ะคุณ: ${baht(subtotal)} — กดรับโค้ดพิเศษและกดใช้เพื่อรับส่วนลดท้ายบิลได้ทันที`;
  introCard.appendChild(introTitle);
  introCard.appendChild(introSub);
  container.appendChild(introCard);

  if (promos.length === 0) {
    container.appendChild(
      createMessageCard({
        icon: 'info',
        title: 'ยังไม่มีโปรโมชันสมาชิกในขณะนี้',
        text: 'กรุณาติดตามโปรโมชันใหม่จากทางร้าน',
        color: 'grey',
      })
    );
    return;
  }

  const claimedList = member.claimed_promos || [];

  for (const p of promos) {
    const isClaimed = claimedList.includes(p.code);
    const isApplied = appliedPromoCode === p.code;
    const meetsMin = subtotal >= Number(p.min_subtotal || 0);

    const pCard = document.createElement('div');
    pCard.className = `cust-promo-card audit-block ${isApplied ? 'is-applied' : ''}`;

    const topRow = document.createElement('div');
    topRow.style.display = 'flex';
    topRow.style.alignItems = 'center';
    topRow.style.justifyContent = 'space-between';
    topRow.style.gap = 'var(--space-2)';
    topRow.style.flexWrap = 'wrap';

    const pTitle = document.createElement('div');
    pTitle.className = 'cust-section-title';
    pTitle.textContent = p.title;
    topRow.appendChild(pTitle);

    const codeBadge = document.createElement('span');
    codeBadge.className = 'cust-promo-code-tag';
    codeBadge.textContent = isClaimed ? `โค้ด: ${p.code}` : 'กดรับโค้ด';
    topRow.appendChild(codeBadge);

    pCard.appendChild(topRow);

    const descEl = document.createElement('div');
    descEl.className = 'cust-note-hint';
    descEl.textContent = p.description || '';
    pCard.appendChild(descEl);

    const actionRow = document.createElement('div');
    actionRow.style.display = 'flex';
    actionRow.style.alignItems = 'center';
    actionRow.style.justifyContent = 'space-between';
    actionRow.style.gap = 'var(--space-2)';
    actionRow.style.marginTop = 'var(--space-1)';
    actionRow.style.flexWrap = 'wrap';

    const condTxt = document.createElement('span');
    condTxt.style.fontSize = 'var(--fs-xs)';
    condTxt.style.color = meetsMin ? 'var(--color-success)' : 'var(--color-warning)';
    condTxt.style.fontWeight = '600';
    condTxt.textContent =
      p.min_subtotal > 0
        ? meetsMin
          ? `✓ ยอดถึงเกณฑ์ขั้นต่ำ ${money(p.min_subtotal)} บาทแล้ว`
          : `ต้องมียอดอาหารขั้นต่ำ ${money(p.min_subtotal)} บาท`
        : '✓ ไม่มีขั้นต่ำ ใช้ได้ทันที';
    actionRow.appendChild(condTxt);

    if (!isClaimed) {
      const claimBtn = document.createElement('button');
      claimBtn.type = 'button';
      claimBtn.className = 'btn btn-primary cust-btn-touch';
      claimBtn.dataset.testid = `btn-claim-${p.code}`;
      claimBtn.textContent = 'เก็บโค้ดส่วนลด';
      claimBtn.addEventListener('click', async () => {
        try {
          const res = await apiPost('/api/customer/member/promo/claim', { code: p.code });
          showToast(res.message || `รับโค้ด "${p.code}" สำเร็จ`, 'success');
          onRefresh(true, res);
        } catch (err) {
          showToast(err.message || 'ไม่สามารถเก็บโค้ดได้', 'error');
        }
      });
      actionRow.appendChild(claimBtn);
    } else if (isApplied) {
      const appliedBtn = document.createElement('button');
      appliedBtn.type = 'button';
      appliedBtn.className = 'btn btn-success cust-btn-touch';
      appliedBtn.textContent = '✓ กำลังใช้โค้ดนี้ (กดเพื่อยกเลิก)';
      appliedBtn.addEventListener('click', async () => {
        try {
          const res = await apiPost('/api/customer/member/promo/apply', { code: null });
          showToast(res.message || 'ยกเลิกการใช้โค้ดส่วนลดแล้ว', 'info');
          onRefresh(true, res);
        } catch (err) {
          showToast(err.message || 'ไม่สามารถยกเลิกโค้ดได้', 'error');
        }
      });
      actionRow.appendChild(appliedBtn);
    } else {
      const useBtn = document.createElement('button');
      useBtn.type = 'button';
      useBtn.className = 'btn btn-primary cust-btn-touch';
      useBtn.dataset.testid = `btn-apply-${p.code}`;
      useBtn.textContent = 'ใช้โค้ดส่วนลดนี้';
      useBtn.disabled = !meetsMin;
      useBtn.addEventListener('click', async () => {
        try {
          const res = await apiPost('/api/customer/member/promo/apply', { code: p.code });
          showToast(res.message || `ใช้โค้ด "${p.code}" สำเร็จ`, 'success');
          onRefresh(true, res);
        } catch (err) {
          showToast(err.message || 'ไม่สามารถใช้โค้ดนี้ได้', 'error');
        }
      });
      actionRow.appendChild(useBtn);
    }

    pCard.appendChild(actionRow);
    container.appendChild(pCard);
  }
}

function renderHistoryTab(container, statePayload, uiState, onRefresh) {
  const member = statePayload.member || null;
  if (!member) {
    renderPromoTab(container, statePayload, uiState, onRefresh);
    return;
  }

  const historyList = member.history || [];

  const headCard = document.createElement('section');
  headCard.className = 'cust-section-card audit-block';
  const headTitle = document.createElement('div');
  headTitle.className = 'cust-section-title';
  headTitle.textContent = '🕒 ประวัติการทำรายการย้อนหลัง';
  const headSub = document.createElement('div');
  headSub.className = 'cust-note-hint';
  headSub.textContent = `ประวัติการใช้บริการของคุณ ${member.name} ทั้งหมด ${historyList.length} ครั้ง`;
  headCard.appendChild(headTitle);
  headCard.appendChild(headSub);
  container.appendChild(headCard);

  if (historyList.length === 0) {
    container.appendChild(
      createMessageCard({
        icon: 'receipt_long',
        title: 'ยังไม่มีประวัติการทำรายการ',
        text: 'เมื่อคุณชำระเงินค่าอาหารเรียบร้อย ประวัติและใบเสร็จจะแสดงที่นี่',
        color: 'grey',
      })
    );
    return;
  }

  for (const h of historyList) {
    const card = document.createElement('div');
    card.className = 'cust-history-card audit-block';

    const topRow = document.createElement('div');
    topRow.style.display = 'flex';
    topRow.style.alignItems = 'center';
    topRow.style.justifyContent = 'space-between';
    topRow.style.gap = 'var(--space-2)';

    const tName = document.createElement('div');
    tName.className = 'cust-section-title';
    tName.textContent = `🪑 นั่งที่: ${h.table_name}`;

    const badge = createStatusBadge('ชำระแล้ว', '#2f9e44');
    topRow.appendChild(tName);
    topRow.appendChild(badge);
    card.appendChild(topRow);

    card.appendChild(createSummaryRow('เลขที่ใบเสร็จ', h.id));
    card.appendChild(createSummaryRow('วันที่ใช้บริการ', fmt_datetime(h.visited_at, '-')));
    card.appendChild(
      createSummaryRow('ยอดชำระสุทธิ', baht(h.bill ? h.bill.total : h.total), {
        bold: true,
        color: 'primary',
      })
    );

    const btnRow = document.createElement('div');
    btnRow.style.display = 'flex';
    btnRow.style.justifyContent = 'flex-end';
    btnRow.style.marginTop = 'var(--space-1)';

    const viewReceiptBtn = document.createElement('button');
    viewReceiptBtn.type = 'button';
    viewReceiptBtn.className = 'btn btn-ghost cust-btn-secondary-outline cust-btn-touch history-receipt-btn';
    viewReceiptBtn.textContent = '🧾 ดูใบเสร็จย้อนหลัง';
    viewReceiptBtn.addEventListener('click', () => openPastReceiptDialog(h));

    btnRow.appendChild(viewReceiptBtn);
    card.appendChild(btnRow);
    container.appendChild(card);
  }
}

async function openPastReceiptDialog(historyItem) {
  const dlg = new BaseDialog(
    `ใบเสร็จย้อนหลัง · ${historyItem.table_name}`,
    { width: 440 }
  );

  const meta = document.createElement('div');
  meta.style.fontSize = 'var(--fs-sm)';
  meta.style.color = 'var(--color-text-muted)';
  meta.textContent = `เลขที่ ${historyItem.id} · วันที่ ${fmt_datetime(historyItem.visited_at, '-')}`;
  dlg.body.appendChild(meta);

  if (historyItem.bill) {
    const billEl = createBillCard(historyItem.bill, { paid: true });
    dlg.body.appendChild(billEl);
  }

  dlg.addButtons({
    confirmText: 'ปิดหน้าต่าง',
    cancelText: null,
    variant: 'primary',
    onConfirm: () => dlg.close(true),
  });

  await dlg.show();
}

export function renderOrderView(container, statePayload, uiState, onRefresh) {
  const snap = statePayload.snapshot;

  if (uiState.authPage === 'login') {
    renderLoginPage(container, uiState, onRefresh);
    return;
  }
  if (uiState.authPage === 'signup') {
    renderSignupPage(container, uiState, onRefresh);
    return;
  }
  if (uiState.authPage === 'reset') {
    renderResetPasswordPage(container, uiState, onRefresh);
    return;
  }

  renderMemberBanner(container, statePayload, uiState, onRefresh);

  if (
    Array.isArray(statePayload.removed_from_cart) &&
    statePayload.removed_from_cart.length > 0
  ) {
    showToast(
      `เอาออกจากตะกร้าแล้ว (สินค้าหมด/ไม่มีขาย): ${statePayload.removed_from_cart.join(', ')}`,
      'warning',
      5000
    );
  }

  // แถบแท็บ
  const tabs = getOrderTabs(statePayload.member);
  const tabRow = document.createElement('nav');
  tabRow.className = 'cust-tabs audit-block';
  for (const t of tabs) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.dataset.tab = t.dataTab;
    btn.className = `cust-tab-btn ${uiState.tab === t.key ? 'is-active' : ''}`;
    let label = t.label;
    if (t.key === 'notice' && Array.isArray(snap.notices) && snap.notices.length > 0) {
      label = `${label} (${snap.notices.length})`;
    }
    btn.textContent = label;
    btn.addEventListener('click', () => {
      if (uiState.tab !== t.key) {
        uiState.tab = t.key;
        onRefresh(false);
      }
    });
    tabRow.appendChild(btn);
  }
  container.appendChild(tabRow);

  if (uiState.tab === 'mine') {
    renderMineTab(container, snap, statePayload);
  } else if (uiState.tab === 'notice') {
    renderNotices(container, snap);
  } else if (uiState.tab === 'promo') {
    renderPromoTab(container, statePayload, uiState, onRefresh);
  } else if (uiState.tab === 'history') {
    renderHistoryTab(container, statePayload, uiState, onRefresh);
  } else {
    renderMenuTab(container, statePayload, uiState, onRefresh);
  }
}

function stockCaption(it) {
  const stockQty = it.stock_quantity;
  const stockUnit = String(it.stock_unit || '').trim();
  const soldOut =
    Boolean(it.is_sold_out) ||
    (stockQty !== null && stockQty !== undefined && Number(stockQty) <= 0);
  if (soldOut) {
    const unitPart = stockUnit ? ` ${stockUnit}` : '';
    return { text: `สินค้าหมด · คงเหลือ 0${unitPart}`, cls: 'cust-stock-out' };
  }
  if (stockQty !== null && stockQty !== undefined) {
    const n = Number(stockQty);
    const qtyTxt = Number.isInteger(n) ? String(n) : String(Number(n.toPrecision(6)));
    const unitPart = stockUnit ? ` ${stockUnit}` : '';
    return { text: `คงเหลือ ${qtyTxt}${unitPart}`, cls: 'cust-stock-ok' };
  }
  return { text: it.stock_text || 'พร้อมจำหน่าย', cls: 'cust-stock-ready' };
}

function createThumbnail(it) {
  const box = document.createElement('div');
  box.className = 'cust-item-thumb';

  const showPlaceholder = () => {
    box.textContent = '';
    const ph = document.createElement('div');
    ph.className = 'cust-item-placeholder';
    ph.textContent = '🍲';
    box.appendChild(ph);
  };

  if (it.image_url && it.has_image) {
    const img = document.createElement('img');
    img.src = it.image_url;
    img.alt = it.name || '';
    img.addEventListener('error', showPlaceholder);
    box.appendChild(img);
  } else {
    showPlaceholder();
  }
  return box;
}

function renderMenuTab(container, statePayload, uiState, onRefresh) {
  const snap = statePayload.snapshot;
  const menu = snap.menu || [];
  const cart = statePayload.cart || {};

  if (menu.length === 0) {
    container.appendChild(
      createMessageCard({
        icon: 'restaurant_menu',
        title: 'ยังไม่มีเมนู',
        text: 'กรุณาสอบถามพนักงาน',
        color: 'grey',
      })
    );
    return;
  }

  const validCatIds = new Set(menu.map((c) => c.id));
  if (!validCatIds.has(uiState.cat)) {
    uiState.cat = menu[0].id;
  }

  // ปุ่มเลือกหมวดเมนู
  const catsRow = document.createElement('div');
  catsRow.className = 'cust-cats audit-block';
  for (const cat of menu) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `cust-cat-btn ${uiState.cat === cat.id ? 'is-active' : ''}`;
    b.textContent = cat.name;
    b.addEventListener('click', () => {
      uiState.cat = cat.id;
      onRefresh(false);
    });
    catsRow.appendChild(b);
  }
  container.appendChild(catsRow);

  const currentCat = menu.find((c) => c.id === uiState.cat) || menu[0];
  const listEl = document.createElement('div');
  listEl.className = 'cust-menu-list audit-block';

  for (const it of currentCat.items || []) {
    const weighed = it.item_type === 'weighed';
    const stockQty = it.stock_quantity;
    const soldOut =
      Boolean(it.is_sold_out) ||
      (stockQty !== null && stockQty !== undefined && Number(stockQty) <= 0);
    const caption = stockCaption(it);

    const card = document.createElement('div');
    card.className = 'cust-item-card';

    const left = document.createElement('div');
    left.className = 'cust-item-left';
    left.appendChild(createThumbnail(it));

    const info = document.createElement('div');
    info.className = 'cust-item-info';

    const nameEl = document.createElement('div');
    nameEl.className = 'cust-item-name';
    nameEl.textContent = it.name;
    info.appendChild(nameEl);

    const priceEl = document.createElement('div');
    priceEl.className = 'cust-item-price';
    priceEl.textContent = weighed
      ? `${money(it.price)} บาท/กก. · ชั่งกิโล สั่งกับพนักงาน`
      : `${money(it.price)} บาท`;
    info.appendChild(priceEl);

    const stockEl = document.createElement('div');
    stockEl.className = caption.cls;
    stockEl.textContent = caption.text;
    info.appendChild(stockEl);

    left.appendChild(info);
    card.appendChild(left);

    if (soldOut) {
      card.appendChild(createStatusBadge('สินค้าหมด', '#e03131'));
    } else if (weighed) {
      const wBadge = document.createElement('span');
      wBadge.className = 'cust-badge-outline-info';
      wBadge.textContent = 'ชั่งกิโล';
      card.appendChild(wBadge);
    } else {
      const curQ = Number(cart[String(it.id)] || cart[it.id] || 0);
      const maxQ =
        it.max_orderable_qty !== undefined ? Number(it.max_orderable_qty) : 99;

      const ctrls = document.createElement('div');
      ctrls.className = 'cust-qty-controls';

      const minusBtn = document.createElement('button');
      minusBtn.type = 'button';
      minusBtn.className = 'cust-qty-btn cust-qty-btn-minus';
      minusBtn.textContent = '−';
      minusBtn.setAttribute('aria-label', `ลด ${it.name}`);
      minusBtn.addEventListener('click', () => handleCartChange(it.id, -1, onRefresh));

      const qtyLbl = document.createElement('span');
      qtyLbl.className = 'cust-qty-num';
      qtyLbl.textContent = String(curQ);

      const plusBtn = document.createElement('button');
      plusBtn.type = 'button';
      plusBtn.className = 'cust-qty-btn cust-qty-btn-plus';
      plusBtn.textContent = '+';
      plusBtn.setAttribute('aria-label', `เพิ่ม ${it.name}`);
      if (curQ >= maxQ) {
        plusBtn.disabled = true;
      }
      plusBtn.addEventListener('click', () => handleCartChange(it.id, 1, onRefresh));

      ctrls.appendChild(minusBtn);
      ctrls.appendChild(qtyLbl);
      ctrls.appendChild(plusBtn);
      card.appendChild(ctrls);
    }

    listEl.appendChild(card);
  }
  container.appendChild(listEl);

  const spacer = document.createElement('div');
  spacer.className = 'cust-bottom-spacer';
  container.appendChild(spacer);

  // แถบล่างตะกร้า
  const barWrap = document.createElement('div');
  barWrap.className = 'cust-cart-bar-wrap';

  const bar = document.createElement('div');
  bar.className = 'cust-cart-bar';

  const count = Number(statePayload.cart_count || 0);
  const total = Number(statePayload.cart_total || 0);

  const summary = document.createElement('div');
  summary.className = 'cust-cart-summary';
  summary.textContent = count > 0 ? `ตะกร้า ${count} รายการ · ${baht(total)}` : 'ตะกร้ายังว่าง';

  const orderBtn = document.createElement('button');
  orderBtn.type = 'button';
  orderBtn.className = 'btn btn-primary cust-btn-touch';
  orderBtn.textContent = 'ตรวจสอบ/สั่งอาหาร';
  orderBtn.disabled = count <= 0;
  orderBtn.addEventListener('click', () =>
    openOrderConfirmDialog(statePayload, uiState, onRefresh)
  );

  bar.appendChild(summary);
  bar.appendChild(orderBtn);
  barWrap.appendChild(bar);
  container.appendChild(barWrap);
}

async function handleCartChange(itemId, delta, onRefresh) {
  try {
    const newState = await apiPost('/api/customer/cart/change', {
      item_id: itemId,
      delta,
    });
    onRefresh(true, newState);
  } catch (err) {
    showToast(err.message || 'ไม่สามารถแก้ไขตะกร้าได้', 'warning');
    onRefresh(true, err.data || null);
  }
}

async function openOrderConfirmDialog(statePayload, uiState, onRefresh) {
  const lines = statePayload.cart_lines || [];
  if (lines.length === 0) {
    showToast('ยังไม่ได้เลือกรายการ', 'warning');
    return;
  }
  const total = Number(statePayload.cart_total || 0);

  const dlg = new BaseDialog('ยืนยันการสั่งอาหาร', { width: 420 });
  for (const ln of lines) {
    dlg.body.appendChild(
      createSummaryRow(`${ln.name}  x${ln.quantity}`, money(ln.line_total))
    );
  }
  dlg.body.appendChild(createSeparator());
  dlg.body.appendChild(
    createSummaryRow('รวม', baht(total), { bold: true, color: 'primary' })
  );

  const noteGroup = document.createElement('div');
  noteGroup.className = 'field-group';
  const noteLbl = document.createElement('label');
  noteLbl.className = 'field-label';
  noteLbl.textContent = 'หมายเหตุถึงครัว (ถ้ามี)';
  const noteInput = document.createElement('input');
  noteInput.type = 'text';
  noteInput.className = 'field-input';
  noteInput.placeholder = 'หมายเหตุถึงครัว (ถ้ามี)';
  noteGroup.appendChild(noteLbl);
  noteGroup.appendChild(noteInput);
  dlg.body.appendChild(noteGroup);

  let submitting = false;
  dlg.addButtons({
    confirmText: 'ยืนยันสั่ง',
    cancelText: 'กลับไปแก้',
    variant: 'primary',
    onConfirm: async () => {
      if (submitting) return;
      submitting = true;
      dlg.confirmBtn.disabled = true;
      try {
        const res = await apiPost('/api/customer/order', {
          note: noteInput.value.trim() || null,
        });
        dlg.close(true);
        uiState.tab = 'mine';
        showToast('ส่งออเดอร์ให้ครัวแล้ว', 'success');
        onRefresh(true, res);
      } catch (err) {
        dlg.close(false);
        showToast(err.message || 'ไม่สามารถสั่งอาหารได้', 'error');
        onRefresh(true);
      } finally {
        submitting = false;
      }
    },
  });

  await dlg.show();
}

function renderMineTab(container, snap, statePayload = {}) {
  const weigh = snap.weigh_entries || [];
  const orders = snap.orders || [];

  if (weigh.length === 0 && orders.length === 0) {
    container.appendChild(
      createMessageCard({
        icon: 'receipt',
        title: 'ยังไม่มีรายการ',
        text: 'เมื่อสั่งอาหารหรือพนักงานชั่งเนื้อให้ จะแสดงที่นี่',
        color: 'grey',
      })
    );
    return;
  }

  if (weigh.length > 0) {
    const wCard = document.createElement('section');
    wCard.className = 'cust-section-card audit-block';
    const wTitle = document.createElement('div');
    wTitle.className = 'cust-section-title';
    wTitle.textContent = 'หมูกระทะชั่งกิโล';
    wCard.appendChild(wTitle);

    for (const w of weigh) {
      wCard.appendChild(
        createSummaryRow(
          `${w.name_snapshot}  ${weight_text(w.weight_grams)}`,
          money(w.amount)
        )
      );
    }
    container.appendChild(wCard);
  }

  for (const o of orders) {
    const oCard = document.createElement('section');
    oCard.className = 'cust-section-card audit-block';

    const headRow = document.createElement('div');
    headRow.style.display = 'flex';
    headRow.style.alignItems = 'center';
    headRow.style.justifyContent = 'space-between';
    headRow.style.gap = 'var(--space-2)';

    const oTitle = document.createElement('div');
    oTitle.className = 'cust-section-title';
    oTitle.textContent = `ออเดอร์ #${o.id} · ${fmt_time(o.created_at, '')}`;

    const badge = createStatusBadge(
      ORDER_STATUS_CUSTOMER_TH[o.status] || o.status,
      ORDER_STATUS_CUSTOMER_COLORS[o.status] || '#868e96'
    );
    headRow.appendChild(oTitle);
    headRow.appendChild(badge);
    oCard.appendChild(headRow);

    for (const it of o.items || []) {
      oCard.appendChild(
        createSummaryRow(
          `${it.name_snapshot}  x${it.quantity}`,
          money(it.line_total)
        )
      );
    }

    if (o.note) {
      const noteEl = document.createElement('div');
      noteEl.className = 'cust-note-hint';
      noteEl.textContent = `หมายเหตุ: ${o.note}`;
      oCard.appendChild(noteEl);
    }
    container.appendChild(oCard);
  }

  const totalCard = document.createElement('section');
  totalCard.className = 'cust-section-card audit-block';
  const memberDiscount = Number(snap.member_discount || 0);
  totalCard.appendChild(
    createSummaryRow('ยอดรวมปัจจุบัน', baht(snap.subtotal), {
      bold: !memberDiscount,
      color: memberDiscount ? null : 'primary',
    })
  );
  if (memberDiscount > 0) {
    totalCard.appendChild(
      createSummaryRow(
        `ส่วนลดสมาชิก (${snap.member_promo_name || statePayload.applied_promo_code || ''})`,
        `-${baht(memberDiscount)}`,
        { color: 'positive' }
      )
    );
    totalCard.appendChild(
      createSummaryRow(
        'ยอดรวมหลังหักส่วนลดสมาชิก',
        baht(Math.max(0, Number(snap.subtotal || 0) - memberDiscount)),
        { bold: true, color: 'primary' }
      )
    );
  }
  const hint = document.createElement('div');
  hint.className = 'cust-note-hint';
  hint.textContent =
    'ยังไม่รวมส่วนลด/ค่าบริการ/ภาษีมูลค่าเพิ่ม — เมื่อต้องการเช็คบิล กรุณาเรียกพนักงาน';
  totalCard.appendChild(hint);
  container.appendChild(totalCard);
}
