/**
 * frontend/customer/js/app.js — จุดเริ่มเว็บมือถือลูกค้า (/, /t/{table_no}, /s)
 * โพลทุก 3 วินาที วาดใหม่เฉพาะเมื่อ signature หรือตะกร้าเปลี่ยน หยุดโพลเมื่อจบรอบ
 */

import { apiGet } from '../../shared/js/api.js';
import { renderBill } from './bill.js';
import { renderCancelled, renderNoSession, renderPaid } from './closed.js';
import { APP_NAME_SHORT, createCustomerHeader } from './components.js';
import { runEnterPage } from './enter.js';
import { showUnreadNotices } from './notice.js';
import { renderOrderView } from './order.js';
import { renderWaiting } from './waiting.js';

const POLL_MS = 3000;
const TERMINAL_VIEWS = new Set(['closed', 'cancelled']);

const rootEl = document.getElementById('customer-root');

const uiState = {
  tab: 'menu',
  cat: null,
  authPage: null,
  authSuccessMessage: '',
  signupStep: 1,
  signupDraft: {
    name: '',
    email: '',
    maskedEmail: '',
    phone: '',
    password: '',
    passwordConfirm: '',
    cooldownUntil: 0,
  },
  resetStep: 1,
  resetDraft: {
    email: '',
    maskedEmail: '',
    cooldownUntil: 0,
  },
  countdownTimer: null,
  lastSig: null,
  lastPayload: null,
  pollTimer: null,
};

function computeUiSignature(payload) {
  if (!payload || !payload.has_session || !payload.snapshot) {
    return 'no_session';
  }
  const cartStr = JSON.stringify(payload.cart || {});
  return `${payload.signature || ''}::${cartStr}`;
}

function renderSessionPage(payload) {
  if (uiState.countdownTimer) {
    clearInterval(uiState.countdownTimer);
    uiState.countdownTimer = null;
  }
  rootEl.textContent = '';

  if (!payload || !payload.has_session || !payload.snapshot) {
    rootEl.appendChild(createCustomerHeader(APP_NAME_SHORT));
    renderNoSession(rootEl);
    return;
  }

  const snap = payload.snapshot;
  const tableName = (snap.table && snap.table.name) || APP_NAME_SHORT;
  const status = snap.session ? snap.session.status : null;
  rootEl.appendChild(createCustomerHeader(tableName, status));

  const view = snap.view;
  if (view === 'waiting') {
    renderWaiting(rootEl, () => refreshCustomerState(true));
  } else if (view === 'order') {
    renderOrderView(rootEl, payload, uiState, (fetchFromServer, directPayload = null) => {
      if (directPayload) {
        uiState.lastPayload = directPayload;
        uiState.lastSig = computeUiSignature(directPayload);
        renderSessionPage(directPayload);
      } else if (fetchFromServer) {
        refreshCustomerState(true);
      } else {
        renderSessionPage(uiState.lastPayload);
      }
    });
  } else if (view === 'bill') {
    renderBill(rootEl, snap);
  } else if (view === 'closed') {
    renderPaid(rootEl, snap);
  } else {
    renderCancelled(rootEl, snap);
  }
}

async function refreshCustomerState(force = false) {
  // ถ้ามีกล่อง modal เปิดอยู่ ไม่วาดทับระหว่างโพลปกติเพื่อกันค่าที่ลูกค้ากำลังพิมพ์หาย
  if (!force && (document.querySelector('.modal-backdrop') || uiState.authPage)) {
    return;
  }

  let payload;
  try {
    payload = await apiGet('/api/customer/state');
  } catch (_err) {
    return;
  }

  if (payload && payload.snapshot) {
    await showUnreadNotices(payload.snapshot);
  }

  const nextSig = computeUiSignature(payload);
  if (force || nextSig !== uiState.lastSig) {
    uiState.lastPayload = payload;
    uiState.lastSig = nextSig;
    renderSessionPage(payload);
  }

  const view = payload && payload.snapshot ? payload.snapshot.view : null;
  if (!payload || !payload.has_session || TERMINAL_VIEWS.has(view)) {
    stopPolling();
  }
}

function startPolling() {
  stopPolling();
  uiState.pollTimer = setInterval(() => {
    if (!document.hidden) {
      refreshCustomerState(false);
    }
  }, POLL_MS);
}

function stopPolling() {
  if (uiState.pollTimer) {
    clearInterval(uiState.pollTimer);
    uiState.pollTimer = null;
  }
}

async function bootstrap() {
  const path = window.location.pathname || '/';
  const matchEnter = /^\/t\/(\d+)\/?$/.exec(path);

  if (matchEnter) {
    const tableNo = Number(matchEnter[1]);
    const params = new URLSearchParams(window.location.search);
    const k = params.get('k') || '';
    await runEnterPage(rootEl, tableNo, k);
    return;
  }

  if (path === '/s' || path.startsWith('/s/')) {
    await refreshCustomerState(true);
    const view =
      uiState.lastPayload && uiState.lastPayload.snapshot
        ? uiState.lastPayload.snapshot.view
        : null;
    if (uiState.lastPayload && uiState.lastPayload.has_session && !TERMINAL_VIEWS.has(view)) {
      startPolling();
    }
    return;
  }

  // GET / — หน้าบอกให้สแกน QR
  rootEl.textContent = '';
  rootEl.appendChild(createCustomerHeader(APP_NAME_SHORT));
  renderNoSession(rootEl);
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden && (window.location.pathname === '/s' || window.location.pathname.startsWith('/s/'))) {
    refreshCustomerState(false);
  }
});

bootstrap();
