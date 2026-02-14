# -*- coding: utf-8 -*-
import json
import logging
from urllib.parse import quote

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class InstagramDMWebhookController(http.Controller):

    @http.route("/instagram/webhook", type="http", auth="none", methods=["GET", "POST"], csrf=False)
    def instagram_webhook(self, **kwargs):
        # =========================
        # GET: Webhook verification
        # =========================
        if request.httprequest.method == "GET":
            mode = kwargs.get("hub.mode")
            token = kwargs.get("hub.verify_token")
            challenge = kwargs.get("hub.challenge")

            ig_channel = request.env["social.channel"].sudo().search(
                ["|", ("channel_type", "=", "instagram"), ("code", "in", ["instagram", "cm_instagram"])],
                limit=1,
            )
            expected = (ig_channel.webhook_secret if ig_channel else "") or ""

            if mode == "subscribe" and token == expected:
                return str(challenge or "")
            return "Verification failed"

        # =========================
        # POST: Incoming messages
        # =========================
        try:
            payload = json.loads((request.httprequest.data or b"{}").decode("utf-8"))
        except Exception:
            return "bad request"

        if payload.get("object") != "instagram":
            return "ok"

        # Accept both legacy and new code conventions.
        ig_channel = request.env["social.channel"].sudo().search(
            ["|", ("channel_type", "=", "instagram"), ("code", "in", ["instagram", "cm_instagram"])],
            limit=1,
        )

        Partner = request.env["res.partner"].sudo()
        Conversation = request.env["whatsapp.conversation"].sudo()
        Log = request.env["whatsapp.message.log"].sudo()

        for entry in payload.get("entry", []):
            for m in entry.get("messaging", []):
                sender_id = (m.get("sender") or {}).get("id")  # IGSID (scoped)
                message = m.get("message") or {}
                text = message.get("text")
                mid = message.get("mid")

                if not sender_id or not text:
                    continue

                _logger.info("IG DM received sender=%s mid=%s text=%s", sender_id, mid, text)

                # 1) Find or create partner by instagram_id (adapt field name if yours is different)
                partner = Partner.search([("instagram_id", "=", sender_id)], limit=1)
                if not partner:
                    partner = Partner.create({
                        "name": "Instagram %s" % sender_id,
                        "instagram_id": sender_id,
                    })

                # 2) Get or create Instagram conversation (this is what your JS expects)
                conv = Conversation.get_or_create_instagram_conversation(
                    partner,
                    sender_id,
                    channel_id=(ig_channel.id if ig_channel else None),
                )

                # 3) Create the log WITH conversation_id (no more orphan)
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
                if ig_channel:
                    vals["channel_id"] = ig_channel.id
                else:
                    # If you don't have social.channel configured, still tag as instagram
                    vals["channel_type"] = "instagram"

                Log.create(vals)

        return "ok"

    @http.route("/instagram/oauth/start/<int:channel_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def instagram_oauth_start(self, channel_id, **kwargs):
        channel = request.env["social.channel"].sudo().browse(channel_id)
        if not channel.exists():
            return request.redirect("/web")
        action = channel.action_connect_instagram_oauth()
        if action.get("type") == "ir.actions.act_url" and action.get("url"):
            return request.redirect(action["url"])
        return request.redirect(
            f"/web#id={channel.id}&model=social.channel&view_type=form"
        )

    @http.route("/instagram/oauth/callback", type="http", auth="user", methods=["GET"], csrf=False)
    def instagram_oauth_callback(self, **kwargs):
        state = kwargs.get("state") or ""
        code = kwargs.get("code")
        error = kwargs.get("error")
        error_description = kwargs.get("error_description")

        channel_id = False
        try:
            channel_id = int((state or "").split(":", 1)[0])
        except Exception:
            channel_id = False

        if not channel_id:
            return request.redirect("/web")

        channel = request.env["social.channel"].sudo().browse(channel_id)
        if not channel.exists():
            return request.redirect("/web")

        if error:
            channel.sudo().write({"state": "error"})
            msg = quote(error_description or error)
            return request.redirect(
                f"/web#id={channel.id}&model=social.channel&view_type=form&oauth_error={msg}"
            )

        try:
            channel.complete_instagram_oauth(code=code, state=state)
            return request.redirect(
                f"/web#id={channel.id}&model=social.channel&view_type=form&oauth_success=1"
            )
        except Exception as e:
            _logger.exception("Instagram OAuth callback failed")
            channel.sudo().write({"state": "error"})
            msg = quote(str(e))
            return request.redirect(
                f"/web#id={channel.id}&model=social.channel&view_type=form&oauth_error={msg}"
            )
