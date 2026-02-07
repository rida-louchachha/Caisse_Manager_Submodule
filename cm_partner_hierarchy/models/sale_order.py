# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleOrder(models.Model):
    """Extend sale.order with client/franchise hierarchy fields."""
    _inherit = 'sale.order'

    # ===== Hierarchy Fields (Related from Partner) =====
    subscription_client_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        related='partner_id.hierarchy_client_id',
        store=True,
        help='Top-level client for this subscription'
    )
    
    subscription_franchise_id = fields.Many2one(
        comodel_name='res.partner',
        string='Franchise',
        related='partner_id.hierarchy_franchise_id',
        store=True,
        help='Franchise for this subscription (if any)'
    )
    
    partner_level = fields.Selection(
        related='partner_id.partner_level',
        string='Partner Level',
        store=True
    )
    
    # ===== Revenue Classification =====
    is_subscription_revenue = fields.Boolean(
        compute='_compute_is_subscription_revenue',
        store=True,
        string='Is Subscription Revenue',
        help='True if this order is a subscription order (has recurring plan)'
    )
    
    @api.depends('is_subscription', 'subscription_state')
    def _compute_is_subscription_revenue(self):
        """Determine if this order should be counted as subscription revenue."""
        for order in self:
            # Check if it's a subscription (has recurring plan)
            order.is_subscription_revenue = bool(
                order.is_subscription or 
                (hasattr(order, 'plan_id') and order.plan_id)
            )
