# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class FacebookMessengerWebhookController(http.Controller):
    """
    Meta Messenger Webhook (Facebook Page)
    - GET: verification (hub.*)
    - POST: incoming messages
    Verify token comes from social.channel.webhook_secret
    """

    @http.route("/facebook/webhook", type="http", auth="none", methods=["GET", "POST"], csrf=False)
    def facebook_webhook(self, **kwargs):
        # -------------------------
        # 1) Webhook verification
        # -------------------------
        if request.httprequest.method == "GET":
            mode = kwargs.get("hub.mode")
            token = kwargs.get("hub.verify_token")
            challenge = kwargs.get("hub.challenge")

            fb_channel = request.env["social.channel"].sudo().search(
                [
                    "|",
                    ("channel_type", "in", ["messenger", "facebook"]),
                    ("code", "in", ["messenger", "facebook", "cm_messenger", "cm_facebook"]),
                ],
                limit=1,
            )
            expected = (fb_channel.webhook_secret if fb_channel else "") or ""
            if mode == "subscribe" and token == expected:
                return str(challenge or "")
            return "Verification failed"

        # -------------------------
        # 2) Webhook receive
        # -------------------------
        try:
            payload = json.loads((request.httprequest.data or b"{}").decode("utf-8"))
        except Exception:
            return "bad request"

        # Messenger page webhook usually uses object="page"
        if payload.get("object") not in ("page", "facebook"):
            return "ok"

        Channel = request.env["social.channel"].sudo()
        Partner = request.env["res.partner"].sudo()
        Conversation = request.env["whatsapp.conversation"].sudo()
        Log = request.env["whatsapp.message.log"].sudo()

        for entry in payload.get("entry", []):
            page_id = str(entry.get("id") or "").strip()
            fb_channel = False
            if page_id:
                fb_channel = Channel.search(
                    [
                        ("facebook_page_id", "=", page_id),
                        "|",
                        ("channel_type", "in", ["messenger", "facebook"]),
                        ("code", "in", ["messenger", "facebook", "cm_messenger", "cm_facebook"]),
                    ],
                    limit=1,
                )
            if not fb_channel:
                fb_channel = Channel.search(
                    [
                        "|",
                        ("channel_type", "in", ["messenger", "facebook"]),
                        ("code", "in", ["messenger", "facebook", "cm_messenger", "cm_facebook"]),
                    ],
                    limit=1,
                )

            for event in entry.get("messaging", []):
                if event.get("delivery") or event.get("read"):
                    continue

                sender_id = (event.get("sender") or {}).get("id")     # PSID
                msg = event.get("message") or {}
                if msg.get("is_echo"):
                    continue
                text = msg.get("text")
                mid = msg.get("mid")

                if not text:
                    attachments = msg.get("attachments") or []
                    if attachments:
                        att_type = (attachments[0] or {}).get("type") or "attachment"
                        text = f"[{att_type.capitalize()}]"

                # Ignore delivery/read echoes and non-text events
                if not sender_id or not text:
                    continue

                _logger.info("FB incoming message sender=%s mid=%s text=%s", sender_id, mid, text)

                # Find or create partner (recommended: use facebook_psid if you add it)
                partner = False
                if "facebook_psid" in Partner._fields:
                    partner = Partner.search([("facebook_psid", "=", sender_id)], limit=1)

                if not partner:
                    partner = Partner.create({
                        "name": f"Facebook {sender_id}",
                        **({"facebook_psid": sender_id} if "facebook_psid" in Partner._fields else {}),
                    })

                # Create or get conversation
                conv = Conversation.get_or_create_messenger_conversation(
                    partner=partner,
                    external_user_id=sender_id,
                    channel_id=(fb_channel.id if fb_channel else None),
                )

                # Create incoming log
                vals = {
                    "partner_id": partner.id,
                    "phone": False,
                    "message": text,
                    "status": "received",
                    "direction": "incoming",
                    "is_read": False,
                    "message_id": mid,
                    "external_user_id": sender_id,
                    "conversation_id": conv.id,
                }
                if fb_channel:
                    vals["channel_id"] = fb_channel.id

                # If your whatsapp.message.log has channel_type stored/computed, this is optional
                if "channel_type" in Log._fields:
                    vals["channel_type"] = "messenger"

                Log.create(vals)

        return "ok"
