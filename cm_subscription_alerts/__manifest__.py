# -*- coding: utf-8 -*-
{
    'name': 'CM Subscription Alerts',
    'version': '18.0.1.0.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Enhanced subscription list view with payment tracking and alerts',
    'description': """
CM Subscription Alerts
======================

This module enhances the sale order list view with subscription payment tracking:

* **Payment Tracking**: Shows who paid, when, and how much
* **Next Invoice Date**: Displays upcoming billing dates
* **Payment Status**: Visual indicators (paid/requires payment/pending/expired)
* **Alert System**: Notifications for unpaid invoices
* **Payment Window**: Validates payments between 1st-5th of month

Status Logic:
-------------
* Paid: Invoice for next month is paid
* Requires Payment: Between 1st-5th, invoice exists but not paid
* Pending: After 5th, invoice exists but not paid
* Expired: NO invoice exists at all for next period (after 5th)
* No Invoice: No invoice created yet (before 5th)
    """,
    'author': 'Rida Louchachha',
    'maintainer': 'Rida Louchachha',
    'support': 'ridalouchachha2580@gmail.com',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'sale_subscription',
        'account',
        'ma_regional_access',  # For city_ma_id, region_id, system_version_ids on sale.order
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/server_actions.xml',
        'views/sale_order_views.xml',
        'views/subscription_summary_wizard_views.xml',
        'views/res_users_views.xml',
        'data/cron_jobs.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'cm_subscription_alerts/static/src/css/alerts.css',
            'cm_subscription_alerts/static/src/js/subscription_summary.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
