import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.ai_private.client import AiClientDeepseek

from ._const import IMAGE_MODELS, MODELS_BY_KIND

_logger = logging.getLogger(__name__)

OPEN_IAP_CONNECTION_PARAM = "ai.open_iap.connection_id"
# Where the local proxy listens, and the URL it calls back into Odoo with.
OPEN_IAP_PROXY_ENDPOINT_PARAM = "ai.open_iap.proxy_endpoint"
OPEN_IAP_PROXY_WEBHOOK_PARAM = "ai.open_iap.proxy_webhook_url"
# Optional public URL (e.g. ngrok) Odoo's IAP servers can call back into.
OPEN_IAP_STANDARD_WEBHOOK_PARAM = "ai.open_iap.standard_webhook_url"
OPEN_IAP_PROXY_DEFAULT_ENDPOINT = "http://127.0.0.1:8019"
AI_ENDPOINT_PARAM = "ai.endpoint"
# Mirrors DEFAULT_ODOO_AI_ENDPOINT of the enterprise "ai" module.
ODOO_AI_DEFAULT_ENDPOINT = "https://ai.api.odoo.com"
AI_WEBHOOK_PARAM = "ai.webhook_url"
ODOO_AI_SERVICE = "odoo_ai"
MODEL_SELECTION = [option for options in MODELS_BY_KIND.values() for option in options]


class AiConnection(models.Model):
    _inherit = "ai.connection"

    kind = fields.Selection(
        selection_add=[
            ("gemini", "Gemini"),
            ("openai_compatible", "OpenAI Compatible"),
        ],
        ondelete={"gemini": "cascade", "openai_compatible": "cascade"},
    )
    # Picks "model" from the known provider models (Claude, DeepSeek).
    model_choice = fields.Selection(
        selection=MODEL_SELECTION,
        string="Model",
        compute="_compute_model_choice",
        inverse="_inverse_model_choice",
        groups="base.group_system",
    )
    # Read by the local IAP proxy to decide whether images are forwarded.
    supports_images = fields.Boolean(
        compute="_compute_supports_images",
        store=True,
    )

    @api.depends("kind", "model")
    def _compute_model_choice(self):
        for record in self:
            options = dict(MODELS_BY_KIND.get(record.kind, []))
            record.model_choice = record.model if record.model in options else False

    def _inverse_model_choice(self):
        for record in self:
            if record.model_choice:
                record.model = record.model_choice

    @api.depends("kind", "model")
    def _compute_supports_images(self):
        for record in self:
            record.supports_images = record.sudo().model in IMAGE_MODELS

    @api.constrains("kind", "model")
    def _check_model_matches_kind(self):
        for record in self:
            options = dict(MODELS_BY_KIND.get(record.kind, []))
            model = record.sudo().model
            if options and model and model not in options:
                message = self.env._(
                    "Model %(model)s is not available for %(kind)s connections."
                )
                message = message % {"model": model, "kind": record.kind}
                raise ValidationError(message)

    def _get_client_openai_compatible(self, tools):
        return AiClientDeepseek(self, tools)

    def _get_client_gemini(self, tools):
        # Gemini is called through Google's OpenAI-compatible endpoint.
        return AiClientDeepseek(self, tools)

    def action_open_connection(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def _check_open_iap_connection_access(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                self.env._(
                    "Only administrators can change the IAP replacement connection."
                )
            )

    def _get_kind_labels(self):
        return dict(self._fields["kind"]._description_selection(self.env))

    def _format_open_iap_connection(self):
        self.ensure_one()
        kind_labels = self._get_kind_labels()
        return {
            "id": self.id,
            "name": self.display_name,
            "kind": self.kind,
            "kind_label": kind_labels.get(self.kind, self.kind),
            "model": self.sudo().model,
            "supports_images": self.supports_images,
            "url": self.sudo().url,
            "active": self.active,
        }

    @api.model
    def get_open_iap_connection_selection(self):
        self._check_open_iap_connection_access()
        selected_connection_ref = (
            self.env["ir.config_parameter"].sudo().get_int(OPEN_IAP_CONNECTION_PARAM, 0)
        )
        connection_ids = self.search([("active", "=", True)], order="name, id")
        param_model = self.env["ir.config_parameter"].sudo()
        return {
            "selected_connection_id": selected_connection_ref or False,
            # Effective values, including the fallbacks the "ai" module applies.
            "endpoint": param_model.get_str(AI_ENDPOINT_PARAM)
            or ODOO_AI_DEFAULT_ENDPOINT,
            "webhook_url": param_model.get_str(AI_WEBHOOK_PARAM) or self.get_base_url(),
            "connections": [
                connection_id._format_open_iap_connection()
                for connection_id in connection_ids
            ],
        }

    @api.model
    def set_open_iap_connection(self, connection_ref=False):
        """Select a replacement connection, or the standard Odoo IAP when empty."""
        self._check_open_iap_connection_access()
        connection_id = self.browse(connection_ref).exists() if connection_ref else self
        if connection_ref and not connection_id:
            raise UserError(self.env._("The selected AI connection no longer exists."))
        param_model = self.env["ir.config_parameter"].sudo()
        if connection_id:
            param_model.set_int(OPEN_IAP_CONNECTION_PARAM, connection_id.id)
            self._set_or_clear_param(
                AI_ENDPOINT_PARAM,
                param_model.get_str(OPEN_IAP_PROXY_ENDPOINT_PARAM)
                or OPEN_IAP_PROXY_DEFAULT_ENDPOINT,
            )
            self._set_or_clear_param(
                AI_WEBHOOK_PARAM,
                param_model.get_str(OPEN_IAP_PROXY_WEBHOOK_PARAM)
                or self.get_base_url(),
            )
        else:
            self._set_or_clear_param(OPEN_IAP_CONNECTION_PARAM, False)
            # Without ai.endpoint, Odoo falls back to its own IAP server.
            self._set_or_clear_param(AI_ENDPOINT_PARAM, False)
            self._set_or_clear_param(
                AI_WEBHOOK_PARAM, param_model.get_str(OPEN_IAP_STANDARD_WEBHOOK_PARAM)
            )
        return self.get_open_iap_connection_selection()

    @api.model
    def _set_or_clear_param(self, key, value):
        param_model = self.env["ir.config_parameter"].sudo()
        if value:
            param_model.set_str(key, value)
        else:
            param_model.search([("key", "=", key)]).unlink()

    @api.model
    def get_open_iap_credits(self):
        """Return the standard Odoo AI IAP balance; -1 when IAP is unreachable."""
        self._check_open_iap_connection_access()
        account_model = self.env["iap.account"].sudo()
        account_id = account_model.get(ODOO_AI_SERVICE, force_create=False)
        if not account_id:
            return {"has_account": False, "credit": 0, "buy_url": False}
        credit = account_model.get_credits(ODOO_AI_SERVICE)
        if credit == -1:
            _logger.info("Could not fetch the %s IAP balance.", ODOO_AI_SERVICE)
        return {
            "has_account": True,
            "credit": credit,
            "buy_url": account_model.get_credits_url(ODOO_AI_SERVICE),
        }
