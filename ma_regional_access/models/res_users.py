from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_region_ids = fields.Many2many(
        'res.region.ma',
        'res_users_region_ma_rel',
        'user_id',
        'region_id',
        string='Régions Autorisées'
    )
