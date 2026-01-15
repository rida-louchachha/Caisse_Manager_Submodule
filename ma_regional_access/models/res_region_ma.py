from odoo import models, fields

class ResRegionMa(models.Model):
    _name = 'res.region.ma'
    _description = 'Région Maroc'
    _order = 'name'

    name = fields.Char(string='Nom de la région', required=True, translate=True)
    code = fields.Char(string='Code', required=True)
    active = fields.Boolean(default=True)
    city_ids = fields.One2many('res.city.ma', 'region_id', string='Villes')
