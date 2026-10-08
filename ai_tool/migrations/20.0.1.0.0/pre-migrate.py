# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)

OLD_MODEL = "ai.tool"
NEW_MODEL = "ai.oca.tool"
OLD_TABLE = "ai_tool"
NEW_TABLE = "ai_oca_tool"

# (table, column) pairs storing a model name
MODEL_NAME_COLUMNS = [
    ("ir_model", "model"),
    ("ir_model_fields", "model"),
    ("ir_model_fields", "relation"),
    ("ir_model_data", "model"),
    ("ir_ui_view", "model"),
    ("ir_act_window", "res_model"),
    ("ir_act_server", "model_name"),
    ("ir_attachment", "res_model"),
    ("mail_message", "model"),
    ("mail_followers", "res_model"),
    ("mail_activity", "res_model"),
]


def _rename_model(cr):
    """Rename ``ai.tool`` into ``ai.oca.tool``.

    Odoo 20.0 Enterprise ships an abstract ``ai.tool`` model in the ``ai``
    module (auto-installed through ``ai_auto_install``). Both definitions
    would replace each other in the registry, so the OCA model is renamed.
    """
    if sql.table_exists(cr, OLD_TABLE) and not sql.table_exists(cr, NEW_TABLE):
        cr.execute(f"ALTER TABLE {OLD_TABLE} RENAME TO {NEW_TABLE}")
        cr.execute(
            f"ALTER SEQUENCE IF EXISTS {OLD_TABLE}_id_seq RENAME TO {NEW_TABLE}_id_seq"
        )
        cr.execute(
            f"ALTER TABLE {NEW_TABLE} ALTER COLUMN id "
            f"SET DEFAULT nextval('{NEW_TABLE}_id_seq'::regclass)"
        )
    for table, column in MODEL_NAME_COLUMNS:
        if sql.column_exists(cr, table, column):
            cr.execute(
                f"UPDATE {table} SET {column} = %s WHERE {column} = %s",
                (NEW_MODEL, OLD_MODEL),
            )
    # Keep the generated xmlids of the model and its fields, otherwise they
    # would be considered obsolete and removed at the end of the update.
    cr.execute(
        """
        UPDATE ir_model_data
           SET name = regexp_replace(name, %s, %s)
         WHERE module = 'ai_tool'
           AND model IN ('ir.model', 'ir.model.fields', 'ir.model.fields.selection')
           AND name ~ %s
        """,
        (
            r"^(model_|field_|selection__)ai_tool(__|$)",
            r"\1ai_oca_tool\2",
            r"^(model_|field_|selection__)ai_tool(__|$)",
        ),
    )


def migrate(cr, version):
    if not version:
        return
    _logger.info("Renaming model %s into %s", OLD_MODEL, NEW_MODEL)
    _rename_model(cr)
