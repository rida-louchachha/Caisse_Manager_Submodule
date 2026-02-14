# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class WhatsAppWebhookController(http.Controller):
    """
    Webhook controller for Meta WhatsApp Cloud API
    
    Callback URL: https://your-domain.com/whatsapp/webhook
    Verify Token: social.channel.webhook_secret on WhatsApp channel
    """
    
    @http.route('/whatsapp/webhook', type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def whatsapp_webhook(self, **kwargs):
        """
        Handle WhatsApp webhook - both verification and incoming messages
        
        GET: Webhook verification from Meta
        POST: Incoming messages from Meta
        """
        if request.httprequest.method == 'GET':
            return self._verify_webhook(kwargs)
        else:
            return self._process_webhook()
    
    def _verify_webhook(self, params):
        """Verify webhook with Meta (GET request)"""
        try:
            mode = params.get('hub.mode')
            token = params.get('hub.verify_token')
            challenge = params.get('hub.challenge')

            wa_channel = request.env["social.channel"].sudo().search(
                ["|", ("channel_type", "=", "whatsapp"), ("code", "in", ["whatsapp", "cm_whatsapp"])],
                limit=1,
            )
            verify_token = (wa_channel.webhook_secret if wa_channel else "") or ""
            
            _logger.info("Webhook verification attempt: mode=%s, token=%s, expected=%s", 
                        mode, token, verify_token)
            
            if mode == 'subscribe' and token == verify_token:
                _logger.info("WhatsApp webhook verified successfully")
                return str(challenge)
            else:
                _logger.warning("WhatsApp webhook verification failed - token mismatch or wrong mode")
                return 'Verification failed'
        except Exception as e:
            _logger.error("Error in webhook verification: %s", str(e))
            return f'Error: {str(e)}'
    
    def _process_webhook(self):
        """Process incoming webhook (POST request)"""
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            _logger.info("Received WhatsApp webhook: %s", json.dumps(data, indent=2))
            
            # Process the webhook data
            if 'entry' in data:
                for entry in data['entry']:
                    changes = entry.get('changes', [])
                    for change in changes:
                        value = change.get('value', {})
                        
                        # Handle incoming messages
                        if 'messages' in value:
                            self._process_incoming_messages(value)
                        
                        # Handle status updates (sent, delivered, read)
                        if 'statuses' in value:
                            self._process_status_updates(value)
            
            return json.dumps({'status': 'ok'})
        
        except Exception as e:
            _logger.error("Error processing WhatsApp webhook: %s", str(e))
            return json.dumps({'status': 'error', 'message': str(e)})
    
    def _process_incoming_messages(self, value):
        """Process incoming WhatsApp messages"""
        try:
            messages = value.get('messages', [])
            contacts = value.get('contacts', [])
            
            for message in messages:
                phone = message.get('from')
                msg_id = message.get('id')
                msg_type = message.get('type')
                
                # Get sender name from contacts
                sender_name = ''
                for contact in contacts:
                    if contact.get('wa_id') == phone:
                        sender_name = contact.get('profile', {}).get('name', '')
                        break
                
                # Get message content
                if msg_type == 'text':
                    text = message.get('text', {}).get('body', '')
                elif msg_type == 'button':
                    text = message.get('button', {}).get('text', '')
                elif msg_type == 'interactive':
                    interactive = message.get('interactive', {})
                    if interactive.get('type') == 'button_reply':
                        text = interactive.get('button_reply', {}).get('title', '')
                    elif interactive.get('type') == 'list_reply':
                        text = interactive.get('list_reply', {}).get('title', '')
                    else:
                        text = '[Interactive message]'
                else:
                    text = f'[{msg_type} message]'
                
                _logger.info("Incoming message from %s (%s): %s", phone, sender_name, text)
                
                # Find or create partner
                partner = self._find_or_create_partner(phone, sender_name)
                
                # USE receive_incoming_message to properly handle the message
                # This updates the 24-hour window and creates the message log
                try:
                    result = request.env['whatsapp.conversation'].sudo().receive_incoming_message(
                        phone=phone,
                        message_text=text,
                        partner_id=partner.id if partner else None,
                        message_id=msg_id
                    )
                    _logger.info("Incoming message processed: %s", result)
                except Exception as e:
                    _logger.error("Error using receive_incoming_message: %s - falling back to direct log", str(e))
                    # Fallback: Log the incoming message directly
                    try:
                        Conversation = request.env['whatsapp.conversation'].sudo()
                        conversation = Conversation.get_or_create_conversation(partner, phone)
                        
                        # Update 24h window manually
                        from odoo import fields
                        conversation.write({'last_customer_message_date': fields.Datetime.now()})
                        
                        request.env['whatsapp.message.log'].sudo().create({
                            'partner_id': partner.id if partner else False,
                            'phone': phone,
                            'message': text,
                            'status': 'received',
                            'direction': 'incoming',
                            'message_id': msg_id,
                            'external_user_id': phone,
                            'conversation_id': conversation.id if conversation else False,
                        })
                    except Exception as e2:
                        _logger.error("Could not log message: %s", str(e2))
        except Exception as e:
            _logger.error("Error processing incoming messages: %s", str(e))
    
    def _process_status_updates(self, value):
        """Process message status updates (sent, delivered, read)"""
        try:
            statuses = value.get('statuses', [])
            
            for status in statuses:
                msg_id = status.get('id')
                status_type = status.get('status')
                recipient = status.get('recipient_id')
                
                _logger.info("Message %s status: %s (recipient: %s)", msg_id, status_type, recipient)
                
                # Update message log if exists
                if msg_id:
                    try:
                        logs = request.env['whatsapp.message.log'].sudo().search([
                            ('message_id', '=', msg_id)
                        ], limit=1)
                        
                        if logs:
                            if status_type == 'delivered':
                                logs.write({'status': 'delivered'})
                            elif status_type == 'read':
                                logs.write({'status': 'read'})
                            elif status_type == 'failed':
                                error = status.get('errors', [{}])[0]
                                logs.write({
                                    'status': 'failed',
                                    'failure_reason': error.get('message', 'Unknown error')
                                })
                    except Exception as e:
                        _logger.warning("Could not update message status: %s", str(e))
        except Exception as e:
            _logger.error("Error processing status updates: %s", str(e))
    
    def _find_or_create_partner(self, phone, name):
        """Find existing partner by phone or create new one"""
        try:
            Partner = request.env['res.partner'].sudo()
            
            # Clean phone number for search
            clean_phone = phone.replace('+', '').replace(' ', '').replace('-', '')
            
            # Search by phone or mobile
            partner = Partner.search([
                '|',
                ('phone', 'ilike', clean_phone[-9:]),
                ('mobile', 'ilike', clean_phone[-9:])
            ], limit=1)
            
            if not partner and name:
                # Create new partner
                partner = Partner.create({
                    'name': name or f'WhatsApp {phone}',
                    'mobile': phone,
                })
                _logger.info("Created new partner for WhatsApp user: %s (%s)", name, phone)
            
            return partner
        except Exception as e:
            _logger.error("Error finding/creating partner: %s", str(e))
            return None
