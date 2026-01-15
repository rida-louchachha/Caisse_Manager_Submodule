from odoo import models, fields

class ResCityMa(models.Model):
    _name = 'res.city.ma'
    _description = 'Ville Maroc'
    _order = 'name'

    name = fields.Char(string='Nom de la ville', required=True, translate=True)
    region_id = fields.Many2one('res.region.ma', string='Région', required=True, ondelete='cascade')
    active = fields.Boolean(default=True)
