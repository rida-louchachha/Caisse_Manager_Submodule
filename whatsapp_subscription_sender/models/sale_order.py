from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Message logs linked to this subscription
    whatsapp_log_ids = fields.One2many('whatsapp.message.log', 'order_id', string='WhatsApp Logs')
    
    # Computed fields for status display
    last_whatsapp_date = fields.Datetime(string='Last WhatsApp', compute='_compute_whatsapp_fields', store=True)
    whatsapp_status = fields.Selection([
        ('not_sent', 'Not Sent'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed')
    ], string='WhatsApp Status', compute='_compute_whatsapp_fields', store=True, default='not_sent')
    whatsapp_message_count = fields.Integer(string='Message Count', compute='_compute_whatsapp_messages')

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

    @api.depends('whatsapp_log_ids')
    def _compute_whatsapp_messages(self):
        """Compute WhatsApp message count from our local logs"""
        for order in self:
            order.whatsapp_message_count = len(order.whatsapp_log_ids)

    def action_view_whatsapp_logs(self):
        """View all WhatsApp logs for this subscription"""
        self.ensure_one()
        return {
            'name': 'WhatsApp Messages',
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.message.log',
            'view_mode': 'list,form',
            'domain': [('order_id', '=', self.id)],
            'context': {'default_order_id': self.id},
        }

    def action_send_whatsapp_template(self):
        """Open template selector to send WhatsApp message"""
        self.ensure_one()
        # Find templates that apply to sale.order model
        templates = self.env['whatsapp.template'].search([
            ('model', '=', 'sale.order'),
            ('status', '=', 'approved')
        ])
        
        if not templates:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Templates Available',
                    'message': 'No approved WhatsApp templates found for Sales Orders. Please create one in WhatsApp → Templates.',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # If only one template, send directly
        if len(templates) == 1:
            return self._send_whatsapp_with_template(templates[0])
        
        # Otherwise open wizard to select template
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send WhatsApp Message',
            'res_model': 'whatsapp.subscription.sender',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_ids': [(6, 0, self.ids)],
            }
        }

    def _send_whatsapp_with_template(self, template):
        """Send WhatsApp message using the specified template"""
        self.ensure_one()
        partner = self.partner_id
        phone = partner.mobile or partner.phone
        
        if not phone:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Phone Number',
                    'message': 'This customer does not have a phone number set.',
                    'type': 'warning',
                }
            }
        
        clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        # Try to use Odoo's WhatsApp composer with correct fields
        try:
            # Odoo 18/19 uses res_ids (list) instead of res_id
            composer = self.env['whatsapp.composer'].with_context(
                active_model='sale.order',
                active_id=self.id,
                active_ids=self.ids,
            ).create({
                'wa_template_id': template.id,
            })
            result = composer.action_send_whatsapp_template()
            status = 'sent'
            failure_reason = None
        except Exception as e:
            status = 'failed'
            failure_reason = str(e)
            result = None
        
        # Create local log entry
        conversation = self.env['whatsapp.conversation'].get_or_create_conversation(partner, clean_phone)
        self.env['whatsapp.message.log'].create({
            'order_id': self.id,
            'partner_id': partner.id,
            'phone': clean_phone,
            'message': f"Template: {template.name}",
            'status': status,
            'failure_reason': failure_reason,
            'direction': 'outgoing',
            'conversation_id': conversation.id if conversation else False,
        })
        
        if result:
            return result
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'WhatsApp Error',
                    'message': f'Failed to send: {failure_reason}',
                    'type': 'danger',
                }
            }

    def action_open_whatsapp_chat(self):
        """Open WhatsApp chat interface for this subscription"""
        self.ensure_one()
        partner = self.partner_id
        phone = partner.mobile or partner.phone
        
        if not phone:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Phone Number',
                    'message': 'This customer does not have a phone number set.',
                    'type': 'warning',
                }
            }
        
        # Find or create conversation
        conversation = self.env['whatsapp.conversation'].get_or_create_conversation(partner, phone)
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Chat - {partner.name}',
            'res_model': 'whatsapp.conversation',
            'res_id': conversation.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_bulk_send_whatsapp(self):
        """Bulk send WhatsApp from subscription list (action button)"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send WhatsApp to Selected',
            'res_model': 'whatsapp.subscription.sender',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_ids': [(6, 0, self.ids)],
            }
        }
