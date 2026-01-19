from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    whatsapp_log_ids = fields.One2many('whatsapp.message.log', 'order_id', string='WhatsApp Logs')
    last_whatsapp_date = fields.Datetime(string='Last WhatsApp', compute='_compute_whatsapp_fields', store=True)
    whatsapp_status = fields.Selection([
        ('not_sent', 'Not Sent'),
        ('sent', 'Sent'),
        ('failed', 'Failed')
    ], string='WhatsApp Status', compute='_compute_whatsapp_fields', store=True, default='not_sent')

    @api.depends('whatsapp_log_ids', 'whatsapp_log_ids.status', 'whatsapp_log_ids.create_date')
    def _compute_whatsapp_fields(self):
        for order in self:
            logs = order.whatsapp_log_ids.sorted(key=lambda r: r.create_date, reverse=True)
            if logs:
                latest_log = logs[0]
                order.last_whatsapp_date = latest_log.create_date
                order.whatsapp_status = latest_log.status
            else:
                order.last_whatsapp_date = False
                order.whatsapp_status = 'not_sent'

    def action_view_whatsapp_logs(self):
        self.ensure_one()
        return {
            'name': 'WhatsApp Logs',
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.message.log',
            'view_mode': 'list,form',
            'domain': [('order_id', '=', self.id)],
            'context': {'default_order_id': self.id},
        }
