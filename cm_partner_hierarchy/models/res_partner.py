# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    """Extend res.partner with Client/Franchise/Company hierarchy."""
    _inherit = 'res.partner'

    # ===== Partner Level (Manual Assignment) =====
    partner_level = fields.Selection([
        ('client', '🏢 Client / Account'),
        ('franchise', '🏪 Franchise'),
        ('company', '🏬 Company / Store'),
    ], string='Partner Level',
       help='Hierarchical level of this partner:\n'
            '• Client: Top-level commercial entity\n'
            '• Franchise: Intermediate level, belongs to a client\n'
            '• Company: Operational entity, belongs to franchise or client',
       tracking=True)

    # ===== Computed Structural Fields (Stored) =====
    hierarchy_client_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        compute='_compute_hierarchy_fields',
        store=True,
        help='Top-level client this partner belongs to'
    )
    
    hierarchy_franchise_id = fields.Many2one(
        comodel_name='res.partner',
        string='Franchise',
        compute='_compute_hierarchy_fields',
        store=True,
        help='Franchise this partner belongs to (if any)'
    )
    
    hierarchy_parent_id = fields.Many2one(
        comodel_name='res.partner',
        string='Hierarchy Parent',
        compute='_compute_hierarchy_fields',
        store=True,
        recursive=True,
        help='Parent for the hierarchy tree view'
    )

    # ===== Computed Revenue Stats (for Hierarchy View) =====
    # Non-stored computed fields - for display only
    report_total_orders = fields.Integer(
        compute='_compute_hierarchy_revenue', 
        string='Total Orders'
    )
    report_total_revenue = fields.Monetary(
        compute='_compute_hierarchy_revenue', 
        string='Total Revenue', 
        currency_field='currency_id'
    )
    report_subscription_revenue = fields.Monetary(
        compute='_compute_hierarchy_revenue', 
        string='Subscription Revenue', 
        currency_field='currency_id'
    )
    report_total_invoiced = fields.Monetary(
        compute='_compute_hierarchy_revenue', 
        string='Total Invoiced', 
        currency_field='currency_id'
    )
    report_total_paid = fields.Monetary(
        compute='_compute_hierarchy_revenue', 
        string='Total Paid', 
        currency_field='currency_id'
    )
    report_amount_to_pay = fields.Monetary(
        compute='_compute_hierarchy_revenue', 
        string='Amount To Pay', 
        currency_field='currency_id'
    )

    def _compute_hierarchy_revenue(self):
        """Compute revenue stats for the hierarchy view."""
        SaleOrder = self.env['sale.order']
        for partner in self:
            # 1. Identify all relevant child partners (including self)
            if partner.partner_level == 'client':
                child_ids = self.search(['|', ('id', '=', partner.id), ('hierarchy_client_id', '=', partner.id)]).ids
            elif partner.partner_level == 'franchise':
                child_ids = self.search(['|', ('id', '=', partner.id), ('hierarchy_franchise_id', '=', partner.id)]).ids
            else:
                child_ids = [partner.id]
            
            # 2. Fetch Orders
            orders = SaleOrder.search([
                ('partner_id', 'in', child_ids),
                ('state', 'in', ['sale', 'done'])
            ])
            
            # 3. Aggregate
            partner.report_total_orders = len(orders)
            partner.report_total_revenue = sum(orders.mapped('amount_total'))
            
            # Logic from revenue_analysis SQL: sub if is_subscription or plan_id
            subs = orders.filtered(lambda o: o.is_subscription or o.plan_id)
            partner.report_subscription_revenue = sum(subs.mapped('amount_total'))
            
            partner.report_total_invoiced = sum(orders.mapped('total_invoiced_amount'))
            partner.report_total_paid = sum(orders.mapped('total_paid_amount'))
            partner.report_amount_to_pay = partner.report_total_invoiced - partner.report_total_paid

    @api.model
    def _cron_recompute_hierarchy_revenue(self):
        """Scheduled action to recompute revenue stats for all partners with levels."""
        partners = self.search([('partner_level', 'in', ['client', 'franchise', 'company'])])
        partners._compute_hierarchy_revenue()
        return True
    
    def action_recompute_revenue(self):
        """Manual action to recompute revenue stats for selected partners."""
        self._compute_hierarchy_revenue()
        return True

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        """Override read_group to sort groups by total revenue (highest first).
        
        This enables ordering by revenue without storing the computed fields.
        """
        result = super().read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        
        # Only sort by revenue for hierarchy groupings
        if not result or not groupby:
            return result
        
        group_field = groupby[0] if isinstance(groupby, list) else groupby
        if group_field not in ('hierarchy_client_id', 'hierarchy_franchise_id'):
            return result
        
        # Calculate revenue for each group and sort
        for group in result:
            group_domain = group.get('__domain', [])
            if group_domain:
                # Get all partners in this group
                partners = self.search(group_domain)
                if partners:
                    # Sum up the total revenue for all child companies
                    total_revenue = 0
                    SaleOrder = self.env['sale.order']
                    for partner in partners:
                        # For clients/franchises, get revenue from child companies
                        if partner.partner_level == 'client':
                            child_ids = self.search([
                                '|', ('id', '=', partner.id), 
                                ('hierarchy_client_id', '=', partner.id)
                            ]).ids
                        elif partner.partner_level == 'franchise':
                            child_ids = self.search([
                                '|', ('id', '=', partner.id), 
                                ('hierarchy_franchise_id', '=', partner.id)
                            ]).ids
                        else:
                            child_ids = [partner.id]
                        
                        orders = SaleOrder.search([
                            ('partner_id', 'in', child_ids),
                            ('state', 'in', ['sale', 'done'])
                        ])
                        total_revenue += sum(orders.mapped('amount_total'))
                    
                    group['__revenue_sort'] = total_revenue
                else:
                    group['__revenue_sort'] = 0
            else:
                group['__revenue_sort'] = 0
        
        # Sort by revenue descending
        result = sorted(result, key=lambda x: x.get('__revenue_sort', 0), reverse=True)
        
        # Remove the temporary sort key
        for group in result:
            if '__revenue_sort' in group:
                del group['__revenue_sort']
        
        return result

    # ===== Helper Fields =====
    child_franchise_ids = fields.One2many(
        comodel_name='res.partner',
        inverse_name='hierarchy_client_id',
        string='Franchises',
        domain=[('partner_level', '=', 'franchise')],
        help='Franchises belonging to this client'
    )
    
    child_company_ids = fields.One2many(
        comodel_name='res.partner',
        inverse_name='hierarchy_franchise_id',
        string='Companies/Stores',
        domain=[('partner_level', '=', 'company')],
        help='Companies/Stores belonging to this franchise'
    )
    
    franchise_count = fields.Integer(
        compute='_compute_hierarchy_counts',
        string='# Franchises'
    )
    
    company_count = fields.Integer(
        compute='_compute_hierarchy_counts',
        string='# Companies'
    )

    @api.depends('parent_id', 'parent_id.partner_level', 'parent_id.hierarchy_client_id', 
                 'parent_id.hierarchy_franchise_id', 'partner_level')
    def _compute_hierarchy_fields(self):
        """Compute client_id and franchise_id based on partner hierarchy."""
        for partner in self:
            if partner.partner_level == 'client':
                # Clients don't reference themselves - only children reference the client
                partner.hierarchy_client_id = False
                partner.hierarchy_franchise_id = False
                partner.hierarchy_parent_id = False
                
            elif partner.partner_level == 'franchise':
                # Franchise references its parent client, but NOT itself
                if partner.parent_id and partner.parent_id.partner_level == 'client':
                    partner.hierarchy_client_id = partner.parent_id.id
                else:
                    partner.hierarchy_client_id = partner._find_client_in_chain()
                partner.hierarchy_franchise_id = False  # Franchise doesn't reference itself
                partner.hierarchy_parent_id = partner.hierarchy_client_id
                
            elif partner.partner_level == 'company':
                if partner.parent_id:
                    if partner.parent_id.partner_level == 'franchise':
                        partner.hierarchy_franchise_id = partner.parent_id.id
                        partner.hierarchy_client_id = partner.parent_id.hierarchy_client_id.id if partner.parent_id.hierarchy_client_id else False
                    elif partner.parent_id.partner_level == 'client':
                        partner.hierarchy_client_id = partner.parent_id.id
                        partner.hierarchy_franchise_id = False
                    else:
                        partner.hierarchy_client_id = partner.parent_id.hierarchy_client_id.id if partner.parent_id.hierarchy_client_id else False
                        partner.hierarchy_franchise_id = partner.parent_id.hierarchy_franchise_id.id if partner.parent_id.hierarchy_franchise_id else False
                else:
                    partner.hierarchy_client_id = False
                    partner.hierarchy_franchise_id = False
                partner.hierarchy_parent_id = partner.hierarchy_franchise_id or partner.hierarchy_client_id

            else:
                if partner.parent_id:
                    partner.hierarchy_client_id = partner.parent_id.hierarchy_client_id.id if partner.parent_id.hierarchy_client_id else False
                    partner.hierarchy_franchise_id = partner.parent_id.hierarchy_franchise_id.id if partner.parent_id.hierarchy_franchise_id else False
                else:
                    partner.hierarchy_client_id = False
                    partner.hierarchy_franchise_id = False

    def _find_client_in_chain(self):
        """Walk up the parent chain to find a client."""
        partner = self.parent_id
        while partner:
            if partner.partner_level == 'client':
                return partner.id
            partner = partner.parent_id
        return False

    def _compute_hierarchy_counts(self):
        """Compute counts of franchises and companies."""
        for partner in self:
            if partner.partner_level == 'client':
                partner.franchise_count = self.search_count([
                    ('hierarchy_client_id', '=', partner.id),
                    ('partner_level', '=', 'franchise')
                ])
                partner.company_count = self.search_count([
                    ('hierarchy_client_id', '=', partner.id),
                    ('partner_level', '=', 'company')
                ])
            elif partner.partner_level == 'franchise':
                partner.franchise_count = 0
                partner.company_count = self.search_count([
                    ('hierarchy_franchise_id', '=', partner.id),
                    ('partner_level', '=', 'company')
                ])
            else:
                partner.franchise_count = 0
                partner.company_count = 0

    @api.model
    def auto_assign_partner_levels(self, partner_ids=None):
        """Automatically assign partner levels based on parent hierarchy."""
        domain = [('partner_level', '=', False)]
        if partner_ids:
            domain.append(('id', 'in', partner_ids))
        
        partners = self.search(domain)
        
        counts = {'client': 0, 'franchise': 0, 'company': 0}
        
        for partner in partners:
            if not partner.parent_id:
                partner.partner_level = 'client'
                counts['client'] += 1
            elif partner.parent_id.partner_level == 'client':
                partner.partner_level = 'franchise'
                counts['franchise'] += 1
            elif partner.parent_id.partner_level == 'franchise':
                partner.partner_level = 'company'
                counts['company'] += 1
        
        return counts
