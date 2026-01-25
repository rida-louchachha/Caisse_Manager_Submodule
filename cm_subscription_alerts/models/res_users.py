# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    subscription_allowed_fields = fields.Many2many(
        comodel_name='subscription.field.access',
        relation='res_users_subscription_field_access_rel',
        column1='user_id',
        column2='field_access_id',
        string='Allowed Subscription Fields',
        help='Fields that this user is allowed to edit on subscriptions. '
             'Only applies to users in the "Subscription Limited Access" group.'
    )

    def has_subscription_field_access(self, field_name):
        """Check if user has access to edit a specific subscription field."""
        self.ensure_one()
        # Check if user is in the limited access group
        limited_group = self.env.ref(
            'cm_subscription_alerts.group_subscription_limited_access',
            raise_if_not_found=False
        )
        if not limited_group or limited_group not in self.groups_id:
            # User is not in limited group, so they have full access (admin/manager)
            return True
        
        # User is in limited group, check if field is in their allowed list
        return field_name in self.subscription_allowed_fields.mapped('field_name')
