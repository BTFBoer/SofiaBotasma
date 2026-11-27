"""Telegram layer (python-telegram-bot v22, asyncio).

Responsibilities: access control, turning Telegram updates into
IncomingMessages, batching, human-timed delivery with the native typing
indicator, out-of-character commands, and scheduled jobs. All companion logic
lives in the engine. Long polling by default; webhook mode is a config switch.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReactionTypeEmoji,
    Update,
)
from telegram.constants import ChatAction, ChatType
from telegram.error import BadRequest, Conflict, Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    MessageReactionHandler,
    TypeHandler,
    filters,
)

from app.companion.coordinator import ChatCoordinator
from app.companion.engine import CompanionEngine, IncomingMessage, TurnPlan
from app.companion.style import split_for_telegram
from app.config import Settings
from app.controls import ControlService
from app.llm.provider import ImagePart, LLMProvider
from app.memory.database import Database
from app.memory.store import MemoryStore
from app.scheduler.proactive import TICK_MINUTES, ProactiveScheduler
from app.utils.logging import get_logger
from app.utils.timeutil import utcnow
from app.utils.timing import TypingIndicator, plan_timings

log = get_logger(__name__)

BOT_COMMANDS = [
    ("start", "Start Sofia"),
    ("memory", "View remembered information"),
    ("forget", "Remove a memory"),
    ("proactive", "Control spontaneous messages"),
    ("privacy", "Data and privacy information"),
    ("export", "Export your data"),
    ("reset", "Reset Sofia's memory"),
    ("about", "About Sofia"),
    ("help", "List commands"),
]

HELP_TEXT = (
    "⚙️ Out-of-character controls (Sofia doesn't see these):\n"
    "/memory — what's currently remembered\n"
    "/forget <words> — find and delete memories\n"
    "/proactive on|off — let Sofia occasionally text first (default off)\n"
    "/privacy — where your data lives and what's sent where\n"
    "/export — download everything as JSON\n"
    "/reset — erase history, memories and relationship state\n"
    "/about — what Sofia is\n\n"
    "Everything else you type is just conversation."
)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PHOTO_SIDE = 1600


def is_authorized(update: Update, allowed_user_id: int | None) -> bool:
    user = update.effective_user
    return allowed_user_id is not None and user is not None and user.id == allowed_user_id


def _forward_name(message: Message) -> str | None:
    origin = getattr(message, "forward_origin", None)
    if origin is None:
        return None
    for path in (("sender_user", "full_name"), ("sender_user_name",), ("sender_chat", "title"), ("chat", "title")):
        value: Any = origin
        for attr in path:
            value = getattr(value, attr, None)
            if value is None:
                break
        if value:
            return str(value)
    return "someone"


class SofiaBot:
    def __init__(
        self,
        settings: Settings,
        *,
        db: Database,
        store: MemoryStore,
        provider: LLMProvider,
        engine: CompanionEngine,
        controls: ControlService,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.store = store
        self.provider = provider
        self.engine = engine
        self.controls = controls
        self.rng = rng or random.Random()
        self.coordinator = ChatCoordinator(
            self._process_batch, debounce=settings.debounce_seconds, max_wait=settings.debounce_max_seconds
        )
        self._images: dict[int, list[ImagePart]] = {}
        self._background: set[asyncio.Task[Any]] = set()
        self.app: Application | None = None
        self.proactive: ProactiveScheduler | None = None
        self._conflict_logged_at = -1e9

    # ================================================================== wiring
    def build(self) -> Application:
        app = (
            ApplicationBuilder()
            .token(self.settings.telegram_bot_token)
            .post_init(self._post_init)
            .post_shutdown(self._post_shutdown)
            .build()
        )
        app.add_handler(TypeHandler(Update, self._gate), group=-1)
        for name, handler in (
            ("start", self.cmd_start),
            ("memory", self.cmd_memory),
            ("forget", self.cmd_forget),
            ("export", self.cmd_export),
            ("reset", self.cmd_reset),
            ("privacy", self.cmd_privacy),
            ("about", self.cmd_about),
            ("proactive", self.cmd_proactive),
            ("help", self.cmd_help),
        ):
            app.add_handler(CommandHandler(name, handler))
        app.add_handler(CallbackQueryHandler(self.on_callback))
        app.add_handler(MessageReactionHandler(self.on_reaction))
        new_messages = filters.UpdateType.MESSAGE
        app.add_handler(MessageHandler(new_messages & filters.COMMAND, self.cmd_unknown))
        app.add_handler(MessageHandler(new_messages & ~filters.COMMAND & ~filters.StatusUpdate.ALL, self.on_message))
        app.add_error_handler(self._on_error)
        self.app = app
        return app

    async def _post_init(self, app: Application) -> None:
        await self.db.connect()
        if self.settings.keep_images:
            self.settings.image_dir.mkdir(parents=True, exist_ok=True)
        try:
            await app.bot.set_my_commands([BotCommand(c, d) for c, d in BOT_COMMANDS])
        except TelegramError:
            log.warning("could not set bot commands", exc_info=True)

        chat_id = self.settings.allowed_telegram_user_id
        assert chat_id is not None
        self.proactive = ProactiveScheduler(
            self.settings, self.store, self.engine, self.controls, self.send_plan, chat_id, rng=self.rng
        )
        jq = app.job_queue
        if jq is None:
            log.warning("JobQueue unavailable (install python-telegram-bot[job-queue]); proactive messages disabled")
        else:
            jq.run_repeating(self._proactive_job, interval=TICK_MINUTES * 60, first=600, job_kwargs={"jitter": 240})
            jq.run_repeating(self._maintenance_job, interval=3600, first=900)
            jq.run_repeating(self._heartbeat_job, interval=60, first=1)
        me = await app.bot.get_me()
        log.info(
            "Sofia is online",
            extra={"bot": me.username, "model": self.settings.llm_model, "mode": self.settings.telegram_mode},
        )

    async def _post_shutdown(self, app: Application) -> None:
        await self.coordinator.shutdown()
        for task in list(self._background):
            task.cancel()
        await self.provider.aclose()
        await self.db.close()

    def run(self) -> None:
        app = self.build()
        allowed = Update.ALL_TYPES
        if self.settings.telegram_mode == "webhook":
            assert self.settings.webhook_url
            path = hashlib.sha256(self.settings.telegram_bot_token.encode()).hexdigest()[:24]
            app.run_webhook(
                listen=self.settings.webhook_listen,
                port=self.settings.webhook_port,
                url_path=path,
                webhook_url=f"{self.settings.webhook_url.rstrip('/')}/{path}",
                secret_token=self.settings.webhook_secret,
                allowed_updates=allowed,
            )
        else:
            # A few retries at startup: a laptop's Wi-Fi is often still connecting.
            app.run_polling(allowed_updates=allowed, drop_pending_updates=False, bootstrap_retries=4)

    # ================================================================== gate
    async def _gate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Runs before every handler. Unauthorized updates never reach anything else."""
        user = update.effective_user
        if not is_authorized(update, self.settings.allowed_telegram_user_id):
            if user is not None:
                log.warning("ignored update from unauthorized user", extra={"user_id": user.id})
                if self.settings.unauthorized_reply and update.effective_message is not None:
                    try:
                        await update.effective_message.reply_text(self.settings.unauthorized_reply)
                    except TelegramError:
                        pass
            raise ApplicationHandlerStop
        chat = update.effective_chat
        if chat is not None and chat.type != ChatType.PRIVATE:
            raise ApplicationHandlerStop
        if not await self.store.mark_update_processed(update.update_id):
            log.info("duplicate update ignored", extra={"update_id": update.update_id})
            raise ApplicationHandlerStop

    def _authorized(self, update: Update) -> bool:
        # Defense in depth: every handler re-checks, even though the gate already did.
        return is_authorized(update, self.settings.allowed_telegram_user_id)

    # ================================================================== conversation
    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update) or update.effective_message is None or update.effective_chat is None:
            return
        message = update.effective_message
        chat_id = update.effective_chat.id
        incoming = await self._to_incoming(message, context)
        local_id = await self.engine.record_incoming(chat_id, incoming)
        if local_id is None:
            return  # duplicate
        if incoming.images:
            self._images[local_id] = incoming.images
            if self.settings.keep_images:
                for i, image in enumerate(incoming.images):
                    (self.settings.image_dir / f"{local_id}_{i}.jpg").write_bytes(image.data)
        self.coordinator.submit(chat_id, local_id)

    async def _download(self, file_id: str, context: ContextTypes.DEFAULT_TYPE) -> bytes | None:
        try:
            tg_file = await context.bot.get_file(file_id)
            return bytes(await tg_file.download_as_bytearray())
        except TelegramError:
            log.warning("file download failed", exc_info=True)
            return None

    async def _to_incoming(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> IncomingMessage:
        text = message.text or message.caption or ""
        kind = "text"
        images: list[ImagePart] = []
        caption = f" {message.caption}" if message.caption else ""

        if message.photo:
            kind = "photo"
            if self.settings.vision_enabled and self.provider.supports_vision:
                sizes = [p for p in message.photo if max(p.width, p.height) <= MAX_PHOTO_SIDE] or [message.photo[-1]]
                data = await self._download(sizes[-1].file_id, context)
                if data:
                    images.append(ImagePart(data, "image/jpeg"))
        elif message.document and (message.document.mime_type or "").startswith("image/"):
            kind = "photo"
            doc = message.document
            if self.settings.vision_enabled and (doc.file_size or 0) <= MAX_IMAGE_BYTES:
                data = await self._download(doc.file_id, context)
                if data:
                    images.append(ImagePart(data, doc.mime_type or "image/jpeg"))
        elif message.voice:
            kind = "voice"
            text = ""
            if self.provider.can_transcribe:
                data = await self._download(message.voice.file_id, context)
                if data:
                    text = await self.provider.transcribe(data, "voice.ogg") or ""
        elif message.sticker:
            kind = "sticker"
            text = message.sticker.emoji or "a sticker"
        elif message.audio:
            kind = "other"
            who = " – ".join(x for x in (message.audio.performer, message.audio.title) if x)
            text = f"[he shared an audio file{': ' + who if who else ''}]{caption}"
        elif message.animation:
            kind = "other"
            text = f"[he sent a GIF]{caption}"
        elif message.video:
            kind = "other"
            text = f"[he sent a video — she can't watch videos here]{caption}"
        elif message.video_note:
            kind = "other"
            text = "[he sent a round video message — she can't watch it here]"
        elif message.location:
            kind = "other"
            text = "[he shared a location]"
        elif message.contact:
            kind = "other"
            text = "[he shared a contact card]"
        elif message.poll:
            kind = "other"
            text = f"[he sent a poll: {message.poll.question}]"
        elif message.document:
            kind = "other"
            text = f"[he sent a file: {message.document.file_name or 'document'}]{caption}"
        elif not text:
            kind = "other"
            text = "[he sent something she can't open here]"

        reply_to = None
        if message.reply_to_message is not None:
            target = message.reply_to_message
            from_bot = target.from_user is not None and target.from_user.id == context.bot.id
            reply_to = {
                "who": "sofia" if from_bot else "bram",
                "text": target.text or target.caption or "",
                "telegram_message_id": target.message_id,
                "quote": message.quote.text if getattr(message, "quote", None) else None,
            }
        return IncomingMessage(
            telegram_message_id=message.message_id,
            text=text,
            kind=kind,
            images=images,
            reply_to=reply_to,
            forwarded_from=_forward_name(message),
            sent_at=message.date or utcnow(),
        )

    async def on_reaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update) or update.message_reaction is None:
            return
        reaction = update.message_reaction
        old = {getattr(r, "emoji", None) for r in reaction.old_reaction or ()}
        added = [getattr(r, "emoji", None) for r in reaction.new_reaction or () if getattr(r, "emoji", None) not in old]
        for emoji in [e for e in added if e]:
            await self.engine.record_user_reaction(reaction.chat.id, reaction.message_id, emoji)

    async def _process_batch(self, chat_id: int, batch_ids: list[int]) -> None:
        assert self.app is not None
        started = time.monotonic() - min(self.settings.debounce_seconds, 2.0)
        images = {i: self._images.pop(i, []) for i in batch_ids}
        typing = TypingIndicator(lambda: self.app.bot.send_chat_action(chat_id, ChatAction.TYPING))  # type: ignore[union-attr]
        await asyncio.sleep(self.rng.uniform(0.2, 0.9))  # a beat before she starts typing
        typing.start()
        try:
            plan = await self.engine.plan_reply(chat_id, batch_ids, images)
            # He added something while she was typing: re-read everything once.
            extra = self.coordinator.take_pending(chat_id)
            if extra and plan.kind in ("reply", "fallback"):
                batch_ids = [*batch_ids, *extra]
                images.update({i: self._images.pop(i, []) for i in extra})
                plan = await self.engine.plan_reply(chat_id, batch_ids, images)
        except Exception:
            await typing.stop()
            raise
        await self.send_plan(plan, typing=typing, already_elapsed=time.monotonic() - started)
        if plan.kind == "reply":
            self._spawn(self.engine.maintenance(chat_id))

    # ================================================================== sending
    async def send_plan(
        self, plan: TurnPlan, *, typing: TypingIndicator | None = None, already_elapsed: float = 0.0
    ) -> bool:
        assert self.app is not None
        bot = self.app.bot
        chat_id = plan.chat_id
        typing = typing or TypingIndicator(lambda: bot.send_chat_action(chat_id, ChatAction.TYPING))
        timings = plan_timings(
            plan.incoming_text, plan.bubbles, already_elapsed=already_elapsed, weighty=plan.weighty, rng=self.rng
        )
        delivered = False
        try:
            if plan.reaction and plan.react_to_telegram_id is not None:
                try:
                    await bot.set_message_reaction(chat_id, plan.react_to_telegram_id, ReactionTypeEmoji(plan.reaction))
                    await self.engine.record_sofia_reaction(plan, plan.reaction)
                    delivered = True
                except TelegramError:
                    log.info("could not set reaction", exc_info=True)
            for bubble, timing in zip(plan.bubbles, timings, strict=True):
                if timing.pause_before > 0:
                    await typing.stop()
                    await asyncio.sleep(timing.pause_before)
                typing.start()
                await asyncio.sleep(timing.typing)
                for chunk in split_for_telegram(bubble):
                    sent = await self._send_text(chat_id, chunk)
                    if sent is None:
                        continue
                    delivered = True
                    if not plan.ooc:
                        await self.engine.record_outgoing(plan, chunk, sent.message_id)
        finally:
            await typing.stop()
        if delivered:
            await self.engine.apply(plan)
        return delivered

    async def _send_text(self, chat_id: int, text: str) -> Message | None:
        assert self.app is not None
        for attempt in range(4):
            try:
                return await self.app.bot.send_message(chat_id, text)
            except RetryAfter as exc:
                wait = exc.retry_after
                seconds = wait.total_seconds() if isinstance(wait, timedelta) else float(wait)
                await asyncio.sleep(seconds + 0.5)
            except (TimedOut, NetworkError):
                await asyncio.sleep(1.5 * (attempt + 1))
            except Forbidden:
                log.warning("bot was blocked by the user")
                return None
            except BadRequest:
                log.exception("telegram rejected a message")
                return None
        log.error("giving up sending a message after retries")
        return None

    async def _ooc(self, update: Update, text: str, **kwargs: Any) -> None:
        if update.effective_message is None:
            return
        for chunk in split_for_telegram(text):
            await update.effective_message.reply_text(chunk, **kwargs)

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    # ================================================================== commands
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update) or update.effective_chat is None:
            return
        chat_id = update.effective_chat.id
        first_time = await self.store.count_messages(chat_id) == 0
        if not first_time:
            await self._ooc(update, "⚙️ Sofia's here. Just talk — /help lists the out-of-character controls.")
            return
        await self._ooc(
            update,
            "⚙️ Private chat with Sofia, a fictional AI character (/about). Talk to her like you'd text anyone. "
            "Out-of-character controls: /help.",
        )
        typing = TypingIndicator(lambda: context.bot.send_chat_action(chat_id, ChatAction.TYPING))
        await asyncio.sleep(self.rng.uniform(1.0, 2.5))
        typing.start()
        try:
            plan = await self.engine.plan_opener(chat_id)
        except Exception:
            await typing.stop()
            raise
        if plan.kind != "opener":
            await typing.stop()
            return  # model unavailable: she'll simply answer his first message
        await self.send_plan(plan, typing=typing)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._ooc(update, HELP_TEXT)

    async def cmd_about(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._ooc(update, "⚙️ " + self.controls.about_text())

    async def cmd_privacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._ooc(update, self.controls.privacy_text())

    async def cmd_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._ooc(update, await self.controls.memory_summary())

    async def cmd_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._ooc(update, "⚙️ Unknown command. /help lists what exists.")

    async def cmd_proactive(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        arg = (context.args[0].lower() if context.args else "").strip()
        if arg in {"on", "aan", "true", "1"}:
            await self.controls.set_proactive(True)
            await self._ooc(
                update,
                "⚙️ Spontaneous messages: ON. Sofia may occasionally text first — at most twice a day, usually "
                "not at all, never at night, never twice in a row without a reply from you.",
            )
        elif arg in {"off", "uit", "false", "0"}:
            await self.controls.set_proactive(False)
            await self._ooc(update, "⚙️ Spontaneous messages: OFF. Sofia only replies.")
        else:
            state = "ON" if await self.controls.proactive_enabled() else "OFF"
            await self._ooc(update, f"⚙️ Spontaneous messages are {state}. Use /proactive on or /proactive off.")

    async def cmd_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update) or update.effective_message is None:
            return
        data = await self.controls.export_json()
        stamp = utcnow().strftime("%Y%m%d-%H%M")
        await update.effective_message.reply_document(
            document=data,
            filename=f"sofia-export-{stamp}.json",
            caption="⚙️ Everything stored locally: chat log, memories, episodes, threads, state. Keep it private.",
        )

    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        token = self.controls.request_reset()
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Yes, erase everything", callback_data=f"rs:{token}:y"),
                    InlineKeyboardButton("Cancel", callback_data=f"rs:{token}:n"),
                ]
            ]
        )
        await self._ooc(
            update,
            "⚠️ This permanently erases the conversation history, all learned memories, episodes, open threads and "
            "the relationship state. Sofia will start from zero. Settings are kept.\n\nAre you sure? (expires in 5 min)",
            reply_markup=keyboard,
        )

    async def cmd_forget(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        query = " ".join(context.args or []).strip()
        if not query:
            await self._ooc(update, "⚙️ Usage: /forget <words>  — e.g. /forget levenslang")
            return
        matches = await self.controls.find_forget_matches(query)
        if not matches:
            await self._ooc(update, "⚙️ Nothing in memory matches that.")
            return
        token = self.controls.request_forget(matches)
        lines = ["⚙️ Matching memories:"]
        for i, match in enumerate(matches, start=1):
            label = "moment" if match.kind == "episode" else "memory"
            lines.append(f"{i}. ({label}) {match.text[:200]}")
        lines.append(
            "\nDelete which? (The raw chat log still contains the original messages; /reset erases those too.)"
        )
        buttons = [
            InlineKeyboardButton(str(i), callback_data=f"fg:{token}:{i - 1}") for i in range(1, len(matches) + 1)
        ]
        rows = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
        rows.append(
            [
                InlineKeyboardButton("All of these", callback_data=f"fg:{token}:all"),
                InlineKeyboardButton("Cancel", callback_data=f"fg:{token}:n"),
            ]
        )
        await self._ooc(update, "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or not self._authorized(update):
            return
        await query.answer()
        try:
            action, token, arg = (query.data or "").split(":", 2)
        except ValueError:
            return
        if action == "rs":
            if arg != "y":
                self.controls.cancel(token)
                await query.edit_message_text("⚙️ Reset cancelled. Nothing was erased.")
                return
            if await self.controls.confirm_reset(token):
                if update.effective_chat is not None:
                    self.coordinator.clear(update.effective_chat.id)
                self._images.clear()
                await query.edit_message_text("⚙️ Erased. Sofia starts from zero the next time you write.")
            else:
                await query.edit_message_text("⚙️ That confirmation expired. Send /reset again.")
        elif action == "fg":
            if arg == "n":
                self.controls.cancel(token)
                await query.edit_message_text("⚙️ Nothing deleted.")
                return
            index = None if arg == "all" else int(arg)
            deleted = await self.controls.confirm_forget(token, index)
            if deleted < 0:
                await query.edit_message_text("⚙️ That list expired. Send /forget again.")
            else:
                await query.edit_message_text(f"⚙️ Deleted {deleted} item{'s' if deleted != 1 else ''}.")

    # ================================================================== jobs
    async def _proactive_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self.proactive is None:
            return
        chat_id = self.settings.allowed_telegram_user_id
        assert chat_id is not None
        if self.coordinator.is_busy(chat_id):
            return
        async with self.coordinator.lock(chat_id):
            await self.proactive.tick()

    async def _maintenance_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self.settings.allowed_telegram_user_id
        assert chat_id is not None
        last = await self.store.last_message(chat_id)
        if last is not None and utcnow() - last.created_at > timedelta(hours=2):
            await self.engine.maintenance(chat_id, idle=True)
        await self.store.prune_processed_updates()

    async def _heartbeat_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        path: Path = self.settings.heartbeat_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(int(time.time())), encoding="utf-8")
        except OSError:
            log.warning("could not write heartbeat", exc_info=True)

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        err = context.error
        if update is None and isinstance(err, Conflict):
            # Another copy of Sofia polls the same bot (second window or second computer).
            now = time.monotonic()
            if now - self._conflict_logged_at > 300:
                self._conflict_logged_at = now
                log.warning("Sofia draait OOK in een ander venster of op een andere computer. Sluit er een van.")
            return
        if update is None and isinstance(err, NetworkError):
            # Polling hiccup (Wi-Fi gone, laptop woke up): python-telegram-bot retries by itself.
            log.warning("Telegram is even niet bereikbaar (%s). Ik probeer het vanzelf opnieuw.", err)
            return
        log.error("unhandled error in handler", exc_info=err)
        if isinstance(update, Update) and update.callback_query is None and update.effective_message is not None:
            text = update.effective_message.text or ""
            if text.startswith("/") and self._authorized(update):
                try:
                    await update.effective_message.reply_text("⚙️ Something went wrong with that command.")
                except TelegramError:
                    pass


def build_setup_app(settings: Settings) -> Application:
    """ALLOWED_TELEGRAM_USER_ID not set: tell whoever writes their numeric id, nothing else."""

    async def reply_with_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.effective_message is None:
            return
        log.info("setup mode: user wrote to the bot", extra={"user_id": user.id})
        await update.effective_message.reply_text(
            f"Setup mode. Your Telegram user ID is {user.id}\n\n"
            f"Put ALLOWED_TELEGRAM_USER_ID={user.id} in your .env and restart the bot."
        )

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()
    app.add_handler(MessageHandler(filters.ALL, reply_with_id))
    return app
