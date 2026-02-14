from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'
    
    # Note: WhatsApp API configuration is now handled by Odoo's whatsapp.account model
    # Configure it in WhatsApp → Configuration → WhatsApp Accounts
    
    # Keep only subscription-specific settings if needed
    whatsapp_subscription_reminder_enabled = fields.Boolean(
        string='WhatsApp Subscription Reminders',
        default=True,
        help='Enable automatic WhatsApp reminders for subscriptions'
    )
