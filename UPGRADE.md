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
* `upgrade_code` walks the **current working directory** as well as the
  addons paths, so `owl3-migration.py` must only be invoked from inside the
  module directory being migrated. Running it from an Odoo checkout rewrites
  the core JS/XML sources (`addons/*/static/src/**`) and produces broken
  files (e.g. `addons/web/static/src/search/action_hook.js` ends up with the
  same `const { useEnv } = ...` import twice, which makes
  `web.assets_unit_tests` fail to parse and turns every JS unit test red).
  A contaminated checkout was reverted to `HEAD`; the removed diff is kept in
  `/home/weinni2000/odev/core-dirty-backup-20261007/`.

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

## ai_oca_bridge

### Technical changes

| Change | Why | Odoo source |
| --- | --- | --- |
| `ir.model.access.csv` + `ir.rule.xml` -> `ir.access.csv` | `ir.model.access` and `ir.rule` are merged into `ir.access` | odoo/odoo@77c17e7111c18fffe06fea9b9149cc6d3119e893 (odoo/odoo#166359) |
| `get_param()` -> typed `get_str()` on `ir.config_parameter` | `get_param`/`set_param` were removed | odoo/odoo@a4f2879697a7d5d016094e5f60e88e4bf0f10609 |
| Owl templates rewritten with the Owl 3 syntax (`t-esc`/`t-out`, `t-foreach` scoping, `props` -> `useProps`) | Owl 3 replaced Owl 2 | odoo/odoo@44f50381c39b84e13c0bc296c3a04e560afd0313 (`upgrade_code: add owl3 migration tooling`) |
| Chatter AI menu re-imported from `@mail/chatter/web_portal_project/chatter` | the portal chatter components moved out of `mail/static/src/chatter` | odoo/odoo@058c4ab12d083b753191ec859205a024e11afc62 |
| The owl2 `makeTestEnv` wrapper in the hoot tests is dropped; the suite now filters by the module name injected by the runner | `WebSuite.test_unit_desktop`/`MobileWebSuite.test_unit_mobile` became parameterised, and the JS tests are selected from `web.assets_unit_tests` | odoo/odoo@898af7dd9b1303426ab37d8d643dc128620a5277, odoo/odoo@8d210fc9e118ccaa04808ce36ec268affb682556 |
| Fake test models unload through `transaction.will_change_registry()` | setting `registry.registry_invalidated` no longer exists; the registry rebuild is now signalled on the transaction | odoo/odoo@9fca3bea4427 (`[IMP] orm: link signaling to transaction lifecycle`) |

### Functional test scenarios

1. Open a partner form: the AI cog menu shows the configured bridges.
2. Create a record on a bridged model: an `ai.bridge.execution` is logged and
   the bridge endpoint receives the payload.
3. `test_mixin.py` registers and unregisters its fake models without leaking
   them into the next test (registry rebuild asserted by the runners).
4. JS unit tests (`WebSuite`/`MobileWebSuite`) run green, including the two
   chatter tests shipped in `static/tests`.

## ai_connection

### Technical changes

| Change | Why | Odoo source |
| --- | --- | --- |
| `ir.model.access.csv` -> `ir.access.csv` | `ir.model.access` and `ir.rule` are merged into `ir.access` | odoo/odoo@77c17e7111c18fffe06fea9b9149cc6d3119e893 (odoo/odoo#166359) |
| `attachment.datas.decode("utf-8")` -> `attachment.raw.to_base64()` | `ir.attachment.datas` was removed; `raw` is the only content field and `BinaryValue.to_base64()` returns the same base64 payload | odoo/odoo@7662537c878ffe58ed5c7248e4114062c333312b (odoo/odoo#245916) |
| Attachment test creates the file with `raw` bytes | `create()` silently drops a `datas` key (it only logs a warning), so the attachment was empty | odoo/odoo@7662537c878ffe58ed5c7248e4114062c333312b |

### Functional test scenarios

1. Settings > Technical > AI > Connections: the `kind` selection is populated
   by the installed connector modules.
2. `_run(prompt)` returns the assistant answer and the iteration count.
3. `_run(attachments=...)` sends the file to the AI endpoint; the demo client
   still base64-decodes the payload and answers about the file content.

## ai_oca_mcp

### Technical changes

| Change | Why | Odoo source |
| --- | --- | --- |
| `ir.model.access.csv` -> `ir.access.csv` | `ir.model.access` and `ir.rule` are merged into `ir.access` | odoo/odoo@77c17e7111c18fffe06fea9b9149cc6d3119e893 (odoo/odoo#166359) |
| `tool_ids` points to `ai.oca.tool` | the OCA model was renamed to avoid the clash with the Enterprise `ai.tool` | (see ai_tool) |
| `env.registry.clear_cache()` -> `env.transaction.invalidate_ormcache()` and `tools.ormcache` -> `api.ormcache` | the ORM cache is owned by the transaction since 20.0 | odoo/odoo@2e256040eed3, odoo/odoo@b450601c632c |
| `get_formview_action()` -> `get_record_default_action()` | the method was renamed; the returned act_window action has the same shape | odoo/odoo@a7e2e0007089661f91e119ac314d18f5726ea964 |
| `get_param()` -> `get_str()` in `_compute_url` | `get_param`/`set_param` were removed | odoo/odoo@a4f2879697a7d5d016094e5f60e88e4bf0f10609 |

### Functional test scenarios

1. Create an MCP server, generate an access key from the wizard and use the
   returned action to reopen the key form.
2. `POST /mcp/<key>` with `tools/list` returns the generic tools of the server.
3. `POST /mcp/<key>` with `tools/call` executes the tool and logs the exchange
   in `mcp.server.log` (including the error path for an unknown tool).
4. An expired key is rejected, and expiring a key invalidates the ormcache.

## Validation

Fresh database (`odev create -f -V 20.0 <db> -i base`) then
`odev test -V 20.0 <db> -i <module> -t "/<module>"` for every module:

| Module | Result |
| --- | --- |
| ai_tool | 0 failed, 0 error(s) of 8 tests |
| ai_oca_bridge | 0 failed, 0 error(s) of 31 tests |
| ai_connection | 0 failed, 0 error(s) of 9 tests |
| ai_oca_mcp | 0 failed, 0 error(s) of 11 tests |
