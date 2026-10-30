/**
 * frontend/staff/js/app.js — แอปหลักของพนักงานและเจ้าของร้าน (App shell, Sidebar, Topbar, Router)
 * คัดลอกจาก ui/app.py
 */

import { apiGet, apiPost, setAuthHandlers } from '../../shared/js/api.js';
import { confirmDialog } from '../../shared/js/dialogs.js';
import { showToast } from '../../shared/js/toast.js';
import {
  AlertCenter,
  isSoundEnabled,
  setSoundEnabled,
  unlockAudioContext,
} from './alert-center.js';
import {
  DEFAULT_PAGE,
  NAV_BY_KEY,
  NAV_ITEMS,
  buildHashUrl,
  hasPermission,
  parseHashRoute,
} from './router.js';
import { ShopControl } from './shop-control.js';

import { renderLoginPage } from './pages/login.js';
import { TablesPage } from './pages/tables.js';
import { TakeawayPage } from './pages/takeaway.js';
import { WeighPage } from './pages/weigh.js';
import { OrdersPage } from './pages/orders.js';
import { CheckoutPage } from './pages/checkout.js';
import { DashboardPage } from './pages/dashboard.js';
import { MenuPage } from './pages/menu.js';
import { StockPage } from './pages/stock.js';
import { PromoPage } from './pages/promo.js';
import { TablesManagePage } from './pages/tables_manage.js';
import { UsersPage } from './pages/users.js';
import { SettingsPage } from './pages/settings.js';
import { LogPage } from './pages/log.js';
import { BackupPage } from './pages/backup.js';

const PAGE_CLASSES = {
  tables: TablesPage,
  takeaway: TakeawayPage,
  weigh: WeighPage,
  orders: OrdersPage,
  checkout: CheckoutPage,
  dashboard: DashboardPage,
  menu: MenuPage,
  stock: StockPage,
  promo: PromoPage,
  tables_manage: TablesManagePage,
  users: UsersPage,
  settings: SettingsPage,
  log: LogPage,
  backup: BackupPage,
};

class StaffApp {
  constructor(rootEl) {
    this.rootEl = rootEl;
    this.user = null;
    this.currentKey = null;
    this.currentPage = null;
    this.navButtons = {};
    this.shopControl = null;
    this.alertCenter = null;
    this.titleLabel = null;
    this.contentEl = null;

    setAuthHandlers({
      onUnauthorized: () => {
        if (this.user) {
          this.showLogin();
        }
      },
      onForbidden: (detail) => {
        showToast(detail || 'คุณไม่มีสิทธิ์ดำเนินการนี้', 'error');
      },
    });

    window.addEventListener('hashchange', () => this._onHashChange());
    document.addEventListener('click', () => unlockAudioContext(), { once: true });
  }

  async init() {
    try {
      const me = await apiGet('/api/staff/me', null, { ignoreAuth: true });
      if (me && me.authenticated && me.user) {
        this.onLogin(me.user, false);
        return;
      }
    } catch (_err) {
      // not logged in
    }
    this.showLogin();
  }

  showLogin() {
    this._teardownMain();
    this.user = null;
    renderLoginPage(this.rootEl, (user) => {
      unlockAudioContext();
      this.onLogin(user, true);
    });
  }

  onLogin(user, replaceRoute = false) {
    this.user = user;
    this._buildMain();

    const parsed = parseHashRoute(window.location.hash);
    const defaultKey = DEFAULT_PAGE[user.role] || 'tables';
    if (replaceRoute || !parsed.key || parsed.key === 'login') {
      this.navigate(defaultKey);
    } else {
      this._onHashChange();
    }
  }

  async logout() {
    const ok = await confirmDialog('ออกจากระบบใช่หรือไม่?', {
      title: 'ออกจากระบบ',
      confirmText: 'ออกจากระบบ',
    });
    if (!ok) return;
    try {
      await apiPost('/api/staff/logout', {});
    } catch (_e) {
      // ignore
    }
    window.history.replaceState(null, '', '#/login');
    this.showLogin();
  }

  _teardownMain() {
    if (this.currentPage && typeof this.currentPage.deactivate === 'function') {
      this.currentPage.deactivate();
    }
    this.currentPage = null;
    this.currentKey = null;
    if (this.shopControl) {
      this.shopControl.stop();
      this.shopControl = null;
    }
    if (this.alertCenter) {
      this.alertCenter.stop();
      this.alertCenter = null;
    }
    this.navButtons = {};
    this.rootEl.textContent = '';
  }

  _buildMain() {
    this._teardownMain();

    const shell = document.createElement('div');
    shell.className = 'app-shell';

    // 1) Sidebar 230px
    const sidebar = document.createElement('aside');
    sidebar.className = 'app-sidebar';

    const brand = document.createElement('div');
    brand.className = 'sidebar-brand';
    const logo = document.createElement('img');
    logo.src = '/logo.png';
    logo.alt = 'ต้นมะค่า';
    logo.className = 'sidebar-logo';
    logo.addEventListener('error', () => {
      logo.style.display = 'none';
    });
    const brandTitle = document.createElement('div');
    brandTitle.className = 'sidebar-title';
    brandTitle.textContent = 'ต้นมะค่า';
    brand.appendChild(logo);
    brand.appendChild(brandTitle);
    sidebar.appendChild(brand);

    const nav = document.createElement('nav');
    nav.className = 'sidebar-nav';
    let lastGroup = null;
    for (const item of NAV_ITEMS) {
      if (!hasPermission(this.user, item.role)) continue;
      if (item.group !== lastGroup) {
        const grp = document.createElement('div');
        grp.className = 'sidebar-group-label';
        grp.textContent = item.group;
        nav.appendChild(grp);
        lastGroup = item.group;
      }
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'sidebar-nav-btn';
      btn.dataset.navKey = item.key;
      btn.textContent = item.label;
      btn.addEventListener('click', () => this.navigate(item.key));
      nav.appendChild(btn);
      this.navButtons[item.key] = btn;
    }
    sidebar.appendChild(nav);

    const foot = document.createElement('div');
    foot.className = 'sidebar-footer';
    const uName = document.createElement('div');
    uName.className = 'sidebar-user-name';
    uName.textContent = this.user.display_name;
    const uRole = document.createElement('div');
    uRole.className = 'sidebar-user-role';
    uRole.textContent = this.user.role === 'owner' ? 'เจ้าของร้าน' : 'พนักงาน';
    const logoutBtn = document.createElement('button');
    logoutBtn.type = 'button';
    logoutBtn.className = 'sidebar-logout-btn';
    logoutBtn.textContent = 'ออกจากระบบ';
    logoutBtn.addEventListener('click', () => this.logout());
    foot.appendChild(uName);
    foot.appendChild(uRole);
    foot.appendChild(logoutBtn);
    sidebar.appendChild(foot);

    // 2) Right area
    const main = document.createElement('div');
    main.className = 'app-main';

    const topbar = document.createElement('header');
    topbar.className = 'app-topbar';

    this.titleLabel = document.createElement('div');
    this.titleLabel.className = 'topbar-title';
    topbar.appendChild(this.titleLabel);

    const topRight = document.createElement('div');
    topRight.className = 'topbar-right';

    // ปุ่มเปิด/ปิดเสียงแจ้งเตือน
    const soundBtn = document.createElement('button');
    soundBtn.type = 'button';
    soundBtn.className = 'btn btn-sm btn-ghost';
    const syncSoundBtn = () => {
      const on = isSoundEnabled();
      soundBtn.textContent = on ? '🔊 เสียงเตือน: เปิด' : '🔇 เสียงเตือน: ปิด';
    };
    syncSoundBtn();
    soundBtn.addEventListener('click', () => {
      setSoundEnabled(!isSoundEnabled());
      syncSoundBtn();
    });
    topRight.appendChild(soundBtn);

    this.shopControl = new ShopControl(topRight, {
      onStatusChange: () => {
        if (this.currentPage && typeof this.currentPage.reload === 'function') {
          this.currentPage.reload();
        }
      },
    });
    topbar.appendChild(topRight);
    main.appendChild(topbar);

    const alertHolder = document.createElement('div');
    main.appendChild(alertHolder);
    this.alertCenter = new AlertCenter(alertHolder, {
      onChange: () => {
        if (this.currentPage && typeof this.currentPage.reload === 'function') {
          this.currentPage.reload();
        }
      },
    });

    this.contentEl = document.createElement('main');
    this.contentEl.className = 'app-content audit-align-root';
    main.appendChild(this.contentEl);

    shell.appendChild(sidebar);
    shell.appendChild(main);
    this.rootEl.appendChild(shell);

    this.shopControl.start();
    this.alertCenter.start();
  }

  navigate(key, params = {}) {
    if (key === 'report') key = 'dashboard';
    if (key === 'kitchen') return;
    const targetHash = buildHashUrl(key, params);
    if (window.location.hash === targetHash) {
      this._openRoute(key, params);
    } else {
      window.location.hash = targetHash;
    }
  }

  _onHashChange() {
    if (!this.user) {
      return;
    }
    const { key, params } = parseHashRoute(window.location.hash);
    if (!key || key === 'login') {
      const defKey = DEFAULT_PAGE[this.user.role] || 'tables';
      this.navigate(defKey);
      return;
    }
    if (key === 'kitchen') {
      return;
    }
    this._openRoute(key, params);
  }

  _openRoute(key, params = {}) {
    const item = NAV_BY_KEY[key];
    if (!item || !this.user) return;

    if (!hasPermission(this.user, item.role)) {
      showToast('หน้านี้สำหรับเจ้าของร้านเท่านั้น', 'error');
      this.navigate('tables');
      return;
    }

    if (this.currentPage && typeof this.currentPage.deactivate === 'function') {
      this.currentPage.deactivate();
    }

    this.currentKey = key;
    this.titleLabel.textContent = item.label;
    for (const [k, btn] of Object.entries(this.navButtons)) {
      if (k === key) {
        btn.classList.add('is-active');
      } else {
        btn.classList.remove('is-active');
      }
    }

    this.contentEl.textContent = '';
    const PageCls = PAGE_CLASSES[key];
    if (!PageCls) {
      return;
    }
    this.currentPage = new PageCls(this.contentEl, this);
    this.currentPage.activate(params);
  }

  toast(text, kind = 'info') {
    showToast(text, kind);
  }
}

const root = document.getElementById('staff-root');
const app = new StaffApp(root);
app.init();
