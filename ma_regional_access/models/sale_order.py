from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    system_version_ids = fields.Many2many(
        related='partner_id.system_version_ids',
        string='Versions Système',
        readonly=True
    )
    region_id = fields.Many2one(
        related='partner_id.region_id',
        string='Région (Maroc)',
        store=True,
        readonly=True
    )
    city_ma_id = fields.Many2one(
        related='partner_id.city_ma_id',
        string='Ville (Maroc)',
        store=True,
        readonly=True
    )
