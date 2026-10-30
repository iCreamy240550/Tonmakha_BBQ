/**
 * frontend/shared/js/api.js — ตัวช่วยเรียก API หลังบ้าน (จัดการ JSON, FormData, 401/403/400/500 และข้อความไทย)
 */

export class ApiError extends Error {
  constructor(message, status = 500, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

let onUnauthorizedHandler = null;
let onForbiddenHandler = null;

export function setAuthHandlers({ onUnauthorized, onForbidden } = {}) {
  if (onUnauthorized) onUnauthorizedHandler = onUnauthorized;
  if (onForbidden) onForbiddenHandler = onForbidden;
}

export async function apiRequest(url, options = {}) {
  const opts = {
    method: options.method || 'GET',
    credentials: 'same-origin',
    headers: { ...(options.headers || {}) },
  };

  if (options.body !== undefined && options.body !== null) {
    if (options.body instanceof FormData) {
      opts.body = options.body;
    } else if (typeof options.body === 'string') {
      opts.headers['Content-Type'] = opts.headers['Content-Type'] || 'application/json';
      opts.body = options.body;
    } else {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(options.body);
    }
  } else if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(opts.method.toUpperCase())) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify({});
  }

  let response;
  try {
    response = await fetch(url, opts);
  } catch (err) {
    throw new ApiError('ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้ กรุณาตรวจสอบการเชื่อมต่อ', 0, null);
  }

  const contentType = response.headers.get('content-type') || '';
  let payload = null;
  if (contentType.includes('application/json')) {
    try {
      payload = await response.json();
    } catch (_e) {
      payload = null;
    }
  } else {
    try {
      const text = await response.text();
      payload = { detail: text };
    } catch (_e) {
      payload = null;
    }
  }

  if (!response.ok) {
    const detail =
      (payload && (payload.detail || payload.message || payload.error)) ||
      `เกิดข้อผิดพลาด (${response.status})`;
    if (response.status === 401 && !options.ignoreAuth && onUnauthorizedHandler) {
      onUnauthorizedHandler(detail);
    } else if (response.status === 403 && !options.ignoreAuth && onForbiddenHandler) {
      onForbiddenHandler(detail);
    }
    throw new ApiError(String(detail), response.status, payload);
  }

  return payload;
}

export function apiGet(url, params = null, options = {}) {
  let fullUrl = url;
  if (params && typeof params === 'object') {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') {
        qs.append(k, String(v));
      }
    }
    const qStr = qs.toString();
    if (qStr) {
      fullUrl += (url.includes('?') ? '&' : '?') + qStr;
    }
  }
  return apiRequest(fullUrl, { ...options, method: 'GET' });
}

export function apiPost(url, body = {}, options = {}) {
  return apiRequest(url, { ...options, method: 'POST', body });
}

export function apiPut(url, body = {}, options = {}) {
  return apiRequest(url, { ...options, method: 'PUT', body });
}

export function apiPatch(url, body = {}, options = {}) {
  return apiRequest(url, { ...options, method: 'PATCH', body });
}

export function apiDelete(url, body = {}, options = {}) {
  return apiRequest(url, { ...options, method: 'DELETE', body });
}

export function apiUpload(url, formData, options = {}) {
  return apiRequest(url, { ...options, method: 'POST', body: formData });
}
