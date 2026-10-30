/**
 * frontend/staff/js/router.js — รายการเมนูและตัวนำทาง hash router (#/key?params)
 * คัดลอกจาก NAV_ITEMS และ App.navigate ใน ui/app.py
 */

export const STAFF_GROUP = 'หน้าร้าน';
export const OWNER_GROUP = 'เจ้าของร้าน';

export const NAV_ITEMS = [
  { key: 'tables', label: 'โต๊ะ', role: 'staff', group: STAFF_GROUP },
  { key: 'takeaway', label: 'สั่งกลับบ้าน', role: 'staff', group: STAFF_GROUP },
  { key: 'weigh', label: 'ชั่งน้ำหนัก', role: 'staff', group: STAFF_GROUP },
  { key: 'orders', label: 'ออเดอร์', role: 'staff', group: STAFF_GROUP },
  { key: 'checkout', label: 'เช็คเอาท์', role: 'staff', group: STAFF_GROUP },
  { key: 'dashboard', label: 'แดชบอร์ด', role: 'owner', group: OWNER_GROUP },
  { key: 'menu', label: 'เมนูและราคา', role: 'owner', group: OWNER_GROUP },
  { key: 'stock', label: 'สต๊อก', role: 'owner', group: OWNER_GROUP },
  { key: 'promo', label: 'โปรโมชั่น', role: 'owner', group: OWNER_GROUP },
  { key: 'tables_manage', label: 'จัดการโต๊ะ/QR', role: 'owner', group: OWNER_GROUP },
  { key: 'users', label: 'ผู้ใช้', role: 'owner', group: OWNER_GROUP },
  { key: 'settings', label: 'ตั้งค่า', role: 'owner', group: OWNER_GROUP },
  { key: 'log', label: 'ประวัติการใช้งาน', role: 'owner', group: OWNER_GROUP },
  { key: 'backup', label: 'สำรองข้อมูล', role: 'owner', group: OWNER_GROUP },
];

export const NAV_BY_KEY = Object.fromEntries(NAV_ITEMS.map((item) => [item.key, item]));

export const DEFAULT_PAGE = {
  staff: 'tables',
  owner: 'dashboard',
};

export function hasPermission(user, requiredRole) {
  if (!user || !user.active) return false;
  if (user.role === 'owner') return true;
  return user.role === requiredRole;
}

export function parseHashRoute(hashStr = window.location.hash) {
  const raw = (hashStr || '').replace(/^#\/?/, '');
  if (!raw) {
    return { key: '', params: {} };
  }
  const [pathPart, queryPart] = raw.split('?', 2);
  let key = (pathPart || '').trim().replace(/\/+$/, '');
  if (key === 'report') {
    key = 'dashboard';
  }
  const params = {};
  if (queryPart) {
    const usp = new URLSearchParams(queryPart);
    for (const [k, v] of usp.entries()) {
      if (k === 'session_id' && /^\d+$/.test(v)) {
        params[k] = Number(v);
      } else {
        params[k] = v;
      }
    }
  }
  return { key, params };
}

export function buildHashUrl(key, params = {}) {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '') {
      usp.append(k, String(v));
    }
  }
  const qs = usp.toString();
  return `#/${key}${qs ? `?${qs}` : ''}`;
}
