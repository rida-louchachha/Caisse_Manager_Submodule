# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools


class RevenueAnalysis(models.Model):
    """SQL View for revenue analysis by Client/Franchise/Company.
    
    Includes subscription payment tracking fields from cm_subscription_alerts.
    Uses region_id and city_ma_id from ma_regional_access module.
    """
    _name = 'cm.revenue.analysis'
    _description = 'Revenue Analysis'
    _auto = False
    _order = 'total_revenue desc'

    # ===== Partner Hierarchy =====
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    partner_level = fields.Selection([
        ('client', 'Client'),
        ('franchise', 'Franchise'),
        ('company', 'Company'),
    ], string='Partner Level', readonly=True)
    
    client_id = fields.Many2one('res.partner', string='Client', readonly=True)
    franchise_id = fields.Many2one('res.partner', string='Franchise', readonly=True)
    
    # ===== Location (using ma_regional_access fields) =====
    city_ma_id = fields.Many2one('res.city.ma', string='City', readonly=True)
    region_id = fields.Many2one('res.region.ma', string='Region', readonly=True)
    country_id = fields.Many2one('res.country', string='Country', readonly=True)
    
    # ===== Revenue Metrics =====
    total_revenue = fields.Monetary(string='Total Revenue', readonly=True)
    subscription_revenue = fields.Monetary(string='Subscription Revenue', readonly=True)
    non_subscription_revenue = fields.Monetary(string='Non-Subscription Revenue', readonly=True)
    
    # ===== Subscription Payment Tracking (from cm_subscription_alerts) =====
    total_invoiced = fields.Monetary(string='Total Invoiced', readonly=True)
    total_paid = fields.Monetary(string='Total Paid', readonly=True)
    amount_to_pay = fields.Monetary(string='Amount To Pay', readonly=True)
    
    # ===== Order Counts =====
    total_orders = fields.Integer(string='Total Orders', readonly=True)
    subscription_orders = fields.Integer(string='Subscription Orders', readonly=True)
    non_subscription_orders = fields.Integer(string='Non-Subscription Orders', readonly=True)
    
    # ===== Resume Data (Computed) =====
    child_partner_ids = fields.Many2many('res.partner', compute='_compute_resume_data', string='Child Partners')
    sale_order_ids = fields.Many2many('sale.order', compute='_compute_resume_data', string='Sales Orders')
    subscription_ids = fields.Many2many('sale.order', compute='_compute_resume_data', string='Subscriptions')
    material_line_ids = fields.Many2many('sale.order.line', compute='_compute_resume_data', string='Materials')
    subscription_line_ids = fields.Many2many('sale.order.line', compute='_compute_resume_data', string='Abonnement Products')

    def _get_hierarchy_partner_ids(self, partner):
        """Helper to get hierarchy ids for a partner."""
        if not partner.partner_level:
            return [partner.id]
        
        if partner.partner_level == 'client':
            return self.env['res.partner'].search([
                '|', ('id', '=', partner.id), ('hierarchy_client_id', '=', partner.id)
            ]).ids
        elif partner.partner_level == 'franchise':
            return self.env['res.partner'].search([
                '|', ('id', '=', partner.id), ('hierarchy_franchise_id', '=', partner.id)
            ]).ids
        else:
            return [partner.id]

    def _compute_resume_data(self):
        """Compute resume-like data for the form view."""
        for record in self:
            if not record.partner_id:
                record.child_partner_ids = False
                record.sale_order_ids = False
                record.subscription_ids = False
                record.material_line_ids = False
                record.subscription_line_ids = False
                continue

            # 1. Child Partners
            if record.partner_level == 'client':
                record.child_partner_ids = self.env['res.partner'].search([
                    ('hierarchy_client_id', '=', record.partner_id.id),
                    ('id', '!=', record.partner_id.id)
                ])
            elif record.partner_level == 'franchise':
                record.child_partner_ids = self.env['res.partner'].search([
                    ('hierarchy_franchise_id', '=', record.partner_id.id),
                    ('id', '!=', record.partner_id.id)
                ])
            else:
                record.child_partner_ids = False

            # 2. Sales & Subs (Hierarchy based)
            partner_ids = self._get_hierarchy_partner_ids(record.partner_id)
            all_orders = self.env['sale.order'].search([
                ('partner_id', 'in', partner_ids),
                ('state', 'in', ['sale', 'done'])
            ])
            
            non_sub_orders = all_orders.filtered(lambda o: not o.is_subscription and not o.plan_id)
            sub_orders = all_orders.filtered(lambda o: o.is_subscription or o.plan_id)
            
            record.sale_order_ids = non_sub_orders
            record.subscription_ids = sub_orders
            record.material_line_ids = non_sub_orders.mapped('order_line')
            record.subscription_line_ids = sub_orders.mapped('order_line')
    
    # ===== Currency =====
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    
    # ===== Date Range =====
    date_order = fields.Date(string='Order Date', readonly=True)
    year = fields.Char(string='Year', readonly=True)
    month = fields.Char(string='Month', readonly=True)

    def init(self):
        """Create SQL view for revenue analysis."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () as id,
                    so.partner_id,
                    rp.partner_level,
                    rp.hierarchy_client_id as client_id,
                    rp.hierarchy_franchise_id as franchise_id,
                    rp.city_ma_id,
                    rp.region_id,
                    rp.country_id,
                    so.company_id,
                    so.currency_id,
                    so.date_order::date as date_order,
                    to_char(so.date_order, 'YYYY') as year,
                    to_char(so.date_order, 'MM') as month,
                    
                    -- Total Revenue (from order amount)
                    SUM(so.amount_total) as total_revenue,
                    
                    -- Subscription Revenue (where is_subscription = true or plan_id is set)
                    SUM(CASE 
                        WHEN so.is_subscription = true OR so.plan_id IS NOT NULL 
                        THEN so.amount_total 
                        ELSE 0 
                    END) as subscription_revenue,
                    
                    -- Non-Subscription Revenue
                    SUM(CASE 
                        WHEN so.is_subscription = false AND so.plan_id IS NULL 
                        THEN so.amount_total 
                        ELSE 0 
                    END) as non_subscription_revenue,
                    
                    -- Subscription Payment Tracking (from cm_subscription_alerts stored fields)
                    SUM(COALESCE(so.total_invoiced_amount, 0)) as total_invoiced,
                    SUM(COALESCE(so.total_paid_amount, 0)) as total_paid,
                    -- Calculate amount_to_pay as difference (invoiced - paid)
                    SUM(COALESCE(so.total_invoiced_amount, 0)) - SUM(COALESCE(so.total_paid_amount, 0)) as amount_to_pay,
                    
                    -- Order Counts
                    COUNT(*) as total_orders,
                    SUM(CASE 
                        WHEN so.is_subscription = true OR so.plan_id IS NOT NULL 
                        THEN 1 ELSE 0 
                    END) as subscription_orders,
                    SUM(CASE 
                        WHEN so.is_subscription = false AND so.plan_id IS NULL 
                        THEN 1 ELSE 0 
                    END) as non_subscription_orders
                    
                FROM sale_order so
                LEFT JOIN res_partner rp ON so.partner_id = rp.id
                WHERE so.state IN ('sale', 'done')
                GROUP BY
                    so.partner_id,
                    rp.partner_level,
                    rp.hierarchy_client_id,
                    rp.hierarchy_franchise_id,
                    rp.city_ma_id,
                    rp.region_id,
                    rp.country_id,
                    so.company_id,
                    so.currency_id,
                    so.date_order::date,
                    to_char(so.date_order, 'YYYY'),
                    to_char(so.date_order, 'MM')
            )
        """ % self._table)

    def action_open_resume(self):
        """Open the partner resume wizard for the company/store (current row)."""
        self.ensure_one()
        return self.env['partner.resume.wizard'].action_open_resume(self.partner_id.id)

    def action_open_franchise_resume(self):
        """Open the partner resume wizard for the franchise."""
        self.ensure_one()
        if not self.franchise_id:
            return
        return self.env['partner.resume.wizard'].action_open_resume(self.franchise_id.id)

    def action_open_client_resume(self):
        """Open the partner resume wizard for the client."""
        self.ensure_one()
        if not self.client_id:
            return
        return self.env['partner.resume.wizard'].action_open_resume(self.client_id.id)


