from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    region_id = fields.Many2one('res.region.ma', string='Région (Maroc)', index=True)
    city_ma_id = fields.Many2one('res.city.ma', string='Ville (Maroc)', domain="[('region_id', '=', region_id)]")
    system_version_ids = fields.Many2many('ma.system.version', string='Versions Système', help="Versions installées chez le client")

    @api.onchange('region_id')
    def _onchange_region_id(self):
        if self.region_id and self.city_ma_id and self.city_ma_id.region_id != self.region_id:
            self.city_ma_id = False
