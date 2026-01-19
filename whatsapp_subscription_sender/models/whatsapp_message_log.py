from odoo import fields, models

class WhatsappMessageLog(models.Model):
    _name = 'whatsapp.message.log'
    _description = 'WhatsApp Message Log'
    _order = 'create_date asc'

    order_id = fields.Many2one('sale.order', string='Subscription/Order')
    partner_id = fields.Many2one('res.partner', string='Client')
    phone = fields.Char(string='Phone Number')
    message = fields.Text(string='Message Content')
    status = fields.Selection([
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
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
    message_id = fields.Char(string='WhatsApp Message ID', help='Message ID from Meta API')
