from odoo import fields, models, api


class WhatsappMessageLog(models.Model):
    _name = 'whatsapp.message.log'
    _description = 'Social Message Log'
    _order = 'create_date asc'

    order_id = fields.Many2one('sale.order', string='Subscription/Order')
    partner_id = fields.Many2one('res.partner', string='Client')
    phone = fields.Char(string='Phone Number')
    message = fields.Text(string='Message Content')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('received', 'Received'),
        ('failed', 'Failed')
    ], string='Delivery Status', default='sent')
    
    api_response = fields.Text(string='API Response/Error')
    failure_reason = fields.Char(string='Failure Reason')
    
    # Chat features
    conversation_id = fields.Many2one('whatsapp.conversation', string='Conversation', ondelete='cascade')
    direction = fields.Selection([
        ('outgoing', 'Outgoing'),
        ('incoming', 'Incoming')
    ], string='Direction', default='outgoing')
    is_read = fields.Boolean(string='Read', default=True)
    
    # ========== MULTI-CHANNEL SUPPORT ==========
    channel_id = fields.Many2one('social.channel', string='Channel', 
                                  help='The social media channel this message was sent/received on')
    channel_code = fields.Char(string='Channel Code', related='channel_id.code', store=True)
    channel_icon = fields.Char(string='Channel Icon', related='channel_id.icon', store=True)
    channel_color = fields.Char(string='Channel Color', related='channel_id.color', store=True)
    
    # Legacy field for backward compatibility (will be computed from channel_id)
    channel_type = fields.Selection([
        ('whatsapp', '💬 WhatsApp'),
        ('instagram', '📸 Instagram'),
        ('facebook', '📘 Facebook'),
        ('twitter', '𝕏 X (Twitter)'),
        ('linkedin', '💼 LinkedIn'),
        ('youtube', '▶️ YouTube'),
        ('sms', '📱 SMS'),
        ('email', '✉️ Email'),
        ('telegram', '✈️ Telegram'),
        ('messenger', '💬 Messenger'),
        ('tiktok', '🎵 TikTok'),
        ('other', '🔧 Other'),
    ], string='Channel Type', default='whatsapp', compute='_compute_channel_type', store=True)
    
    # External message ID (from the social platform)
    message_id = fields.Char(string='External Message ID', help='Message ID from the social platform API')
    
    external_user_id = fields.Char(string="External User ID",index=True,help="Sender identifier on the platform (Instagram user id, Facebook PSID, WhatsApp wa_id/phone, etc.)")

    # Media support
    media_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
        ('sticker', 'Sticker'),
        ('location', 'Location'),
    ], string='Media Type', default='text')
    media_url = fields.Char(string='Media URL')
    media_filename = fields.Char(string='Media Filename')
    media_attachment_id = fields.Many2one('ir.attachment', string='Attachment')

    @api.depends('channel_id', 'channel_id.channel_type')
    def _compute_channel_type(self):
        for msg in self:
            if msg.channel_id and msg.channel_id.channel_type:
                msg.channel_type = msg.channel_id.channel_type
            else:
                msg.channel_type = 'whatsapp'  # Default for existing messages

    @api.model
    def create(self, vals):
        """Auto-set channel to WhatsApp if not specified (backward compatibility)"""
        if not vals.get('channel_id') and not vals.get('channel_type'):
            whatsapp_channel = self.env['social.channel'].search(
                [
                    "|",
                    ("channel_type", "=", "whatsapp"),
                    ("code", "in", ["whatsapp", "cm_whatsapp"]),
                ],
                limit=1,
            )
            if whatsapp_channel:
                vals['channel_id'] = whatsapp_channel.id
        return super().create(vals)

    def get_channel_display(self):
        """Get display info for the channel"""
        self.ensure_one()
        if self.channel_id:
            return {
                'icon': self.channel_id.icon,
                'color': self.channel_id.color,
                'name': self.channel_id.name,
            }
        # Fallback for legacy messages
        channel_info = {
            'whatsapp': {'icon': '💬', 'color': '#25D366', 'name': 'WhatsApp'},
            'instagram': {'icon': '📸', 'color': '#E4405F', 'name': 'Instagram'},
            'facebook': {'icon': '📘', 'color': '#1877F2', 'name': 'Facebook'},
            'twitter': {'icon': '𝕏', 'color': '#000000', 'name': 'X'},
            'linkedin': {'icon': '💼', 'color': '#0A66C2', 'name': 'LinkedIn'},
            'sms': {'icon': '📱', 'color': '#4CAF50', 'name': 'SMS'},
            'email': {'icon': '✉️', 'color': '#EA4335', 'name': 'Email'},
        }
        return channel_info.get(self.channel_type, {'icon': '💬', 'color': '#666', 'name': 'Unknown'})

