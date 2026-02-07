# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PartnerClassificationWizard(models.TransientModel):
    """Wizard to auto-assign partner levels based on hierarchy."""
    _name = 'partner.classification.wizard'
    _description = 'Partner Classification Wizard'

    mode = fields.Selection([
        ('all', 'All Partners (without level)'),
        ('selected', 'Selected Partners Only'),
    ], string='Apply To', default='all', required=True)
    
    partner_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Partners to Classify',
        help='Leave empty to process all partners without a level assigned'
    )
    
    preview_client_count = fields.Integer(
        string='Will be assigned as Client',
        compute='_compute_preview'
    )
    preview_franchise_count = fields.Integer(
        string='Will be assigned as Franchise',
        compute='_compute_preview'
    )
    preview_company_count = fields.Integer(
        string='Will be assigned as Company',
        compute='_compute_preview'
    )
    preview_total = fields.Integer(
        string='Total to Process',
        compute='_compute_preview'
    )

    @api.depends('mode', 'partner_ids')
    def _compute_preview(self):
        """Preview how many partners will be assigned to each level."""
        for wizard in self:
            domain = [('partner_level', '=', False)]
            if wizard.mode == 'selected' and wizard.partner_ids:
                domain.append(('id', 'in', wizard.partner_ids.ids))
            
            partners = self.env['res.partner'].search(domain)
            
            client_count = 0
            franchise_count = 0
            company_count = 0
            
            for partner in partners:
                if not partner.parent_id:
                    client_count += 1
                elif partner.parent_id.partner_level == 'client':
                    franchise_count += 1
                elif partner.parent_id.partner_level == 'franchise':
                    company_count += 1
            
            wizard.preview_client_count = client_count
            wizard.preview_franchise_count = franchise_count
            wizard.preview_company_count = company_count
            wizard.preview_total = client_count + franchise_count + company_count

    def action_classify(self):
        """Execute automatic partner classification."""
        self.ensure_one()
        
        partner_ids = None
        if self.mode == 'selected' and self.partner_ids:
            partner_ids = self.partner_ids.ids
        
        counts = self.env['res.partner'].auto_assign_partner_levels(partner_ids)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Partner Classification Complete',
                'message': f"Assigned levels:\n• {counts['client']} Clients\n• {counts['franchise']} Franchises\n• {counts['company']} Companies",
                'type': 'success',
                'sticky': True,
            }
        }
    
    def action_preview(self):
        """Refresh preview."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
