# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ===== Override to trigger refresh on access =====
    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        """Override search_read to refresh payment status fields when listing subscriptions"""
        result = super().search_read(domain, fields, offset, limit, order, **read_kwargs)
        
        # Trigger recomputation for subscription-related fields if they are requested
        status_fields = {'subscription_payment_status', 'payment_alert_message', 'payment_info_tooltip',
                        'invoice_created_for_period', 'has_pending_invoice', 'has_missing_invoice'}
        
        if fields and status_fields.intersection(set(fields)):
            # Get the IDs from the result and recompute
            ids = [r['id'] for r in result if 'id' in r]
            if ids:
                records = self.browse(ids)
                # Invalidate cache and recompute
                records.invalidate_recordset()
                # Force recomputation by accessing the fields
                for record in records:
                    if record.is_cm_subscription:
                        _ = record.subscription_payment_status
                        _ = record.invoice_created_for_period
                # Re-fetch the data
                result = super().search_read(domain, fields, offset, limit, order, **read_kwargs)
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to set is_cm_subscription for new subscriptions"""
        records = super().create(vals_list)
        # Set is_cm_subscription for records with plan_id
        for record in records:
            plan_id = getattr(record, 'plan_id', None)
            if plan_id and not record.is_cm_subscription:
                # Use SQL update to avoid triggering another write
                record.env.cr.execute(
                    "UPDATE sale_order SET is_cm_subscription = TRUE WHERE id = %s",
                    (record.id,)
                )
                record.invalidate_recordset(['is_cm_subscription'])
        return records

    def write(self, vals):
        """Override write to set is_cm_subscription when plan_id changes"""
        result = super().write(vals)
        # Only update is_cm_subscription if we're not already setting it
        if 'is_cm_subscription' not in vals:
            for record in self:
                plan_id = getattr(record, 'plan_id', None)
                if plan_id and not record.is_cm_subscription:
                    # Use SQL update to avoid triggering another write
                    record.env.cr.execute(
                        "UPDATE sale_order SET is_cm_subscription = TRUE WHERE id = %s",
                        (record.id,)
                    )
                    record.invalidate_recordset(['is_cm_subscription'])
        return result


    # ===== Subscription Identification =====
    # Boolean field - set automatically when plan_id is present
    is_cm_subscription = fields.Boolean(
        string='Is Subscription',
        default=False,
        store=True,
        help='True if this order has a recurring plan'
    )
    
    # Boolean field to mark if server has been shutdown for this subscription
    is_server_shutdown = fields.Boolean(
        string='Server Shutdown',
        default=False,
        store=True,
        help='Set to True when the server has been shut down for non-payment. When False, shows "System Should Shutdown" alert.'
    )
    
    # Client information validation status (manual field)
    client_info_validated = fields.Selection([
        ('not_validated', '❌ Not Validated'),
        ('pending', '🔄 Pending'),
        ('validated', '✅ Validated'),
    ], string='Client Validated', default='not_validated', store=True,
       help='Manual field to indicate if client information has been verified and validated.')
    
    # ===== Free Subscription Fields =====
    # For influencers, partners, promotional accounts, etc.
    is_free_subscription = fields.Boolean(
        string='Free Subscription',
        default=False,
        store=True,
        help='Mark as FREE subscription - no payment alerts will be shown'
    )
    
    free_subscription_reason = fields.Selection([
        ('influencer', '🎬 Influencer'),
        ('partner', '🤝 Partner'),
        ('promo', '🎁 Promotional'),
        ('vip', '⭐ VIP Client'),
        ('test', '🧪 Test Account'),
        ('other', '📋 Other'),
    ], string='Free Reason', store=True,
       help='Reason why this subscription is free')
    
    free_subscription_note = fields.Text(
        string='Free Sub Notes',
        help='Additional notes about this free subscription (e.g., influencer name, campaign, etc.)'
    )
    
    free_subscription_expiry = fields.Date(
        string='Free Until',
        help='Optional: Date when the free period ends. Leave empty for permanent free subscription.'
    )
    
    free_subscription_expired = fields.Boolean(
        string='Free Period Expired',
        compute='_compute_free_subscription_expired',
        store=True,
        help='True if the free subscription period has expired'
    )
    
    free_days_remaining = fields.Integer(
        string='Free Days Left',
        compute='_compute_free_subscription_expired',
        store=True,
        help='Number of days remaining in free subscription period'
    )
    
    # ===== Client Contact Info =====
    client_phone = fields.Char(
        string='Client Phone',
        related='partner_id.phone',
        store=False,
        help='Phone number of the client'
    )

    # ===== Payment Tracking Fields =====
    last_payment_date = fields.Date(
        string='Last Payment Date',
        compute='_compute_payment_info',
        store=True,
        help='Date of the last successful payment for this subscription'
    )
    
    last_payment_partner_id = fields.Many2one(
        'res.partner',
        string='Last Paid By',
        compute='_compute_payment_info',
        store=True,
        help='Partner who made the last payment'
    )
    
    last_payment_amount = fields.Monetary(
        string='Last Payment Amount',
        compute='_compute_payment_info',
        store=True,
        currency_field='currency_id',
        help='Amount of the last payment'
    )
    
    # ===== Total Invoice Tracking =====
    total_invoiced_amount = fields.Monetary(
        string='Total Invoiced',
        compute='_compute_total_invoiced',
        store=True,
        currency_field='currency_id',
        help='Total amount invoiced since first payment'
    )
    
    first_invoice_date = fields.Date(
        string='First Invoice Date',
        compute='_compute_total_invoiced',
        store=True,
        help='Date of the first invoice'
    )
    
    # ===== Invoice Tracking Fields =====
    days_until_next_invoice = fields.Integer(
        string='Days Until Next Invoice',
        compute='_compute_days_until_next_invoice',
        help='Number of days remaining until the next invoice'
    )
    
    amount_to_pay = fields.Monetary(
        string='Amount To Pay',
        compute='_compute_amount_to_pay',
        currency_field='currency_id',
        help='Amount that should be paid for the current/next period'
    )
    
    # ===== Enhanced Status Fields =====
    # Logic based on NEXT invoice date:
    # - free: Free subscription (influencer, partner, promo)
    # - paid: Invoice for the target period is PAID
    # - in_payment: Invoice is partially paid or in payment
    # - requires_payment: Before deadline, invoice exists but NOT paid
    # - pending: After deadline, invoice exists but NOT paid  
    # - should_invoice: Before deadline, NO invoice exists - need to create
    # - expired: After deadline, NO invoice exists
    subscription_payment_status = fields.Selection([
        ('free', 'Free'),
        ('paid', 'Paid'),
        ('in_payment', 'In Payment'),
        ('requires_payment', 'Requires Payment'),
        ('pending', 'Pending Payment'),
        ('should_invoice', 'Should Invoice'),
        ('expired', 'Expired'),
    ], string='Payment Status',
        compute='_compute_subscription_payment_status',
        store=True,
        help='Current payment status of the subscription'
    )
    
    has_pending_invoice = fields.Boolean(
        string='Has Pending Invoice',
        compute='_compute_invoice_alerts',
        store=True,
        help='True if there is an unpaid invoice for this subscription'
    )
    
    has_missing_invoice = fields.Boolean(
        string='Missing Next Invoice',
        compute='_compute_invoice_alerts',
        store=True,
        help='True if no invoice has been created for the next billing period'
    )
    
    is_payment_window_active = fields.Boolean(
        string='Payment Window Active',
        compute='_compute_payment_window',
        help='True if today is between the 1st and 5th of the month'
    )
    
    invoice_created_for_period = fields.Boolean(
        string='Invoice Created',
        compute='_compute_invoice_alerts',
        store=True,
        help='True if invoice has been created for next period'
    )
    
    # ===== Display Fields =====
    payment_alert_message = fields.Html(
        string='Alerts',
        compute='_compute_payment_alert_message',
        sanitize=False,
        help='Alert message with hover tooltip showing payment details'
    )
    
    payment_status_display = fields.Char(
        string='Status Display',
        compute='_compute_payment_status_display',
        help='Formatted status display for list view'
    )
    
    # ===== Tooltip Field for List View Hover =====
    payment_info_tooltip = fields.Text(
        string='Payment Info',
        compute='_compute_payment_info_tooltip',
        help='Detailed payment information shown on hover'
    )
    
    # ===== Total Paid Amount =====
    total_paid_amount = fields.Monetary(
        string='Total Paid',
        compute='_compute_total_paid',
        store=True,
        currency_field='currency_id',
        help='Total amount paid from all invoices'
    )

    # ===== Compute Methods =====

    @api.depends('is_free_subscription', 'free_subscription_expiry')
    def _compute_free_subscription_expired(self):
        """Check if the free subscription period has expired"""
        today = fields.Date.today()
        for order in self:
            if order.is_free_subscription and order.free_subscription_expiry:
                order.free_subscription_expired = today > order.free_subscription_expiry
                order.free_days_remaining = (order.free_subscription_expiry - today).days
            else:
                order.free_subscription_expired = False
                order.free_days_remaining = 0

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.invoice_date', 
                 'invoice_ids.amount_total', 'invoice_ids.amount_residual', 'invoice_ids.partner_id', 'invoice_ids.state')
    def _compute_payment_info(self):
        """Compute last payment information - only for invoices with actual payments or in_payment status"""
        for order in self:
            # Only get invoices that have been PAID or have payment in progress
            # Exclude 'not_paid' invoices - those don't have actual payments
            paid_invoices = order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' 
                and inv.state == 'posted'
                and inv.payment_state in ('paid', 'in_payment', 'partial')
            ).sorted(key=lambda inv: inv.invoice_date or fields.Date.today(), reverse=True)
            
            if paid_invoices:
                last_paid_invoice = paid_invoices[0]
                order.last_payment_date = last_paid_invoice.invoice_date
                order.last_payment_partner_id = last_paid_invoice.partner_id.id
                
                # Calculate amount paid
                amount_paid = last_paid_invoice.amount_total - last_paid_invoice.amount_residual
                
                # For 'in_payment' status, the payment might not be reconciled yet
                # so amount_paid could be 0, but we should show the invoice amount
                if last_paid_invoice.payment_state == 'in_payment' and amount_paid == 0:
                    # Payment registered but not reconciled yet - show full invoice amount
                    order.last_payment_amount = last_paid_invoice.amount_total
                else:
                    order.last_payment_amount = amount_paid
            else:
                # No payments made - clear the fields
                order.last_payment_date = False
                order.last_payment_partner_id = False
                order.last_payment_amount = 0.0

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.invoice_date', 
                 'invoice_ids.amount_total', 'invoice_ids.state')
    def _compute_total_invoiced(self):
        """Compute total invoiced amount and first invoice date"""
        for order in self:
            all_invoices = order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted'
            ).sorted(key=lambda inv: inv.invoice_date or fields.Date.today())
            
            if all_invoices:
                order.first_invoice_date = all_invoices[0].invoice_date
                order.total_invoiced_amount = sum(all_invoices.mapped('amount_total'))
            else:
                order.first_invoice_date = False
                order.total_invoiced_amount = 0.0

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.amount_total', 
                 'invoice_ids.amount_residual', 'invoice_ids.state')
    def _compute_total_paid(self):
        """Compute total paid amount from all invoices (includes in_payment status)"""
        for order in self:
            all_invoices = order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted'
            )
            
            total_paid = 0.0
            for inv in all_invoices:
                if inv.payment_state == 'paid':
                    # Fully paid invoice - count full amount
                    total_paid += inv.amount_total
                elif inv.payment_state in ('in_payment', 'partial'):
                    # In payment or partial - count the paid portion
                    # For in_payment, treat as fully paid (payment is in progress)
                    total_paid += inv.amount_total - inv.amount_residual
                    # Also add any in_payment amount (payment registered but not reconciled)
                    if inv.payment_state == 'in_payment':
                        total_paid += inv.amount_residual  # Count in_payment as paid
                        
            order.total_paid_amount = total_paid

    def _compute_days_until_next_invoice(self):
        """Compute days until next invoice - uses existing next_invoice_date if available"""
        today = fields.Date.today()
        for order in self:
            # Use existing next_invoice_date field if it exists (from sale_subscription)
            next_date = getattr(order, 'next_invoice_date', None)
            if next_date:
                order.days_until_next_invoice = (next_date - today).days
            else:
                order.days_until_next_invoice = 0

    @api.depends('amount_total', 'invoice_ids', 'invoice_ids.amount_residual', 'invoice_ids.state')
    def _compute_amount_to_pay(self):
        """Compute the amount that should be paid"""
        for order in self:
            # Get unpaid invoices
            unpaid_invoices = order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and 
                           inv.payment_state not in ('paid', 'reversed') and
                           inv.state == 'posted'
            )
            if unpaid_invoices:
                order.amount_to_pay = sum(unpaid_invoices.mapped('amount_residual'))
            else:
                # Use order total as reference
                order.amount_to_pay = order.amount_total

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.invoice_date_due',
                 'invoice_ids.state', 'invoice_ids.invoice_date', 'invoice_ids.amount_total',
                 'invoice_ids.amount_residual', 'is_cm_subscription', 'state',
                 'is_free_subscription', 'free_subscription_expired')
    def _compute_subscription_payment_status(self):
        """
        Compute payment status based on NEXT invoice date:
        - free: Free subscription (influencer, partner, promo) - no payment required
        - paid: Invoice for the target period is PAID
        - in_payment: Invoice is partially paid or in payment
        - requires_payment: Before 15th, invoice exists but NOT paid
        - pending: After 15th, invoice exists but NOT paid (SHUTDOWN!)
        - should_invoice: NO invoice exists - need to create
        - expired: After 15th, NO invoice exists (SHUTDOWN!)
        
        Target Month Logic:
        - Before the 20th of current month: target = CURRENT month
        - After the 20th of current month: target = NEXT month
        
        Example (today = Dec 31, 2025):
          - Since 31 >= 20, target month = January 2026
          - Check if invoice for Jan 2026 exists and is paid
          
        Example (today = Jan 15, 2026):
          - Since 15 < 20, target month = January 2026
          - Check if invoice for Jan 2026 exists and is paid
        """
        today = fields.Date.today()
        current_day = today.day
        
        for order in self:
            if not order.is_cm_subscription:
                order.subscription_payment_status = False
                continue
            
            # ===== FREE SUBSCRIPTION HANDLING =====
            # Free subscriptions skip all payment logic unless their free period expired
            if order.is_free_subscription and not order.free_subscription_expired:
                order.subscription_payment_status = 'free'
                continue
            
            # Determine target month based on current day
            # Before 20th: check current month
            # After 20th: check next month
            if current_day < 20:
                # Target is CURRENT month
                target_month_start = today.replace(day=1)
            else:
                # Target is NEXT month
                target_month_start = (today.replace(day=1) + relativedelta(months=1))
            
            target_month_end = (target_month_start + relativedelta(months=1)) - timedelta(days=1)
            
            # The deadline is the 15th of the target month (changed from 5th)
            # Users can pay from 1st-15th, after 15th = system should shutdown
            deadline_date = target_month_start.replace(day=15)
            is_past_deadline = today > deadline_date
            
            # CRITICAL CHECK: If next_invoice_date is AFTER the target month,
            # it means the target month is already covered (invoice created and the system 
            # moved to the next billing period). This happens when invoice is paid.
            next_inv_date = order.next_invoice_date
            if next_inv_date and next_inv_date > target_month_end:
                # The subscription has already moved past this period
                # Check the most recent invoice to confirm it's paid
                recent_invoices = order.invoice_ids.filtered(
                    lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted'
                ).sorted(key=lambda inv: inv.invoice_date or fields.Date.today(), reverse=True)
                
                if recent_invoices and recent_invoices[0].payment_state == 'paid':
                    order.subscription_payment_status = 'paid'
                    continue
                elif recent_invoices and recent_invoices[0].payment_state in ('in_payment', 'partial'):
                    order.subscription_payment_status = 'in_payment'
                    continue
            
            
            # Find invoices for the target period
            # Check by invoice_date within target month
            target_period_invoices = order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and 
                           inv.state == 'posted' and
                           inv.invoice_date and 
                           target_month_start <= inv.invoice_date <= target_month_end
            )
            
            # Also check for invoices from previous month that might be for this period
            # (invoices are often created in advance for the next billing period)
            if not target_period_invoices:
                two_months_before_target = target_month_start - relativedelta(months=2)
                prev_month_end = target_month_start - timedelta(days=1)
                
                # Find invoices from any time in the previous 2 months
                # These could be advance invoices for the target period
                prev_month_invoices = order.invoice_ids.filtered(
                    lambda inv: inv.move_type == 'out_invoice' and 
                               inv.state == 'posted' and
                               inv.invoice_date and 
                               two_months_before_target <= inv.invoice_date <= prev_month_end
                )
                
                # If we found invoices from previous month(s), use the most recent ones as target
                # This handles the case where invoice was created early for next period
                if prev_month_invoices:
                    # Get the most recent invoice by date
                    sorted_invoices = prev_month_invoices.sorted(key=lambda inv: inv.invoice_date, reverse=True)
                    # Use the most recent invoice(s) - usually invoice created for upcoming period
                    target_period_invoices = sorted_invoices[:1]  # Take most recent
                    
                    # If the most recent invoice is PAID, check if it's likely for the target period
                    # by checking if next_invoice_date is after target_month_start
                    if target_period_invoices and target_period_invoices[0].payment_state == 'paid':
                        # Check if subscription's next_invoice_date is in or after target month
                        next_inv_date = order.next_invoice_date
                        if next_inv_date and next_inv_date >= target_month_start:
                            # This paid invoice is likely covering the target period
                            target_period_invoices = sorted_invoices[:1]
                        else:
                            # The paid invoice might be for a previous period, need new invoice
                            target_period_invoices = order.invoice_ids.browse()  # Empty recordset
            
            # Check payment states
            paid_invoices = target_period_invoices.filtered(
                lambda inv: inv.payment_state == 'paid'
            )
            in_payment_invoices = target_period_invoices.filtered(
                lambda inv: inv.payment_state in ('partial', 'in_payment')
            )
            unpaid_invoices = target_period_invoices.filtered(
                lambda inv: inv.payment_state not in ('paid', 'reversed', 'partial', 'in_payment')
            )
            
            if paid_invoices:
                # Invoice for target period is PAID
                order.subscription_payment_status = 'paid'
            elif in_payment_invoices:
                # Invoice is partially paid or in payment process
                order.subscription_payment_status = 'in_payment'
            elif unpaid_invoices:
                # Invoice exists but NOT paid
                if not is_past_deadline:
                    # Before the 5th of target month - still time to pay
                    order.subscription_payment_status = 'requires_payment'
                else:
                    # After 5th, but invoice exists - pending payment
                    order.subscription_payment_status = 'pending'
            else:
                # NO invoice exists for target period
                if not is_past_deadline:
                    # Need to create invoice for target month
                    order.subscription_payment_status = 'should_invoice'
                else:
                    # After 5th and NO invoice = EXPIRED
                    order.subscription_payment_status = 'expired'

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.state',
                 'invoice_ids.invoice_date', 'invoice_ids.amount_total', 
                 'invoice_ids.amount_residual', 'is_cm_subscription', 'state')
    def _compute_invoice_alerts(self):
        """Compute alert flags for pending/missing invoices
        
        Target Month Logic (same as payment status):
        - Before the 20th of current month: target = CURRENT month
        - After the 20th of current month: target = NEXT month
        """
        today = fields.Date.today()
        current_day = today.day
        
        for order in self:
            if not order.is_cm_subscription:
                order.has_pending_invoice = False
                order.has_missing_invoice = False
                order.invoice_created_for_period = False
                continue
            
            # Determine target month based on current day
            if current_day < 20:
                # Target is CURRENT month
                target_month_start = today.replace(day=1)
            else:
                # Target is NEXT month
                target_month_start = (today.replace(day=1) + relativedelta(months=1))
            
            target_month_end = (target_month_start + relativedelta(months=1)) - timedelta(days=1)
            
            # Check for pending (unpaid) invoices
            pending_invoices = order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and 
                           inv.payment_state not in ('paid', 'reversed') and
                           inv.state == 'posted'
            )
            order.has_pending_invoice = bool(pending_invoices)
            
            # Check if invoice exists for the target period
            target_period_invoices = order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and 
                           inv.state == 'posted' and
                           inv.invoice_date and 
                           target_month_start <= inv.invoice_date <= target_month_end
            )
            
            # Also check for invoices created at end of previous month for target month
            if not target_period_invoices:
                one_month_before_target = target_month_start - relativedelta(months=1)
                prev_month_end = target_month_start - timedelta(days=1)
                
                # Find invoices from previous month created after the 20th
                late_prev_month_invoices = order.invoice_ids.filtered(
                    lambda inv: inv.move_type == 'out_invoice' and 
                               inv.state == 'posted' and
                               inv.invoice_date and 
                               one_month_before_target <= inv.invoice_date <= prev_month_end and
                               inv.invoice_date.day >= 20
                )
                # Use recordset union
                target_period_invoices = target_period_invoices | late_prev_month_invoices
            
            order.invoice_created_for_period = bool(target_period_invoices)
            order.has_missing_invoice = not bool(target_period_invoices)

    def _compute_payment_window(self):
        """Check if current date is within payment window (1st-15th of month)"""
        today = fields.Date.today()
        for order in self:
            order.is_payment_window_active = 1 <= today.day <= 15

    @api.depends('subscription_payment_status', 'has_pending_invoice', 
                 'has_missing_invoice', 'is_payment_window_active', 'is_cm_subscription',
                 'last_payment_date', 'last_payment_partner_id', 'last_payment_amount',
                 'total_invoiced_amount', 'amount_to_pay', 'days_until_next_invoice',
                 'is_free_subscription', 'free_subscription_reason', 'free_subscription_expiry',
                 'free_days_remaining', 'free_subscription_expired')
    def _compute_payment_alert_message(self):
        """Generate HTML alert message with hover tooltip showing payment details"""
        from markupsafe import Markup
        
        today = fields.Date.today()
        is_past_15th = today.day > 15  # Deadline for payment (changed from 5th)
        is_past_25th = today.day > 25  # For paid subs: remind to invoice next month
        
        # Reason display mapping
        reason_labels = {
            'influencer': '🎬 Influencer',
            'partner': '🤝 Partner',
            'promo': '🎁 Promotional',
            'vip': '⭐ VIP Client',
            'test': '🧪 Test Account',
            'other': '📋 Other',
        }
        
        for order in self:
            if not order.is_cm_subscription:
                order.payment_alert_message = False
                continue
            
            # Build status message and determine alert styling
            status_msg = ""
            status_emoji = ""
            alert_class = ""  # CSS class for animation
            is_shutdown_state = False  # Flag for shutdown alert
            is_free_state = False  # Flag for free subscription
            
            # ===== FREE SUBSCRIPTION HANDLING =====
            if order.is_free_subscription and not order.free_subscription_expired:
                is_free_state = True
                reason_label = reason_labels.get(order.free_subscription_reason, '🎁 Free')
                
                if order.free_subscription_expiry and order.free_days_remaining <= 30:
                    # Expiring soon warning
                    if order.free_days_remaining <= 7:
                        status_msg = f"{reason_label} - {order.free_days_remaining}d left!"
                        alert_class = "o_free_expiring_soon"
                    else:
                        status_msg = f"{reason_label} - {order.free_days_remaining}d"
                        alert_class = "o_free_subscription_badge"
                else:
                    status_msg = reason_label
                    alert_class = "o_free_subscription_badge"
                status_emoji = "🎁"
            elif order.free_subscription_expired:
                # Free period has expired - treat as regular subscription
                status_msg = "Free period ended"
                status_emoji = "⚡"
                alert_class = "o_free_expired"
            # Check for SHUTDOWN condition: past 15th AND (pending or expired or requires_payment)
            elif is_past_15th and order.subscription_payment_status in ('pending', 'expired', 'requires_payment'):
                is_shutdown_state = True
                if order.is_server_shutdown:
                    # Server is ALREADY shutdown
                    status_msg = "SERVER SHUTDOWN"
                    status_emoji = "🔴"
                    alert_class = "o_already_shutdown"
                else:
                    # Server SHOULD be shutdown (not yet marked)
                    status_msg = "System Should Shutdown"
                    status_emoji = "⚠️"
                    alert_class = "o_shutdown_alert"
            elif order.subscription_payment_status == 'expired':
                status_msg = "EXPIRED - No invoice!"
                status_emoji = "🔥"
                alert_class = "o_urgent_alert"
            elif order.subscription_payment_status == 'pending':
                status_msg = "Pending payment"
                status_emoji = "⚠️"
                alert_class = "o_warning_alert"
            elif order.subscription_payment_status == 'requires_payment':
                status_msg = "Pay before the 15th"
                status_emoji = "🔴"
                alert_class = "o_unpaid_alert"
            elif order.subscription_payment_status == 'in_payment':
                status_msg = "Payment in progress"
                status_emoji = "🔵"
                alert_class = ""
            elif order.subscription_payment_status == 'paid':
                # For paid subscriptions after 25th: remind to invoice next month
                if is_past_25th:
                    status_msg = "📋 Invoice next month"
                    status_emoji = "✅"
                    alert_class = "o_invoice_reminder"
                else:
                    status_msg = "Paid"
                    status_emoji = "✅"
                    alert_class = "o_success_indicator"
            elif order.subscription_payment_status == 'should_invoice':
                status_msg = "Should create invoice"
                status_emoji = "📋"
                alert_class = "o_warning_alert"
            
            # Format currency
            currency = order.currency_id.symbol or 'DH'
            
            # Build tooltip text (shown on hover) - cleaner format
            tooltip_lines = []
            tooltip_lines.append("╔══════════════════════════════╗")
            tooltip_lines.append("║      📊 PAYMENT SUMMARY      ║")
            tooltip_lines.append("╠══════════════════════════════╣")
            tooltip_lines.append(f"║  Status: {status_emoji} {status_msg[:20]}")
            tooltip_lines.append("╠══════════════════════════════╣")
            
            # Show payment info only if there's actual payment
            if order.last_payment_date and order.last_payment_amount > 0:
                tooltip_lines.append("║  💰 LAST PAYMENT")
                tooltip_lines.append(f"║  ├─ Date: {order.last_payment_date.strftime('%d/%m/%Y')}")
                if order.last_payment_partner_id:
                    tooltip_lines.append(f"║  ├─ By: {order.last_payment_partner_id.name[:15]}")
                tooltip_lines.append(f"║  └─ Amount: {order.last_payment_amount:,.2f} {currency}")
            else:
                tooltip_lines.append("║  💰 LAST PAYMENT")
                tooltip_lines.append("║  └─ ❌ No payment yet")
                
            tooltip_lines.append("╠══════════════════════════════╣")
            tooltip_lines.append("║  📋 TOTALS")
            tooltip_lines.append(f"║  ├─ Invoiced: {order.total_invoiced_amount:,.2f} {currency}")
            tooltip_lines.append(f"║  └─ To Pay: {order.amount_to_pay:,.2f} {currency}")
            tooltip_lines.append("╠══════════════════════════════╣")
            tooltip_lines.append("║  📅 NEXT INVOICE")
            tooltip_lines.append(f"║  ├─ In: {order.days_until_next_invoice} days")
            tooltip_lines.append(f"║  └─ Created: {'✓ Yes' if order.invoice_created_for_period else '✗ No'}")
            tooltip_lines.append("╚══════════════════════════════╝")
            
            tooltip_text = "&#10;".join(tooltip_lines)  # &#10; is line break in HTML title
            
            # Create HTML with animated indicator for unpaid statuses
            if is_shutdown_state:
                # Shutdown state - calm pulsing indicator with circle
                order.payment_alert_message = Markup(
                    f'<span class="o_payment_alert_badge" title="{tooltip_text}" style="cursor: help;">'
                    f'<span class="o_shutdown_indicator">{status_emoji}</span>'
                    f'<span class="{alert_class}">{status_msg}</span>'
                    f'</span>'
                )
            elif is_free_state:
                # Free subscription - beautiful purple gradient badge
                order.payment_alert_message = Markup(
                    f'<span class="o_payment_alert_badge" title="{tooltip_text}" style="cursor: help;">'
                    f'<span class="{alert_class}">{status_emoji} {status_msg}</span>'
                    f'</span>'
                )
            elif order.free_subscription_expired:
                # Expired free subscription - orange alert
                order.payment_alert_message = Markup(
                    f'<span class="o_payment_alert_badge" title="{tooltip_text}" style="cursor: help;">'
                    f'<span class="{alert_class}">{status_emoji} {status_msg}</span>'
                    f'</span>'
                )
            elif alert_class and order.subscription_payment_status in ('expired', 'requires_payment', 'pending', 'should_invoice'):
                # Show flashing indicator for urgent statuses
                order.payment_alert_message = Markup(
                    f'<span class="o_payment_alert_badge" title="{tooltip_text}" style="cursor: help;">'
                    f'<span class="{alert_class}" style="animation: pulse-red 1s infinite;">{status_emoji}</span>'
                    f'<span style="color: {"#ff4444" if order.subscription_payment_status in ("expired", "requires_payment") else "#ffa500"}; font-weight: bold;">{status_msg}</span>'
                    f'</span>'
                )
            else:
                # Normal display for paid/in_payment
                visible_text = f"{status_emoji} {status_msg}"
                order.payment_alert_message = Markup(
                    f'<span title="{tooltip_text}" style="cursor: help; white-space: nowrap;">{visible_text}</span>'
                )

    @api.depends('subscription_payment_status')
    def _compute_payment_status_display(self):
        """Generate formatted status display with icons"""
        status_icons = {
            'paid': '✅ Paid',
            'in_payment': '🔵 In Payment',
            'requires_payment': '⚠️ Requires Payment',
            'pending': '🟠 Pending Payment',
            'expired': '🔴 Expired',
            'should_invoice': '� Should Invoice',
        }
        for order in self:
            if order.subscription_payment_status:
                order.payment_status_display = status_icons.get(
                    order.subscription_payment_status, 
                    order.subscription_payment_status
                )
            else:
                order.payment_status_display = ''

    @api.depends('subscription_payment_status', 'last_payment_date', 'last_payment_partner_id',
                 'last_payment_amount', 'first_invoice_date', 'total_invoiced_amount',
                 'amount_to_pay', 'has_pending_invoice', 'has_missing_invoice',
                 'invoice_created_for_period', 'days_until_next_invoice', 'is_cm_subscription',
                 'invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.invoice_date')
    def _compute_payment_info_tooltip(self):
        """Generate tooltip text with all payment information for hover display"""
        status_labels = {
            'paid': 'PAID - Invoice is paid',
            'in_payment': 'IN PAYMENT - Payment in progress',
            'requires_payment': 'REQUIRES PAYMENT - Pay before the 5th',
            'pending': 'PENDING - Invoice awaiting payment',
            'expired': 'EXPIRED - No invoice created after deadline!',
            'should_invoice': 'SHOULD INVOICE - Create invoice before the 5th',
        }
        
        today = fields.Date.today()
        current_day = today.day
        
        for order in self:
            if not order.is_cm_subscription:
                order.payment_info_tooltip = ''
                continue
            
            # Calculate target month using same logic as payment status
            if current_day < 20:
                # Target is CURRENT month
                target_month_date = today.replace(day=1)
            else:
                # Target is NEXT month
                target_month_date = (today.replace(day=1) + relativedelta(months=1))
            
            target_month = target_month_date.strftime('%m/%Y')
            
            # Build tooltip text
            lines = []
            
            # Status
            status_text = status_labels.get(order.subscription_payment_status, '-')
            lines.append(f"📊 STATUS: {status_text}")
            lines.append(f"   Target Month: {target_month}")
            lines.append("")
            
            # Get the most recent posted invoice
            recent_invoices = order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted'
            ).sorted(key=lambda inv: inv.invoice_date or fields.Date.today(), reverse=True)
            
            # Last Payment Info - show for any invoice with payment activity
            lines.append("💰 LAST PAYMENT:")
            if recent_invoices:
                last_inv = recent_invoices[0]
                amount_paid = last_inv.amount_total - last_inv.amount_residual
                lines.append(f"   • Invoice Date: {last_inv.invoice_date.strftime('%d/%m/%Y') if last_inv.invoice_date else 'N/A'}")
                lines.append(f"   • Invoice Amount: {last_inv.amount_total:.2f} {order.currency_id.symbol}")
                lines.append(f"   • Amount Paid: {amount_paid:.2f} {order.currency_id.symbol}")
                if last_inv.amount_residual > 0:
                    lines.append(f"   • Remaining: {last_inv.amount_residual:.2f} {order.currency_id.symbol}")
                lines.append(f"   • Payment Status: {last_inv.payment_state.upper() if last_inv.payment_state else 'N/A'}")
                lines.append(f"   • Partner: {last_inv.partner_id.name if last_inv.partner_id else 'N/A'}")
            else:
                lines.append("   • No invoices found")
            lines.append("")
            
            # Totals
            lines.append("📋 TOTALS:")
            lines.append(f"   • Invoiced: {order.total_invoiced_amount:.2f} {order.currency_id.symbol}")
            lines.append(f"   • To Pay: {order.amount_to_pay:.2f} {order.currency_id.symbol}")
            lines.append("")
            
            # Next Invoice Info
            lines.append("📅 NEXT INVOICE:")
            lines.append(f"   • In: {order.days_until_next_invoice} days")
            lines.append(f"   • Created: {'✓ Yes' if order.invoice_created_for_period else '✗ No'}")
            
            order.payment_info_tooltip = '\n'.join(lines)

    # ===== Cron Job Methods =====
    
    @api.model
    def _cron_check_subscription_payments(self):
        """Scheduled action to check and update subscription payment statuses"""
        today = fields.Date.today()
        
        # Get all active subscriptions (EXCLUDE free subscriptions from alerts)
        subscriptions = self.search([
            ('is_cm_subscription', '=', True),
            ('state', '=', 'sale'),
            '|',
            ('is_free_subscription', '=', False),
            '&',
            ('is_free_subscription', '=', True),
            ('free_subscription_expired', '=', True),  # Include expired free subs
        ])
        
        # Send alerts for expired subscriptions (no invoice created for next month)
        expired_subs = subscriptions.filtered(
            lambda s: s.subscription_payment_status == 'expired'
        )
        for sub in expired_subs:
            sub.message_post(
                body=_("🔴 EXPIRED: Subscription %s has no invoice for next month. Create and pay to reactivate.") % sub.name,
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
        
        # Send alerts for requiring payment (1st-15th)
        if 1 <= today.day <= 15:
            pending_subs = subscriptions.filtered(
                lambda s: s.subscription_payment_status == 'requires_payment'
            )
            for sub in pending_subs:
                sub.message_post(
                    body=_("⚠️ Payment reminder: Invoice pending for subscription %s. Pay before the 15th!") % sub.name,
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
        
        return True

    # ===== Action Methods =====
    
    def action_view_pending_invoices(self):
        """Open list of pending invoices for this subscription"""
        self.ensure_one()
        pending_invoices = self.invoice_ids.filtered(
            lambda inv: inv.move_type == 'out_invoice' and inv.payment_state not in ('paid', 'reversed')
        )
        
        return {
            'name': _('Pending Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pending_invoices.ids)],
            'context': {'default_move_type': 'out_invoice'},
        }
    
    def action_mark_as_subscription(self):
        """Mark selected orders as subscriptions"""
        self.write({'is_cm_subscription': True})
    
    def action_unmark_subscription(self):
        """Remove subscription marking from selected orders"""
        self.write({'is_cm_subscription': False})
    
    def action_refresh_all_button(self):
        """Button action to refresh all subscription payment data (can be called from list view)"""
        # Call the model method
        return self.env['sale.order'].action_refresh_all_subscriptions()
    
    @api.model
    def action_show_summary(self):
        """Show subscription summary without refreshing - just display totals"""
        subscriptions = self.search([('is_cm_subscription', '=', True)])
        
        # Calculate summary totals
        total_paid = sum(subscriptions.mapped('total_paid_amount'))
        total_to_pay = sum(subscriptions.mapped('amount_to_pay'))
        total_invoiced = sum(subscriptions.mapped('total_invoiced_amount'))
        currency = self.env.company.currency_id.symbol
        
        # Count by status
        paid_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'paid'))
        in_payment_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'in_payment'))
        pending_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status in ('requires_payment', 'pending', 'should_invoice')))
        expired_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'expired'))
        
        summary_message = _(
            '📊 %d Total Subscriptions\n\n'
            '💰 Total Paid: %s %s\n'
            '⏳ To Pay: %s %s\n'
            '📄 Invoiced: %s %s\n\n'
            '✅ %d Paid | 🔵 %d In Payment | ⚠️ %d Pending | 🔴 %d Expired'
        ) % (
            len(subscriptions),
            '{:,.2f}'.format(total_paid), currency,
            '{:,.2f}'.format(total_to_pay), currency,
            '{:,.2f}'.format(total_invoiced), currency,
            paid_count, in_payment_count, pending_count, expired_count
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('📊 Subscription Summary'),
                'message': summary_message,
                'type': 'info',
                'sticky': True,
            }
        }
    
    @api.model
    def action_refresh_all_subscriptions(self):
        """Server action to refresh all subscription payment data"""
        try:
            # First, update is_cm_subscription for all orders that have plan_id
            self.env.cr.execute("""
                UPDATE sale_order 
                SET is_cm_subscription = TRUE 
                WHERE plan_id IS NOT NULL AND (is_cm_subscription = FALSE OR is_cm_subscription IS NULL)
            """)
            
            # Get all subscriptions
            subscriptions = self.search([('is_cm_subscription', '=', True)])
            
            if subscriptions:
                # Invalidate the entire cache
                subscriptions.invalidate_recordset()
                
                # Use modified() with only direct field names (no dotted paths)
                subscriptions.modified(['invoice_ids', 'is_cm_subscription'])
                
                # Force recomputation by calling compute methods directly
                subscriptions._compute_total_paid()
                subscriptions._compute_total_invoiced()
                subscriptions._compute_payment_info()
                subscriptions._compute_amount_to_pay()
                subscriptions._compute_subscription_payment_status()
                subscriptions._compute_invoice_alerts()
                
                # Flush all changes to database
                subscriptions.env.flush_all()
                
            # Calculate summary totals
            total_paid = sum(subscriptions.mapped('total_paid_amount'))
            total_to_pay = sum(subscriptions.mapped('amount_to_pay'))
            total_invoiced = sum(subscriptions.mapped('total_invoiced_amount'))
            currency = self.env.company.currency_id.symbol
            
            # Count by status
            paid_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'paid'))
            in_payment_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'in_payment'))
            pending_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status in ('requires_payment', 'pending', 'should_invoice')))
            expired_count = len(subscriptions.filtered(lambda s: s.subscription_payment_status == 'expired'))
            
            summary_message = _(
                '📊 %d Subscriptions Refreshed!\n\n'
                '💰 Total Paid: %s %s\n'
                '⏳ To Pay: %s %s\n'
                '📄 Invoiced: %s %s\n\n'
                '✅ %d Paid | 🔵 %d In Payment | ⚠️ %d Pending | 🔴 %d Expired'
            ) % (
                len(subscriptions),
                '{:,.2f}'.format(total_paid), currency,
                '{:,.2f}'.format(total_to_pay), currency,
                '{:,.2f}'.format(total_invoiced), currency,
                paid_count, in_payment_count, pending_count, expired_count
            )
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('📊 Subscription Summary'),
                    'message': summary_message,
                    'type': 'success',
                    'sticky': True,  # Keep visible so user can see totals
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Refresh Error'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_refresh_selected_subscriptions(self):
        """Refresh payment data for selected subscriptions"""
        # Invalidate the entire cache for selected records
        self.invalidate_recordset()
        
        # Use modified() to trigger recomputation of stored computed fields
        self.modified(['invoice_ids', 'is_cm_subscription'])
        
        # Flush changes to database
        self.env.flush_all()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Refresh Complete'),
                'message': _('%d subscriptions refreshed! Please refresh the page.') % len(self),
                'type': 'success',
                'sticky': False,
            }
        }



