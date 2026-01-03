# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import timedelta
from dateutil.relativedelta import relativedelta


class SubscriptionSummaryWizard(models.TransientModel):
    _name = 'subscription.summary.wizard'
    _description = 'Subscription Summary Wizard'
    
    # Date Range Fields
    date_from = fields.Date(string='From Date', default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string='To Date', default=lambda self: fields.Date.today())
    
    # Quick Filter Selection
    date_range_type = fields.Selection([
        ('this_month', 'This Month'),
        ('last_month', 'Last Month'),
        ('this_year', 'This Year'),
        ('last_3_months', 'Last 3 Months'),
        ('last_6_months', 'Last 6 Months'),
        ('custom', 'Custom Range'),
    ], string='Period', default='this_month')
    
    # Summary Fields
    total_subscriptions = fields.Integer(string='Total Subscriptions', readonly=True)
    total_paid = fields.Float(string='Total Paid', readonly=True)
    total_to_pay = fields.Float(string='Total To Pay', readonly=True)
    total_invoiced = fields.Float(string='Total Invoiced', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    
    # Status Counts
    paid_count = fields.Integer(string='Paid', readonly=True)
    in_payment_count = fields.Integer(string='In Payment', readonly=True)
    pending_count = fields.Integer(string='Pending', readonly=True)
    expired_count = fields.Integer(string='Expired', readonly=True)
    
    # Display Fields
    summary_html = fields.Html(string='Summary', readonly=True, sanitize=False)
    
    @api.onchange('date_range_type')
    def _onchange_date_range_type(self):
        """Update date_from and date_to based on selected period"""
        today = fields.Date.today()
        
        if self.date_range_type == 'this_month':
            self.date_from = today.replace(day=1)
            self.date_to = today
        elif self.date_range_type == 'last_month':
            first_of_month = today.replace(day=1)
            last_month_end = first_of_month - timedelta(days=1)
            self.date_from = last_month_end.replace(day=1)
            self.date_to = last_month_end
        elif self.date_range_type == 'this_year':
            self.date_from = today.replace(month=1, day=1)
            self.date_to = today
        elif self.date_range_type == 'last_3_months':
            self.date_from = today - relativedelta(months=3)
            self.date_to = today
        elif self.date_range_type == 'last_6_months':
            self.date_from = today - relativedelta(months=6)
            self.date_to = today
        # For 'custom', don't change the dates
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        # Set default dates
        today = fields.Date.today()
        date_from = today.replace(day=1)
        date_to = today
        
        # Generate summary with default dates
        summary_data = self._compute_summary_data(date_from, date_to)
        res.update(summary_data)
        
        return res
    
    def _compute_summary_data(self, date_from, date_to):
        """Compute all summary data filtered by date range"""
        
        # Get all subscriptions
        SaleOrder = self.env['sale.order']
        subscriptions = SaleOrder.search([('is_cm_subscription', '=', True)])
        currency = self.env.company.currency_id
        
        # Filter invoices by date range
        total_paid = 0
        total_to_pay = 0
        total_invoiced = 0
        
        for sub in subscriptions:
            # Get invoices within date range
            invoices_in_range = sub.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' 
                and inv.state == 'posted'
                and inv.invoice_date 
                and date_from <= inv.invoice_date <= date_to
            )
            
            for inv in invoices_in_range:
                total_invoiced += inv.amount_total
                if inv.payment_state in ('paid', 'in_payment', 'partial'):
                    if inv.payment_state == 'in_payment':
                        total_paid += inv.amount_total
                    else:
                        total_paid += inv.amount_total - inv.amount_residual
                total_to_pay += inv.amount_residual
        
        # Count by status (current status, not filtered by date)
        paid_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'paid'))
        in_payment_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'in_payment'))
        pending_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status in ('requires_payment', 'pending', 'should_invoice')))
        expired_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'expired'))
        
        # Average subscription value
        avg_subscription_value = total_paid / len(subscriptions) if subscriptions and total_paid > 0 else 0
        
        # Top 5 Clients by Revenue (within date range)
        client_totals = {}
        for sub in subscriptions:
            invoices_in_range = sub.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' 
                and inv.state == 'posted'
                and inv.invoice_date 
                and date_from <= inv.invoice_date <= date_to
            )
            if invoices_in_range:
                partner_name = sub.partner_id.name or 'Unknown'
                if partner_name not in client_totals:
                    client_totals[partner_name] = {'paid': 0, 'to_pay': 0}
                for inv in invoices_in_range:
                    if inv.payment_state in ('paid', 'in_payment', 'partial'):
                        client_totals[partner_name]['paid'] += inv.amount_total - inv.amount_residual
                    client_totals[partner_name]['to_pay'] += inv.amount_residual
        
        top_clients = sorted(client_totals.items(), key=lambda x: x[1]['paid'], reverse=True)[:5]
        
        # Clients at Risk
        at_risk_subs = subscriptions.filtered(
            lambda s: s.subscription_payment_status in ('expired', 'requires_payment', 'pending')
        )
        clients_at_risk = list(set(s.partner_id.name for s in at_risk_subs))[:5]
        
        # Time insights
        today = fields.Date.today()
        next_week = today + timedelta(days=7)
        expiring_soon = subscriptions.filtered(
            lambda s: s.next_invoice_date and today <= s.next_invoice_date <= next_week
        )
        
        is_past_5th = today.day > 5
        critical_count = len(at_risk_subs) if is_past_5th else 0
        
        # Oldest unpaid
        oldest_unpaid_days = 0
        for sub in at_risk_subs:
            unpaid_invoices = sub.invoice_ids.filtered(
                lambda inv: inv.state == 'posted' and inv.payment_state == 'not_paid'
            )
            if unpaid_invoices:
                oldest = min(unpaid_invoices.mapped('invoice_date'))
                days_old = (today - oldest).days if oldest else 0
                if days_old > oldest_unpaid_days:
                    oldest_unpaid_days = days_old
        
        # Build HTML
        top_clients_html = ""
        for i, (name, data) in enumerate(top_clients, 1):
            top_clients_html += f'''
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 8px; text-align: center;">{i}</td>
                <td style="padding: 8px;">{name[:20]}</td>
                <td style="padding: 8px; text-align: right; color: #28a745; font-weight: bold;">{data['paid']:,.2f}</td>
                <td style="padding: 8px; text-align: right; color: #dc3545;">{data['to_pay']:,.2f}</td>
            </tr>
            '''
        
        at_risk_html = ""
        for client in clients_at_risk[:5]:
            at_risk_html += f'''
            <div style="background: #fff3cd; padding: 8px 12px; border-radius: 5px; margin: 5px 0; border-left: 4px solid #dc3545;">
                ⚠️ {client[:25]}
            </div>
            '''
        if not at_risk_html:
            at_risk_html = '<div style="color: #28a745; text-align: center; padding: 20px;">✅ No clients at risk!</div>'
        
        # Format date range for display
        date_range_str = f"{date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}"
        
        summary_html = f'''
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <!-- Header -->
            <div style="text-align: center; margin-bottom: 25px;">
                <h1 style="color: #333; margin: 0;">📊 Subscription Summary</h1>
                <p style="color: #666; margin-top: 5px;">Total: {len(subscriptions)} Active Subscriptions</p>
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 10px 20px; border-radius: 20px; display: inline-block; margin-top: 10px;">
                    📅 Period: <strong>{date_range_str}</strong>
                </div>
            </div>
            
            <!-- Financial Summary Cards -->
            <div style="display: flex; justify-content: space-around; margin-bottom: 25px; flex-wrap: wrap; gap: 15px;">
                <div style="background: linear-gradient(135deg, #28a745 0%, #218838 100%); color: white; padding: 15px 25px; border-radius: 10px; text-align: center; min-width: 130px; box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3); cursor: help;" title="TOTAL PAID&#10;&#10;Sum of all payments received in this period.&#10;&#10;Includes: Fully paid + In Payment + Partial payments">
                    <div style="font-size: 24px; font-weight: bold;">{total_paid:,.2f}</div>
                    <div style="font-size: 12px; opacity: 0.9;">{currency.symbol} Total Paid <span style="font-size: 10px;">ℹ️</span></div>
                    <div style="font-size: 18px; margin-top: 3px;">💰</div>
                </div>
                
                <div style="background: linear-gradient(135deg, #ffc107 0%, #e0a800 100%); color: #333; padding: 15px 25px; border-radius: 10px; text-align: center; min-width: 130px; box-shadow: 0 4px 15px rgba(255, 193, 7, 0.3); cursor: help;" title="TO PAY&#10;&#10;Total amount still pending payment in this period.">
                    <div style="font-size: 24px; font-weight: bold;">{total_to_pay:,.2f}</div>
                    <div style="font-size: 12px; opacity: 0.9;">{currency.symbol} To Pay <span style="font-size: 10px;">ℹ️</span></div>
                    <div style="font-size: 18px; margin-top: 3px;">⏳</div>
                </div>
                
                <div style="background: linear-gradient(135deg, #17a2b8 0%, #138496 100%); color: white; padding: 15px 25px; border-radius: 10px; text-align: center; min-width: 130px; box-shadow: 0 4px 15px rgba(23, 162, 184, 0.3); cursor: help;" title="TOTAL INVOICED&#10;&#10;Sum of all invoices created in this period.">
                    <div style="font-size: 24px; font-weight: bold;">{total_invoiced:,.2f}</div>
                    <div style="font-size: 12px; opacity: 0.9;">{currency.symbol} Invoiced <span style="font-size: 10px;">ℹ️</span></div>
                    <div style="font-size: 18px; margin-top: 3px;">📄</div>
                </div>
                
                <div style="background: linear-gradient(135deg, #6f42c1 0%, #5a32a3 100%); color: white; padding: 15px 25px; border-radius: 10px; text-align: center; min-width: 130px; box-shadow: 0 4px 15px rgba(111, 66, 193, 0.3); cursor: help;" title="AVERAGE PER SUBSCRIPTION&#10;&#10;Average payment per subscription in this period.">
                    <div style="font-size: 24px; font-weight: bold;">{avg_subscription_value:,.2f}</div>
                    <div style="font-size: 12px; opacity: 0.9;">{currency.symbol} Avg/Sub <span style="font-size: 10px;">ℹ️</span></div>
                    <div style="font-size: 18px; margin-top: 3px;">📈</div>
                </div>
            </div>
            
            <!-- Two Column Layout -->
            <div style="display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap;">
                
                <!-- Left Column: Status Breakdown + Collection Rate -->
                <div style="flex: 1; min-width: 280px;">
                    <!-- Status Breakdown -->
                    <div style="background: #f8f9fa; border-radius: 10px; padding: 15px; margin-bottom: 15px;">
                        <h3 style="color: #333; margin-bottom: 12px; text-align: center; font-size: 16px;">Payment Status Breakdown <span style="font-size: 12px; cursor: help;" title="Current status of all subscriptions">ℹ️</span></h3>
                        <div style="display: flex; justify-content: space-around; flex-wrap: wrap; gap: 10px;">
                            <div style="text-align: center; padding: 8px 15px; cursor: help;" title="PAID - Subscriptions with fully paid invoices">
                                <div style="font-size: 28px; color: #28a745;">✅</div>
                                <div style="font-size: 20px; font-weight: bold; color: #28a745;">{paid_count}</div>
                                <div style="font-size: 11px; color: #666;">Paid <span style="font-size: 10px;">ℹ️</span></div>
                            </div>
                            
                            <div style="text-align: center; padding: 8px 15px; cursor: help;" title="IN PAYMENT - Payment registered but not reconciled">
                                <div style="font-size: 28px; color: #007bff;">🔵</div>
                                <div style="font-size: 20px; font-weight: bold; color: #007bff;">{in_payment_count}</div>
                                <div style="font-size: 11px; color: #666;">In Payment <span style="font-size: 10px;">ℹ️</span></div>
                            </div>
                            
                            <div style="text-align: center; padding: 8px 15px; cursor: help;" title="PENDING - Subscriptions with unpaid invoices">
                                <div style="font-size: 28px; color: #ffc107;">⚠️</div>
                                <div style="font-size: 20px; font-weight: bold; color: #e0a800;">{pending_count}</div>
                                <div style="font-size: 11px; color: #666;">Pending <span style="font-size: 10px;">ℹ️</span></div>
                            </div>
                            
                            <div style="text-align: center; padding: 8px 15px; cursor: help;" title="EXPIRED - No invoice created for billing period">
                                <div style="font-size: 28px; color: #dc3545;">🔴</div>
                                <div style="font-size: 20px; font-weight: bold; color: #dc3545;">{expired_count}</div>
                                <div style="font-size: 11px; color: #666;">Expired <span style="font-size: 10px;">ℹ️</span></div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Collection Rate & Metrics -->
                    <div style="display: flex; gap: 10px;">
                        <div style="flex: 1; text-align: center; padding: 12px; background: linear-gradient(135deg, #6c757d 0%, #5a6268 100%); border-radius: 10px; color: white; cursor: help;" title="COLLECTION RATE&#10;&#10;Percentage collected in this period.">
                            <div style="font-size: 11px; opacity: 0.9;">Collection Rate <span style="font-size: 10px;">ℹ️</span></div>
                            <div style="font-size: 28px; font-weight: bold;">
                                {(total_paid / total_invoiced * 100) if total_invoiced > 0 else 0:.1f}%
                            </div>
                        </div>
                        
                        <div style="flex: 1; text-align: center; padding: 12px; background: {'linear-gradient(135deg, #dc3545 0%, #c82333 100%)' if critical_count > 0 else 'linear-gradient(135deg, #28a745 0%, #218838 100%)'}; border-radius: 10px; color: white; cursor: help;" title="CRITICAL ALERTS&#10;&#10;Subscriptions past the 5th with NO PAYMENT.">
                            <div style="font-size: 11px; opacity: 0.9;">🔥 Critical Alerts <span style="font-size: 10px;">ℹ️</span></div>
                            <div style="font-size: 28px; font-weight: bold;">{critical_count}</div>
                        </div>
                    </div>
                </div>
                
                <!-- Right Column: Top Clients -->
                <div style="flex: 1; min-width: 280px;">
                    <div style="background: #f8f9fa; border-radius: 10px; padding: 15px; height: 100%;">
                        <h3 style="color: #333; margin-bottom: 12px; text-align: center; font-size: 16px;">🏆 Top 5 Clients (this period) <span style="font-size: 12px; cursor: help;" title="Clients ranked by payments in this period">ℹ️</span></h3>
                        <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                            <thead>
                                <tr style="background: #e9ecef;">
                                    <th style="padding: 6px; text-align: center;">#</th>
                                    <th style="padding: 6px; text-align: left;">Client</th>
                                    <th style="padding: 6px; text-align: right;">Paid</th>
                                    <th style="padding: 6px; text-align: right;">To Pay</th>
                                </tr>
                            </thead>
                            <tbody>
                                {top_clients_html if top_clients_html else '<tr><td colspan="4" style="text-align: center; padding: 20px; color: #666;">No data for this period</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- Bottom Row: Time Insights + Clients at Risk -->
            <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                
                <!-- Time Insights -->
                <div style="flex: 1; min-width: 200px; background: #e3f2fd; border-radius: 10px; padding: 15px;">
                    <h3 style="color: #1565c0; margin-bottom: 12px; text-align: center; font-size: 16px;">📅 Time Insights <span style="font-size: 12px; cursor: help;" title="Upcoming billing and payment delays">ℹ️</span></h3>
                    <div style="display: flex; justify-content: space-around; flex-wrap: wrap; gap: 10px;">
                        <div style="text-align: center; padding: 10px; background: white; border-radius: 8px; min-width: 100px; cursor: help;" title="Subscriptions with next invoice in 7 days">
                            <div style="font-size: 24px; font-weight: bold; color: #1565c0;">{len(expiring_soon)}</div>
                            <div style="font-size: 11px; color: #666;">Expiring in 7 days <span style="font-size: 10px;">ℹ️</span></div>
                        </div>
                        <div style="text-align: center; padding: 10px; background: white; border-radius: 8px; min-width: 100px; cursor: help;" title="Age of oldest unpaid invoice">
                            <div style="font-size: 24px; font-weight: bold; color: {'#dc3545' if oldest_unpaid_days > 30 else '#ffc107'};">{oldest_unpaid_days}</div>
                            <div style="font-size: 11px; color: #666;">Days oldest unpaid <span style="font-size: 10px;">ℹ️</span></div>
                        </div>
                    </div>
                </div>
                
                <!-- Clients at Risk -->
                <div style="flex: 1; min-width: 200px; background: #fff3e0; border-radius: 10px; padding: 15px;">
                    <h3 style="color: #e65100; margin-bottom: 12px; text-align: center; font-size: 16px;">⚠️ Clients at Risk ({len(clients_at_risk)}) <span style="font-size: 12px; cursor: help;" title="Clients with expired/pending payment status">ℹ️</span></h3>
                    {at_risk_html}
                </div>
            </div>
        </div>
        '''
        
        return {
            'total_subscriptions': len(subscriptions),
            'total_paid': total_paid,
            'total_to_pay': total_to_pay,
            'total_invoiced': total_invoiced,
            'currency_id': currency.id,
            'paid_count': paid_count,
            'in_payment_count': in_payment_count,
            'pending_count': pending_count,
            'expired_count': expired_count,
            'summary_html': summary_html,
        }
    
    def action_apply_filter(self):
        """Apply date filter and refresh dashboard"""
        summary_data = self._compute_summary_data(self.date_from, self.date_to)
        self.write(summary_data)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.summary.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_refresh(self):
        """Refresh subscription data and reload wizard"""
        self.env['sale.order'].action_refresh_all_subscriptions()
        return self.action_apply_filter()
    
    def action_close(self):
        """Close the wizard"""
        return {'type': 'ir.actions.act_window_close'}
