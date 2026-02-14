# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class WhatsappSubscriptionSender(models.TransientModel):
    _name = 'whatsapp.subscription.sender'
    _description = 'Send WhatsApp to Subscribers'

    order_ids = fields.Many2many('sale.order', string='Subscriptions')
    
    # Direct partner mode (from chat interface)
    partner_id = fields.Many2one('res.partner', string='Contact')
    phone = fields.Char(string='Phone')
    
    # Template - uses Odoo's built-in whatsapp.template model
    template_id = fields.Many2one('whatsapp.template', string='Select Template', required=True,
        domain="[('status', '=', 'approved')]",
        help='Select an approved WhatsApp template')
    
    # Preview fields
    preview_text = fields.Text(string='Template Preview', compute='_compute_preview')
    
    # Results
    failed_client_ids = fields.Many2many('res.partner', string='Failed Recipients', readonly=True)
    sent_count = fields.Integer(string='Successfully Sent', readonly=True)
    total_count = fields.Integer(string='Total Recipients', compute='_compute_counts')
    
    @api.model
    def default_get(self, fields_list):
        res = super(WhatsappSubscriptionSender, self).default_get(fields_list)
        # From sale.order context (bulk send from subscriptions)
        if self.env.context.get('active_model') == 'sale.order' and self.env.context.get('active_ids'):
            res['order_ids'] = [(6, 0, self.env.context.get('active_ids'))]
        # Direct partner context (from chat interface)
        if self.env.context.get('default_partner_id'):
            res['partner_id'] = self.env.context.get('default_partner_id')
        if self.env.context.get('default_phone'):
            res['phone'] = self.env.context.get('default_phone')
        return res
    
    @api.depends('template_id')
    def _compute_preview(self):
        for wizard in self:
            if wizard.template_id:
                wizard.preview_text = wizard.template_id.body or 'No preview available'
            else:
                wizard.preview_text = 'Select a template to see preview'
    
    @api.depends('order_ids', 'partner_id')
    def _compute_counts(self):
        for wizard in self:
            if wizard.order_ids:
                wizard.total_count = len(wizard.order_ids)
            elif wizard.partner_id:
                wizard.total_count = 1
            else:
                wizard.total_count = 0
    
    def action_send_whatsapp(self):
        """Send WhatsApp messages using Odoo's WhatsApp module"""
        self.ensure_one()
        
        # Mode 1: Bulk send to orders
        if self.order_ids:
            return self._send_to_orders()
        
        # Mode 2: Direct send to partner (from chat)
        if self.partner_id:
            return self._send_to_partner()
        
        return {'type': 'ir.actions.act_window_close'}
    
    def _send_to_partner(self):
        """Send template to a single partner (from chat interface)"""
        partner = self.partner_id
        phone = self.phone or partner.mobile or partner.phone
        
        if not phone:
            return self._show_result(0, partner)
        
        clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        try:
            # Find any sale.order for this partner to use as context for template
            order = self.env['sale.order'].search([
                ('partner_id', '=', partner.id)
            ], limit=1, order='create_date desc')
            
            if order:
                # Use order context for template variables
                composer = self.env['whatsapp.composer'].with_context(
                    active_model='sale.order',
                    active_id=order.id,
                    active_ids=[order.id],
                ).create({
                    'wa_template_id': self.template_id.id,
                })
                composer.action_send_whatsapp_template()
            else:
                # Send without order context (use res.partner)
                composer = self.env['whatsapp.composer'].with_context(
                    active_model='res.partner',
                    active_id=partner.id,
                    active_ids=[partner.id],
                ).create({
                    'wa_template_id': self.template_id.id,
                })
                composer.action_send_whatsapp_template()
            
            # Log success
            self._create_log(None, partner, clean_phone, 'sent')
            return self._show_result(1, self.env['res.partner'])
            
        except Exception as e:
            _logger.error("Failed to send WhatsApp to %s: %s", partner.name, str(e))
            self._create_log(None, partner, clean_phone, 'failed', str(e))
            return self._show_result(0, partner)
    
    def _send_to_orders(self):
        """Send template to multiple orders (bulk mode)"""
        failed_partners = self.env['res.partner']
        sent_count = 0
        
        for order in self.order_ids:
            partner = order.partner_id
            phone = partner.mobile or partner.phone
            
            if not phone:
                failed_partners |= partner
                self._create_log(order, partner, 'N/A', 'failed', 'No phone number')
                continue
            
            clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
            
            if len(clean_phone) < 8:
                failed_partners |= partner
                self._create_log(order, partner, phone, 'failed', 'Invalid phone number')
                continue
            
            try:
                # Use Odoo's WhatsApp composer with context
                composer = self.env['whatsapp.composer'].with_context(
                    active_model='sale.order',
                    active_id=order.id,
                    active_ids=[order.id],
                ).create({
                    'wa_template_id': self.template_id.id,
                })
                composer.action_send_whatsapp_template()
                
                sent_count += 1
                self._create_log(order, partner, clean_phone, 'sent')
                
            except Exception as e:
                _logger.error("Failed to send WhatsApp to %s: %s", partner.name, str(e))
                failed_partners |= partner
                self._create_log(order, partner, clean_phone, 'failed', str(e))

        return self._show_result(sent_count, failed_partners)
    
    def _show_result(self, sent_count, failed_partners):
        """Show result dialog"""
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
    
    def _create_log(self, order, partner, phone, status, failure_reason=None):
        """Create message log entry"""
        # Get or create conversation
        try:
            conversation = self.env['whatsapp.conversation'].get_or_create_conversation(partner, phone)
        except Exception:
            conversation = None
        
        log_vals = {
            'partner_id': partner.id,
            'phone': phone,
            'message': f"Template: {self.template_id.name}",
            'status': status,
            'failure_reason': failure_reason,
            'conversation_id': conversation.id if conversation else False,
            'direction': 'outgoing',
        }
        if order:
            log_vals['order_id'] = order.id
            
        self.env['whatsapp.message.log'].create(log_vals)

