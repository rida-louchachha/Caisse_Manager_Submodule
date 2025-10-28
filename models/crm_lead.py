# -*- coding: utf-8 -*-
"""
CRM: Per-user stage visibility (Kanban columns) per Sales Team.

- Reads the active Sales Team(s) from context and/or search domain.
- Unions allowed stages across those teams for the current user.
- If the user has no rules for the active team(s), falls back to Odoo defaults.
- If rules exist but contain no stages, Kanban shows no columns (by design).
"""
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

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
