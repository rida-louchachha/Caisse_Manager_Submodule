# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CrmStage(models.Model):
    _inherit = "crm.stage"

    create_helpdesk_on_enter = fields.Boolean(
        string="Create Helpdesk Ticket on Enter",
        help="If enabled, moving a lead to this stage will automatically create a Helpdesk ticket.",
    )
    default_helpdesk_team_id = fields.Many2one(
        comodel_name="helpdesk.team",
        string="Default Helpdesk Team",
        help="Team used when creating tickets from leads that enter this stage.",
    )
