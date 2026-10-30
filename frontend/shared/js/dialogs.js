/**
 * frontend/shared/js/dialogs.js — กล่องโต้ตอบแบบ modal (BaseDialog, confirm, ask_text, ask_reason, show_info, show_error)
 * รองรับ Esc ปิด, โฟกัสวนใน modal (focus trap), ปุ่มยืนยันสีตามชนิด ตาม ui/widgets/dialogs.py
 */

export class BaseDialog {
  constructor(title = 'แจ้งให้ทราบ', { width = 460 } = {}) {
    this.title = title;
    this.width = width;
    this.result = null;
    this._resolve = null;
    this._previousActive = document.activeElement;

    this.backdrop = document.createElement('div');
    this.backdrop.className = 'modal-backdrop';

    this.card = document.createElement('div');
    this.card.className = 'modal-card';
    this.card.style.maxWidth = `${width}px`;
    this.card.setAttribute('role', 'dialog');
    this.card.setAttribute('aria-modal', 'true');

    this.header = document.createElement('div');
    this.header.className = 'modal-header';

    this.titleEl = document.createElement('div');
    this.titleEl.className = 'modal-title';
    this.titleEl.textContent = title;
    this.header.appendChild(this.titleEl);

    this.closeBtn = document.createElement('button');
    this.closeBtn.type = 'button';
    this.closeBtn.className = 'btn btn-sm btn-ghost';
    this.closeBtn.textContent = '✕';
    this.closeBtn.style.minWidth = '36px';
    this.closeBtn.addEventListener('click', () => this.cancel());
    this.header.appendChild(this.closeBtn);

    this.body = document.createElement('div');
    this.body.className = 'modal-body';

    this.footer = document.createElement('div');
    this.footer.className = 'modal-footer';

    this.card.appendChild(this.header);
    this.card.appendChild(this.body);
    this.card.appendChild(this.footer);
    this.backdrop.appendChild(this.card);

    this._onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        this.cancel();
      } else if (e.key === 'Tab') {
        this._trapFocus(e);
      }
    };
  }

  _trapFocus(e) {
    const focusables = Array.from(
      this.card.querySelectorAll(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
      )
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  addButtons({
    confirmText = 'ตกลง',
    cancelText = 'ยกเลิก',
    variant = 'primary',
    onConfirm = null,
  } = {}) {
    this.footer.textContent = '';
    if (cancelText) {
      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'btn btn-ghost';
      cancelBtn.textContent = cancelText;
      cancelBtn.addEventListener('click', () => this.cancel());
      this.footer.appendChild(cancelBtn);
    }

    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = `btn btn-${variant}`;
    confirmBtn.textContent = confirmText;
    confirmBtn.addEventListener('click', () => {
      if (onConfirm) {
        onConfirm();
      } else {
        this.close(true);
      }
    });
    this.footer.appendChild(confirmBtn);
    this.confirmBtn = confirmBtn;
    return confirmBtn;
  }

  cancel() {
    this.close(null);
  }

  close(result = null) {
    this.result = result;
    document.removeEventListener('keydown', this._onKeyDown);
    if (this.backdrop.parentNode) {
      this.backdrop.parentNode.removeChild(this.backdrop);
    }
    if (this._previousActive && typeof this._previousActive.focus === 'function') {
      try {
        this._previousActive.focus();
      } catch (_e) {
        // ignore
      }
    }
    if (this._resolve) {
      const r = this._resolve;
      this._resolve = null;
      r(result);
    }
  }

  show() {
    document.body.appendChild(this.backdrop);
    document.addEventListener('keydown', this._onKeyDown);
    setTimeout(() => {
      const firstInput = this.body.querySelector('input, textarea, select');
      if (firstInput) {
        firstInput.focus();
      } else if (this.confirmBtn) {
        this.confirmBtn.focus();
      }
    }, 20);
    return new Promise((resolve) => {
      this._resolve = resolve;
    });
  }
}

export async function confirmDialog(
  message,
  {
    title = 'ยืนยัน',
    confirmText = 'ตกลง',
    cancelText = 'ยกเลิก',
    danger = false,
  } = {}
) {
  const dlg = new BaseDialog(title);
  const msgEl = document.createElement('div');
  msgEl.style.fontSize = 'var(--fs-lg)';
  msgEl.style.whiteSpace = 'pre-line';
  msgEl.textContent = message;
  dlg.body.appendChild(msgEl);
  dlg.addButtons({
    confirmText,
    cancelText,
    variant: danger ? 'danger' : 'primary',
  });
  const res = await dlg.show();
  return Boolean(res);
}

export async function askTextDialog(
  promptText,
  {
    title = 'กรอกข้อมูล',
    required = true,
    initial = '',
    multiline = false,
    confirmText = 'ตกลง',
    cancelText = 'ยกเลิก',
    danger = false,
  } = {}
) {
  const dlg = new BaseDialog(title);
  const labelEl = document.createElement('div');
  labelEl.style.fontSize = 'var(--fs-lg)';
  labelEl.style.whiteSpace = 'pre-line';
  labelEl.textContent = promptText;
  dlg.body.appendChild(labelEl);

  let inputEl;
  if (multiline) {
    inputEl = document.createElement('textarea');
    inputEl.className = 'field-textarea';
    inputEl.value = initial || '';
  } else {
    inputEl = document.createElement('input');
    inputEl.type = 'text';
    inputEl.className = 'field-input';
    inputEl.value = initial || '';
  }
  dlg.body.appendChild(inputEl);

  const errorEl = document.createElement('div');
  errorEl.className = 'modal-error';
  dlg.body.appendChild(errorEl);

  const submit = () => {
    const val = inputEl.value.trim();
    if (required && !val) {
      errorEl.textContent = 'กรุณากรอกข้อมูล';
      return;
    }
    dlg.close(val);
  };

  if (!multiline) {
    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        submit();
      }
    });
  }

  dlg.addButtons({
    confirmText,
    cancelText,
    variant: danger ? 'danger' : 'primary',
    onConfirm: submit,
  });

  return dlg.show();
}

export async function askReasonDialog(
  promptText = 'เหตุผล',
  { title = 'ระบุเหตุผล', confirmText = 'ยืนยัน' } = {}
) {
  return askTextDialog(promptText, {
    title,
    required: true,
    multiline: true,
    confirmText,
    danger: true,
  });
}

export async function showInfoDialog(message, { title = 'แจ้งให้ทราบ' } = {}) {
  const dlg = new BaseDialog(title);
  const msgEl = document.createElement('div');
  msgEl.style.fontSize = 'var(--fs-lg)';
  msgEl.style.whiteSpace = 'pre-line';
  msgEl.textContent = message;
  dlg.body.appendChild(msgEl);
  dlg.addButtons({ confirmText: 'ตกลง', cancelText: null, variant: 'primary' });
  await dlg.show();
}

export async function showErrorDialog(message, { title = 'เกิดข้อผิดพลาด' } = {}) {
  const dlg = new BaseDialog(title);
  const msgEl = document.createElement('div');
  msgEl.style.fontSize = 'var(--fs-lg)';
  msgEl.style.color = 'var(--color-danger)';
  msgEl.style.whiteSpace = 'pre-line';
  msgEl.textContent = message;
  dlg.body.appendChild(msgEl);
  dlg.addButtons({ confirmText: 'ตกลง', cancelText: null, variant: 'danger' });
  await dlg.show();
}
