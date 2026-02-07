# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PartnerResumeWizard(models.TransientModel):
    """Wizard to display a comprehensive summary of a partner (Client/Franchise/Company).
    
    Shows:
    - Partner information summary
    - Sales history
    - Active subscriptions
    - Materials (products from sale.order lines)
    - Abonnement products (from subscription orders)
    """
    _name = 'partner.resume.wizard'
    _description = 'Partner Resume / Dashboard'

    # ===== Partner Info =====
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        required=True,
        readonly=True
    )
    partner_level = fields.Selection(
        related='partner_id.partner_level',
        string='Level'
    )
    
    # ===== Hierarchy Info =====
    client_id = fields.Many2one(
        related='partner_id.hierarchy_client_id',
        string='Client'
    )
    franchise_id = fields.Many2one(
        related='partner_id.hierarchy_franchise_id',
        string='Franchise'
    )
    
    # ===== Location =====
    city_ma_id = fields.Many2one(
        related='partner_id.city_ma_id',
        string='City'
    )
    region_id = fields.Many2one(
        related='partner_id.region_id',
        string='Region'
    )
    
    # ===== Statistics =====
    total_sales = fields.Integer(
        compute='_compute_statistics',
        string='Total Sales'
    )
    total_subscriptions = fields.Integer(
        compute='_compute_statistics',
        string='Active Subscriptions'
    )
    total_revenue = fields.Monetary(
        compute='_compute_statistics',
        string='Total Revenue',
        currency_field='currency_id'
    )
    subscription_revenue = fields.Monetary(
        compute='_compute_statistics',
        string='Subscription Revenue',
        currency_field='currency_id'
    )
    total_invoiced = fields.Monetary(
        compute='_compute_statistics',
        string='Total Invoiced',
        currency_field='currency_id'
    )
    total_paid = fields.Monetary(
        compute='_compute_statistics',
        string='Total Paid',
        currency_field='currency_id'
    )
    amount_to_pay = fields.Monetary(
        compute='_compute_statistics',
        string='Amount To Pay',
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_statistics'
    )
    
    # ===== Related Records =====
    sale_order_ids = fields.Many2many(
        comodel_name='sale.order',
        compute='_compute_related_records',
        string='Sales Orders'
    )
    subscription_ids = fields.Many2many(
        comodel_name='sale.order',
        compute='_compute_related_records',
        string='Subscriptions'
    )
    material_line_ids = fields.Many2many(
        comodel_name='sale.order.line',
        compute='_compute_related_records',
        string='Materials (Products)',
        relation='partner_resume_material_rel'
    )
    subscription_line_ids = fields.Many2many(
        comodel_name='sale.order.line',
        compute='_compute_related_records',
        string='Abonnement Products',
        relation='partner_resume_subscription_rel'
    )
    
    # ===== Child Partners (for Clients/Franchises) =====
    child_partner_ids = fields.Many2many(
        comodel_name='res.partner',
        compute='_compute_child_partners',
        string='Child Partners'
    )

    @api.depends('partner_id')
    def _compute_statistics(self):
        """Compute revenue and order statistics for the partner."""
        for wizard in self:
            partner = wizard.partner_id
            if not partner:
                wizard.total_sales = 0
                wizard.total_subscriptions = 0
                wizard.total_revenue = 0
                wizard.subscription_revenue = 0
                wizard.total_invoiced = 0
                wizard.total_paid = 0
                wizard.amount_to_pay = 0
                wizard.currency_id = self.env.company.currency_id.id
                continue
            
            # Get all partners in hierarchy (for Client/Franchise, include children)
            partner_ids = wizard._get_hierarchy_partner_ids()
            
            # Get sale orders for these partners
            orders = self.env['sale.order'].search([
                ('partner_id', 'in', partner_ids),
                ('state', 'in', ['sale', 'done'])
            ])
            
            # Regular sales (non-subscription)
            regular_orders = orders.filtered(lambda o: not o.is_subscription and not o.plan_id)
            
            # Subscription orders
            subscriptions = orders.filtered(lambda o: o.is_subscription or o.plan_id)
            
            wizard.total_sales = len(regular_orders)
            wizard.total_subscriptions = len(subscriptions)
            wizard.total_revenue = sum(orders.mapped('amount_total'))
            wizard.subscription_revenue = sum(subscriptions.mapped('amount_total'))
            wizard.total_invoiced = sum(orders.mapped('total_invoiced_amount'))
            wizard.total_paid = sum(orders.mapped('total_paid_amount'))
            wizard.amount_to_pay = wizard.total_invoiced - wizard.total_paid
            wizard.currency_id = self.env.company.currency_id.id

    @api.depends('partner_id')
    def _compute_related_records(self):
        """Compute related sale orders and order lines."""
        for wizard in self:
            if not wizard.partner_id:
                wizard.sale_order_ids = False
                wizard.subscription_ids = False
                wizard.material_line_ids = False
                wizard.subscription_line_ids = False
                continue
            
            # Get all partners in hierarchy
            partner_ids = wizard._get_hierarchy_partner_ids()
            
            # Get sale orders
            all_orders = self.env['sale.order'].search([
                ('partner_id', 'in', partner_ids),
                ('state', 'in', ['sale', 'done'])
            ])
            
            # Regular sales
            regular_orders = all_orders.filtered(lambda o: not o.is_subscription and not o.plan_id)
            wizard.sale_order_ids = regular_orders
            
            # Subscriptions
            subscriptions = all_orders.filtered(lambda o: o.is_subscription or o.plan_id)
            wizard.subscription_ids = subscriptions
            
            # Material lines (from regular orders)
            wizard.material_line_ids = regular_orders.mapped('order_line')
            
            # Subscription lines (from subscriptions)
            wizard.subscription_line_ids = subscriptions.mapped('order_line')

    @api.depends('partner_id', 'partner_level')
    def _compute_child_partners(self):
        """Compute child partners for Clients and Franchises."""
        for wizard in self:
            if not wizard.partner_id:
                wizard.child_partner_ids = False
                continue
            
            if wizard.partner_level == 'client':
                # Get all franchises and companies under this client
                wizard.child_partner_ids = self.env['res.partner'].search([
                    ('hierarchy_client_id', '=', wizard.partner_id.id),
                    ('id', '!=', wizard.partner_id.id)
                ])
            elif wizard.partner_level == 'franchise':
                # Get all companies under this franchise
                wizard.child_partner_ids = self.env['res.partner'].search([
                    ('hierarchy_franchise_id', '=', wizard.partner_id.id),
                    ('id', '!=', wizard.partner_id.id)
                ])
            else:
                wizard.child_partner_ids = False

    def _get_hierarchy_partner_ids(self):
        """Get all partner IDs in the hierarchy based on partner level.
        
        For Client: include all franchises and companies
        For Franchise: include all companies
        For Company: just the company itself
        """
        self.ensure_one()
        partner = self.partner_id
        
        if not partner.partner_level:
            return [partner.id]
        
        if partner.partner_level == 'client':
            # Include client and all descendants
            return self.env['res.partner'].search([
                '|',
                ('id', '=', partner.id),
                ('hierarchy_client_id', '=', partner.id)
            ]).ids
        elif partner.partner_level == 'franchise':
            # Include franchise and all companies
            return self.env['res.partner'].search([
                '|',
                ('id', '=', partner.id),
                ('hierarchy_franchise_id', '=', partner.id)
            ]).ids
        else:
            return [partner.id]

    @api.model
    def action_open_resume(self, partner_id):
        """Open the resume wizard for a specific partner."""
        wizard = self.create({'partner_id': partner_id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Partner Resume',
            'res_model': self._name,
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
