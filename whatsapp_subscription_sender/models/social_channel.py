# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SocialChannel(models.Model):
    """Configuration model for social media channels"""
    _name = 'social.channel'
    _description = 'Social Media Channel Configuration'
    _order = 'sequence, name'

    name = fields.Char(string='Channel Name', required=True)
    code = fields.Char(string='Code', required=True, help='Unique identifier: whatsapp, instagram, sms, etc.')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    
    # Channel Type
    channel_type = fields.Selection([
        ('whatsapp', 'WhatsApp'),
        ('instagram', 'Instagram'),
        ('facebook', 'Facebook'),
        ('twitter', 'X (Twitter)'),
        ('linkedin', 'LinkedIn'),
        ('youtube', 'YouTube'),
        ('sms', 'SMS'),
        ('email', 'Email'),
        ('telegram', 'Telegram'),
        ('messenger', 'Messenger'),
        ('tiktok', 'TikTok'),
        ('custom', 'Custom'),
    ], string='Channel Type', required=True, default='custom')
    
    # Visual - Brand Icons
    image_icon = fields.Image(string='Channel Icon', max_width=128, max_height=128,
                               help='Brand icon for this channel (48x48 recommended)')
    icon = fields.Char(string='Icon (Emoji Fallback)', default='💬')
    color = fields.Char(string='Color (Hex)', default='#25D366', help='Brand color for this channel')
    
    # Connection Status
    state = fields.Selection([
        ('disconnected', 'Not Connected'),
        ('pending', 'Pending Verification'),
        ('connected', 'Connected'),
        ('error', 'Connection Error'),
    ], string='Status', default='disconnected', readonly=True)
    
    # API Configuration
    api_base_url = fields.Char(string='API Base URL')
    api_key = fields.Char(string='API Key')
    api_secret = fields.Char(string='API Secret')
    access_token = fields.Char(string='Access Token')
    refresh_token = fields.Char(string='Refresh Token')
    token_expiry = fields.Datetime(string='Token Expiry')
    
    # WhatsApp Specific
    whatsapp_phone_number_id = fields.Char(string='Phone Number ID')
    whatsapp_business_account_id = fields.Char(string='Business Account ID')
    
    # Webhook
    webhook_url = fields.Char(string='Webhook URL', compute='_compute_webhook_url')
    webhook_secret = fields.Char(string='Webhook Verify Token')
    
    # Capabilities
    can_send_text = fields.Boolean(string='Can Send Text', default=True)
    can_send_media = fields.Boolean(string='Can Send Media', default=False)
    can_receive = fields.Boolean(string='Can Receive Messages', default=True)
    requires_template = fields.Boolean(string='Requires Templates', default=False, 
                                        help='WhatsApp requires templates for business-initiated messages')
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Channel code must be unique!')
    ]

    @api.depends('code')
    def _compute_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for channel in self:
            if channel.code:
                channel.webhook_url = f"{base_url}/social/{channel.code}/webhook"
            else:
                channel.webhook_url = False

    @api.onchange('channel_type')
    def _onchange_channel_type(self):
        """Set default values based on channel type"""
        defaults = {
            'whatsapp': {'name': 'WhatsApp', 'code': 'whatsapp', 'icon': '💬', 'color': '#25D366', 'requires_template': True},
            'instagram': {'name': 'Instagram', 'code': 'instagram', 'icon': '📸', 'color': '#E4405F', 'can_send_media': True},
            'facebook': {'name': 'Facebook', 'code': 'facebook', 'icon': '📘', 'color': '#1877F2'},
            'twitter': {'name': 'X (Twitter)', 'code': 'twitter', 'icon': '𝕏', 'color': '#000000'},
            'linkedin': {'name': 'LinkedIn', 'code': 'linkedin', 'icon': '💼', 'color': '#0A66C2'},
            'youtube': {'name': 'YouTube', 'code': 'youtube', 'icon': '▶️', 'color': '#FF0000', 'can_receive': False},
            'sms': {'name': 'SMS', 'code': 'sms', 'icon': '📱', 'color': '#4CAF50'},
            'email': {'name': 'Email', 'code': 'email', 'icon': '✉️', 'color': '#EA4335'},
            'telegram': {'name': 'Telegram', 'code': 'telegram', 'icon': '✈️', 'color': '#0088CC'},
            'messenger': {'name': 'Messenger', 'code': 'messenger', 'icon': '💬', 'color': '#006AFF'},
            'tiktok': {'name': 'TikTok', 'code': 'tiktok', 'icon': '🎵', 'color': '#000000'},
        }
        if self.channel_type and self.channel_type in defaults:
            for field, value in defaults[self.channel_type].items():
                setattr(self, field, value)

    def action_test_connection(self):
        """Test the API connection"""
        self.ensure_one()
        # TODO: Implement connection test for each channel type
        self.state = 'connected'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Connection Test',
                'message': f'{self.name} connection successful!',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_disconnect(self):
        """Disconnect the channel"""
        self.ensure_one()
        self.write({
            'state': 'disconnected',
            'access_token': False,
            'refresh_token': False,
        })

    @api.model
    def get_active_channels(self):
        """Get all active and connected channels"""
        return self.search([('active', '=', True), ('state', '=', 'connected')])

    @api.model
    def get_channel_by_code(self, code):
        """Get channel by code"""
        return self.search([('code', '=', code)], limit=1)
