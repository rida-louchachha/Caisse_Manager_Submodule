from odoo import models, fields, api
from datetime import date
import requests
import json
import re


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
    
    # Template - uses our standalone template model
    template_id = fields.Many2one('whatsapp.subscription.template', string='Template', required=True)
    
    # Auto-run
    auto_run = fields.Boolean(string='Run Automatically', default=False, 
        help='If checked, this will run automatically via scheduled action')
    
    def action_send_now(self):
        """Manually trigger sending for this scheduled message"""
        self.ensure_one()
        count = self._send_messages()
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
        """Send messages using Meta WhatsApp Cloud API"""
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
        
        # Get company config - needs to be set somewhere
        company = self.env.company
        api_token = self.env['ir.config_parameter'].sudo().get_param('whatsapp.api_token')
        phone_number_id = self.env['ir.config_parameter'].sudo().get_param('whatsapp.phone_number_id')
        
        if not api_token or not phone_number_id:
            return 0
        
        phone_pattern = re.compile(r'^\+?[0-9\s-]{8,}$')
        count = 0
        
        for order in orders:
            partner = order.partner_id
            phone = partner.mobile or partner.phone or getattr(order, 'client_phone', None)
            
            if not phone:
                continue
            
            clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
            
            if len(clean_phone) < 8:
                continue
            
            # Build template parameters
            params = []
            if self.template_id.param_1:
                params.append({"type": "text", "text": partner.name or ''})
            if self.template_id.param_2:
                params.append({"type": "text", "text": order.name or ''})
            if self.template_id.param_3:
                params.append({"type": "text", "text": str(order.amount_total or 0)})
            
            # Send via Meta API
            url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": clean_phone,
                "type": "template",
                "template": {
                    "name": self.template_id.meta_template_name,
                    "language": {"code": self.template_id.language or "en"}
                }
            }
            
            if params:
                payload["template"]["components"] = [{"type": "body", "parameters": params}]
            
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                response_data = response.json()
                status = 'sent' if response.status_code == 200 else 'failed'
                failure_reason = response_data.get('error', {}).get('message') if status == 'failed' else None
                
                if status == 'sent':
                    count += 1
            except Exception as e:
                status = 'failed'
                failure_reason = str(e)
                response_data = {}
            
            # Log
            self.env['whatsapp.message.log'].create({
                'order_id': order.id,
                'partner_id': partner.id,
                'phone': clean_phone,
                'message': f"Scheduled: {self.name} - {self.template_id.meta_template_name}",
                'status': status,
                'api_response': json.dumps(response_data) if response_data else '',
                'failure_reason': failure_reason,
                'direction': 'outgoing',
            })
        
        return count

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
            msg._send_messages()
