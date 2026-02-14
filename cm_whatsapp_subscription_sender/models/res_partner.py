from odoo import models, fields

class ResPartner(models.Model):
    _inherit = "res.partner"

    instagram_id = fields.Char()
    instagram_username = fields.Char()
    facebook_psid = fields.Char(
        string="Facebook PSID",
        help="Scoped user identifier used by Facebook Messenger webhooks.",
    )
