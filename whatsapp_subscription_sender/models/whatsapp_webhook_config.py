from odoo import models, fields, api


class WhatsappWebhookConfig(models.Model):
    _name = 'whatsapp.webhook.config'
    _description = 'WhatsApp Webhook Configuration'
    _rec_name = 'name'
    
    name = fields.Char(string='Configuration Name', default='Default', required=True)
    active = fields.Boolean(default=True)
    
    # Webhook Settings
    callback_url = fields.Char(
        string='Callback URL',
        compute='_compute_callback_url',
        help='This is the URL you should enter in Meta for Developers'
    )
    verify_token = fields.Char(
        string='Verify Token',
        default=lambda self: self._generate_token(),
        help='Token used to verify webhook requests from Meta'
    )
    
    # API Settings
    api_token = fields.Char(
        string='Meta API Token',
        help='Your Meta WhatsApp Cloud API access token'
    )
    phone_number_id = fields.Char(
        string='Phone Number ID',
        help='Your WhatsApp Business Phone Number ID from Meta'
    )
    business_account_id = fields.Char(
        string='Business Account ID',
        help='Your WhatsApp Business Account ID (optional)'
    )
    
    # Webhook Status
    webhook_verified = fields.Boolean(
        string='Webhook Verified',
        default=False,
        readonly=True,
        help='Whether Meta has successfully verified this webhook'
    )
    last_webhook_activity = fields.Datetime(
        string='Last Webhook Activity',
        readonly=True
    )
    
    @api.depends('verify_token')
    def _compute_callback_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.callback_url = f"{base_url}/whatsapp/webhook"
    
    def _generate_token(self):
        """Generate a random verify token"""
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(32))
    
    def action_regenerate_token(self):
        """Regenerate the verify token"""
        self.verify_token = self._generate_token()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Token Regenerated',
                'message': 'New verify token generated. Remember to update it in Meta!',
                'type': 'warning',
            }
        }
    
    def action_copy_callback_url(self):
        """Helper action - the actual copy is done via JS"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Callback URL',
                'message': f'Copy this URL to Meta: {self.callback_url}',
                'type': 'info',
            }
        }
    
    def action_test_connection(self):
        """Test the API connection"""
        import requests
        
        if not self.api_token or not self.phone_number_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Missing Configuration',
                    'message': 'Please fill in API Token and Phone Number ID',
                    'type': 'warning',
                }
            }
        
        try:
            url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}"
            headers = {"Authorization": f"Bearer {self.api_token}"}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Successful!',
                        'message': 'WhatsApp API connection is working.',
                        'type': 'success',
                    }
                }
            else:
                error = response.json().get('error', {}).get('message', 'Unknown error')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Failed',
                        'message': f'API Error: {error}',
                        'type': 'danger',
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Connection Error',
                    'message': str(e),
                    'type': 'danger',
                }
            }
    
    @api.model
    def get_active_config(self):
        """Get the active webhook configuration"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            config = self.create({'name': 'Default Configuration'})
        return config
    
    def write(self, vals):
        """Sync values to system parameters for the controller to use"""
        res = super().write(vals)
        if 'verify_token' in vals:
            self.env['ir.config_parameter'].sudo().set_param('whatsapp.verify_token', vals['verify_token'])
        if 'api_token' in vals:
            self.env['ir.config_parameter'].sudo().set_param('whatsapp.api_token', vals['api_token'])
        if 'phone_number_id' in vals:
            self.env['ir.config_parameter'].sudo().set_param('whatsapp.phone_number_id', vals['phone_number_id'])
        return res
    
    @api.model_create_multi
    def create(self, vals_list):
        """Sync values to system parameters on create"""
        records = super().create(vals_list)
        for record in records:
            if record.verify_token:
                self.env['ir.config_parameter'].sudo().set_param('whatsapp.verify_token', record.verify_token)
            if record.api_token:
                self.env['ir.config_parameter'].sudo().set_param('whatsapp.api_token', record.api_token)
            if record.phone_number_id:
                self.env['ir.config_parameter'].sudo().set_param('whatsapp.phone_number_id', record.phone_number_id)
        return records
