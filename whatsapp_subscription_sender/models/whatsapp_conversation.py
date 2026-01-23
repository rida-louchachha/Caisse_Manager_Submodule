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
        """Check if the 24-hour window is still active for free-text messages.
        Window is active if customer has sent a message within the last 24 hours.
        """
        from datetime import timedelta
        import logging
        _logger = logging.getLogger(__name__)
        
        now = fields.Datetime.now()
        window_start = now - timedelta(hours=24)
        
        for conv in self:
            is_active = False
            latest_incoming_date = None
            phone = conv.phone or ''
            
            _logger.info(f"Checking 24h window for conversation {conv.id}, phone: {phone}")
            
            # Method 1: Check stored date first
            if conv.last_customer_message_date:
                window_end = conv.last_customer_message_date + timedelta(hours=24)
                if now <= window_end:
                    is_active = True
                    _logger.info(f"  -> Active via stored date: {conv.last_customer_message_date}")
            
            # Method 2: Check linked message_ids
            if not is_active and conv.message_ids:
                incoming_msgs = conv.message_ids.filtered(
                    lambda m: m.direction == 'incoming' and m.create_date >= window_start
                )
                if incoming_msgs:
                    is_active = True
                    latest_incoming_date = max(m.create_date for m in incoming_msgs)
                    _logger.info(f"  -> Active via linked messages, count: {len(incoming_msgs)}")
            
            # Method 3: Search ALL incoming messages with flexible phone matching
            if not is_active and phone:
                # Extract just the digits from phone
                phone_digits = ''.join(c for c in phone if c.isdigit())
                
                # Search for ANY incoming message matching this phone (last 9 digits)
                phone_pattern = '%' + phone_digits[-9:] + '%' if len(phone_digits) >= 9 else '%' + phone_digits + '%'
                
                try:
                    incoming_msg = self.env['whatsapp.message.log'].search([
                        ('direction', '=', 'incoming'),
                        ('create_date', '>=', window_start),
                        ('phone', 'ilike', phone_pattern)
                    ], limit=1, order='create_date desc')
                    
                    if incoming_msg:
                        is_active = True
                        latest_incoming_date = incoming_msg.create_date
                        _logger.info(f"  -> Active via phone search, found message ID: {incoming_msg.id}, phone: {incoming_msg.phone}")
                        
                        # Link this message to the conversation if not linked
                        if not incoming_msg.conversation_id:
                            incoming_msg.write({'conversation_id': conv.id})
                except Exception as e:
                    _logger.warning(f"  -> Error searching messages: {e}")
            
            # Update the stored date for future checks
            if latest_incoming_date:
                if not conv.last_customer_message_date or latest_incoming_date > conv.last_customer_message_date:
                    try:
                        conv.sudo().write({'last_customer_message_date': latest_incoming_date})
                        _logger.info(f"  -> Updated last_customer_message_date to {latest_incoming_date}")
                    except Exception as e:
                        _logger.warning(f"  -> Error updating date: {e}")
            
            if not is_active:
                _logger.info(f"  -> 24h window NOT active for {phone}")
            
            conv.is_24h_window_active = is_active

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

    def action_refresh_24h_window(self):
        """Manually refresh the 24h window by checking messages in the database"""
        self.ensure_one()
        self.link_orphan_messages()
        # Force recompute
        self._compute_is_24h_window_active()
        return True

    def action_debug_24h(self):
        """Debug action to show why 24h window is/isn't active"""
        self.ensure_one()
        from datetime import timedelta
        now = fields.Datetime.now()
        window_start = now - timedelta(hours=24)
        
        phone = self.phone or ''
        phone_digits = ''.join(c for c in phone if c.isdigit())
        phone_pattern = '%' + phone_digits[-9:] + '%' if len(phone_digits) >= 9 else '%' + phone_digits + '%'
        
        # Get info
        linked_count = len(self.message_ids.filtered(lambda m: m.direction == 'incoming'))
        linked_recent = len(self.message_ids.filtered(lambda m: m.direction == 'incoming' and m.create_date >= window_start))
        
        all_incoming = self.env['whatsapp.message.log'].search([
            ('direction', '=', 'incoming'),
            ('create_date', '>=', window_start)
        ])
        
        matching = self.env['whatsapp.message.log'].search([
            ('direction', '=', 'incoming'),
            ('create_date', '>=', window_start),
            ('phone', 'ilike', phone_pattern)
        ])
        
        msg = f"""
🔍 DEBUG: 24h Window Check

📞 Conversation Phone: {phone}
🔢 Phone Digits: {phone_digits}
🔎 Search Pattern: {phone_pattern}

📅 Last Customer Message Date: {self.last_customer_message_date}
✅ Is 24h Window Active: {self.is_24h_window_active}

📨 Linked Messages (incoming): {linked_count}
📨 Linked Recent (24h): {linked_recent}

🌍 All Incoming Messages (24h): {len(all_incoming)}
🎯 Matching Phone Pattern: {len(matching)}

Sample phones in matching messages:
"""
        for m in matching[:5]:
            msg += f"  - ID {m.id}: {m.phone} ({m.create_date})\n"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🔍 24h Window Debug',
                'message': msg,
                'type': 'info',
                'sticky': True,
            }
        }

    def link_orphan_messages(self):
        """Link orphan message logs to this conversation by phone number"""
        self.ensure_one()
        phone_clean = ''.join(c for c in (self.phone or '') if c.isdigit())
        phone_last9 = phone_clean[-9:] if len(phone_clean) >= 9 else phone_clean
        
        if not phone_last9:
            return
        
        # Find orphan messages (no conversation_id) with matching phone
        orphans = self.env['whatsapp.message.log'].search([
            ('conversation_id', '=', False),
            '|', '|', '|',
            ('phone', '=', self.phone),
            ('phone', '=', phone_clean),
            ('phone', 'like', phone_last9),
            ('phone', '=', '+' + phone_clean),
        ])
        
        if orphans:
            orphans.write({'conversation_id': self.id})
            
    @api.model
    def fix_all_conversations(self):
        """Utility method to fix all conversations - link orphan messages and update 24h windows"""
        for conv in self.search([]):
            conv.link_orphan_messages()
            conv._compute_is_24h_window_active()
        return True

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
    def get_or_create_conversation_by_phone(self, phone, name=None, partner_id=None):
        """
        Find or create a conversation by phone number.
        Creates a new contact if needed.
        Used by the frontend new chat modal.
        """
        clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        # Try to find existing conversation
        conv = self.search([('phone', 'ilike', clean_phone[-9:])], limit=1)
        if conv:
            return {'id': conv.id, 'phone': conv.phone, 'partner_id': conv.partner_id.id}
        
        # Find or create partner
        partner = None
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
            if not partner.exists():
                partner = None
        
        if not partner:
            # Search by phone
            partner = self.env['res.partner'].search([
                '|', ('mobile', 'ilike', clean_phone[-9:]), ('phone', 'ilike', clean_phone[-9:])
            ], limit=1)
        
        if not partner:
            # Create new partner
            partner = self.env['res.partner'].create({
                'name': name or f'WhatsApp {clean_phone}',
                'mobile': clean_phone,
            })
        
        # Create conversation
        conv = self.create({
            'partner_id': partner.id,
            'phone': clean_phone,
        })
        
        return {'id': conv.id, 'phone': conv.phone, 'partner_id': partner.id}

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
    def send_chat_message(self, partner_id, message_text, phone=None, skip_24h_check=False):
        """
        Send a free-text message via Meta WhatsApp Cloud API.
        
        Args:
            partner_id: res.partner ID
            message_text: The message to send
            phone: Optional phone number (will use partner's phone if not provided)
            skip_24h_check: If True, bypass the 24-hour window check (for testing)
        """
        import requests
        import json
        import logging
        _logger = logging.getLogger(__name__)
        
        # Get partner
        partner = self.env['res.partner'].browse(partner_id) if partner_id else False
        if not partner or not partner.exists():
            # Try to find partner by phone
            if phone:
                partner = self.env['res.partner'].search([
                    '|', ('mobile', 'ilike', phone[-9:]), ('phone', 'ilike', phone[-9:])
                ], limit=1)
        
        # Get phone number
        clean_phone = phone or (partner.mobile if partner else '') or (partner.phone if partner else '') or ''
        clean_phone = ''.join(c for c in clean_phone if c.isdigit() or c == '+')
        
        if not clean_phone:
            return {'status': 'error', 'message': 'No phone number provided'}
        
        # Format for WhatsApp API (no + prefix)
        wa_phone = clean_phone.lstrip('+')
        
        _logger.info(f"Sending WhatsApp message to {wa_phone}: {message_text[:50]}...")
        
        # Find or create conversation
        conversation = self.search([('phone', 'ilike', wa_phone[-9:])], limit=1)
        if not conversation and partner:
            conversation = self.get_or_create_conversation(partner, clean_phone)
        
        # Check 24-hour window (can be bypassed via system parameter)
        enforce_24h = self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.enforce_24h_window', 'False'
        ).lower() in ('true', '1', 'yes')
        
        if enforce_24h and not skip_24h_check:
            if conversation and not conversation.is_24h_window_active:
                msg = ("⏰ 24-hour window expired. The customer needs to reply first. "
                       "Use a Template message to re-engage the customer.")
                return {'status': 'error', 'message': msg}
        
        # Get WhatsApp channel configuration from social.channel
        whatsapp_channel = self.env['social.channel'].search([
            ('channel_type', '=', 'whatsapp'),
            ('state', '=', 'connected')
        ], limit=1)
        
        if not whatsapp_channel:
            # Try any WhatsApp channel with credentials
            whatsapp_channel = self.env['social.channel'].search([
                ('channel_type', '=', 'whatsapp'),
                ('access_token', '!=', False)
            ], limit=1)
        
        if not whatsapp_channel or not whatsapp_channel.access_token:
            return {
                'status': 'error', 
                'message': 'WhatsApp channel not configured. Please configure your WhatsApp Business API credentials in Social Inbox → Channels.'
            }
        
        # Prepare the API call to Meta WhatsApp Cloud API
        access_token = whatsapp_channel.access_token
        phone_number_id = whatsapp_channel.whatsapp_phone_number_id
        
        if not phone_number_id:
            return {
                'status': 'error',
                'message': 'WhatsApp Phone Number ID not configured. Please set the Phone Number ID in your WhatsApp channel configuration.'
            }
        
        # Meta WhatsApp Cloud API endpoint
        api_url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
        
        # Prepare the message payload
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": wa_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message_text
            }
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Prepare log entry
        log_vals = {
            'partner_id': partner.id if partner else False,
            'phone': clean_phone,
            'message': message_text,
            'direction': 'outgoing',
            'create_date': fields.Datetime.now(),
            'conversation_id': conversation.id if conversation else False,
            'channel_id': whatsapp_channel.id,
        }
        
        try:
            # Make the API call
            _logger.info(f"Calling Meta WhatsApp API: {api_url}")
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            
            _logger.info(f"API Response: {response.status_code} - {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                message_id = result.get('messages', [{}])[0].get('id', '')
                
                log_vals['status'] = 'sent'
                log_vals['message_id'] = message_id
                log_entry = self.env['whatsapp.message.log'].create(log_vals)
                
                return {
                    'status': 'success', 
                    'id': log_entry.id,
                    'whatsapp_message_id': message_id
                }
            else:
                error_data = response.json().get('error', {})
                error_msg = error_data.get('message', response.text)
                error_code = error_data.get('code', response.status_code)
                
                # Handle specific WhatsApp API errors
                if error_code == 131026:
                    error_msg = "Message not sent: Customer hasn't replied in 24 hours. Please send a Template message first."
                elif error_code == 131047:
                    error_msg = "Re-engagement required: Too much time passed since customer's last message. Use a Template."
                elif error_code == 100:
                    error_msg = f"Invalid phone number format: {wa_phone}"
                
                _logger.warning(f"WhatsApp API error: {error_code} - {error_msg}")
                
                log_vals['status'] = 'failed'
                log_vals['failure_reason'] = f"API Error {error_code}: {error_msg}"
                self.env['whatsapp.message.log'].create(log_vals)
                
                return {'status': 'error', 'message': error_msg}
                
        except requests.exceptions.Timeout:
            error_msg = "Request timed out while connecting to WhatsApp API"
            log_vals['status'] = 'failed'
            log_vals['failure_reason'] = error_msg
            self.env['whatsapp.message.log'].create(log_vals)
            return {'status': 'error', 'message': error_msg}
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            _logger.error(f"WhatsApp API request failed: {e}")
            log_vals['status'] = 'failed'
            log_vals['failure_reason'] = error_msg
            self.env['whatsapp.message.log'].create(log_vals)
            return {'status': 'error', 'message': error_msg}
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            _logger.exception(f"Unexpected error sending WhatsApp message: {e}")
            log_vals['status'] = 'failed'
            log_vals['failure_reason'] = error_msg
            self.env['whatsapp.message.log'].create(log_vals)
            return {'status': 'error', 'message': error_msg}


