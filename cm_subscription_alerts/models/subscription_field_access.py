# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SubscriptionFieldAccess(models.Model):
    """Defines which subscription fields can be edited by limited access users.
    Links to actual ir.model.fields for dynamic field selection."""
    _name = 'subscription.field.access'
    _description = 'Subscription Field Access'
    _order = 'sequence, name'
    _rec_name = 'display_name'

    name = fields.Char(
        string='Custom Label',
        help='Optional custom display name for this field access rule'
    )
    
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True
    )
    
    # Link to actual model field
    field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Field',
        required=True,
        domain="[('model', '=', 'sale.order'), ('store', '=', True), ('ttype', 'not in', ['one2many', 'many2many'])]",
        ondelete='cascade',
        help='Select a field from the Sale Order model'
    )
    
    # Computed field name for easy access
    field_name = fields.Char(
        related='field_id.name',
        store=True,
        readonly=True
    )
    
    field_description = fields.Char(
        related='field_id.field_description',
        string='Field Label',
        readonly=True
    )
    
    field_type = fields.Selection(
        related='field_id.ttype',
        string='Field Type',
        readonly=True
    )
    
    # Security Group (optional - for future group-specific permissions)
    group_id = fields.Many2one(
        comodel_name='res.groups',
        string='Security Group',
        help='If set, this field access only applies to users in this group. '
             'Leave empty to apply to all limited access users.'
    )
    
    # Permissions
    perm_read = fields.Boolean(
        string='Read',
        default=True,
        help='Allow reading this field'
    )
    perm_write = fields.Boolean(
        string='Write',
        default=True,
        help='Allow writing to this field'
    )
    perm_create = fields.Boolean(
        string='Create',
        default=True,
        help='Allow setting this field on new records'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    description = fields.Text(
        string='Notes',
        help='Additional notes about this field access rule'
    )
    
    _sql_constraints = [
        ('unique_field_group', 'UNIQUE(field_id, group_id)', 
         'A field access rule already exists for this field and group combination!')
    ]
    
    @api.depends('name', 'field_id', 'field_id.field_description', 'group_id')
    def _compute_display_name(self):
        for record in self:
            if record.name:
                record.display_name = record.name
            elif record.field_id:
                field_label = record.field_id.field_description or record.field_id.name
                if record.group_id:
                    record.display_name = f"{field_label} ({record.group_id.name})"
                else:
                    record.display_name = field_label
            else:
                record.display_name = 'New Field Access'
    
    @api.onchange('field_id')
    def _onchange_field_id(self):
        """Set default name from field description"""
        if self.field_id and not self.name:
            self.name = self.field_id.field_description
