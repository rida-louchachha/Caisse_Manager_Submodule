from odoo import models, fields, api

class WhatsappConversation(models.Model):
    _name = 'whatsapp.conversation'
    _description = 'WhatsApp Conversation'
    _order = 'last_message_date desc'

    partner_id = fields.Many2one('res.partner', string='Contact', required=True, ondelete='cascade')
    phone = fields.Char(string='WhatsApp Number', required=True, index=True)
    
    # Conversation preview
    last_message = fields.Text(string='Last Message', compute='_compute_last_message', store=True)
    last_message_date = fields.Datetime(string='Last Activity', compute='_compute_last_message', store=True)
    unread_count = fields.Integer(string='Unread', compute='_compute_unread_count')
    
    # 24-hour window tracking (for WhatsApp Business API policy)
    last_customer_message_date = fields.Datetime(string='Last Customer Reply', 
                                                   help='When the customer last messaged us. Free-text replies are allowed within 24 hours.')
    is_24h_window_active = fields.Boolean(string='24h Window Active', compute='_compute_is_24h_window_active')
    
    # Messages
    message_ids = fields.One2many('whatsapp.message.log', 'conversation_id', string='Messages')
    
    _sql_constraints = [
        ('phone_unique', 'unique(phone)', 'A conversation with this phone number already exists!')
    ]

    def _compute_is_24h_window_active(self):
        """Check if the 24-hour window is still active for free-text messages"""
        from datetime import timedelta
        now = fields.Datetime.now()
        for conv in self:
            if conv.last_customer_message_date:
                window_end = conv.last_customer_message_date + timedelta(hours=24)
                conv.is_24h_window_active = now <= window_end
            else:
                conv.is_24h_window_active = False

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
            # Also try without + prefix
            clean_phone_no_plus = clean_phone.lstrip('+')
            conv = self.search([('phone', 'like', clean_phone_no_plus)], limit=1)
        if not conv:
            conv = self.create({
                'partner_id': partner.id,
                'phone': clean_phone
            })
        return conv

    @api.model
    def receive_incoming_message(self, phone, message_text, partner_id=None, message_id=None):
        """
        Handle an incoming message from a customer.
        Updates the 24-hour window and creates a message log entry.
        Called by the WhatsApp webhook controller.
        """
        clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        # Find conversation by phone number
        conversation = self.search([('phone', '=', clean_phone)], limit=1)
        if not conversation:
            clean_phone_no_plus = clean_phone.lstrip('+')
            conversation = self.search([('phone', 'like', clean_phone_no_plus)], limit=1)
        
        # If no conversation exists, try to find or create one
        partner = None
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
        if not partner or not partner.exists():
            # Try to find partner by phone
            partner = self.env['res.partner'].search([
                '|', ('mobile', 'like', clean_phone), ('phone', 'like', clean_phone)
            ], limit=1)
        
        if not partner:
            # Create a new partner for this phone number
            partner = self.env['res.partner'].create({
                'name': f'WhatsApp {clean_phone}',
                'mobile': clean_phone,
            })
        
        if not conversation:
            conversation = self.get_or_create_conversation(partner, clean_phone)
        
        # UPDATE THE 24-HOUR WINDOW - This is critical!
        conversation.write({
            'last_customer_message_date': fields.Datetime.now()
        })
        
        # Create message log entry
        msg_vals = {
            'partner_id': partner.id,
            'phone': clean_phone,
            'message': message_text,
            'direction': 'incoming',
            'status': 'received',
            'is_read': False,
            'conversation_id': conversation.id,
            'message_id': message_id,
        }
        
        msg = self.env['whatsapp.message.log'].create(msg_vals)
        return {'status': 'success', 'message_id': msg.id, 'conversation_id': conversation.id}

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

    @api.model
    def send_chat_message(self, partner_id, message_text, phone=None):
        """
        Send a free-text message to a partner using Odoo's WhatsApp machinery.
        Checks the 24-hour window first, then tries:
        1. Post to existing discuss.channel (best approach for ongoing conversations)
        2. Use Odoo's whatsapp.message model to send via Meta API directly
        3. Falls back to informative error if no channel and API not available
        """
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return {'status': 'error', 'message': 'Partner not found'}

        # Get phone number - prefer passed phone, then partner mobile/phone
        clean_phone = phone or partner.mobile or partner.phone or ''
        clean_phone = ''.join(c for c in clean_phone if c.isdigit() or c == '+')
        
        if not clean_phone:
            return {'status': 'error', 'message': 'No phone number on contact'}
        
        # Find conversation by PHONE NUMBER (more reliable than partner_id)
        conversation = self.search([('phone', '=', clean_phone)], limit=1)
        if not conversation:
            # Try without + prefix
            clean_phone_no_plus = clean_phone.lstrip('+')
            conversation = self.search([('phone', 'like', clean_phone_no_plus)], limit=1)
        if not conversation:
            conversation = self.get_or_create_conversation(partner, clean_phone)

        # Check if 24-hour window is active
        if not conversation.is_24h_window_active:
            msg = ("⏰ 24-hour window expired or not started. The customer needs to reply first. "
                   "Use the 📎 button to send a Template message to re-engage the customer.")
            return {'status': 'error', 'message': msg}

        # Prepare log entry values
        log_vals = {
            'partner_id': partner.id,
            'phone': clean_phone,
            'message': message_text,
            'direction': 'outgoing',
            'create_date': fields.Datetime.now(),
            'conversation_id': conversation.id,
        }

        # Strategy 1: Try to find an existing WhatsApp channel with this partner
        discuss_channel = self.env['discuss.channel'].search([
            ('channel_type', '=', 'whatsapp'),
            ('channel_member_ids.partner_id', '=', partner.id)
        ], limit=1, order='create_date desc')
        
        if discuss_channel:
            try:
                # Post to the WhatsApp channel - Odoo's WhatsApp module will forward to Meta API
                discuss_channel.message_post(
                    body=message_text,
                    message_type='whatsapp_message',
                    subtype_xmlid='mail.mt_comment'
                )
                log_vals['status'] = 'sent'
                log_entry = self.env['whatsapp.message.log'].create(log_vals)
                return {'status': 'success', 'id': log_entry.id}
            except Exception as e:
                log_vals['status'] = 'failed'
                log_vals['failure_reason'] = f"Channel post failed: {str(e)}"
                self.env['whatsapp.message.log'].create(log_vals)
                return {'status': 'error', 'message': str(e)}
        
        # Strategy 2: Try using Odoo's WhatsApp API directly
        try:
            # Get the connected WhatsApp Business Account
            if 'whatsapp.account' in self.env:
                wa_account = self.env['whatsapp.account'].search([
                    ('state', '=', 'connected')
                ], limit=1)
                
                if wa_account:
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.info(f"Attempting to send free-text via WhatsApp API to {clean_phone}")
                    
                    # Format phone number for WhatsApp API (remove + prefix if present)
                    wa_phone = clean_phone.lstrip('+')
                    
                    # Try to send using whatsapp.account's API methods
                    # Odoo Enterprise typically has _api_send_message or similar
                    if hasattr(wa_account, '_send_whatsapp'):
                        # Use Odoo's built-in method
                        wa_account._send_whatsapp(
                            phone_number=wa_phone,
                            message=message_text,
                        )
                        log_vals['status'] = 'sent'
                        log_entry = self.env['whatsapp.message.log'].create(log_vals)
                        return {'status': 'success', 'id': log_entry.id}
                    
                    # Alternative: Create whatsapp.message record if model exists
                    if 'whatsapp.message' in self.env:
                        msg_vals = {
                            'mobile_number': wa_phone,
                            'wa_account_id': wa_account.id,
                            'message_type': 'outgoing',
                        }
                        # Check what fields the model has
                        msg_model = self.env['whatsapp.message']
                        if 'body' in msg_model._fields:
                            msg_vals['body'] = message_text
                        elif 'free_text_json' in msg_model._fields:
                            import json
                            msg_vals['free_text_json'] = json.dumps({'body': message_text})
                        
                        wa_message = msg_model.create(msg_vals)
                        
                        # Try to send
                        if hasattr(wa_message, '_send_message'):
                            wa_message._send_message()
                        elif hasattr(wa_message, '_send'):
                            wa_message._send()
                        elif hasattr(wa_message, 'send'):
                            wa_message.send()
                        
                        log_vals['status'] = 'sent'
                        log_entry = self.env['whatsapp.message.log'].create(log_vals)
                        return {'status': 'success', 'id': log_entry.id}
                        
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"WhatsApp API send failed: {str(e)}")
            # Fall through to error message - this likely means 24-hour window expired
        
        # No channel exists and direct API failed
        # Meta WhatsApp Business API policy requires customer to message first for free-text
        msg = "No active WhatsApp conversation found. To start a new conversation, please use the 📎 button to send a Template message first. You can then reply with free text within 24 hours of the customer's response."
        log_vals['status'] = 'failed'
        log_vals['failure_reason'] = msg
        self.env['whatsapp.message.log'].create(log_vals)
        return {'status': 'error', 'message': msg}


