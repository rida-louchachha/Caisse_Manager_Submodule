# -*- coding: utf-8 -*-
"""
CRM: Per-user stage visibility (Kanban columns) per Sales Team.

- Reads the active Sales Team(s) from context and/or search domain.
- Unions allowed stages across those teams for the current user.
- If the user has no rules for the active team(s), falls back to Odoo defaults.
- If rules exist but contain no stages, Kanban shows no columns (by design).
"""
import logging
from odoo import api, models, fields, _

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    helpdesk_ticket_ids = fields.One2many(
        comodel_name="helpdesk.ticket",
        inverse_name="lead_id",
        string="Helpdesk Tickets",
    )
    helpdesk_ticket_count = fields.Integer(
        string="Helpdesk Tickets Count",
        compute="_compute_helpdesk_ticket_count",
        store=False,
    )
    stage_create_helpdesk_on_enter = fields.Boolean(
        related="stage_id.create_helpdesk_on_enter",
        readonly=True,
        string="Stage Creates Helpdesk"
    )


    @api.depends("helpdesk_ticket_ids")
    def _compute_helpdesk_ticket_count(self):
        for rec in self:
            rec.helpdesk_ticket_count = len(rec.helpdesk_ticket_ids)



    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _rules_for_user_team(self, user, team_id):
        """Return the visibility-rule records for (user, team_id)."""
        Rule = self.env["res.users.crm.stage.rule"]
        return Rule.search([("user_id", "=", user.id), ("team_id", "=", team_id)])

    def _allowed_stage_ids_union(self, user, team_ids):
        """
        Union of allowed stage IDs for (user, each team_id in team_ids).

        Returns:
            set[int]: union of allowed stage ids, possibly empty if rules exist but no stages
            None:     when NO rule exists for any of the provided team_ids
        """
        any_rule = False
        out = set()
        for tid in team_ids:
            rules = self._rules_for_user_team(user, tid)
            if rules:
                any_rule = True
                for r in rules:
                    out.update(r.stage_ids.ids)
        return out if any_rule else None

    def _extract_team_ids_from_domain(self, domain):
        """
        Collect Sales Team IDs referenced in a domain.
        Supports leaves like:
            ('team_id', '=', 3)
            ('team_id', 'in', [1, 2, 3])
        """
        found = set()
        if not domain:
            return found

        def walk(node):
            if isinstance(node, (list, tuple)):
                # Leaf
                if len(node) >= 3 and node[0] == "team_id":
                    op, val = node[1], node[2]
                    if op == "=" and isinstance(val, int):
                        found.add(val)
                    elif op == "in" and isinstance(val, (list, tuple)):
                        found.update(v for v in val if isinstance(v, int))
                else:
                    # Nested groups
                    for it in node:
                        walk(it)

        walk(domain)
        return found

    # -------------------------------------------------------------------------
    # group_expand hook (controls Kanban columns for stage_id)
    # -------------------------------------------------------------------------
    @api.model
    def _read_group_stage_ids(self, stages, domain, *args, **kwargs):
        """
        Compatible with both core signatures:
            (stages, domain)  and  (stages, domain, order, ...)

        Steps:
          1) Ask super() for default stage columns.
          2) Detect active team(s) from context and domain; if none, use teams the
             user has rules for (so “All teams” still enforces user choices).
          3) Filter the columns to the union of allowed stages across those teams.
        """
        # 1) Default columns from core
        result = super()._read_group_stage_ids(stages, domain, *args, **kwargs)

        user = self.env.user

        # 2) Resolve active team(s)
        #    a) from context (menus often set one of these)
        ctx_team_id = self.env.context.get("default_team_id") or self.env.context.get("team_id")
        team_ids = {ctx_team_id} if ctx_team_id else set()
        #    b) from the current search domain (e.g. "Mon pipeline" => team_id in [...])
        team_ids |= self._extract_team_ids_from_domain(domain)
        #    c) fallback: all teams the user has rules for
        if not team_ids:
            rule_obj = self.env["res.users.crm.stage.rule"].sudo()
            team_ids = set(rule_obj.search([("user_id", "=", user.id)]).mapped("team_id.id"))

        # If we still don't have any team ids, keep default columns
        if not team_ids:
            return result

        # 3) Union allowed stages across detected teams
        allowed = self._allowed_stage_ids_union(user, team_ids)
        if allowed is None:
            # User has no rules for these teams -> keep default behavior
            return result

        # allowed may be an empty set if rules exist but contain no stages -> show no columns
        allowed = set(allowed)
        return result.filtered(lambda s: s.id in allowed)

    # -------------------------------------------------------------------------
    # Optional: limit stage picker in the form when team changes
    # -------------------------------------------------------------------------
    @api.onchange("team_id")
    def _onchange_team_id_limit_stage_domain(self):
        team = self.team_id
        if not team:
            return
        allowed = self._allowed_stage_ids_union(self.env.user, {team.id})
        if allowed is None:
            return
        return {"domain": {"stage_id": [("id", "in", list(allowed))]}}

        # ---------------- auto-create ticket when entering a flagged stage --------

    def write(self, vals):
        """When stage_id changes to a stage flagged with create_helpdesk_on_enter, create a ticket
        if none is open for this lead (avoid duplicates)."""
        stage_changed = "stage_id" in vals
        # Pre-fetch stage data to avoid multiple queries
        stage_by_id = {}
        if stage_changed:
            stage_ids = set(vals.get("stage_id") for _ in self if vals.get("stage_id"))
            if stage_ids:
                stage_by_id = {
                    s.id: s
                    for s in self.env["crm.stage"].browse(list(stage_ids))
                }

        res = super().write(vals)

        if stage_changed and vals.get("stage_id"):
            for lead in self:
                stage = stage_by_id.get(vals["stage_id"])
                if not stage or not stage.create_helpdesk_on_enter:
                    continue

                # Avoid duplicates: if there is any not-done ticket linked, skip creation
                existing = lead.helpdesk_ticket_ids.filtered(lambda t: t.stage_id and not t.stage_id.fold)
                if existing:
                    _logger.info("Skip creating ticket for lead %s: open ticket already exists", lead.id)
                    continue

                # Compose basic ticket values
                vals_ticket = {
                    "name": _("Ticket for Lead: %s") % (lead.name or _("No title")),
                    "lead_id": lead.id,  # inverse below
                    "partner_id": lead.partner_id.id or False,
                    "email": lead.email_from or False,
                    "description": lead.description or "",
                    "team_id": stage.default_helpdesk_team_id.id or False,
                    # You can map priority, tags, etc. here if desired
                }
                ticket = self.env["helpdesk.ticket"].sudo().create(vals_ticket)

                # Post a message on lead & ticket for traceability
                lead.message_post(body=_("Helpdesk ticket created: %s") % (ticket.display_name,))
                ticket.message_post(body=_("Created from CRM Lead: %s") % (lead.display_name,))

        return res

        # ---- smart button handler -----------------------------------------------

    def action_open_helpdesk_tickets(self):
        self.ensure_one()
        # If exactly one ticket, open form; else open list filtered by this lead.
        if len(self.helpdesk_ticket_ids) == 1:
            base_form = self.env.ref("helpdesk.helpdesk_ticket_view_form").id
            return {
                "type": "ir.actions.act_window",
                "name": _("Helpdesk Ticket"),
                "res_model": "helpdesk.ticket",
                "view_mode": "form",
                "views": [(base_form, "form")],
                "view_id": base_form,
                "res_id": self.helpdesk_ticket_ids.id,
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Helpdesk Tickets"),
            "res_model": "helpdesk.ticket",
            "view_mode": "list,form",
            "domain": [("lead_id", "=", self.id)],
            "target": "current",
        }
        # ---- manual create button -----------------------------------------------

    def action_create_helpdesk_ticket(self):
        self.ensure_one()
        # Pick default team from current stage if available
        team_id = self.stage_id.default_helpdesk_team_id.id if self.stage_id else False
        ticket = self.env["helpdesk.ticket"].sudo().create({
            "name": _("Ticket for Lead: %s") % (self.name or _("No title")),
            "lead_id": self.id,
            "partner_id": self.partner_id.id or False,
            "email_cc": self.email_from or False,
            "description": self.description or "",
            "team_id": team_id,
        })
        self.message_post(body=_("Helpdesk ticket created: %s") % ticket.display_name)
        ticket.message_post(body=_("Created from CRM Lead: %s") % self.display_name)
        return {
            "type": "ir.actions.act_window",
            "res_model": "helpdesk.ticket",
            "res_id": ticket.id,
            "view_mode": "form",
            "target": "current",
        }

