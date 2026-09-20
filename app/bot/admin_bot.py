from __future__ import annotations

from datetime import UTC, datetime

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..services.admin_service import AdminService
from ..services.nyaa_service import NyaaSearchService


class AdminBot:
    def __init__(self, settings, mongo, admin_service: AdminService):
        self.settings = settings
        self.mongo = mongo
        self.admin_service = admin_service
        self.nyaa = NyaaSearchService()
        self.admin_ids = {int(value.strip()) for value in settings.admin_user_ids.split(",") if value.strip().lstrip("-").isdigit()}
        self.client: Client | None = None
        self._manual_waiting: set[int] = set()
        self._search_cache: dict[int, tuple[list[dict], int]] = {}

    def _allowed(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.admin_ids

    def _menu(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[InlineKeyboardButton("📊 System Status", callback_data="status"), InlineKeyboardButton("🎬 Recent Uploads", callback_data="recent")], [InlineKeyboardButton("🚀 Manual Add", callback_data="manual"), InlineKeyboardButton("⚠️ Error Logs", callback_data="errors")], [InlineKeyboardButton("🔄 Restart Services", callback_data="restart")]])

    def _search_keyboard(self, page: int, count: int) -> InlineKeyboardMarkup:
        buttons = [[InlineKeyboardButton("⬅️ Prev", callback_data="ns_prev"), InlineKeyboardButton("Next ➡️", callback_data="ns_next")]]
        for index in range(page * 5, min((page + 1) * 5, count)):
            buttons.append([InlineKeyboardButton(f"🔍 Inspect {index + 1}", callback_data=f"ni_{index}"), InlineKeyboardButton(f"⬇️ Download {index + 1}", callback_data=f"nd_{index}")])
        return InlineKeyboardMarkup(buttons)

    def _search_text(self, results: list[dict], page: int) -> str:
        items = results[page * 5:(page + 1) * 5]
        if not items:
            return "No Nyaa results found."
        return "🔎 **Nyaa Search**\n\n" + "\n\n".join(f"{page * 5 + index + 1}. {item['title']}\nTags: {', '.join(item['tags']) or 'none'}\nSize: {item['size']} · Seeders: {item['seeders']}" for index, item in enumerate(items)) + f"\n\nPage {page + 1}/{(len(results) + 4) // 5}"

    async def start(self) -> None:
        if not self.settings.bot_token or "replace-me" in self.settings.bot_token.lower() or not self.admin_ids:
            return
        self.client = Client("aniz-admin-bot", api_id=self.settings.api_id, api_hash=self.settings.api_hash, bot_token=self.settings.bot_token, in_memory=True)

        @self.client.on_message(filters.command("start") & filters.private)
        async def start_handler(_, message: Message):
            if self._allowed(message.from_user.id): await message.reply_text("Aniz Admin Panel", reply_markup=self._menu())

        @self.client.on_message(filters.command("search") & filters.private)
        async def search_handler(_, message: Message):
            if not self._allowed(message.from_user.id): return
            query = message.text.split(maxsplit=1)[1].strip() if message.text and len(message.text.split(maxsplit=1)) > 1 else ""
            if not query:
                await message.reply_text("Usage: /search anime title")
                return
            await message.reply_text("Searching Nyaa.si...")
            results = await self.nyaa.search(query, 500)
            self._search_cache[message.from_user.id] = (results, 0)
            await message.reply_text(self._search_text(results, 0), reply_markup=self._search_keyboard(0, len(results)), disable_web_page_preview=True)

        @self.client.on_callback_query()
        async def callback_handler(_, callback: CallbackQuery):
            if not self._allowed(callback.from_user.id):
                await callback.answer("Not authorized", show_alert=True); return
            await callback.answer()
            action = callback.data
            if action in {"ns_prev", "ns_next"}:
                results, page = self._search_cache.get(callback.from_user.id, ([], 0))
                page = max(0, page - 1) if action == "ns_prev" else min(max(0, (len(results) - 1) // 5), page + 1)
                self._search_cache[callback.from_user.id] = (results, page)
                await callback.message.edit_text(self._search_text(results, page), reply_markup=self._search_keyboard(page, len(results)), disable_web_page_preview=True)
                return
            if action.startswith(("ni_", "nd_")):
                results, _ = self._search_cache.get(callback.from_user.id, ([], 0))
                index = int(action.split("_", 1)[1])
                if index >= len(results): return
                item = results[index]
                if action.startswith("ni_"):
                    files = await self.nyaa.inspect(item["nyaa_id"])
                    text = "📁 **File List**\n" + ("\n".join(f"{file['name']} — {file['size']}" for file in files) or "No file rows detected")
                    await callback.message.reply_text(text)
                else:
                    await self.mongo.db.manual_jobs.insert_one({"source": item["magnet"], "title": item["title"], "tags": item["tags"], "nyaa_id": item["nyaa_id"], "status": "PENDING", "created_at": datetime.now(UTC)})
                    await callback.message.reply_text(f"Queued: {item['title']}")
                return
            if action == "status":
                stats = await self.admin_service.stats(self.mongo)
                await callback.message.edit_text("📊 **System Status**\n" + "\n".join(f"{key}: `{value}`" for key, value in stats.items()), reply_markup=self._menu())
            elif action == "recent":
                docs = await self.mongo.db.episodes.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(length=5)
                base = self.settings.api_public_base_url.rstrip("/")
                text = "🎬 **Recent Uploads**\n" + ("\n".join(f"• {d.get('anime_id')} ep {d.get('episode_number')} {d.get('quality')}\n{base}/api/v1/stream/{d.get('stream_slug')}" for d in docs) or "No uploads yet")
                await callback.message.edit_text(text, reply_markup=self._menu(), disable_web_page_preview=True)
            elif action == "manual":
                self._manual_waiting.add(callback.from_user.id)
                await callback.message.edit_text("🚀 Send a magnet link or Nyaa URL in your next private message.", reply_markup=self._menu())
            elif action == "errors":
                lines = self.admin_service.tail("errors.log", 30)
                await callback.message.edit_text("⚠️ **Recent errors**\n```\n" + ("\n".join(lines)[-3500:] or "No errors") + "\n```", reply_markup=self._menu())
            elif action == "restart":
                await callback.message.edit_text("🔄 Use Docker/systemd restart policy. Downloads and sessions are preserved.", reply_markup=self._menu())

        @self.client.on_message(filters.private & ~filters.command("start") & ~filters.command("search"))
        async def manual_handler(_, message: Message):
            user_id = message.from_user.id if message.from_user else None
            if not self._allowed(user_id) or user_id not in self._manual_waiting: return
            source = (message.text or "").strip()
            self._manual_waiting.discard(user_id)
            if not source.startswith(("magnet:", "http://", "https://")):
                await message.reply_text("Invalid source. Send a magnet link or Nyaa URL.", reply_markup=self._menu()); return
            result = await self.mongo.db.manual_jobs.insert_one({"source": source, "status": "PENDING", "created_at": datetime.now(UTC)})
            await message.reply_text(f"Queued manual job `{result.inserted_id}`", reply_markup=self._menu())

        await self.client.start()

    async def stop(self) -> None:
        if self.client:
            await self.client.stop()
            self.client = None
