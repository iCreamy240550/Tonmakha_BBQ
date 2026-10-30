"""ui/widgets/data_table.py — ตารางรายการแบบเลื่อนได้ (ใช้ในหน้ารายงาน/log/เมนู/สต๊อก/โปรโมชั่น/โต๊ะ/ผู้ใช้/สำรองข้อมูล)

columns = [{"key": "name", "title": "ชื่อ", "weight": 3, "anchor": "w", "header_anchor": "w",
            "format": lambda value, row: str(value),            # ไม่ส่ง = str(value)
            "widget": lambda parent, row: ActionButton(...)}]    # ไม่ส่ง = แสดงเป็นข้อความ
- `weight` = สัดส่วนความกว้าง (ค่าเริ่มต้น 1), `min_width` = กว้างต่ำสุดพิกเซล
- การจัดแนวคอลัมน์ (แนวตั้งและแนวนอน):
  - ใช้ `uniform` และโครงสร้างขอบซ้าย/ขวา (padding) เดียวกันระหว่างหัวตารางและแถวข้อมูล เพื่อให้หัวตารางตรงกับข้อมูลในทุกคอลัมน์
  - ค่าเริ่มต้นของ `anchor` และ `header_anchor` คือ `"w"` (ชิดซ้าย) ยกเว้นคอลัมน์ที่กำหนด `"center"` (กึ่งกลาง) เช่น สถานะ หรือ รูปภาพ
- `set_rows(rows)` rows = list[dict]; `on_select(row)` เรียกเมื่อคลิกแถว; `selected` = แถวที่เลือกอยู่
- แสดงสูงสุด MAX_ROWS แถวต่อครั้ง (กันหน้าค้าง) — ให้หน้าที่เรียกใช้แบ่งหน้า/กรองเอง
"""
from __future__ import annotations

import customtkinter as ctk

from ui.theme import COLORS, font
from ui.widgets.basic import EmptyState

MAX_ROWS = 300

_ANCHOR_TO_STICKY = {
    "w": "w",
    "center": "",
    "e": "e",
}


class DataTable(ctk.CTkFrame):
    def __init__(self, master, columns: list[dict], on_select=None, row_height: int = 40,
                 empty_text: str = "ไม่มีข้อมูล", font_size: int = 14):
        super().__init__(master, fg_color=COLORS["card"], border_width=1,
                         border_color=COLORS["card_border"], corner_radius=12)
        self.columns = columns
        self.on_select = on_select
        self.row_height = row_height
        self.empty_text = empty_text
        self.font_size = font_size
        self.rows: list[dict] = []
        self.selected: dict | None = None
        self._row_frames: list[tuple[dict, ctk.CTkFrame, str]] = []

        self.header = ctk.CTkFrame(self, fg_color=COLORS["sidebar"], corner_radius=10, height=40)
        # ชดเชยความกว้าง scrollbar ด้านขวาของ CTkScrollableFrame เพื่อให้แนวคอลัมน์ของหัวตารางและแถวข้อมูลตรงกันทั้งแนวตั้งและแนวนอน
        self.header.pack(fill="x", padx=(6, 20), pady=(6, 0))
        self.header.grid_rowconfigure(0, weight=1)
        self._configure_columns(self.header)
        for i, col in enumerate(columns):
            col_anchor = col.get("header_anchor") or col.get("anchor", "w")
            justify = "center" if col_anchor == "center" else ("right" if col_anchor == "e" else "left")
            ctk.CTkLabel(
                self.header,
                text=col["title"],
                font=font(self.font_size, True),
                text_color=COLORS["sidebar_text"],
                anchor=col_anchor,
                justify=justify,
            ).grid(row=0, column=i, sticky="ew", padx=10, pady=7)
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=2, pady=(2, 6))

    def _configure_columns(self, frame) -> None:
        for i, col in enumerate(self.columns):
            # uniform ทำให้ความกว้างคอลัมน์ตามสัดส่วน weight เสมอ (หัวตารางกับแถวตรงกัน ไม่ขึ้นกับความยาวข้อความ)
            frame.grid_columnconfigure(
                i,
                weight=col.get("weight", 1),
                minsize=col.get("min_width", 50),
                uniform=f"col{i}",
            )

    def set_rows(self, rows: list[dict]) -> None:
        """แทนที่ข้อมูลทั้งตาราง (คงแถวที่เลือกไว้ถ้า id เดิมยังอยู่)"""
        prev_id = self.selected.get("id") if self.selected else None
        for child in self.body.winfo_children():
            child.destroy()
        self._row_frames = []
        self.rows = list(rows)
        self.selected = None
        if not self.rows:
            EmptyState(self.body, self.empty_text).pack(pady=40)
            return
        for idx, row in enumerate(self.rows[:MAX_ROWS]):
            bg = COLORS["card"] if idx % 2 == 0 else COLORS["row_alt"]
            frame = ctk.CTkFrame(self.body, fg_color=bg, corner_radius=6, height=self.row_height)
            frame.pack(fill="x", padx=4, pady=1)
            frame.grid_rowconfigure(0, weight=1)
            self._configure_columns(frame)
            for i, col in enumerate(self.columns):
                col_anchor = col.get("anchor", "w")
                if col.get("widget"):
                    w = col["widget"](frame, row)
                    default_sticky = _ANCHOR_TO_STICKY.get(col_anchor, "w")
                    sticky_val = col.get("sticky", default_sticky)
                    w.grid(row=0, column=i, sticky=sticky_val, padx=10, pady=4)
                    continue
                value = row.get(col["key"])
                text = col["format"](value, row) if col.get("format") else ("" if value is None else str(value))
                justify = "center" if col_anchor == "center" else ("right" if col_anchor == "e" else "left")
                lbl = ctk.CTkLabel(
                    frame,
                    text=text,
                    font=font(self.font_size),
                    text_color=COLORS["text"],
                    anchor=col_anchor,
                    justify=justify,
                    wraplength=col.get("wrap", 0),
                )
                lbl.grid(row=0, column=i, sticky="ew", padx=10, pady=6)
                lbl.bind("<Button-1>", lambda e, r=row: self._click(r))
            frame.bind("<Button-1>", lambda e, r=row: self._click(r))
            self._row_frames.append((row, frame, bg))
            if prev_id is not None and row.get("id") == prev_id:
                self._click(row, notify=False)
        if len(self.rows) > MAX_ROWS:
            ctk.CTkLabel(
                self.body,
                text=f"แสดง {MAX_ROWS} จาก {len(self.rows)} รายการ — กรองข้อมูลเพื่อดูเพิ่ม",
                font=font(13),
                text_color=COLORS["text_muted"],
            ).pack(pady=8)

    def _click(self, row: dict, notify: bool = True) -> None:
        self.selected = row
        for r, frame, bg in self._row_frames:
            frame.configure(fg_color=COLORS["row_hover"] if r is row else bg)
        if notify and self.on_select:
            self.on_select(row)

    def clear_selection(self) -> None:
        self.selected = None
        for _r, frame, bg in self._row_frames:
            frame.configure(fg_color=bg)
