"""
Thai (TH) language strings - ภาษาไทย
"""

STRINGS = {
    # ─── General ───────────────────────────────────────────────────────────────
    "lang_name": "ไทย",
    "lang_flag": "🇹🇭",
    "yes": "ใช่",
    "no": "ไม่",
    "cancel": "ยกเลิก",
    "confirm": "ยืนยัน",
    "success": "สำเร็จ",
    "error": "เกิดข้อผิดพลาด",
    "warning": "คำเตือน",
    "loading": "กำลังโหลด...",
    "not_found": "ไม่พบข้อมูล",
    "permission_denied": "❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้",
    "bot_name": "📝 To-Do List Bot Gen 2",
    "footer_text": "To-Do List Bot Gen 2 • พัฒนาเพื่อประสิทธิภาพสูงสุด",

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    "rate_limited": "⏳ คุณใช้คำสั่งเร็วเกินไป กรุณารอ **{seconds:.0f} วินาที** แล้วลองใหม่",
    "task_rate_limited": "⏳ คุณสร้าง Task เกินกำหนด ({limit} ต่อชั่วโมง) กรุณารอ **{seconds:.0f} วินาที**",

    # ─── Setup ─────────────────────────────────────────────────────────────────
    "setup_title": "⚙️ ตั้งค่า Bot",
    "setup_desc": "กรุณาตั้งค่าต่อไปนี้เพื่อเริ่มใช้งาน",
    "setup_timezone": "เขตเวลา (Timezone)",
    "setup_timezone_desc": "ตัวอย่าง: Asia/Bangkok, UTC, America/New_York",
    "setup_success": "✅ ตั้งค่าสำเร็จ! เขตเวลา: **{tz}** | ช่อง: {channel}",
    "setup_checklist": "✅ เขตเวลา  ✅ ช่องแจ้งเตือน  ☑️ ภาษา (ใช้ `/lang`)",
    "setup_invalid_tz": "❌ เขตเวลา `{tz}` ไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง\n[รายการเขตเวลาทั้งหมด](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)",
    "setup_channel_required": "❌ กรุณาใช้คำสั่งนี้ในช่อง Discord",

    # ─── Language ──────────────────────────────────────────────────────────────
    "lang_changed": "✅ เปลี่ยนภาษาเป็น **ไทย** เรียบร้อยแล้ว",
    "lang_select_title": "🌐 เลือกภาษา / Select Language",
    "lang_select_desc": "เลือกภาษาที่คุณต้องการใช้",

    # ─── Task Creation ──────────────────────────────────────────────────────────
    "task_add_title": "➕ เพิ่ม Task ใหม่",
    "task_name_label": "ชื่อ Task",
    "task_name_placeholder": "เช่น: ส่งรายงาน, ประชุมทีม",
    "task_deadline_label": "กำหนดส่ง (วัน/เดือน/ปี ชั่วโมง:นาที)",
    "task_deadline_placeholder": "เช่น: 25/12/2025 18:00",
    "task_priority_label": "⚡ ความสำคัญ",
    "task_priority_placeholder": "0–7  (0=ปกติ, 3=สำคัญ, 5=เร่งด่วน, 7=วิกฤต)",
    "task_desc_label": "รายละเอียด (ไม่บังคับ)",
    "task_desc_placeholder": "อธิบายรายละเอียดเพิ่มเติม...",
    "task_tags_label": "แท็ก (ไม่บังคับ)",
    "task_tags_placeholder": "เช่น: งาน, เร่งด่วน, บ้าน",
    "task_created": "✅ สร้าง Task สำเร็จ! ID: **#{task_id}**",
    "task_invalid_deadline": "❌ รูปแบบวันที่ไม่ถูกต้อง กรุณาใช้: `วว/ดด/ปปปป ชช:นน`\nตัวอย่าง: `25/12/2025 18:00`",
    "task_past_deadline": "❌ กำหนดส่งต้องเป็นเวลาในอนาคต",
    "task_invalid_priority": "❌ ความสำคัญต้องเป็นตัวเลข 0–7 เท่านั้น",
    "task_name_too_long": "❌ ชื่อ Task ยาวเกินไป (สูงสุด 200 ตัวอักษร)",
    "task_desc_too_long": "❌ รายละเอียดยาวเกินไป (สูงสุด 1000 ตัวอักษร)",

    # ─── Task List ──────────────────────────────────────────────────────────────
    "tasks_title": "📋 รายการ Task ของคุณ",
    "tasks_empty": "📭 ยังไม่มี Task\nกด **`/add`** เพื่อเพิ่ม Task แรกของคุณ!",
    "tasks_page": "หน้า {page}/{total}",
    "tasks_total": "Task ทั้งหมด: **{count}** รายการ",
    "tasks_summary": "{total} tasks · {overdue} เกินกำหนด",
    "today_summary": "📅 วันนี้: **{count}** task · ⚠️ เกินกำหนด: **{overdue}**",
    "overdue_summary": "🚨 เกินกำหนดทั้งหมด: **{total}** task",
    "tasks_filter_pending": "⏳ รอดำเนินการ",
    "tasks_filter_Pending": "⏳ รอดำเนินการ",
    "tasks_filter_done": "✅ เสร็จแล้ว",
    "tasks_filter_Completed": "✅ เสร็จแล้ว",
    "tasks_filter_cancelled": "❌ ยกเลิก",
    "tasks_filter_Cancelled": "❌ ยกเลิก",
    "tasks_filter_all": "📋 ทั้งหมด",
    "tasks_filter_today": "📅 วันนี้",
    "tasks_filter_overdue": "🚨 เกินกำหนด",
    "tasks_filter_pinned": "📌 ปักหมุด",
    "list_filter_placeholder": "🔽 กรองตามสถานะ...",

    # ─── Task Details ───────────────────────────────────────────────────────────
    "task_detail_title": "📌 รายละเอียด Task #{task_id}",
    "task_detail_name": "📝 ชื่อ Task",
    "task_detail_status": "🔖 สถานะ",
    "task_detail_deadline": "📅 กำหนดส่ง",
    "task_detail_priority": "⚡ ความสำคัญ",
    "task_detail_category": "🏷️ หมวดหมู่",
    "task_detail_tags": "🔖 แท็ก",
    "task_detail_desc": "📄 รายละเอียด",
    "task_detail_recurring": "🔄 การทำซ้ำ",
    "task_detail_subtasks": "📊 Subtask",
    "task_not_found": "❌ ไม่พบ Task ID #{task_id}",
    "task_not_owned": "❌ Task นี้ไม่ใช่ของคุณ",

    # ─── Task Actions ───────────────────────────────────────────────────────────
    "btn_done": "✅ เสร็จแล้ว",
    "btn_mark_done": "✅ ทำเครื่องหมายว่าเสร็จ",
    "btn_delete": "🗑️ ลบ",
    "btn_edit": "✏️ แก้ไข",
    "btn_subtask": "➕ Subtask",
    "btn_snooze": "⏰ เลื่อน (+1 วัน)",
    "btn_prev": "◀ ก่อนหน้า",
    "btn_next": "ถัดไป ▶",
    "btn_refresh": "🔄 รีเฟรช",
    "btn_back": "🔙 กลับ",
    "btn_confirm_delete": "🗑️ ยืนยันลบ",
    "page_indicator": "📄 หน้า {page} / {total}",
    # Delete confirm embed
    "delete_confirm_title": "⚠️ ยืนยันการลบ Task",
    "delete_confirm_desc": "คุณแน่ใจหรือไม่ว่าต้องการลบ Task นี้?\n> **{task_name}**\n\n⚠️ การดำเนินการนี้ **ไม่สามารถย้อนกลับได้**",

    "task_marked_done": "✅ Task **#{task_id}** เสร็จแล้ว!",
    "task_already_done": "⚠️ Task นี้เสร็จสิ้นแล้ว",
    "task_already_cancelled": "⚠️ Task นี้ถูกยกเลิกแล้ว",
    "task_deleted": "🗑️ Task **#{task_id}** ถูกลบเรียบร้อยแล้ว",
    "task_delete_confirm": "⚠️ คุณแน่ใจหรือไม่ว่าต้องการลบ Task นี้?\n> **{task_name}**\nการดำเนินการนี้ไม่สามารถย้อนกลับได้",

    # ─── Pin / Unpin ────────────────────────────────────────────────────────────
    "task_pinned": "📌 Task **#{task_id}** ปักหมุดเรียบร้อยแล้ว",
    "task_unpinned": "📌 Task **#{task_id}** เลิกปักหมุดแล้ว",

    # ─── Task Edit ──────────────────────────────────────────────────────────────
    "task_edit_title": "✏️ แก้ไข Task #{task_id}",
    "task_edit_success": "✅ แก้ไข Task สำเร็จ",

    # ─── Subtasks ──────────────────────────────────────────────────────────────
    "subtask_add_title": "➕ เพิ่ม Subtask",
    "subtask_for": "สำหรับ Task: **{parent_name}**",
    "subtask_created": "✅ สร้าง Subtask สำเร็จ!",
    "subtask_no_nested": "⚠️ ไม่สามารถเพิ่ม Subtask ใน Subtask ได้",
    "subtask_progress": "Subtask: {done}/{total} ({pct:.0f}%)",

    # ─── Categories ─────────────────────────────────────────────────────────────
    "cat_title": "🏷️ หมวดหมู่",
    "cat_list_title": "📂 หมวดหมู่ทั้งหมด",
    "cat_empty": "ยังไม่มีหมวดหมู่",
    "cat_section_default": "📌 หมวดหมู่เริ่มต้น",
    "cat_section_custom": "🗂️ หมวดหมู่ของคุณ",
    "cat_add_title": "➕ เพิ่มหมวดหมู่ใหม่",
    "cat_name_label": "ชื่อหมวดหมู่",
    "cat_emoji_label": "Emoji (ไม่บังคับ)",
    "cat_created": "✅ สร้างหมวดหมู่ **{name}** สำเร็จ!",
    "cat_not_found": "❌ ไม่พบหมวดหมู่นี้",

    # ─── Priority Labels ─────────────────────────────────────────────────
    "priority_0": "⬜ ปกติ",
    "priority_1": "🟦 ต่ำ",
    "priority_2": "🟩 ปานกลาง-ต่ำ",
    "priority_3": "🟨 ปานกลาง",
    "priority_4": "🟧 ค่อนข้างสำคัญ",
    "priority_5": "🟥 สำคัญ",
    "priority_6": "🔴 เร่งด่วน",
    "priority_7": "🆘 วิกฤต",
    # Dropdown descriptions
    "priority_0_desc": "ไม่เร่ง ทำได้เมื่อไหร่ก็ได้",
    "priority_1_desc": "รอได้ ไม่ต้องเร่ง",
    "priority_2_desc": "ควรดำเนินการในสัปดาห์นี้",
    "priority_3_desc": "ควรทำในสองสามวันได้",
    "priority_4_desc": "สำคัญ ต้องทำภายในวันนี้หรือพรุ่งนี้",
    "priority_5_desc": "เร่ง! ควรดำเนินการภายในไม่กี่ชั่วโมง",
    "priority_6_desc": "ด่วนมาก! ดำเนินการทันที",
    "priority_7_desc": "วิกฤต! ส่งผลสำคัญ ต้องแก้ไขทันที",
    # Dropdown UI strings
    "priority_select_placeholder": "⚡ เลือกระดับความสำคัญ...",
    "priority_select_title": "⚡ เลือกระดับความสำคัญ",
    "priority_select_desc": "กรุณาเลือกระดับความสำคัญของ Task ก่อนกรอกข้อมูลเพิ่มเติม",
    "priority_changed": "✅ เปลี่ยนระดับความสำคัญสำเร็จ! Task **#{task_id}** เป็น **{priority}**",
    # Legacy aliases (kept for backward compat)
    "priority_low": "⬜ ปกติ",
    "priority_medium": "🟨 ปานกลาง",
    "priority_high": "🔴 เร่งด่วน",

    # ─── Status Labels ──────────────────────────────────────────────────────────
    "status_pending": "⏳ รอดำเนินการ",
    "status_completed": "✅ เสร็จแล้ว",
    "status_cancelled": "❌ ยกเลิก",
    "status_overdue": "🚨 เกินกำหนด",

    # ─── Recurring ──────────────────────────────────────────────────────────────
    "recurring_daily": "🔄 ทุกวัน",
    "recurring_weekly": "🔄 ทุกสัปดาห์",
    "recurring_monthly": "🔄 ทุกเดือน",
    "recurring_none": "—",

    # ─── Reminders ─────────────────────────────────────────────────────────────────
    "reminder_title": "⏰ แจ้งเตือน Task",
    "reminder_overdue": "🚨 **Task เกินกำหนด!**\n`{task}` ครบกำหนดเมื่อ {deadline}",
    "reminder_due_soon": "⚡ **Task ใกล้ครบกำหนด!**\n`{task}` ครบกำหนดในอีก {time_left}",
    "reminder_due_today": "📅 **Task ครบกำหนดวันนี้!**\n`{task}` ครบกำหนดเวลา {time}",
    "reminder_action_hint": "ใช้ `/done {task_id}` หรือกด ✅ Done บน Task เพื่อหยุดการแจ้งเตือน",

    # DM deadline reminders
    "dm_reminder_title": "⏰ แจ้งเตือน Deadline (DM)",
    "dm_reminder_24h": "📅 **Task ของคุณใกล้ Deadline แล้ว!**\n`{task}` เหลือเวลาอีก **{time_left}** เท่านั้นแล้วนะ!",
    "dm_reminder_3h": "🟠 **Task ใกล้ Deadline มากขึ้นแล้ว!**\n`{task}` เหลือ**ไม่ถึง 3 ชั่วโมง** ({time_left}) รีบดำเนินการด้วยนะ!",
    "dm_reminder_1h": "🚨 **เหลือเวลาอีกไม่ถึง 1 ชั่วโมง!**\n`{task}` กำลังจะ Deadline แล้ว! เหลือ **{time_left}** เท่านั้น!",
    "dm_reminder_footer": "ถ้าเสร็จแล้ว ใช้ `/done {task_id}` หรือกด ✅ Done ที่ Task เพื่อหยุดการแจ้งเตือน",

    # ─── Export ─────────────────────────────────────────────────────────────────
    "export_success": "📤 ส่งออกข้อมูลสำเร็จ! ไฟล์: `{filename}`",
    "export_empty": "📭 ไม่มีข้อมูลที่จะส่งออก",
    "export_rate_limited": "⏳ คุณส่งออกข้อมูลเกินกำหนด ({limit} ครั้งต่อวัน) กรุณาลองใหม่พรุ่งนี้",

    # ─── Search ─────────────────────────────────────────────────────────────────
    "search_title": "🔍 ผลการค้นหา: `{query}`",
    "search_results_count": "🔍 ค้นหา: **{query}** — พบ {count} รายการ",
    "search_empty": "🔍 ไม่พบ Task ที่ตรงกับ `{query}`",
    "search_query_label": "คำค้นหา",
    "search_query_placeholder": "พิมพ์ชื่อ Task หรือ Tag...",

    # ─── Stats ──────────────────────────────────────────────────────────────────
    "stats_title": "📊 สถิติของคุณ",
    "stats_total": "Task ทั้งหมด",
    "stats_completed": "เสร็จแล้ว",
    "stats_pending": "รอดำเนินการ",
    "stats_overdue": "เกินกำหนด",
    "stats_completion_rate": "อัตราความสำเร็จ",
    "stats_categories": "หมวดหมู่ที่ใช้",
    # Dynamic stats header messages
    "stats_header_on_track": "🎯 กำลังดำเนินการได้ดี!",
    "stats_header_overdue": "⚠️ มี {overdue} Task เกินกำหนด!",
    "stats_header_all_done": "🏆 เสร็จทุก Task แล้ว!",
    "stats_header_empty": "📭 ยังไม่มี Task",
    # บันทึกแรงบันดาลใจใน /stats
    "stats_note_empty":    "ยังไม่มี Task เลย! ใช้ `/add` เพื่อเริ่มต้น \U0001f680",
    "stats_note_overdue":  "\u26a0\ufe0f มี {overdue} Task เกินกำหนด ใช้ `/overdue` ตรวจสอบ",
    "stats_note_all_done": "\U0001f3c6 เสร็จทุก Task แล้ว! ยอดเยี่ยมมาก!",
    "stats_note_progress": "ทำเสร็จไปแล้ว {pct}% เยี่ยมมาก!",

    # ─── Help ───────────────────────────────────────────────────────────────────
    "help_title": "📖 วิธีใช้งาน To-Do List Bot Gen 2",
    "help_desc": "บอท To-Do List ที่ครบครัน รองรับทั้งภาษาไทยและอังกฤษ",
    "help_commands": "คำสั่งทั้งหมด",
    "help_quickstart": "🚀 เริ่มต้นใช้งาน\n`1.` ใช้ `/setup Asia/Bangkok` เพื่อตั้งค่า timezone\n`2.` ใช้ `/add` เพื่อสร้าง Task แรก\n`3.` ใช้ `/list` เพื่อดู Task ทั้งหมด",
    "help_add": "เพิ่ม Task ใหม่",
    "help_list": "ดูรายการ Task ทั้งหมด",
    "help_done": "ทำเครื่องหมายว่าเสร็จแล้ว",
    "help_delete": "ลบ Task",
    "help_edit": "แก้ไข Task",
    "help_search": "ค้นหา Task",
    "help_categories": "จัดการหมวดหมู่",
    "help_stats": "ดูสถิติของคุณ",
    "help_export": "ส่งออกข้อมูลเป็น CSV",
    "help_setup": "ตั้งค่า Bot",
    "help_lang": "เปลี่ยนภาษา",
    "help_reminder": "ตั้งการแจ้งเตือน",

    # ─── Errors ─────────────────────────────────────────────────────────────────
    "err_generic": "❌ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง",
    "err_db": "❌ เกิดข้อผิดพลาดกับฐานข้อมูล กรุณาติดต่อผู้ดูแลระบบ",
    "err_no_setup": "⚠️ กรุณาตั้งค่า Bot ก่อนโดยใช้ `/setup`",
    "err_input_invalid": "❌ ข้อมูลที่กรอกไม่ถูกต้อง: {detail}",
    "err_suspicious": "🚫 พบพฤติกรรมที่น่าสงสัย คำสั่งถูกบล็อก",

    # ─── Snooze Confirm ─────────────────────────────────────────────────────────
    "snooze_confirm_title": "⏰ ยืนยันการเลื่อนเวลา",
    "snooze_confirm_desc": "คุณแน่ใจหรือไม่ว่าต้องการเลื่อนกำหนดส่งงานนี้ออกไป 1 วัน?\n> **{task_name}**\n📅 กำหนดส่งใหม่: `{new_deadline}`",
    "btn_confirm_snooze": "⏰ ยืนยันเลื่อน (+1 วัน)",
    "task_snoozed": "⏰ เลื่อนกำหนดส่งงานออกไป 1 วันแล้ว! กำหนดส่งใหม่: `{deadline}`",

    # ─── Help Categories (Interactive Select) ───────────────────────────────────
    "help_cat_overview": "🚀 ภาพรวม & เริ่มต้นใช้งาน",
    "help_cat_tasks": "📝 คำสั่งจัดการ Task",
    "help_cat_settings": "⚙️ ตั้งค่า & หมวดหมู่",
    "help_cat_tips": "💡 เคล็ดลับ & ทางลัด",
    "help_version_footer": "To-Do List Bot Gen 2 • /help • github.com",

    # ─── Daily Digest & Overdue ─────────────────────────────────────────────────
    "digest_title": "☀️ สรุป Task วันนี้ — {date}",
    "digest_no_tasks": "ไม่มี Task ที่ต้องส่งวันนี้!",
    "digest_today_tasks": "Task วันนี้",
    "digest_upcoming_title": "🔮 Task ที่กำลังจะมาถึง (3 วันข้างหน้า)",
    "digest_motivational_clean": "✨ ยอดเยี่ยม! วันนี้ไม่มีงานค้างเลย ขอให้เป็นวันที่ดีนะ",
    "digest_motivational_busy": "💪 วันนี้มี {count} งานที่ต้องลุย! สู้ๆ นะคุณทำได้แน่นอน",
    "digest_motivational_overdue": "⚠️ ระวังด้วยนะ! มีงานเกินกำหนด {overdue} งาน รีบเคลียร์เลย!",
    "overdue_none": "ไม่มีงานเกินกำหนด! เยี่ยมมาก จัดการได้ตรงเวลาสุดๆ 🎉",
    "overdue_note": "💪 สู้ๆ นะ! ทยอยเคลียร์งานค้างทีละงานได้เลย",
    "task_done_with_name": "✅ ทำเครื่องหมาย Task **#{task_id}** ({task_name}) เสร็จเรียบร้อยแล้ว!",

    # ─── Settings & Meta ────────────────────────────────────────────────────────
    "setup_current_tz": "Timezone ปัจจุบัน: **{tz}**",
    "lang_current_active": "ภาษาที่ใช้งานอยู่ในปัจจุบัน: {flag} **{name}**",
    "cat_task_count": "{count} งาน",
    "task_detail_created": "สร้างเมื่อ",
    "task_detail_updated": "แก้ไขล่าสุด",

    # ─── UX/UI Additions ─────────────────────────────────────────────────────────
    "cat_no_category": "— ไม่มีหมวดหมู่",
    "cat_removed": "🗑️ ลบหมวดหมู่ **{name}** เรียบร้อยแล้ว",
    "setup_lang_field": "🌐 ภาษา",
    "stats_cancelled": "ยกเลิกแล้ว",
    "priority_timeout": "⌛ หมดเวลาเลือก กรุณารันคำสั่งใหม่อีกครั้ง",
    "reminder_field_deadline": "📅 กำหนดส่ง",
    "reminder_field_priority": "⚡ ความสำคัญ",
    "reminder_field_task_id": "🆔 Task ID",
    "dm_reminder_field_time_left": "⏱️ เวลาที่เหลือ",
    "digest_stats_line": "📊 **{pending}** งานค้าง  ·  🚨 **{overdue}** เกินกำหนด",
    "help_overview_browse": "ใช้เมนูด้านล่างเพื่อเลือกดูคำสั่งตามหมวดหมู่:\n• **📝 คำสั่งจัดการ Task**: การสร้าง, แก้ไข, ทำเสร็จ, และจัดระเบียบ\n• **⚙️ ตั้งค่า & หมวดหมู่**: Timezone, ภาษา, และหมวดหมู่\n• **💡 เคล็ดลับ & ทางลัด**: ฟีเจอร์เด็ดและการใช้งานให้คุ้มค่า",

    # ─── Productivity Analytics (/task-stats) ────────────────────────────────────
    "taskstats_title":              "📊 Productivity Dashboard  ·  {username}",
    "taskstats_overview_tab":       "📊 ภาพรวม",
    "taskstats_speed_tab":          "⏱️ เจาะลึกความเร็ว",
    "taskstats_refresh":            "🔄 รีเฟรช",

    # Overview section
    "taskstats_score_label":        "🏆 Productivity Score",
    "taskstats_score_value":        "{score}/100  {badge}",
    "taskstats_completion_label":   "✅ อัตราความสำเร็จ",
    "taskstats_completion_value":   "{rate}%  ({done}/{total} งาน)",
    "taskstats_velocity_label":     "⚡ Velocity (ความเร็ว)",
    "taskstats_velocity_value":     "7 วัน: **{v7}** งาน  ·  30 วัน: **{v30}** งาน",
    "taskstats_streak_label":       "🔥 Streak",
    "taskstats_streak_value":       "{days} วันต่อเนื่อง",
    "taskstats_pending_overdue":    "⏳ ค้างอยู่: **{pending}**  ·  🚨 เกินกำหนด: **{overdue}**",

    # Speed / Timeliness section
    "taskstats_speed_title":        "⏱️ Speed & Timeliness Analysis  ·  {username}",
    "taskstats_ontime_label":       "✅ เสร็จตรงเวลา",
    "taskstats_ontime_value":       "{rate}%  ({count} งาน)",
    "taskstats_late_label":         "⚠️ เสร็จช้ากว่ากำหนด",
    "taskstats_late_value":         "{rate}%  ({count} งาน)",
    "taskstats_turnaround_label":   "⏰ เวลาเฉลี่ยต่องาน",
    "taskstats_turnaround_value":   "{hours}",
    "taskstats_lead_label":         "🚀 ล่วงหน้าเฉลี่ย (งานที่เสร็จทัน)",
    "taskstats_lead_value":         "{hours} ก่อนกำหนด",
    "taskstats_lag_label":          "🐌 ล่าช้าเฉลี่ย (งานที่เสร็จช้า)",
    "taskstats_lag_value":          "{hours} หลังกำหนด",
    "taskstats_no_completed":       "ยังไม่มีงานที่เสร็จสมบูรณ์ เริ่มทำงานแรกกันเลย! 🚀",
    "taskstats_tip_label":          "💡 คำแนะนำสำหรับคุณ",

    # Productivity Badges
    "badge_master":    "🏆 Productivity Master",
    "badge_pro":       "🎯 On-Time Pro",
    "badge_achiever":  "🛡️ Steady Achiever",
    "badge_rising":    "⚡ Rising Momentum",
    "badge_pacing":    "🐢 Needs Focus",
    "badge_new":       "🌱 Just Getting Started",

    # Personalized tips
    "tip_master":      "เยี่ยมมาก! คุณทำได้ดีเกินคาด ลองตั้งเป้าสูงขึ้นอีกสักนิดดีไหม?",
    "tip_pro":         "เกือบสมบูรณ์แบบแล้ว! ลองวางแผนล่วงหน้าสัก 10 นาทีต่อวันเพื่อดันคะแนนขึ้นอีก",
    "tip_achiever":    "ไปได้ดี! ลองตั้ง Sub-task สำหรับงานใหญ่ๆ เพื่อเร่งความเร็วในการทำงาน",
    "tip_rising":      "กำลังอุ่นเครื่อง! ลองจัดลำดับความสำคัญงานด้วย Priority เพื่อเพิ่ม Focus",
    "tip_pacing":      "ไม่เป็นไร! ลองแบ่งงานใหญ่เป็นงานย่อยๆ และตั้งเวลาทุกวันเพื่อสร้างนิสัยดีๆ",
    "tip_new":         "เริ่มต้นได้เลย! เพิ่มงานแรกด้วย `/add` แล้วทำมันให้เสร็จวันนี้เลย! 💪",

    # Duration format helper strings
    "duration_days":   "{d} วัน {h} ชั่วโมง",
    "duration_hours":  "{h} ชั่วโมง {m} นาที",
    "duration_mins":   "{m} นาที",
    "duration_na":     "ยังไม่มีข้อมูล",

    # ─── On-Demand /digest command ───────────────────────────────────────────────
    "digest_cmd_desc":  "☀️ ดูสรุปภาพรวม Task วันนี้ทันที",
    "digest_btn_list":  "📋 ดูงานทั้งหมด",
    "digest_btn_add":   "➕ เพิ่มงานใหม่",
    "digest_btn_refresh": "🔄 รีเฟรช",

    # ─── Conflict Resolution & Defensive Programming ──────────────────────────
    # Deadline validation — enhanced
    "task_past_deadline_detailed": (
        "❌ กำหนดส่งต้องเป็นเวลาในอนาคต\n"
        "🕒 เวลาปัจจุบันของคุณ: **{current_time}**\n"
        "📅 เวลาที่คุณระบุ: **{input_time}**"
    ),
    "task_invalid_year": "❌ ปีที่ระบุไม่อยู่ในช่วงที่สมเหตุสมผล (ค.ศ. 2000 – ปัจจุบัน +10 ปี)",
    # Subtask integrity
    "subtask_deadline_exceeds_parent": (
        "❌ กำหนดส่งของ Subtask ({subtask_dl}) ต้องไม่เกินกำหนดส่งของงานหลัก ({parent_dl})"
    ),
    "subtask_parent_closed": "❌ ไม่สามารถเพิ่ม Subtask ให้กับงานที่เสร็จสิ้นหรือถูกยกเลิกแล้ว",
    # Duplicate task conflict embed
    "conflict_duplicate_title": "⚠️ ตรวจพบข้อขัดแย้ง: ชื่องานซ้ำกัน",
    "conflict_duplicate_desc": (
        "มีงานที่กำลังรอดำเนินการชื่อ **\"{existing_name}\"** (ID: **#{existing_id}**) อยู่แล้ว\n"
        "กำหนดส่งงานเดิม: **{existing_deadline}**\n\n"
        "กรุณาเลือกวิธีดำเนินการ:"
    ),
    # Conflict resolution buttons
    "btn_conflict_autorename": "🏷️ บันทึกเป็น \"{new_name}\"",
    "btn_conflict_force":      "⚡ ยืนยันสร้างชื่อซ้ำ",
    "btn_conflict_view":       "🔍 ดูงานเดิม",
    "btn_conflict_cancel":     "❌ ยกเลิก",
    # Conflict resolution outcomes
    "conflict_cancelled":       "❌ ยกเลิกการสร้าง Task เรียบร้อยแล้ว",
    "conflict_autorename_done": "✅ บันทึก Task ใหม่เป็น **\"{new_name}\"** สำเร็จ! ID: **#{task_id}**",
    # Edit validation
    "edit_past_deadline_blocked": (
        "❌ ไม่สามารถแก้ไขกำหนดส่งเป็นเวลาในอดีตได้\n"
        "🕒 เวลาปัจจุบันของคุณ: **{current_time}**\n"
        "📅 เวลาที่คุณระบุ: **{input_time}**"
    ),
}
