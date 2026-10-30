/**
 * frontend/shared/js/format.js — ฟังก์ชันจัดรูปแบบข้อความ ตัวเลข น้ำหนัก เวลา และวันที่ พ.ศ.
 * คัดลอกพฤติกรรมตรงตาม ui/theme.py, web/components.py, และ ui/owner/_common.py ทุกประการ
 */

export const GRAMS_PER_KG = 1000;
export const KHEED_PER_KG = 10;

export const THAI_MONTHS = [
  'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
  'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
];

export const THAI_MONTHS_SHORT = [
  'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
  'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.',
];

export const THAI_WEEKDAYS = ['จ.', 'อ.', 'พ.', 'พฤ.', 'ศ.', 'ส.', 'อา.'];

/**
 * ป้องกัน XSS สำหรับกรณีต้องสร้างสตริง HTML (แต่แนะนำใช้ textContent เป็นหลัก)
 */
export function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * จัดรูปแบบทศนิยมแบบ Python `:g` (ตัด 0 ท้ายทศนิยม)
 */
function formatG(num) {
  const n = Number(num || 0);
  if (!Number.isFinite(n)) return '0';
  const rounded = Number(n.toPrecision(6));
  return String(rounded);
}

/**
 * 1234.5 -> '1,234.50' (เสมอ 2 ตำแหน่ง)
 */
export function money(value) {
  const n = Number(value || 0);
  const safe = Number.isFinite(n) ? n : 0;
  const fixed = safe.toFixed(2);
  const [intPart, decPart] = fixed.split('.');
  const sign = intPart.startsWith('-') ? '-' : '';
  const digits = sign ? intPart.slice(1) : intPart;
  const withCommas = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${sign}${withCommas}.${decPart}`;
}

/**
 * 1234.5 -> '1,234.50 บาท'
 */
export function baht(value) {
  return `${money(value)} บาท`;
}

/**
 * น้ำหนักกรัม -> ข้อความ เช่น 1500 -> '1.5 กก. (15 ขีด)', 300 -> '3 ขีด'
 */
export function weight_text(grams) {
  const g = Number(grams || 0);
  const safeG = Number.isFinite(g) ? g : 0;
  const kheed = safeG / (GRAMS_PER_KG / KHEED_PER_KG);
  const kheedTxt = formatG(kheed);
  if (safeG >= GRAMS_PER_KG) {
    const kgTxt = formatG(safeG / GRAMS_PER_KG);
    return `${kgTxt} กก. (${kheedTxt} ขีด)`;
  }
  return `${kheedTxt} ขีด`;
}

/**
 * แปลงข้อความ 'YYYY-MM-DD HH:MM:SS' -> Date หรือ null
 */
export function parseDbDateTime(text) {
  if (!text || typeof text !== 'string') return null;
  const s = text.trim();
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(s);
  if (!m) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  const hour = Number(m[4]);
  const min = Number(m[5]);
  const sec = Number(m[6] || 0);
  const dt = new Date(year, month - 1, day, hour, min, sec);
  if (
    dt.getFullYear() !== year ||
    dt.getMonth() !== month - 1 ||
    dt.getDate() !== day
  ) {
    return null;
  }
  return { year, month, day, hour, min, sec, dateObj: dt };
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

/**
 * '2026-10-10 18:05:30' -> '18:05' (หรือ '-' ตาม ui/theme.py; ถ้าระบุ emptyFallback='' ใช้กับฝั่งลูกค้าได้)
 */
export function fmt_time(text, emptyFallback = '-') {
  const p = parseDbDateTime(text);
  if (!p) return emptyFallback;
  return `${pad2(p.hour)}:${pad2(p.min)}`;
}

/**
 * '2026-10-10 18:05:30' -> '10/10/2026 18:05'
 */
export function fmt_datetime(text, emptyFallback = '-') {
  const p = parseDbDateTime(text);
  if (!p) return emptyFallback;
  return `${pad2(p.day)}/${pad2(p.month)}/${p.year} ${pad2(p.hour)}:${pad2(p.min)}`;
}

/**
 * จำนวนนาทีเต็มตั้งแต่เวลา text (0 ถ้าแปลงไม่ได้)
 */
export function minutes_since(text, now = null) {
  const p = parseDbDateTime(text);
  if (!p) return 0;
  const ref = now instanceof Date ? now : new Date();
  const diffSec = (ref.getTime() - p.dateObj.getTime()) / 1000;
  return Math.max(0, Math.floor(diffSec / 60));
}

/**
 * นานเท่าไรแล้ว เช่น '5 นาที', '1 ชม. 20 นาที'
 */
export function duration_text(text, now = null) {
  const m = minutes_since(text, now);
  if (m < 60) {
    return `${m} นาที`;
  }
  return `${Math.floor(m / 60)} ชม. ${m % 60} นาที`;
}

/**
 * แปลงปี ค.ศ. -> พ.ศ. (ป้องกันการบวก 543 ซ้ำหากค่าเป็น พ.ศ. อยู่แล้ว)
 */
export function ce_to_be_year(ceYear) {
  const y = parseInt(ceYear, 10);
  return y >= 2400 ? y : y + 543;
}

/**
 * แปลงปี พ.ศ. -> ค.ศ. สำหรับค้นหาในฐานข้อมูล (หากเป็น ค.ศ. อยู่แล้วจะไม่ลบซ้ำ)
 */
export function be_to_ce_year(beOrCeYear) {
  const y = parseInt(beOrCeYear, 10);
  return y >= 2400 ? y - 543 : y;
}

/**
 * แปลง 'YYYY-MM-DD' (ค.ศ.) เป็นข้อความวันที่ภาษาไทย พ.ศ. เช่น '24/10/2569 (24 ตุลาคม 2569)'
 */
export function format_thai_date(isoDate, shortMonth = false) {
  if (!isoDate) return 'เลือกวันที่...';
  let year;
  let month;
  let day;
  if (isoDate instanceof Date) {
    year = isoDate.getFullYear();
    month = isoDate.getMonth() + 1;
    day = isoDate.getDate();
  } else {
    const s = String(isoDate).trim().slice(0, 10);
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return String(isoDate);
    year = Number(m[1]);
    month = Number(m[2]);
    day = Number(m[3]);
    const check = new Date(year, month - 1, day);
    if (
      check.getFullYear() !== year ||
      check.getMonth() !== month - 1 ||
      check.getDate() !== day
    ) {
      return String(isoDate);
    }
  }
  const beY = ce_to_be_year(year);
  const mName = shortMonth ? THAI_MONTHS_SHORT[month - 1] : THAI_MONTHS[month - 1];
  return `${pad2(day)}/${pad2(month)}/${beY} (${day} ${mName} ${beY})`;
}

/**
 * รองรับทั้ง 'YYYY-MM-DD' (ค.ศ. หรือ พ.ศ.) และ 'DD/MM/YYYY' (ค.ศ. หรือ พ.ศ.) -> คืนค่า 'YYYY-MM-DD' (ค.ศ.) เสมอ
 */
export function parse_date(text, label = 'วันที่', allowEmpty = true) {
  let t = String(text || '').trim();
  if (!t) {
    if (allowEmpty) return '';
    throw new Error(`กรุณาเลือก${label}`);
  }
  if (t.includes('(')) {
    t = t.split('(', 1)[0].trim();
  }

  const patterns = [
    { sep: '-', order: 'ymd' },
    { sep: '/', order: 'dmy' },
    { sep: '/', order: 'ymd' },
  ];

  for (const { sep, order } of patterns) {
    if (t.includes(sep)) {
      const parts = t.split(sep);
      if (parts.length === 3 && parts.every((p) => /^\d+$/.test(p))) {
        let y;
        let m;
        let d;
        if (order === 'ymd' && parts[0].length === 4) {
          y = parseInt(parts[0], 10);
          m = parseInt(parts[1], 10);
          d = parseInt(parts[2], 10);
        } else if (order === 'dmy' && parts[2].length === 4) {
          d = parseInt(parts[0], 10);
          m = parseInt(parts[1], 10);
          y = parseInt(parts[2], 10);
        } else {
          continue;
        }
        const ceY = be_to_ce_year(y);
        const dt = new Date(ceY, m - 1, d);
        if (
          dt.getFullYear() !== ceY ||
          dt.getMonth() !== m - 1 ||
          dt.getDate() !== d ||
          m < 1 ||
          m > 12 ||
          d < 1 ||
          d > 31
        ) {
          throw new Error(`${label}ไม่ถูกต้อง`);
        }
        return `${String(ceY).padStart(4, '0')}-${pad2(m)}-${pad2(d)}`;
      }
    }
  }
  throw new Error(`${label}ไม่ถูกต้อง (กรุณาเลือกวันที่จากปฏิทิน)`);
}

/**
 * แปลงข้อความเป็นตัวเลขทศนิยม ตาม ui/owner/_common.py::parse_number
 */
export function parse_number(
  text,
  label,
  { minimum = null, maximum = null, allowEmpty = false, defaultValue = 0.0 } = {}
) {
  const t = String(text ?? '').trim().replace(/,/g, '');
  if (!t) {
    if (allowEmpty) return defaultValue;
    throw new Error(`กรุณากรอก${label}`);
  }
  const value = Number(t);
  if (Number.isNaN(value)) {
    throw new Error(`${label}ต้องเป็นตัวเลข`);
  }
  if (!Number.isFinite(value)) {
    throw new Error(`${label}ไม่ถูกต้อง`);
  }
  if (minimum !== null && value < minimum) {
    throw new Error(`${label}ต้องไม่น้อยกว่า ${formatG(minimum)}`);
  }
  if (maximum !== null && value > maximum) {
    throw new Error(`${label}ต้องไม่เกิน ${formatG(maximum)}`);
  }
  return value;
}

/**
 * จำนวนเต็ม ('12' หรือ '12.0' ได้ ; '12.5' ไม่ได้)
 */
export function parse_int(text, label, { minimum = null, maximum = null } = {}) {
  const value = parse_number(text, label);
  if (value !== Math.trunc(value)) {
    throw new Error(`${label}ต้องเป็นจำนวนเต็ม`);
  }
  const intVal = Math.trunc(value);
  if (minimum !== null && intVal < minimum) {
    throw new Error(`${label}ต้องไม่น้อยกว่า ${minimum}`);
  }
  if (maximum !== null && intVal > maximum) {
    throw new Error(`${label}ต้องไม่เกิน ${maximum}`);
  }
  return intVal;
}

export function parse_percent(text, label) {
  return parse_number(text, label, { minimum: 0, maximum: 100 });
}

/**
 * ปริมาณสต๊อก: 12.0 -> '12', 3.250 -> '3.25'
 */
export function fmt_qty(value) {
  const n = Number(value || 0);
  const safe = Number.isFinite(n) ? n : 0;
  const fixed = safe.toFixed(3);
  const [intPart, decPart] = fixed.split('.');
  const sign = intPart.startsWith('-') ? '-' : '';
  const digits = sign ? intPart.slice(1) : intPart;
  const withCommas = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const trimmedDec = decPart.replace(/0+$/, '');
  return trimmedDec ? `${sign}${withCommas}.${trimmedDec}` : `${sign}${withCommas}`;
}

/**
 * ขนาดไฟล์: 1024 -> '1.0 KB', 500 -> '500 ไบต์'
 */
export function human_size(numBytes) {
  let size = Number(numBytes || 0);
  const units = ['ไบต์', 'KB', 'MB', 'GB'];
  for (const unit of units) {
    if (size < 1024 || unit === 'GB') {
      if (unit === 'ไบต์') {
        const rounded = Math.round(size);
        return `${rounded.toLocaleString('en-US')} ${unit}`;
      }
      const fixed = size.toFixed(1);
      const [intPart, decPart] = fixed.split('.');
      const withCommas = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      return `${withCommas}.${decPart} ${unit}`;
    }
    size /= 1024;
  }
  return `${numBytes} ไบต์`;
}
