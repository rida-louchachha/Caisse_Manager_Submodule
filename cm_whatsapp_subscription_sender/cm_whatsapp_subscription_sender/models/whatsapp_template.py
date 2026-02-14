from odoo import models, fields


class WhatsappSubscriptionTemplate(models.Model):
    """Custom WhatsApp template model - standalone, no conflict with Odoo's whatsapp module"""
    _name = 'whatsapp.subscription.template'
    _description = 'WhatsApp Subscription Template'
    _order = 'name'

    name = fields.Char(string='Template Name', required=True, 
        help='Internal name for this template')
    meta_template_name = fields.Char(string='Meta Template ID', required=True,
        help='Exact template name registered in Meta Business Manager')
    language = fields.Char(string='Language Code', default='en', 
        help='e.g. en, en_US, fr, ar')
    
    # For display/preview purposes
    body = fields.Text(string='Template Body', 
        help='Preview of what the template says (for reference)')
    
    # Parameters definition
    param_1 = fields.Char(string='Parameter 1', help='What {{1}} represents, e.g. client name')
    param_2 = fields.Char(string='Parameter 2', help='What {{2}} represents')
    param_3 = fields.Char(string='Parameter 3', help='What {{3}} represents')
    
    active = fields.Boolean(default=True)

    def name_get(self):
        return [(rec.id, f"{rec.name} ({rec.meta_template_name})") for rec in self]
