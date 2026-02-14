# -*- coding: utf-8 -*-
import logging
import requests
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from odoo import models, fields, api

_logger = logging.getLogger(__name__)
IG_OAUTH_SCOPES = (
    "instagram_basic",
    "instagram_manage_messages",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "business_management",
)


class SocialChannel(models.Model):
    """Configuration model for social media channels"""
    _name = "social.channel"
    _description = "Social Media Channel Configuration"
    _order = "sequence, name"

    name = fields.Char(string="Channel Name", required=True)
    code = fields.Char(string="Code", required=True, help="Unique identifier: whatsapp, instagram, sms, etc.")
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(default=True)

    channel_type = fields.Selection([
        ("whatsapp", "WhatsApp"),
        ("instagram", "Instagram"),
        ("facebook", "Facebook"),
        ("twitter", "X (Twitter)"),
        ("linkedin", "LinkedIn"),
        ("youtube", "YouTube"),
        ("sms", "SMS"),
        ("email", "Email"),
        ("telegram", "Telegram"),
        ("messenger", "Messenger"),
        ("tiktok", "TikTok"),
        ("custom", "Custom"),
    ], string="Channel Type", required=True, default="custom")

    image_icon = fields.Image(
        string="Channel Icon",
        max_width=128,
        max_height=128,
        help="Brand icon for this channel (48x48 recommended)",
    )
    icon = fields.Char(string="Icon (Emoji Fallback)", default="💬")
    color = fields.Char(string="Color (Hex)", default="#25D366", help="Brand color for this channel")

    state = fields.Selection([
        ("disconnected", "Not Connected"),
        ("pending", "Pending Verification"),
        ("connected", "Connected"),
        ("error", "Connection Error"),
    ], string="Status", default="disconnected", readonly=True)

    api_base_url = fields.Char(string="API Base URL")
    api_key = fields.Char(string="API Key")
    api_secret = fields.Char(string="API Secret")
    access_token = fields.Char(string="Access Token")
    refresh_token = fields.Char(string="Refresh Token")
    token_expiry = fields.Datetime(string="Token Expiry")

    whatsapp_phone_number_id = fields.Char(string="Phone Number ID")
    whatsapp_business_account_id = fields.Char(string="Business Account ID")

    webhook_url = fields.Char(string="Webhook URL", compute="_compute_webhook_url")
    webhook_secret = fields.Char(string="Webhook Verify Token")
    webhook_verify_token = fields.Char(
        string="Webhook Verify Token (Active)",
        compute="_compute_webhook_verify_token",
    )

    can_send_text = fields.Boolean(string="Can Send Text", default=True)
    can_send_media = fields.Boolean(string="Can Send Media", default=False)
    can_receive = fields.Boolean(string="Can Receive Messages", default=True)
    requires_template = fields.Boolean(
        string="Requires Templates",
        default=False,
        help="WhatsApp requires templates for business-initiated messages",
    )

    # ========= Instagram config =========
    instagram_page_id = fields.Char(string="Instagram Page ID / Sender ID")
    instagram_username = fields.Char(string="Instagram Username", readonly=True)
    instagram_oauth_state = fields.Char(string="Instagram OAuth State", copy=False)
    instagram_oauth_redirect_uri = fields.Char(
        string="Instagram OAuth Redirect URI",
        compute="_compute_instagram_oauth_redirect_uri",
    )
    instagram_required_scopes = fields.Char(
        string="Instagram OAuth Required Scopes",
        compute="_compute_instagram_required_scopes",
    )
    graph_api_version = fields.Char(string="Graph API Version", default="v19.0")

    # ========= Facebook / Messenger config =========
    facebook_page_id = fields.Char(string="Facebook Page ID (for Messenger)")

    _sql_constraints = [
        ("code_unique", "unique(code)", "Channel code must be unique!"),
    ]

    # -------------------
    # Internal helpers
    # -------------------
    def _wa_log_prepare_vals(self, vals):
        """
        Make vals compatible with both versions of whatsapp.message.log:
        - legacy fields: partnerid, channelid, externaluserid, messageid, failurereason
        - snake_case: partner_id, channel_id, external_user_id, message_id, failure_reason
        """
        Log = self.env["whatsapp.message.log"].sudo()
        f = Log._fields

        def move(snake, legacy):
            if snake in vals and snake not in f and legacy in f:
                vals[legacy] = vals.pop(snake)

        move("partner_id", "partnerid")
        move("channel_id", "channelid")
        move("external_user_id", "externaluserid")
        move("message_id", "messageid")
        move("failure_reason", "failurereason")

        def move_back(legacy, snake):
            if legacy in vals and legacy not in f and snake in f:
                vals[snake] = vals.pop(legacy)

        move_back("partnerid", "partner_id")
        move_back("channelid", "channel_id")
        move_back("externaluserid", "external_user_id")
        move_back("messageid", "message_id")
        move_back("failurereason", "failure_reason")

        safe_vals = {}
        for k, v in vals.items():
            if k in f:
                safe_vals[k] = v
        return safe_vals

    def _wa_log_create(self, vals):
        vals = self._wa_log_prepare_vals(vals)
        return self.env["whatsapp.message.log"].sudo().create(vals)

    def _wa_log_write(self, record, vals):
        vals = self._wa_log_prepare_vals(vals)
        return record.sudo().write(vals)

    # -------------------
    # Compute / onchange
    # -------------------
    @api.depends("code")
    def _compute_webhook_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for channel in self:
            route_by_type = {
                "whatsapp": "/whatsapp/webhook",
                "instagram": "/instagram/webhook",
                "facebook": "/facebook/webhook",
                "messenger": "/facebook/webhook",
            }
            route = route_by_type.get(channel.channel_type)
            if route:
                channel.webhook_url = f"{base_url}{route}"
            elif channel.code:
                # Fallback for custom channels
                channel.webhook_url = f"{base_url}/social/{channel.code}/webhook"
            else:
                channel.webhook_url = False

    def _compute_instagram_oauth_redirect_uri(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for channel in self:
            if channel.channel_type == "instagram":
                channel.instagram_oauth_redirect_uri = f"{base_url}/instagram/oauth/callback"
            else:
                channel.instagram_oauth_redirect_uri = False

    def _compute_instagram_required_scopes(self):
        scopes = ", ".join(IG_OAUTH_SCOPES)
        for channel in self:
            if channel.channel_type == "instagram":
                channel.instagram_required_scopes = scopes
            else:
                channel.instagram_required_scopes = False

    @api.depends("channel_type", "code")
    def _compute_webhook_verify_token(self):
        for channel in self:
            if channel.channel_type in ("whatsapp", "instagram", "facebook", "messenger"):
                channel.webhook_verify_token = channel.webhook_secret or False
            else:
                channel.webhook_verify_token = False

    @api.onchange("channel_type")
    def _onchange_channel_type(self):
        defaults = {
            "whatsapp": {"name": "WhatsApp", "code": "whatsapp", "icon": "💬", "color": "#25D366", "requires_template": True},
            "instagram": {"name": "Instagram", "code": "instagram", "icon": "📸", "color": "#E4405F", "can_send_media": True},
            "facebook": {"name": "Facebook", "code": "facebook", "icon": "📘", "color": "#1877F2"},
            "twitter": {"name": "X (Twitter)", "code": "twitter", "icon": "𝕏", "color": "#000000"},
            "linkedin": {"name": "LinkedIn", "code": "linkedin", "icon": "💼", "color": "#0A66C2"},
            "youtube": {"name": "YouTube", "code": "youtube", "icon": "▶️", "color": "#FF0000", "can_receive": False},
            "sms": {"name": "SMS", "code": "sms", "icon": "📱", "color": "#4CAF50"},
            "email": {"name": "Email", "code": "email", "icon": "✉️", "color": "#EA4335"},
            "telegram": {"name": "Telegram", "code": "telegram", "icon": "✈️", "color": "#0088CC"},
            "messenger": {"name": "Messenger", "code": "messenger", "icon": "💬", "color": "#006AFF"},
            "tiktok": {"name": "TikTok", "code": "tiktok", "icon": "🎵", "color": "#000000"},
        }
        if self.channel_type in defaults:
            for field, value in defaults[self.channel_type].items():
                setattr(self, field, value)

    def _ensure_verify_token(self):
        self.ensure_one()
        if self.channel_type in ("whatsapp", "instagram", "facebook", "messenger"):
            if not self.webhook_secret:
                self.sudo().write({"webhook_secret": secrets.token_urlsafe(24)})
            return self.webhook_secret
        return False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._ensure_verify_token()
        return records

    def action_regenerate_verify_token(self):
        self.ensure_one()
        if self.channel_type in ("whatsapp", "instagram", "facebook", "messenger"):
            token = secrets.token_urlsafe(24)
            self.sudo().write({"webhook_secret": token})
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "✅ Verify Token Regenerated",
                    "message": "New token saved in this channel.",
                    "type": "success",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "No Token Required",
                "message": "This channel type does not use a webhook verify token.",
                "type": "warning",
            },
        }

    # -------------------
    # Actions
    # -------------------
    def _get_oauth_redirect_uri(self):
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base_url}/instagram/oauth/callback"

    def action_connect_instagram_oauth(self):
        self.ensure_one()
        if self.channel_type != "instagram":
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Wrong Channel Type",
                    "message": "This action is only available for Instagram channels.",
                    "type": "warning",
                },
            }

        if not self.api_key or not self.api_secret:
            self.state = "error"
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Missing App Credentials",
                    "message": "Please fill API Key (App ID) and API Secret (App Secret) first.",
                    "type": "danger",
                    "sticky": True,
                },
            }

        self._ensure_verify_token()
        nonce = secrets.token_urlsafe(24)
        state = f"{self.id}:{nonce}"
        self.sudo().write({"instagram_oauth_state": state, "state": "pending"})

        api_version = self.graph_api_version or "v19.0"
        auth_base = "https://www.facebook.com"
        redirect_uri = self._get_oauth_redirect_uri()
        scopes = ",".join(IG_OAUTH_SCOPES)
        oauth_params = urlencode({
            "client_id": self.api_key,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "response_type": "code",
            "state": state,
        })
        auth_url = f"{auth_base}/{api_version}/dialog/oauth?{oauth_params}"
        return {
            "type": "ir.actions.act_url",
            "url": auth_url,
            "target": "self",
        }

    def complete_instagram_oauth(self, code=None, state=None):
        """
        Complete Meta OAuth callback:
        - exchange code -> user token
        - exchange user token -> long-lived token
        - fetch pages and linked instagram business account
        - store access_token + instagram_page_id on this channel
        """
        self.ensure_one()
        if self.channel_type != "instagram":
            raise ValueError("OAuth callback called on non-Instagram channel.")
        if not code:
            raise ValueError("Missing OAuth code.")
        if not state or state != (self.instagram_oauth_state or ""):
            raise ValueError("Invalid OAuth state.")
        if not self.api_key or not self.api_secret:
            raise ValueError("Missing App ID / App Secret.")

        api_version = self.graph_api_version or "v19.0"
        graph_base = "https://graph.facebook.com"
        redirect_uri = self._get_oauth_redirect_uri()

        # Step 1: short-lived user token
        token_url = f"{graph_base}/{api_version}/oauth/access_token"
        token_resp = requests.get(
            token_url,
            params={
                "client_id": self.api_key,
                "client_secret": self.api_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
            timeout=30,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json() or {}
        user_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in")
        if not user_token:
            raise ValueError("Meta did not return access_token.")

        # Step 2: exchange to long-lived token when possible
        final_token = user_token
        token_expiry = False
        try:
            long_resp = requests.get(
                token_url,
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.api_key,
                    "client_secret": self.api_secret,
                    "fb_exchange_token": user_token,
                },
                timeout=30,
            )
            if 200 <= long_resp.status_code < 300:
                long_data = long_resp.json() or {}
                final_token = long_data.get("access_token") or user_token
                expires_in = long_data.get("expires_in") or expires_in
        except Exception:
            _logger.warning("Could not exchange Meta token to long-lived token", exc_info=True)

        if expires_in:
            token_expiry = fields.Datetime.now() + timedelta(seconds=int(expires_in))

        # Step 3: resolve page + instagram business account
        pages_url = f"{graph_base}/{api_version}/me/accounts"
        pages_resp = requests.get(
            pages_url,
            params={
                "fields": "id,name,access_token,instagram_business_account{id,username}",
                "access_token": final_token,
            },
            timeout=30,
        )
        pages_resp.raise_for_status()
        pages_data = (pages_resp.json() or {}).get("data") or []
        if not pages_data:
            raise ValueError("No Facebook page found for this Meta account.")

        selected_page = False
        for page in pages_data:
            if (page.get("instagram_business_account") or {}).get("id"):
                selected_page = page
                break
        if not selected_page:
            raise ValueError("No Instagram Business account linked to the selected Meta pages.")

        page_token = selected_page.get("access_token") or final_token
        page_id = selected_page.get("id")
        ig_account = selected_page.get("instagram_business_account") or {}
        ig_id = ig_account.get("id")
        ig_username = ig_account.get("username")

        if not ig_id:
            raise ValueError("Instagram Business ID not found in Meta response.")

        self.sudo().write({
            "access_token": page_token,
            "refresh_token": False,
            "token_expiry": token_expiry,
            "instagram_page_id": ig_id,
            "facebook_page_id": page_id,
            "instagram_username": ig_username,
            "instagram_oauth_state": False,
            "state": "connected",
        })
        return True

    def action_test_connection(self):
        self.ensure_one()
        missing_credentials = []

        if self.channel_type == "whatsapp":
            if not self.whatsapp_phone_number_id:
                missing_credentials.append("Phone Number ID")
            if not self.whatsapp_business_account_id:
                missing_credentials.append("Business Account ID")
            if not self.access_token:
                missing_credentials.append("Access Token")
        elif self.channel_type in ["instagram", "facebook", "messenger"]:
            if not self.access_token:
                missing_credentials.append("Access Token")
            if self.channel_type == "instagram" and not self.instagram_page_id:
                missing_credentials.append("Instagram Page ID")
            if self.channel_type in ["facebook", "messenger"] and not self.facebook_page_id:
                missing_credentials.append("Facebook Page ID")
        elif self.channel_type in ["twitter", "linkedin", "youtube", "tiktok"]:
            if not self.api_key:
                missing_credentials.append("API Key")
            if not self.api_secret:
                missing_credentials.append("API Secret")
        elif self.channel_type == "sms":
            if not self.api_key:
                missing_credentials.append("API Key (Account SID)")
            if not self.api_secret:
                missing_credentials.append("API Secret (Auth Token)")
        elif self.channel_type == "telegram":
            if not self.access_token:
                missing_credentials.append("Bot Token")
        else:
            if not self.api_key and not self.access_token:
                missing_credentials.append("API Key or Access Token")

        if missing_credentials:
            self.state = "error"
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "❌ Connection Failed",
                    "message": f"Missing required credentials: {', '.join(missing_credentials)}",
                    "type": "danger",
                    "sticky": True,
                },
            }

        self.state = "connected"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "✅ Connection Successful",
                "message": f"{self.name} is now connected!",
                "type": "success",
                "sticky": False,
            },
        }

    def action_link_account(self):
        """
        Generic button used by the social-network cards.
        - Instagram: start official Meta OAuth flow.
        - Other channels: reserved for upcoming OAuth integrations.
        """
        self.ensure_one()
        if self.channel_type == "instagram":
            return self.action_connect_instagram_oauth()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "OAuth Not Yet Connected",
                "message": f"{self.name}: OAuth flow will be added next. Instagram is already supported.",
                "type": "info",
                "sticky": False,
            },
        }

    def action_disconnect(self):
        self.ensure_one()
        self.write({
            "state": "disconnected",
            "access_token": False,
            "refresh_token": False,
        })

    @api.model
    def get_active_channels(self):
        return self.search([("active", "=", True), ("state", "=", "connected")])

    @api.model
    def get_channel_by_code(self, code):
        return self.search([("code", "=", code)], limit=1)

    # ==========================
    # Instagram helper / senders
    # ==========================
    @api.model
    def get_instagram_channel_id(self):
        channel = self.sudo().search(
            ["|", ("channel_type", "=", "instagram"), ("code", "in", ["instagram", "cm_instagram"])],
            limit=1,
        )
        return channel.id if channel else False

    @api.model
    def sendinstagrammessagestub(
        self,
        external_user_id=None,
        message_text=None,
        partner_id=None,
        channel_id=None,
        # compat anciens appels
        externaluserid=None,
        messagetext=None,
        partnerid=None,
        channelid=None,
        **kwargs
    ):
        external_user_id = (external_user_id or externaluserid or "").strip()
        message_text = (message_text or messagetext or "").strip()
        partner_id = partner_id or partnerid
        channel_id = channel_id or channelid

        if not external_user_id:
            return {"status": "error", "message": "Missing external_user_id (Instagram sender id)"}
        if not message_text:
            return {"status": "error", "message": "Empty message"}

        igchannel = False
        if channel_id:
            igchannel = self.sudo().browse(int(channel_id))
            if not igchannel.exists():
                igchannel = False
        if not igchannel:
            igchannel = self.sudo().search(
                ["|", ("channel_type", "=", "instagram"), ("code", "in", ["instagram", "cm_instagram"])],
                limit=1,
            )
        if not igchannel:
            return {"status": "error", "message": "Instagram channel not found."}

        log = igchannel._wa_log_create({
            "partner_id": int(partner_id) if partner_id else False,
            "phone": False,
            "message": message_text,
            "direction": "outgoing",
            "status": "failed",
            "failure_reason": "Instagram not configured (stub)",
            "channel_id": igchannel.id,
            "external_user_id": external_user_id,
            "message_id": False,
        })

        return {
            "status": "error",
            "message": "Stub: message saved in logs but not sent (Meta not configured).",
            "logid": log.id,
        }

    @api.model
    def sendinstagrammessagereal(
        self,
        external_user_id=None,
        message_text=None,
        partner_id=None,
        channel_id=None,
        # compat anciens appels
        externaluserid=None,
        messagetext=None,
        partnerid=None,
        channelid=None,
        **kwargs
    ):
        external_user_id = (external_user_id or externaluserid or "").strip()
        message_text = (message_text or messagetext or "").strip()
        partner_id = partner_id or partnerid
        channel_id = channel_id or channelid

        if not external_user_id:
            return {"status": "error", "message": "Missing external_user_id (IGSID)."}
        if not message_text:
            return {"status": "error", "message": "Empty message."}

        igchannel = False
        if channel_id:
            igchannel = self.sudo().browse(int(channel_id))
            if not igchannel.exists():
                igchannel = False
        if not igchannel:
            igchannel = self.sudo().search(
                ["|", ("channel_type", "=", "instagram"), ("code", "in", ["instagram", "cm_instagram"])],
                limit=1,
            )
        if not igchannel:
            return {"status": "error", "message": "Instagram channel not found."}

        access_token = igchannel.access_token
        pageid = igchannel.instagram_page_id
        apiversion = igchannel.graph_api_version or "v19.0"
        baseurl = (igchannel.api_base_url or "https://graph.facebook.com").rstrip("/")

        if not access_token or not pageid:
            return self.sendinstagrammessagestub(
                external_user_id=external_user_id,
                message_text=message_text,
                partner_id=partner_id,
                channel_id=channel_id,
            )

        url = f"{baseurl}/{apiversion}/{pageid}/messages"
        payload = {
            "recipient": {"id": external_user_id},
            "message": {"text": message_text},
            "messaging_type": "RESPONSE",
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        log = igchannel._wa_log_create({
            "partner_id": int(partner_id) if partner_id else False,
            "phone": False,
            "message": message_text,
            "direction": "outgoing",
            "status": "pending",
            "channel_id": igchannel.id,
            "external_user_id": external_user_id,
        })

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)

            if 200 <= resp.status_code < 300:
                try:
                    data = resp.json() or {}
                except Exception:
                    data = {}
                meta_mid = data.get("message_id") or data.get("messageid") or ""
                igchannel._wa_log_write(log, {"status": "sent", "message_id": meta_mid})
                return {"status": "success", "message": "Sent", "logid": log.id, "meta": data}

            try:
                err = resp.json()
            except Exception:
                err = {"error": {"message": resp.text}}
            errmsg = (err.get("error") or {}).get("message") or resp.text
            igchannel._wa_log_write(log, {"status": "failed", "failure_reason": errmsg})
            return {"status": "error", "message": errmsg, "logid": log.id}

        except Exception as e:
            igchannel._wa_log_write(log, {"status": "failed", "failure_reason": str(e)})
            return {"status": "error", "message": str(e), "logid": log.id}

    # ==========================
    # Facebook Messenger sender
    # ==========================
    @api.model
    def sendfacebookmessagereal(self, external_user_id=None, message_text=None, partner_id=None, channel_id=None, channelid=None, **kwargs):
        external_user_id = (external_user_id or "").strip()
        message_text = (message_text or "").strip()
        channel_id = channel_id or channelid

        if not external_user_id:
            return {"status": "error", "message": "Missing external_user_id (PSID)."}
        if not message_text:
            return {"status": "error", "message": "Empty message."}

        fbchannel = False
        if channel_id:
            fbchannel = self.sudo().browse(int(channel_id))
            if not fbchannel.exists():
                fbchannel = False
        if not fbchannel:
            fbchannel = self.sudo().search(
                [
                    "|",
                    ("channel_type", "in", ["messenger", "facebook"]),
                    ("code", "in", ["messenger", "facebook", "cm_messenger", "cm_facebook"]),
                ],
                limit=1,
            )
        if not fbchannel:
            return {"status": "error", "message": "Messenger/Facebook channel not found."}

        access_token = fbchannel.access_token
        pageid = fbchannel.facebook_page_id
        apiversion = fbchannel.graph_api_version or "v19.0"
        baseurl = (fbchannel.api_base_url or "https://graph.facebook.com").rstrip("/")

        if not access_token or not pageid:
            log = fbchannel._wa_log_create({
                "partner_id": int(partner_id) if partner_id else False,
                "phone": False,
                "message": message_text,
                "direction": "outgoing",
                "status": "failed",
                "failure_reason": "Messenger not configured (missing access_token or facebook_page_id).",
                "channel_id": fbchannel.id,
                "external_user_id": external_user_id,
                "message_id": False,
            })
            return {"status": "error", "message": "Stub: logged but not sent.", "logid": log.id}

        url = f"{baseurl}/{apiversion}/{pageid}/messages"
        payload = {
            "recipient": {"id": external_user_id},
            "message": {"text": message_text},
            "messaging_type": "RESPONSE",
        }
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        log = fbchannel._wa_log_create({
            "partner_id": int(partner_id) if partner_id else False,
            "phone": False,
            "message": message_text,
            "direction": "outgoing",
            "status": "pending",
            "channel_id": fbchannel.id,
            "external_user_id": external_user_id,
        })

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)

            if 200 <= resp.status_code < 300:
                try:
                    data = resp.json() or {}
                except Exception:
                    data = {}
                meta_mid = data.get("message_id") or data.get("messageid") or ""
                fbchannel._wa_log_write(log, {"status": "sent", "message_id": meta_mid})
                return {"status": "success", "message": "Sent", "logid": log.id, "meta": data}

            try:
                err = resp.json()
            except Exception:
                err = {"error": {"message": resp.text}}
            errmsg = (err.get("error") or {}).get("message") or resp.text
            fbchannel._wa_log_write(log, {"status": "failed", "failure_reason": errmsg})
            return {"status": "error", "message": errmsg, "logid": log.id}

        except Exception as e:
            fbchannel._wa_log_write(log, {"status": "failed", "failure_reason": str(e)})
            return {"status": "error", "message": str(e), "logid": log.id}

    # ==========================
    # Universal sender (UI calls)
    # ==========================
    @api.model
    def send_text_message(
        self,
        channel_code=None,
        channel_type=None,
        message_text=None,
        partner_id=None,
        phone=None,
        external_user_id=None,
        **kwargs
    ):
        """
        Universal sender for your Inbox UI.
        - WhatsApp: uses whatsapp.conversation.send_chat_message(...) if exists, else stub log
        - Instagram: sendinstagrammessagereal()
        - Messenger/Facebook: sendfacebookmessagereal()
        """
        message_text = (message_text or "").strip()
        if not message_text:
            return {"status": "error", "message": "Empty message."}

        domain = []
        if channel_code:
            domain = [("code", "=", channel_code)]
        elif channel_type:
            domain = [("channel_type", "=", channel_type)]
        channel = self.sudo().search(domain, limit=1) if domain else False

        if not channel:
            return {"status": "error", "message": "Channel not found."}

        ctype = channel.channel_type

        if ctype == "instagram":
            return channel.sendinstagrammessagereal(
                external_user_id=external_user_id,
                message_text=message_text,
                partner_id=partner_id,
            )

        if ctype in ("facebook", "messenger"):
            return channel.sendfacebookmessagereal(
                external_user_id=external_user_id,
                message_text=message_text,
                partner_id=partner_id,
            )

        if ctype == "whatsapp":
            Conversation = self.env["whatsapp.conversation"].sudo()
            if hasattr(Conversation, "send_chat_message"):
                return Conversation.send_chat_message(
                    partner_id=partner_id,
                    message_text=message_text,
                    phone=phone,
                )

            wa = self.sudo().search([("code", "=", "whatsapp")], limit=1) or channel
            log = wa._wa_log_create({
                "partner_id": int(partner_id) if partner_id else False,
                "phone": phone or False,
                "message": message_text,
                "direction": "outgoing",
                "status": "failed",
                "failure_reason": "WhatsApp send method not configured (missing send_chat_message).",
                "channel_id": wa.id,
                "external_user_id": phone or "",
                "message_id": False,
            })
            return {"status": "error", "message": "Stub: logged but not sent.", "logid": log.id}

        return {"status": "error", "message": f"Unsupported channel_type: {ctype}"}
