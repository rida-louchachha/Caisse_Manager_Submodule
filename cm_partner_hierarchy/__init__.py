# -*- coding: utf-8 -*-

from . import models
from . import wizard


def _recompute_hierarchy_fields(env):
    """Force recomputation of hierarchy fields on all partners with partner_level."""
    partners = env['res.partner'].sudo().search([
        ('partner_level', 'in', ('client', 'franchise', 'company'))
    ])
    if partners:
        # Invalidate the computed fields and trigger recomputation
        partners._compute_hierarchy_fields()
