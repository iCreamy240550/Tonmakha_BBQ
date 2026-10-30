"""web/pages/order.py — หน้าสั่งอาหาร (สถานะ open): เมนู + สต๊อกคงเหลือ + รูปภาพเมนู 1:1 + ตะกร้า + รายการของโต๊ะ + ข้อความ

- ลูกค้าสั่งได้เฉพาะเมนูประเภท normal ; เมนูชั่งกิโล (weighed) แสดงราคา/กก. แต่ให้สั่งกับพนักงาน (ตามขั้น 2B)
- แสดงจำนวนสต๊อกคงเหลือและหน่วยจริงจากฐานข้อมูล (เช่น คงเหลือ 8 ขวด / คงเหลือ 0 ขวด)
- ถ้าสต๊อกเป็น 0 หรือเมนูถูกตั้งเป็นหมด แสดงสถานะ 'สินค้าหมด' และซ่อนปุ่มเพิ่มรายการ
- จำกัดจำนวนในตะกร้าไม่ให้เกินสต๊อกคงเหลือ และตรวจสอบซ้ำที่ฝั่งฐานข้อมูลตอนกดยืนยันสั่ง
- แสดงรูปเมนูแบบสัดส่วน 1:1 (square) หากไม่มีรูปใช้ placeholder ที่เรียบร้อย ไม่แสดง broken image
"""
from __future__ import annotations

from nicegui import app, ui

from web import components, session
from web.pages import notice

TABS = (("menu", "เมนู"), ("mine", "รายการของฉัน"), ("notice", "ข้อความ"))


def render(snap: dict, ctx: dict, state: dict, on_change) -> None:
    storage = app.storage.user
    menu = snap["menu"]
    cart = state["cart"]

    removed = session.cart_clean(cart, menu)
    if removed:
        session.cart_save(storage, ctx["session_id"], cart)
        ui.notify("เอาออกจากตะกร้าแล้ว (สินค้าหมด/ไม่มีขาย): " + ", ".join(removed), type="warning", position="top")

    _tab_bar(snap, state, on_change)
    if state["tab"] == "mine":
        _render_mine(snap)
    elif state["tab"] == "notice":
        notice.render(snap)
    else:
        _render_menu(snap, ctx, state, on_change)


# ---------------------------------------------------------------- แท็บ

def _tab_bar(snap: dict, state: dict, on_change) -> None:
    def pick(key: str) -> None:
        if state["tab"] != key:
            state["tab"] = key
            on_change()

    with ui.row().classes("w-full no-wrap gap-2"):
        for key, label in TABS:
            if key == "notice" and snap["notices"]:
                label = f"{label} ({len(snap['notices'])})"
            btn = ui.button(label, on_click=lambda k=key: pick(k)).classes("flex-1")
            btn.props("unelevated color=primary" if state["tab"] == key else "outline color=primary")


# ---------------------------------------------------------------- แท็บเมนู

def _render_menu(snap: dict, ctx: dict, state: dict, on_change) -> None:
    storage = app.storage.user
    menu = snap["menu"]
    cart = state["cart"]

    if not menu:
        components.message_card("restaurant_menu", "ยังไม่มีเมนู", "กรุณาสอบถามพนักงาน", color="grey")
        return

    if state.get("cat") not in {c["id"] for c in menu}:
        state["cat"] = menu[0]["id"]

    def pick_cat(cat_id: int) -> None:
        state["cat"] = cat_id
        on_change()

    with ui.row().classes("w-full gap-2"):
        for cat in menu:
            b = ui.button(cat["name"], on_click=lambda c=cat["id"]: pick_cat(c))
            b.props("unelevated color=primary rounded" if state["cat"] == cat["id"] else "outline color=primary rounded")

    qty_labels: dict[int, ui.label] = {}
    add_buttons: dict[int, ui.button] = {}
    items_by_id: dict[int, dict] = {it["id"]: it for cat in menu for it in cat["items"]}
    bar: dict = {}

    def update_bar() -> None:
        n, total = session.cart_count(cart), session.cart_total(cart, menu)
        bar["summary"].set_text(f"ตะกร้า {n} รายการ · {components.baht(total)}" if n else "ตะกร้ายังว่าง")
        if n:
            bar["button"].enable()
        else:
            bar["button"].disable()

    def update_item_controls(item_id: int) -> None:
        it = items_by_id.get(item_id)
        cur_q = cart.get(item_id, 0)
        if item_id in qty_labels:
            qty_labels[item_id].set_text(str(cur_q))
        if item_id in add_buttons and it is not None:
            max_q = session.max_orderable_qty(it)
            if cur_q >= max_q:
                add_buttons[item_id].disable()
            else:
                add_buttons[item_id].enable()

    def change(item_id: int, delta: int) -> None:
        try:
            session.cart_change_item(cart, menu, item_id, delta)
        except ValueError as e:
            ui.notify(str(e), type="warning", position="top")
            session.cart_save(storage, ctx["session_id"], cart)
            update_item_controls(item_id)
            update_bar()
            on_change()
            return
        session.cart_save(storage, ctx["session_id"], cart)
        update_item_controls(item_id)
        update_bar()

    current = next(c for c in menu if c["id"] == state["cat"])
    for it in current["items"]:
        _item_row(it, cart, qty_labels, add_buttons, change)

    ui.label("").classes("h-24")  # เว้นที่ไม่ให้แถบตะกร้าบังรายการท้ายสุด
    with ui.row().classes("fixed bottom-0 left-0 right-0 bg-white shadow-up-3 p-3 justify-center"):
        with ui.row().classes("w-full max-w-md items-center justify-between no-wrap"):
            bar["summary"] = ui.label("").classes("text-base font-bold")
            bar["button"] = ui.button("ตรวจสอบ/สั่งอาหาร",
                                      on_click=lambda: _open_confirm(snap, ctx, state, on_change)).props("color=primary")
    update_bar()


def _stock_caption(it: dict) -> tuple[str, str]:
    """คืน (ข้อความสต๊อกคงเหลือ, คลาสสี Tailwind) ตามข้อมูลจริงของเมนู"""
    stock_qty = it.get("stock_quantity")
    stock_unit = (it.get("stock_unit") or "").strip()
    sold_out = bool(it.get("is_sold_out")) or (stock_qty is not None and stock_qty <= 0)
    if sold_out:
        unit_part = f" {stock_unit}" if stock_unit else ""
        return f"สินค้าหมด · คงเหลือ 0{unit_part}", "text-xs text-red-600 font-medium"
    if stock_qty is not None:
        qty_txt = str(int(stock_qty)) if float(stock_qty) == int(stock_qty) else f"{float(stock_qty):g}"
        unit_part = f" {stock_unit}" if stock_unit else ""
        return f"คงเหลือ {qty_txt}{unit_part}", "text-xs text-green-700 font-medium"
    return it.get("stock_text") or "พร้อมจำหน่าย", "text-xs text-grey-6"


def _render_thumbnail(it: dict) -> None:
    """แสดงรูปภาพเมนูสัดส่วน 1:1 (square) หรือ placeholder ที่เรียบร้อยเมื่อไม่มีรูป"""
    img_url = it.get("image_url")
    if img_url and it.get("has_image"):
        ui.image(img_url).classes("w-16 h-16 rounded-lg object-cover shrink-0 bg-orange-50")
    else:
        with ui.column().classes(
            "w-16 h-16 rounded-lg bg-orange-100 items-center justify-center shrink-0 gap-0"
        ):
            ui.icon("restaurant", color="primary").classes("text-2xl")


def _item_row(it: dict, cart: dict, qty_labels: dict, add_buttons: dict, change) -> None:
    weighed = it["item_type"] == "weighed"
    stock_qty = it.get("stock_quantity")
    sold_out = bool(it.get("is_sold_out")) or (stock_qty is not None and stock_qty <= 0)
    stock_txt, stock_cls = _stock_caption(it)

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between no-wrap gap-3"):
            with ui.row().classes("items-center no-wrap gap-3 flex-1 min-w-0"):
                _render_thumbnail(it)
                with ui.column().classes("gap-0 min-w-0"):
                    ui.label(it["name"]).classes("text-base font-medium")
                    if weighed:
                        ui.label(f"{components.money(it['price'])} บาท/กก. · ชั่งกิโล สั่งกับพนักงาน").classes(
                            "text-sm text-grey-7")
                    else:
                        ui.label(f"{components.money(it['price'])} บาท").classes("text-sm text-grey-7")
                    ui.label(stock_txt).classes(stock_cls)

            if sold_out:
                ui.badge("สินค้าหมด", color="negative")
            elif weighed:
                ui.badge("ชั่งกิโล", color="info").props("outline")
            else:
                iid = it["id"]
                max_q = session.max_orderable_qty(it)
                cur_q = cart.get(iid, 0)
                with ui.row().classes("items-center no-wrap gap-1 shrink-0"):
                    ui.button(icon="remove", on_click=lambda i=iid: change(i, -1)).props("round dense flat color=primary")
                    qty_labels[iid] = ui.label(str(cur_q)).classes("w-6 text-center text-base font-bold")
                    add_btn = ui.button(icon="add", on_click=lambda i=iid: change(i, 1)).props("round dense color=primary")
                    if cur_q >= max_q:
                        add_btn.disable()
                    add_buttons[iid] = add_btn


def _open_confirm(snap: dict, ctx: dict, state: dict, on_change) -> None:
    menu, cart = snap["menu"], state["cart"]
    lines = session.cart_lines(cart, menu)
    if not lines:
        ui.notify("ยังไม่ได้เลือกรายการ", type="warning")
        return
    total = session.cart_total(cart, menu)

    with ui.dialog() as dlg, ui.card().classes("w-full max-w-md"):
        ui.label("ยืนยันการสั่งอาหาร").classes("text-lg font-bold")
        for ln in lines:
            components.summary_row(f"{ln['name']}  x{ln['quantity']}", components.money(ln["line_total"]))
        ui.separator()
        components.summary_row("รวม", components.baht(total), bold=True, color="primary")
        note = ui.input("หมายเหตุถึงครัว (ถ้ามี)").classes("w-full")
        with ui.row().classes("w-full justify-end"):
            ui.button("กลับไปแก้", on_click=dlg.close).props("flat")
            ui.button("ยืนยันสั่ง", on_click=lambda: _submit(dlg, ctx, state, note.value, on_change)).props("color=primary")
    dlg.open()


def _submit(dlg, ctx: dict, state: dict, note: str | None, on_change) -> None:
    storage = app.storage.user
    try:
        session.place_order(ctx["session_id"], ctx["device_id"], state["cart"], note=note)
    except ValueError as e:  # เมนูหมด/สต๊อกไม่พอ/โต๊ะปิดแล้ว -> ทั้งออเดอร์ไม่ถูกบันทึก ตะกร้าคงไว้ให้แก้
        ui.notify(str(e), type="negative", position="top")
        dlg.close()
        on_change()
        return
    state["cart"].clear()
    session.cart_save(storage, ctx["session_id"], state["cart"])
    state["tab"] = "mine"
    dlg.close()
    ui.notify("ส่งออเดอร์ให้ครัวแล้ว", type="positive", position="top")
    on_change()


# ---------------------------------------------------------------- แท็บรายการของฉัน

def _render_mine(snap: dict) -> None:
    weigh, orders = snap["weigh_entries"], snap["orders"]
    if not weigh and not orders:
        components.message_card("receipt", "ยังไม่มีรายการ", "เมื่อสั่งอาหารหรือพนักงานชั่งเนื้อให้ จะแสดงที่นี่", color="grey")
        return

    if weigh:
        with ui.card().classes("w-full gap-1"):
            components.section_title("หมูกระทะชั่งกิโล")
            for w in weigh:
                components.summary_row(f"{w['name_snapshot']}  {components.weight_text(w['weight_grams'])}",
                                       components.money(w["amount"]))

    for o in snap["orders"]:
        with ui.card().classes("w-full gap-1"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label(f"ออเดอร์ #{o['id']} · {components.fmt_time(o['created_at'])}").classes("text-base font-bold")
                ui.badge(components.ORDER_STATUS_CUSTOMER_TH.get(o["status"], o["status"]),
                         color=components.ORDER_STATUS_COLOR.get(o["status"], "grey"))
            for it in o["items"]:
                components.summary_row(f"{it['name_snapshot']}  x{it['quantity']}", components.money(it["line_total"]))
            if o.get("note"):
                ui.label(f"หมายเหตุ: {o['note']}").classes("text-sm text-grey-7")

    with ui.card().classes("w-full gap-1"):
        components.summary_row("ยอดรวมปัจจุบัน", components.baht(snap["subtotal"]), bold=True, color="primary")
        ui.label("ยังไม่รวมส่วนลด/ค่าบริการ/ภาษีมูลค่าเพิ่ม — เมื่อต้องการเช็คบิล กรุณาเรียกพนักงาน").classes("text-sm text-grey-7")
