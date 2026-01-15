from odoo import models, fields

class MaSystemVersion(models.Model):
    _name = 'ma.system.version'
    _description = 'Version Système'
    _order = 'name'

    name = fields.Char(string='Version', required=True)
    color = fields.Integer(string='Couleur')
    active = fields.Boolean(default=True)
