# Upgrade 19.0 -> 20.0

## Tooling notes

* `odev upgrade-code --from 19.0 --to 20.0` crashes (`TypeError: argument of
  type 'NoneType' is not iterable`) because `19.4-00-ir-access` deletes
  `ir.model.access.csv` and `20.0-00-search-date-filters` then reads the
  deleted file. Workaround: run `--from 19.0 --to 19.5` then
  `--from 20.0 --to 20.0`.
* `19.4-00-ir-access` ignores `--glob` (it converts all modules at once) and
  writes `model_<xmlid>` instead of the model name in `ir.access.csv` for
  models it cannot resolve; fix them by hand (`model_id` holds the model
  name, e.g. `ai.bridge`).
* The `/home/weinni2000/odoo/repositories/odoo/upgrade` directory is empty,
  so no official migration script could be consulted.

## ai_tool

### Technical changes

| Change | Why | Odoo source |
| --- | --- | --- |
| `ir.model.access.csv` -> `ir.access.csv` | `ir.model.access` and `ir.rule` are merged into `ir.access` | odoo/odoo@77c17e7111c18fffe06fea9b9149cc6d3119e893 (odoo/odoo#166359) |
| Model `ai.tool` renamed to `ai.oca.tool` (pre-migration renames table, sequence, model references and generated xmlids) | Enterprise `ai` (auto-installed by `ai_auto_install`) defines an abstract `ai.tool`; same `_name` without `_inherit` replaces the other definition in the registry | odoo/enterprise@ac2ff3b34d394565b3ff0c55a59e78e5abfed1af |

### Functional test scenarios

1. Settings > Technical > AI > AI Tool: list shows `get_date` and
   `post_message`.
2. On a DB upgraded from 19.0, existing tools keep their id and links
   (e.g. MCP servers tools).
3. With Enterprise `ai` installed, both the AI app and the OCA tools work.
