# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.exceptions import AccessError


class SaleOrderLine(models.Model):
    """Extend sale.order.line to enforce field-level permissions for limited access users."""
    _inherit = 'sale.order.line'

    def _check_limited_access_permission(self, operation='write'):
        """Check if current user has permission for the operation on order lines.
        
        Limited access users cannot modify order lines at all unless explicitly allowed.
        """
        user = self.env.user
        limited_group = self.env.ref(
            'cm_subscription_alerts.group_subscription_limited_access',
            raise_if_not_found=False
        )
        
        if limited_group and limited_group in user.groups_id:
            # Check if user has permission to modify order lines
            # For now, we check if they have 'order_line' field access
            allowed_field_names = user.subscription_allowed_fields.mapped('field_name')
            
            if 'order_line' not in allowed_field_names:
                if operation == 'write':
                    raise AccessError(
                        "You don't have permission to modify order lines.\n"
                        "Contact your administrator to get access to the 'Order Lines' field."
                    )
                elif operation == 'create':
                    raise AccessError(
                        "You don't have permission to add order lines.\n"
                        "Contact your administrator to get access to the 'Order Lines' field."
                    )
                elif operation == 'unlink':
                    raise AccessError(
                        "You don't have permission to delete order lines.\n"
                        "Contact your administrator to get access to the 'Order Lines' field."
                    )

    def write(self, vals):
        """Override write to check permissions for limited access users."""
        self._check_limited_access_permission('write')
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to check permissions for limited access users."""
        user = self.env.user
        limited_group = self.env.ref(
            'cm_subscription_alerts.group_subscription_limited_access',
            raise_if_not_found=False
        )
        
        if limited_group and limited_group in user.groups_id:
            allowed_field_names = user.subscription_allowed_fields.mapped('field_name')
            if 'order_line' not in allowed_field_names:
                raise AccessError(
                    "You don't have permission to add order lines.\n"
                    "Contact your administrator to get access to the 'Order Lines' field."
                )
        
        return super().create(vals_list)

    def unlink(self):
        """Override unlink to check permissions for limited access users."""
        self._check_limited_access_permission('unlink')
        return super().unlink()
