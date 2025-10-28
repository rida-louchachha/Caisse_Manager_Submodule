# -*- coding: utf-8 -*-
{
    "name": "CRM – Stage Visibility per User",
    "summary": "Per-user whitelist of visible CRM stages per Sales Team (pipeline).",
    "description": """
Control which CRM stages (Kanban columns) each user can see, per Sales Team.

Key features:
- User-level rules: (User × Sales Team) → Allowed Stages (global or team-bound)
- Kanban columns filtered via group_expand override
- Form stage picker constrained on team change
- Safe defaults: if no rule exists for a team, Odoo’s behavior applies
""",
    "version": "18.0.1.0.0",
    "category": "Sales/CRM",
    "author": "RIDA LOUCHACHHA <ridalouchachha2580@gmail.com>",
    "license": "LGPL-3",
    "depends": ["crm", "helpdesk", "helpdesk_sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_users_views.xml",
        "views/crm_stage_views.xml",
        "views/crm_lead_views.xml",
    ],
    "images": ['static/description/icon.png'],
    "assets": {},
    "application": False,
    "installable": True,
    "auto_install": False,
}
