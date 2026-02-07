# -*- coding: utf-8 -*-
{
    'name': 'CM Partner Hierarchy',
    'version': '18.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Client / Franchise / Company hierarchy for partners with revenue reporting',
    'description': """
CM Partner Hierarchy
====================

This module provides a 3-level partner hierarchy structure:

Client (Account / Group)
 └── Franchise (one or many)
      └── Company / Store (one or many)

Features:
---------
* **Partner Levels**: Classify partners as Client, Franchise, or Company
* **Computed Fields**: Automatic client_id and franchise_id based on hierarchy
* **Classification Wizard**: Auto-assign levels based on existing parent structure
* **Subscription Integration**: Link subscriptions to company with client/franchise tracking
* **Revenue Analysis**: Dashboard with Total/Subscription/Non-subscription revenue
* **Search & Grouping**: Filter and group by Client, Franchise, Company, City, Region
    """,
    'author': 'Rida Louchachha',
    'maintainer': 'Rida Louchachha',
    'support': 'ridalouchachha2580@gmail.com',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'contacts',
        'sale',
        'sale_subscription',
        'account',
        'ma_regional_access',  # For region_id and city_ma_id fields
        'cm_subscription_alerts',  # For subscription payment tracking fields
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/partner_classification_wizard_views.xml',
        'wizard/partner_resume_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/partner_hierarchy_views.xml',
        'views/revenue_analysis_views.xml',
        'data/server_actions.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'cm_partner_hierarchy/static/src/js/hierarchy_list_renderer.js',
            'cm_partner_hierarchy/static/src/xml/hierarchy_list_renderer.xml',
            'cm_partner_hierarchy/static/src/scss/hierarchy_list.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': '_recompute_hierarchy_fields',
}
