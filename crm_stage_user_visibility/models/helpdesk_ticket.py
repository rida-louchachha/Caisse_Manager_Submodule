# -*- coding: utf-8 -*-
from odoo import fields, models

class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    lead_id = fields.Many2one(
        comodel_name="crm.lead",
        string="CRM Lead",
        index=True,
        ondelete="set null",
        help="Lead from which this ticket was created or to which it is related.",
    )
