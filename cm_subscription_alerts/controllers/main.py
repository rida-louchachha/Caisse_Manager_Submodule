# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class SubscriptionAlertController(http.Controller):
    
    @http.route('/cm_subscription_alerts/subscription_banner', type='json', auth='user')
    def get_subscription_banner(self):
        """Return totals for subscription list banner"""
        SaleOrder = request.env['sale.order']
        
        # Get all subscriptions
        subscriptions = SaleOrder.search([('is_cm_subscription', '=', True)])
        
        # Calculate totals
        total_paid = sum(subscriptions.mapped('total_paid_amount'))
        total_to_pay = sum(subscriptions.mapped('amount_to_pay'))
        total_invoiced = sum(subscriptions.mapped('total_invoiced_amount'))
        count = len(subscriptions)
        
        # Count by status
        paid_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'paid'))
        in_payment_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'in_payment'))
        pending_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status in ('requires_payment', 'pending', 'should_invoice')))
        expired_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'expired'))
        
        # Get currency
        currency = request.env.company.currency_id
        
        return {
            'total_paid': total_paid,
            'total_to_pay': total_to_pay,
            'total_invoiced': total_invoiced,
            'count': count,
            'paid_count': paid_count,
            'in_payment_count': in_payment_count,
            'pending_count': pending_count,
            'expired_count': expired_count,
            'currency_symbol': currency.symbol,
            'html': f'''
                <div class="o_subscription_summary" style="padding: 10px 20px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 8px; margin-bottom: 10px; display: flex; gap: 30px; flex-wrap: wrap; align-items: center; color: white;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 24px;">📊</span>
                        <div>
                            <div style="font-size: 12px; opacity: 0.7;">Subscriptions</div>
                            <div style="font-size: 18px; font-weight: bold;">{count}</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 24px;">💰</span>
                        <div>
                            <div style="font-size: 12px; opacity: 0.7;">Total Paid</div>
                            <div style="font-size: 18px; font-weight: bold; color: #4ade80;">{total_paid:,.2f} {currency.symbol}</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 24px;">⏳</span>
                        <div>
                            <div style="font-size: 12px; opacity: 0.7;">To Pay</div>
                            <div style="font-size: 18px; font-weight: bold; color: #fbbf24;">{total_to_pay:,.2f} {currency.symbol}</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 24px;">📄</span>
                        <div>
                            <div style="font-size: 12px; opacity: 0.7;">Total Invoiced</div>
                            <div style="font-size: 18px; font-weight: bold;">{total_invoiced:,.2f} {currency.symbol}</div>
                        </div>
                    </div>
                    <div style="border-left: 1px solid rgba(255,255,255,0.2); padding-left: 20px; display: flex; gap: 15px;">
                        <span style="color: #4ade80;">✅ {paid_count} Paid</span>
                        <span style="color: #60a5fa;">🔵 {in_payment_count} In Payment</span>
                        <span style="color: #fbbf24;">⚠️ {pending_count} Pending</span>
                        <span style="color: #f87171;">🔴 {expired_count} Expired</span>
                    </div>
                </div>
            '''
        }
