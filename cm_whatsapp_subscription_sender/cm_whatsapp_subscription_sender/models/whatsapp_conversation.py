# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappConversation(models.Model):
    _name = "whatsapp.conversation"
    _description = "WhatsApp Conversation"
    _order = "last_message_date desc"

    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        required=True,
        ondelete="cascade",
    )

    # Not required globally: Instagram conversations do not have a phone number.
    phone = fields.Char(string="WhatsApp Number", index=True)

    # === Multi-channel ===
    platform = fields.Selection([
        ("whatsapp", "WhatsApp"),
        ("instagram", "Instagram"),
        ("messenger", "Messenger"),
    ], string="Platform", default="whatsapp", required=True, index=True)

    channel_id = fields.Many2one("social.channel", string="Channel")

    # For Instagram: store sender scoped id (IGSID) here.
    external_user_id = fields.Char(string="External User ID", index=True)

    # Conversation preview
    last_message = fields.Text(string="Last Message", compute="_compute_last_message", store=True)
    last_message_date = fields.Datetime(string="Last Activity", compute="_compute_last_message", store=True)
    unread_count = fields.Integer(string="Unread", compute="_compute_unread_count")

    # 24-hour window tracking (for WhatsApp Business API policy)
    last_customer_message_date = fields.Datetime(
        string="Last Customer Reply",
        help="When the customer last messaged us. Free-text replies are allowed within 24 hours.",
    )
    is_24h_window_active = fields.Boolean(string="24h Window Active", compute="_compute_is_24h_window_active")

    # Messages
    message_ids = fields.One2many("whatsapp.message.log", "conversation_id", string="Messages")

    # DO NOT keep unique(phone) because Instagram conversations would have phone = False.
    _sql_constraints = []

    # --------------------------
    # Constraints (platform rules)
    # --------------------------
    @api.constrains("platform", "phone", "external_user_id")
    def _check_required_identifiers(self):
        for conv in self:
            if conv.platform == "whatsapp":
                if not conv.phone:
                    raise ValidationError("Phone is required for WhatsApp conversations.")
            elif conv.platform == "instagram":
                if not conv.external_user_id:
                    raise ValidationError("External User ID is required for Instagram conversations.")
            elif conv.platform == "messenger":
                if not conv.external_user_id:
                    raise ValidationError("External User ID is required for Messenger conversations.")

    @api.constrains("platform", "phone")
    def _check_unique_whatsapp_phone(self):
        """Enforce uniqueness of phone only for WhatsApp conversations."""
        for conv in self.filtered(lambda c: c.platform == "whatsapp" and c.phone):
            dup = self.search([
                ("id", "!=", conv.id),
                ("platform", "=", "whatsapp"),
                ("phone", "=", conv.phone),
            ], limit=1)
            if dup:
                raise ValidationError("A WhatsApp conversation with this phone number already exists!")

    @api.constrains("platform", "external_user_id", "channel_id")
    def _check_unique_instagram_external(self):
        """
        Enforce uniqueness for Instagram.
        Prefer uniqueness by (channel_id + external_user_id) to support multiple IG accounts.
        """
        for conv in self.filtered(lambda c: c.platform == "instagram" and c.external_user_id):
            domain = [
                ("id", "!=", conv.id),
                ("platform", "=", "instagram"),
                ("external_user_id", "=", conv.external_user_id),
            ]
            if conv.channel_id:
                domain.append(("channel_id", "=", conv.channel_id.id))
            dup = self.search(domain, limit=1)
            if dup:
                raise ValidationError("An Instagram conversation with this External User ID already exists!")

    @api.constrains("platform", "external_user_id", "channel_id")
    def _check_unique_messenger_external(self):
        """
        Enforce uniqueness for Messenger.
        Prefer uniqueness by (channel_id + external_user_id) to support multiple pages.
        """
        for conv in self.filtered(lambda c: c.platform == "messenger" and c.external_user_id):
            domain = [
                ("id", "!=", conv.id),
                ("platform", "=", "messenger"),
                ("external_user_id", "=", conv.external_user_id),
            ]
            if conv.channel_id:
                domain.append(("channel_id", "=", conv.channel_id.id))
            dup = self.search(domain, limit=1)
            if dup:
                raise ValidationError("A Messenger conversation with this External User ID already exists!")

    # --------------------------
    # Compute fields
    # --------------------------
    def _compute_is_24h_window_active(self):
        """WhatsApp-only concept; for Instagram keep it False."""
        now = fields.Datetime.now()
        window_start = now - timedelta(hours=24)

        for conv in self:
            if conv.platform != "whatsapp":
                conv.is_24h_window_active = False
                continue

            is_active = False
            latest_incoming_date = None
            phone = conv.phone or ""

            # Method 1: stored date
            if conv.last_customer_message_date:
                window_end = conv.last_customer_message_date + timedelta(hours=24)
                if now <= window_end:
                    is_active = True

            # Method 2: linked messages
            if not is_active and conv.message_ids:
                incoming_msgs = conv.message_ids.filtered(
                    lambda m: m.direction == "incoming" and m.create_date and m.create_date >= window_start
                )
                if incoming_msgs:
                    is_active = True
                    latest_incoming_date = max(m.create_date for m in incoming_msgs)

            # Method 3: search by phone pattern
            if not is_active and phone:
                phone_digits = "".join(c for c in phone if c.isdigit())
                phone_pattern = "%" + phone_digits[-9:] + "%" if len(phone_digits) >= 9 else "%" + phone_digits + "%"
                try:
                    incoming_msg = self.env["whatsapp.message.log"].sudo().search([
                        ("direction", "=", "incoming"),
                        ("create_date", ">=", window_start),
                        ("phone", "ilike", phone_pattern),
                    ], limit=1, order="create_date desc")
                    if incoming_msg:
                        is_active = True
                        latest_incoming_date = incoming_msg.create_date
                        if not incoming_msg.conversation_id:
                            incoming_msg.write({"conversation_id": conv.id})
                except Exception as e:
                    _logger.warning("Error searching messages for 24h window: %s", e)

            # Update stored date
            if latest_incoming_date:
                if (not conv.last_customer_message_date) or (latest_incoming_date > conv.last_customer_message_date):
                    try:
                        conv.sudo().write({"last_customer_message_date": latest_incoming_date})
                    except Exception as e:
                        _logger.warning("Error updating last_customer_message_date: %s", e)

            conv.is_24h_window_active = is_active

    @api.depends("message_ids", "message_ids.create_date", "message_ids.message")
    def _compute_last_message(self):
        for conv in self:
            last_msg = conv.message_ids.sorted(
                key=lambda r: r.create_date or fields.Datetime.from_string("1970-01-01"),
                reverse=True
            )[:1]
            if last_msg:
                msg = last_msg.message or ""
                conv.last_message = (msg[:50] + "...") if len(msg) > 50 else msg
                conv.last_message_date = last_msg.create_date
            else:
                conv.last_message = False
                conv.last_message_date = False

    def _compute_unread_count(self):
        for conv in self:
            conv.unread_count = len(conv.message_ids.filtered(lambda m: m.direction == "incoming" and not m.is_read))

    # --------------------------
    # Display
    # --------------------------
    def name_get(self):
        res = []
        for conv in self:
            if conv.platform == "instagram":
                label = f"{conv.partner_id.name} (IG: {conv.external_user_id})"
            elif conv.platform == "messenger":
                label = f"{conv.partner_id.name} (FB: {conv.external_user_id})"
            else:
                label = f"{conv.partner_id.name} ({conv.phone})"
            res.append((conv.id, label))
        return res

    # --------------------------
    # Utilities
    # --------------------------
    def action_refresh_24h_window(self):
        self.ensure_one()
        self.link_orphan_messages()
        self._compute_is_24h_window_active()
        return True

    def action_mark_as_read(self):
        """Mark all incoming messages of this conversation as read."""
        self.ensure_one()
        unread = self.message_ids.filtered(lambda m: m.direction == "incoming" and not m.is_read)
        if unread:
            unread.sudo().write({"is_read": True})
        return True

    def action_debug_24h(self):
        """
        Helper action to quickly inspect WhatsApp 24h window state.
        Kept simple for admins/functional users.
        """
        self.ensure_one()
        self._compute_is_24h_window_active()
        last_reply = self.last_customer_message_date or "N/A"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "24h Window Debug",
                "message": (
                    f"Conversation: {self.partner_id.name} | "
                    f"Platform: {self.platform} | "
                    f"Active: {'Yes' if self.is_24h_window_active else 'No'} | "
                    f"Last customer reply: {last_reply}"
                ),
                "type": "info",
                "sticky": True,
            },
        }

    def link_orphan_messages(self):
        """
        Link orphan message logs to this conversation.
        - WhatsApp: match by phone
        - Instagram: match by external_user_id
        """
        self.ensure_one()
        Log = self.env["whatsapp.message.log"].sudo()

        if self.platform == "instagram":
            if not self.external_user_id:
                return
            orphans = Log.search([
                ("conversation_id", "=", False),
                ("direction", "=", "incoming"),
                ("external_user_id", "=", self.external_user_id),
            ])
            if orphans:
                orphans.write({"conversation_id": self.id})
            return

        if self.platform == "messenger":
            if not self.external_user_id:
                return
            orphans = Log.search([
                ("conversation_id", "=", False),
                ("direction", "=", "incoming"),
                ("external_user_id", "=", self.external_user_id),
                ("channel_type", "in", ["messenger", "facebook"]),
            ])
            if orphans:
                orphans.write({"conversation_id": self.id})
            return

        phone_clean = "".join(c for c in (self.phone or "") if c.isdigit())
        phone_last9 = phone_clean[-9:] if len(phone_clean) >= 9 else phone_clean
        if not phone_last9:
            return

        orphans = Log.search([
            ("conversation_id", "=", False),
            "|", "|", "|",
            ("phone", "=", self.phone),
            ("phone", "=", phone_clean),
            ("phone", "like", phone_last9),
            ("phone", "=", "+" + phone_clean),
        ])
        if orphans:
            orphans.write({"conversation_id": self.id})

    @api.model
    def fix_all_conversations(self):
        for conv in self.search([]):
            conv.link_orphan_messages()
            conv._compute_is_24h_window_active()
        return True

    # --------------------------
    # Get or create conversations
    # --------------------------
    @api.model
    def get_or_create_conversation(self, partner, phone):
        """WhatsApp helper."""
        clean_phone = "".join(c for c in (phone or "") if c.isdigit() or c == "+")
        conv = self.search([("platform", "=", "whatsapp"), ("phone", "=", clean_phone)], limit=1)
        if not conv:
            clean_phone_no_plus = clean_phone.lstrip("+")
            conv = self.search([("platform", "=", "whatsapp"), ("phone", "like", clean_phone_no_plus)], limit=1)
        if not conv:
            conv = self.create({
                "partner_id": partner.id,
                "phone": clean_phone,
                "platform": "whatsapp",
            })
        return conv

    @api.model
    def get_or_create_instagram_conversation(self, partner, external_user_id, channel_id=None):
        """Instagram helper."""
        domain = [
            ("platform", "=", "instagram"),
            ("external_user_id", "=", external_user_id),
        ]
        if channel_id:
            domain.append(("channel_id", "=", channel_id))
        conv = self.search(domain, limit=1)
        if not conv:
            conv = self.create({
                "partner_id": partner.id,
                "platform": "instagram",
                "external_user_id": external_user_id,
                "channel_id": channel_id or False,
            })
        return conv

    @api.model
    def get_or_create_messenger_conversation(self, partner, external_user_id, channel_id=None):
        """Messenger helper."""
        domain = [
            ("platform", "=", "messenger"),
            ("external_user_id", "=", external_user_id),
        ]
        if channel_id:
            domain.append(("channel_id", "=", channel_id))
        conv = self.search(domain, limit=1)
        if not conv:
            conv = self.create({
                "partner_id": partner.id,
                "platform": "messenger",
                "external_user_id": external_user_id,
                "channel_id": channel_id or False,
            })
        return conv

    @api.model
    def get_or_create_conversation_by_phone(self, phone, name=None, partner_id=None):
        """
        RPC helper used by the chat UI to create/open a WhatsApp conversation.
        Returns a lightweight dict for JS.
        """
        phone = (phone or "").strip()
        if not phone:
            return {"status": "error", "message": "Missing phone number."}

        clean_phone = "".join(c for c in phone if c.isdigit() or c == "+")
        if not clean_phone:
            return {"status": "error", "message": "Invalid phone number."}

        Partner = self.env["res.partner"].sudo()

        partner = Partner.browse(int(partner_id)) if partner_id else None
        if not partner or not partner.exists():
            no_plus = clean_phone.lstrip("+")
            partner = (
                Partner.search([("mobile", "=", clean_phone)], limit=1)
                or Partner.search([("phone", "=", clean_phone)], limit=1)
                or Partner.search([("mobile", "like", no_plus)], limit=1)
                or Partner.search([("phone", "like", no_plus)], limit=1)
            )

        if not partner:
            partner = Partner.create({
                "name": (name or f"WhatsApp {clean_phone}"),
                "mobile": clean_phone,
            })

        conv = self.get_or_create_conversation(partner, clean_phone)
        return {
            "status": "success",
            "id": conv.id,
            "conversation_id": conv.id,
            "partner_id": partner.id,
            "phone": conv.phone,
            "platform": conv.platform,
        }

    # --------------------------
    # Messaging helpers (UI uses)
    # --------------------------
    @api.model
    def receive_incoming_message(self, phone=None, message_text=None, partner_id=None, message_id=None, **kwargs):
        """
        Create an incoming message log and update WhatsApp 24h window.
        Used by webhook controllers.
        """
        phone = (phone or "").strip()
        message_text = (message_text or "").strip()
        if not phone or not message_text:
            return {"status": "error", "message": "Missing phone or message_text."}

        Partner = self.env["res.partner"].sudo()
        Log = self.env["whatsapp.message.log"].sudo()

        partner = Partner.browse(int(partner_id)) if partner_id else None
        if not partner or not partner.exists():
            partner = Partner.search([("mobile", "=", phone)], limit=1) or Partner.search([("phone", "=", phone)], limit=1)
        if not partner:
            partner = Partner.create({"name": f"WhatsApp {phone}", "mobile": phone})

        conv = self.get_or_create_conversation(partner, phone)

        conv.sudo().write({"last_customer_message_date": fields.Datetime.now()})

        log = Log.create({
            "partner_id": partner.id,
            "phone": phone,
            "message": message_text,
            "status": "received",
            "direction": "incoming",
            "is_read": False,
            "message_id": message_id,
            "conversation_id": conv.id,
            "channel_id": conv.channel_id.id if conv.channel_id else False,
            "external_user_id": phone,
        })

        return {"status": "success", "message": "Received", "logid": log.id, "conversation_id": conv.id}

    @api.model
    def send_chat_message(self, partner_id=None, message_text=None, phone=None, **kwargs):
        """
        Basic sender entrypoint expected by your JS (`sendchatmessage` / `send_chat_message`).
        This method only logs + checks 24h window.
        Real WhatsApp API sending is handled by Odoo's whatsapp module (templates/composer).
        """
        message_text = (message_text or "").strip()
        phone = (phone or "").strip()

        if not message_text:
            return {"status": "error", "message": "Empty message."}
        if not phone and not partner_id:
            return {"status": "error", "message": "Missing phone or partner_id."}

        Partner = self.env["res.partner"].sudo()
        Log = self.env["whatsapp.message.log"].sudo()

        partner = Partner.browse(int(partner_id)) if partner_id else None
        if not partner or not partner.exists():
            partner = Partner.search([("mobile", "=", phone)], limit=1) or Partner.search([("phone", "=", phone)], limit=1)

        if not partner:
            partner = Partner.create({"name": f"WhatsApp {phone}", "mobile": phone})

        if not phone:
            phone = partner.mobile or partner.phone or ""

        if not phone:
            return {"status": "error", "message": "Partner has no phone/mobile."}

        conv = self.get_or_create_conversation(partner, phone)
        conv._compute_is_24h_window_active()

        # If 24h window not active => in real WA you must use templates.
        if not conv.is_24h_window_active:
            log = Log.create({
                "partner_id": partner.id,
                "phone": phone,
                "message": message_text,
                "status": "failed",
                "direction": "outgoing",
                "is_read": True,
                "failure_reason": "Outside 24-hour window. Use an approved WhatsApp template.",
                "conversation_id": conv.id,
                "channel_id": conv.channel_id.id if conv.channel_id else False,
                "external_user_id": phone,
            })
            return {"status": "error", "message": "Outside 24-hour window. Use template.", "logid": log.id}

        # Log as sent (your template sender + status webhooks will update real statuses)
        log = Log.create({
            "partner_id": partner.id,
            "phone": phone,
            "message": message_text,
            "status": "sent",
            "direction": "outgoing",
            "is_read": True,
            "conversation_id": conv.id,
            "channel_id": conv.channel_id.id if conv.channel_id else False,
            "external_user_id": phone,
        })
        return {"status": "success", "message": "Logged as sent.", "logid": log.id, "conversation_id": conv.id}

    @api.model
    def send_audio_message(self, partner_id=None, phone=None, attachment_id=None, conversation_id=None, channel_type=None, external_user_id=None, **kwargs):
        """
        Send an audio message: create log with media_type=audio and optional attachment.
        Used by the Social Inbox when user records and sends voice.
        Real API sending (WhatsApp/Instagram/Messenger) can be extended later.
        """
        phone = (phone or "").strip()
        if not attachment_id:
            return {"status": "error", "message": "Missing audio attachment."}

        Partner = self.env["res.partner"].sudo()
        Log = self.env["whatsapp.message.log"].sudo()
        Attachment = self.env["ir.attachment"].sudo()

        attachment = Attachment.browse(int(attachment_id))
        if not attachment.exists():
            return {"status": "error", "message": "Attachment not found."}

        partner = None
        if partner_id:
            partner = Partner.browse(int(partner_id))
        if not partner or not partner.exists():
            partner = Partner.search([("mobile", "=", phone)], limit=1) or Partner.search([("phone", "=", phone)], limit=1)
        if not partner:
            partner = Partner.create({"name": f"Audio {phone or 'Contact'}", "mobile": phone or ""})
        if not phone:
            phone = partner.mobile or partner.phone or ""

        conv = None
        if conversation_id:
            conv = self.browse(int(conversation_id))
        if not conv or not conv.exists():
            if phone:
                conv = self.get_or_create_conversation(partner, phone)
            elif external_user_id and channel_type in ("instagram", "messenger", "facebook"):
                platform = "messenger" if channel_type in ("messenger", "facebook") else "instagram"
                conv = self.get_or_create_messenger_conversation(partner, external_user_id) if platform == "messenger" else self.get_or_create_instagram_conversation(partner, external_user_id)
            else:
                conv = None
        if not conv:
            return {"status": "error", "message": "Could not resolve conversation."}

        channel_id = conv.channel_id.id if conv.channel_id else False
        ext_uid = external_user_id or phone or (conv.external_user_id if conv else "")

        log = Log.create({
            "partner_id": partner.id,
            "phone": phone or "",
            "message": "[Audio]",
            "status": "sent",
            "direction": "outgoing",
            "is_read": True,
            "conversation_id": conv.id,
            "channel_id": channel_id,
            "external_user_id": ext_uid,
            "media_type": "audio",
            "media_attachment_id": attachment.id,
            "media_filename": attachment.name,
        })
        return {"status": "success", "message": "Audio sent.", "logid": log.id, "conversation_id": conv.id}
