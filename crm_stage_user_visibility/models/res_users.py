# -*- coding: utf-8 -*-
"""
Per-user, per-team CRM stage visibility rules.

Adds:
- On users: One2many `crm_stage_rule_ids` for configuring allowed CRM stages.
- Model `res.users.crm.stage.rule`: (user, team) + Many2many of allowed `crm.stage`.

Notes:
- The `stage_ids` domain allows stages that are global (team_id = False) or
  belong to the selected Sales Team.
- If a user has no rules for a team, the default CRM behavior applies
  (filtering logic implemented in models/crm_lead.py).
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    crm_stage_rule_ids = fields.One2many(
        comodel_name="res.users.crm.stage.rule",
        inverse_name="user_id",
        string="CRM Stage Visibility Rules",
        help=(
            "Per Sales Team, choose which CRM stages this user sees in the pipeline. "
            "If no rule exists for a team, the default Odoo behavior applies."
        ),
    )


class ResUsersCrmStageRule(models.Model):
    _name = "res.users.crm.stage.rule"
    _description = "User CRM Stage Visibility Rule"
    _rec_name = "display_name"
    _order = "team_id, id"

    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
        ondelete="cascade",
        index=True,
    )

    team_id = fields.Many2one(
        comodel_name="crm.team",
        string="Sales Team",
        required=True,
        ondelete="cascade",
        index=True,
        help="Pipeline (Sales Team) to which this rule applies.",
    )

    stage_ids = fields.Many2many(
        comodel_name="crm.stage",
        relation="rel_user_rule_crm_stage",
        column1="rule_id",
        column2="stage_id",
        string="Allowed Stages",
        # Allow stages that are either global (team_id=False) or belong to the selected team
        domain="[('team_id', 'in', [False, team_id])]",
        help="Stages visible to the user within this Sales Team's pipeline.",
    )

    display_name = fields.Char(
        string="Rule",
        compute="_compute_display_name",
        store=False,
    )

    # -------------------- Computed fields --------------------
    @api.depends("team_id", "stage_ids")
    def _compute_display_name(self):
        for rec in self:
            stage_names = ", ".join(rec.stage_ids.mapped("name")) if rec.stage_ids else "<no stages selected>"
            team_name = rec.team_id.name or "No Team"
            rec.display_name = f"{team_name}: {stage_names}"

    # -------------------- Safety / UX --------------------
    @api.constrains("team_id", "stage_ids")
    def _check_stage_team(self):
        """
        Prevent saving stages that don't match the selected Sales Team
        (global stages are allowed).
        """
        for rec in self:
            bad = rec.stage_ids.filtered(lambda s: s.team_id and s.team_id != rec.team_id)
            if bad:
                raise ValidationError(
                    _("Some stages don't belong to the selected Sales Team: %s")
                    % ", ".join(bad.mapped("name"))
                )

    @api.onchange("team_id")
    def _onchange_team_id_trim_stages(self):
        """
        If the team changes, drop stages that no longer match the new team.
        """
        for rec in self:
            if rec.team_id and rec.stage_ids:
                rec.stage_ids = rec.stage_ids.filtered(
                    lambda s: not s.team_id or s.team_id == rec.team_id
                )
