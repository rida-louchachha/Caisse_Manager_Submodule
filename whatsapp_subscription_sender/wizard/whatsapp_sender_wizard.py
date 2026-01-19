# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import requests
import json
import re


class WhatsappSubscriptionSender(models.TransientModel):
    _name = 'whatsapp.subscription.sender'
    _description = 'Send WhatsApp to Subscribers'

    order_ids = fields.Many2many('sale.order', string='Subscriptions')
    
    # Template - uses our standalone template model
    template_id = fields.Many2one('whatsapp.subscription.template', string='Select Template', required=True)
    
    # Results
    failed_client_ids = fields.Many2many('res.partner', string='Failed Recipients', readonly=True)
    sent_count = fields.Integer(string='Successfully Sent', readonly=True)
    
    @api.model
    def default_get(self, fields):
        res = super(WhatsappSubscriptionSender, self).default_get(fields)
        if self.env.context.get('active_model') == 'sale.order' and self.env.context.get('active_ids'):
            res['order_ids'] = [(6, 0, self.env.context.get('active_ids'))]
        return res
    
    def action_send_whatsapp(self):
        """Send WhatsApp messages using Meta Cloud API"""
        self.ensure_one()
        failed_partners = self.env['res.partner']
        sent_count = 0
        
        # Get API config
        api_token = self.env['ir.config_parameter'].sudo().get_param('whatsapp.api_token')
        phone_number_id = self.env['ir.config_parameter'].sudo().get_param('whatsapp.phone_number_id')
        
        phone_pattern = re.compile(r'^\+?[0-9\s-]{8,}$')
        
        for order in self.order_ids:
            partner = order.partner_id
            phone = partner.mobile or partner.phone or getattr(order, 'client_phone', None)
            
            if not phone:
                failed_partners |= partner
                self._create_log(order, partner, 'N/A', 'failed', 'No phone number')
                continue
            
            clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
            
            if len(clean_phone) < 8:
                failed_partners |= partner
                self._create_log(order, partner, phone, 'failed', 'Invalid phone number')
                continue
            
            # Send via Meta API if configured
            if api_token and phone_number_id:
                success, error = self._send_via_meta_api(
                    api_token, phone_number_id, clean_phone, order, partner
                )
                if success:
                    sent_count += 1
                else:
                    failed_partners |= partner
                    self._create_log(order, partner, clean_phone, 'failed', error)
            else:
                # Simulation mode
                sent_count += 1
                self._create_log(order, partner, clean_phone, 'sent', 
                    'Simulated (configure API in Settings → Technical → System Parameters)')

        self.write({
            'failed_client_ids': [(6, 0, failed_partners.ids)],
            'sent_count': sent_count
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Send Results'),
            'res_model': 'whatsapp.subscription.sender',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_initial_mode': 'readonly'}
        }
    
    def _send_via_meta_api(self, api_token, phone_number_id, phone, order, partner):
        """Send message via Meta WhatsApp Cloud API"""
        url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        
        # Build parameters
        params = []
        if self.template_id.param_1:
            params.append({"type": "text", "text": partner.name or ''})
        if self.template_id.param_2:
            params.append({"type": "text", "text": order.name or ''})
        if self.template_id.param_3:
            params.append({"type": "text", "text": str(order.amount_total or 0)})
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
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
            
            if response.status_code == 200:
                msg_id = response_data.get('messages', [{}])[0].get('id', '')
                self._create_log(order, partner, phone, 'sent', None, 
                    json.dumps(response_data), msg_id)
                return True, None
            else:
                error = response_data.get('error', {}).get('message', 'API Error')
                return False, error
        except Exception as e:
            return False, str(e)
    
    def _create_log(self, order, partner, phone, status, failure_reason=None, 
                    api_response=None, message_id=None):
        """Create message log entry"""
        conversation = self.env['whatsapp.conversation'].get_or_create_conversation(partner, phone)
        self.env['whatsapp.message.log'].create({
            'order_id': order.id,
            'partner_id': partner.id,
            'phone': phone,
            'message': f"Template: {self.template_id.name}",
            'status': status,
            'api_response': api_response or '',
            'failure_reason': failure_reason,
            'conversation_id': conversation.id if conversation else False,
            'direction': 'outgoing',
            'message_id': message_id or '',
        })
