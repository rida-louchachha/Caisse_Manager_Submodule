from odoo import models, fields, api
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class WhatsappScheduledMessage(models.Model):
    _name = 'whatsapp.scheduled.message'
    _description = 'WhatsApp Scheduled Message Configuration'
    _order = 'sequence'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    
    # Schedule Type
    schedule_type = fields.Selection([
        ('early_month', 'Early Month (1st-15th)'),
        ('late_month', 'Late Month (16th-End)')
    ], string='Schedule Period', required=True)
    
    # Template - uses Odoo's built-in whatsapp.template model
    template_id = fields.Many2one('whatsapp.template', string='Template', required=True,
        domain="[('model', '=', 'sale.order'), ('status', '=', 'approved')]",
        help='Select an approved WhatsApp template that applies to Sales Orders')
    
    # Auto-run
    auto_run = fields.Boolean(string='Run Automatically', default=False, 
        help='If checked, this will run automatically via scheduled action')
    
    # Statistics
    last_run_date = fields.Datetime(string='Last Run', readonly=True)
    last_run_count = fields.Integer(string='Messages Sent', readonly=True)

    def action_send_now(self):
        """Manually trigger sending for this scheduled message"""
        self.ensure_one()
        count = self._send_messages()
        self.write({
            'last_run_date': fields.Datetime.now(),
            'last_run_count': count
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'WhatsApp Messages',
                'message': f'{count} messages sent for "{self.name}"',
                'type': 'success',
            }
        }
    
    def _send_messages(self):
        """Send messages using Odoo's WhatsApp module"""
        self.ensure_one()
        
        # Find unpaid subscriptions
        domain = [
            ('is_subscription', '=', True),
            ('state', 'in', ['sale', 'done']),
        ]
        
        if 'subscription_payment_status' in self.env['sale.order']._fields:
            domain.append(('subscription_payment_status', 'not in', ['paid', 'in_payment']))
        
        orders = self.env['sale.order'].search(domain)
        
        if not orders:
            return 0
        
        count = 0
        
        for order in orders:
            partner = order.partner_id
            phone = partner.mobile or partner.phone
            
            if not phone or len(phone) < 8:
                continue
            
            try:
                # Use Odoo's WhatsApp composer with context (Odoo 18/19 style)
                composer = self.env['whatsapp.composer'].with_context(
                    active_model='sale.order',
                    active_id=order.id,
                    active_ids=[order.id],
                ).create({
                    'wa_template_id': self.template_id.id,
                })
                composer.action_send_whatsapp_template()
                
                # Log the message
                self._log_message(order, partner, phone, 'sent')
                count += 1
                
            except Exception as e:
                _logger.error("Failed to send WhatsApp to %s: %s", phone, str(e))
                self._log_message(order, partner, phone, 'failed', str(e))
        
        return count

    def _log_message(self, order, partner, phone, status, failure_reason=None):
        """Create message log entry"""
        clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        # Get or create conversation
        try:
            conversation = self.env['whatsapp.conversation'].get_or_create_conversation(partner, clean_phone)
        except Exception:
            conversation = None
        
        self.env['whatsapp.message.log'].create({
            'order_id': order.id,
            'partner_id': partner.id,
            'phone': clean_phone,
            'message': f"Scheduled: {self.name} - Template: {self.template_id.name}",
            'status': status,
            'failure_reason': failure_reason,
            'direction': 'outgoing',
            'conversation_id': conversation.id if conversation else False,
        })

    @api.model
    def run_scheduled_messages(self):
        """Called by cron job - runs appropriate scheduled messages"""
        today = date.today()
        day = today.day
        
        period = 'early_month' if day <= 15 else 'late_month'
        
        messages = self.search([
            ('active', '=', True),
            ('auto_run', '=', True),
            ('schedule_type', '=', period)
        ])
        
        for msg in messages:
            try:
                msg._send_messages()
                msg.write({
                    'last_run_date': fields.Datetime.now(),
                })
            except Exception as e:
                _logger.error("Scheduled message '%s' failed: %s", msg.name, str(e))
