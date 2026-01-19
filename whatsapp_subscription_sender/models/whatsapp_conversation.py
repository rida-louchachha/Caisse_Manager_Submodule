from odoo import models, fields, api

class WhatsappConversation(models.Model):
    _name = 'whatsapp.conversation'
    _description = 'WhatsApp Conversation'
    _order = 'last_message_date desc'

    partner_id = fields.Many2one('res.partner', string='Contact', required=True, ondelete='cascade')
    phone = fields.Char(string='WhatsApp Number', required=True)
    
    # Conversation preview
    last_message = fields.Text(string='Last Message', compute='_compute_last_message', store=True)
    last_message_date = fields.Datetime(string='Last Activity', compute='_compute_last_message', store=True)
    unread_count = fields.Integer(string='Unread', compute='_compute_unread_count')
    
    # Messages
    message_ids = fields.One2many('whatsapp.message.log', 'conversation_id', string='Messages')
    
    _sql_constraints = [
        ('phone_unique', 'unique(phone)', 'A conversation with this phone number already exists!')
    ]

    @api.depends('message_ids', 'message_ids.create_date', 'message_ids.message')
    def _compute_last_message(self):
        for conv in self:
            last_msg = conv.message_ids.sorted(key=lambda r: r.create_date, reverse=True)[:1]
            if last_msg:
                conv.last_message = last_msg.message[:50] + '...' if len(last_msg.message or '') > 50 else last_msg.message
                conv.last_message_date = last_msg.create_date
            else:
                conv.last_message = False
                conv.last_message_date = False

    def _compute_unread_count(self):
        for conv in self:
            conv.unread_count = len(conv.message_ids.filtered(lambda m: m.direction == 'incoming' and not m.is_read))

    def name_get(self):
        return [(conv.id, f"{conv.partner_id.name} ({conv.phone})") for conv in self]

    @api.model
    def get_or_create_conversation(self, partner, phone):
        """Find or create a conversation for the given partner and phone"""
        clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        conv = self.search([('phone', '=', clean_phone)], limit=1)
        if not conv:
            conv = self.create({
                'partner_id': partner.id,
                'phone': clean_phone
            })
        return conv

    def action_send_message(self):
        """Open send message wizard for this conversation"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Message',
            'res_model': 'whatsapp.quick.send',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_conversation_id': self.id,
                'default_phone': self.phone,
                'default_partner_id': self.partner_id.id,
            }
        }

    def action_mark_as_read(self):
        """Mark all messages in this conversation as read"""
        self.ensure_one()
        self.message_ids.filtered(lambda m: m.direction == 'incoming' and not m.is_read).write({'is_read': True})

