# Odoo AI / IAP Strategy

## Current goal

Use standard Odoo AI first, and use the local proxy only when deliberately testing a custom OpenAI-compatible replacement.

Standard Odoo AI in Odoo 20 uses:

- `ai.endpoint` for the Odoo AI API base URL.
- `ai.webhook_url` for async completion callbacks.
- `iap.account` service `odoo_ai` for credits and authentication.

## Standard Odoo AI configuration

For normal Odoo AI credits, use:

```text
ai.endpoint = https://ai.api.odoo.com
```

This can also be omitted because Odoo defaults to `https://ai.api.odoo.com`.

For local development, do not rely on:

```text
web.base.url = http://localhost:20069
```

Odoo's cloud AI service cannot call back to `localhost`. Set a public callback URL instead:

```text
ai.webhook_url = https://<public-tunnel-url>
```

## Start ngrok for local Odoo

For database `plane_20`, the local Odoo server is currently on port `20069`.

Start a tunnel:

```bash
ngrok http 20069 --log=stdout
```

Find the public HTTPS URL:

```bash
curl -s http://127.0.0.1:4040/api/tunnels
```

Or read it from the ngrok stdout line like:

```text
started tunnel ... url=https://xxxx.ngrok-free.app
```

Set the callback URL in Odoo:

```bash
psql -d plane_20 -c "
insert into ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
values ('ai.webhook_url', 'https://xxxx.ngrok-free.app', 1, now(), 1, now())
on conflict (key)
do update set value = excluded.value, write_date = now(), write_uid = 1;
"
```

Check the active values:

```bash
psql -d plane_20 -Atc "
select key, value
from ir_config_parameter
where key in ('ai.endpoint', 'ai.webhook_url', 'web.base.url', 'database.is_neutralized', 'database.uuid')
order by key;
"
```

Verify the public tunnel reaches Odoo:

```bash
curl -I -s https://xxxx.ngrok-free.app/web/login | sed -n '1,12p'
```

Expected: an HTTP response from Odoo, usually `303` or `200`.

## Check credits and IAP account

```bash
psql -d plane_20 -P pager=off -c "
select
    a.id,
    s.technical_name,
    s.name,
    a.name,
    left(a.account_token, 8)
        || case when a.account_token like '%+disabled' then '+disabled' else '...' end
        as token_preview,
    a.state,
    a.balance_amount,
    a.warning_threshold
from iap_account a
join iap_service s on s.id = a.service_id
where s.technical_name = 'odoo_ai'
order by a.id desc;
"
```

Healthy standard setup:

```text
technical_name = odoo_ai
state = registered
balance_amount > 0
token does not end with +disabled
```

If `database.is_neutralized = True`, newly created IAP tokens may be disabled.

## Direct sync smoke test against Odoo AI

This checks credits and the official endpoint without using the async chat callback.

```bash
python3 - <<'PY'
import json
import subprocess
import urllib.request
import urllib.error


def psql_scalar(sql):
    return subprocess.check_output(["psql", "-d", "plane_20", "-Atc", sql], text=True).strip()


token = psql_scalar("""
select a.account_token
from iap_account a
join iap_service s on s.id = a.service_id
where s.technical_name = 'odoo_ai'
order by a.id desc
limit 1
""")
dbuuid = psql_scalar("select value from ir_config_parameter where key = 'database.uuid'")

payload = {
    "jsonrpc": "2.0",
    "method": "call",
    "id": "manual-smoke",
    "params": {
        "account_token": token,
        "dbuuid": dbuuid,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Tell me a one sentence joke."}],
            }
        ],
        "instructions": "Answer briefly.",
        "tools": [],
    },
}

request = urllib.request.Request(
    "https://ai.api.odoo.com/api/odoo_ai/1/get_completions_sync",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode())
        print(json.dumps(data, indent=2)[:2000])
except urllib.error.HTTPError as error:
    print(error.code)
    print(error.read().decode(errors="replace")[:2000])
PY
```

If this works but the Odoo sidekick stays on `Thinking`, the likely problem is `ai.webhook_url`, not credits.

## Inspect AI sessions

```bash
psql -d plane_20 -P pager=off -c "
select id, loop_state, request_round, request_round_limit, request_uuid, create_date, write_date, state
from ai_session
order by write_date desc
limit 10;
"
```

```bash
psql -d plane_20 -P pager=off -c "
select ai_session_id, create_date, left(metadata::text, 500) as metadata
from ai_session_event
order by create_date desc
limit 10;
"
```

If sessions have user events but no assistant events, Odoo AI likely submitted the request but did not get a usable callback.

## Stop the custom proxy when testing standard Odoo AI

The local custom proxy listens on `8019` when running. Stop it before testing standard Odoo AI unless `ai.endpoint` deliberately points to it.

Check processes:

```bash
ps -ef | rg 'uvicorn|ngrok|plane_20'
```

Stop a foreground `uvicorn` session with `Ctrl+C`.

Standard Odoo AI should have:

```text
ai.endpoint = https://ai.api.odoo.com
```

Custom proxy testing uses:

```text
ai.endpoint = http://127.0.0.1:8019
```

## Local custom proxy

Run the proxy:

```bash
cd /home/weinni2000/doodba20/odoo/custom/src/ai/ai_open_IAP
ODOO_AI_PROXY_ODOO_DB=plane_20 \
python3 -m uvicorn odoo_ai_proxy.main:app --host 127.0.0.1 --port 8019
```

When `ODOO_AI_PROXY_ODOO_DB` is set, the proxy reads the selected
`ai.connection` from the Odoo database. If no connection is selected, it falls
back to the environment variables below.

Health check:

```bash
curl -s http://127.0.0.1:8019/health
```

Send Odoo AI to the replacement:

```bash
printf "env['ir.config_parameter'].sudo().set_str('ai.endpoint', 'http://127.0.0.1:8019')\nenv.cr.commit()\nprint(env['ir.config_parameter'].sudo().get_str('ai.endpoint'))\n" \
  | /home/weinni2000/venv_312_20/bin/python3 odoo/custom/src/odoo/odoo-bin shell \
      -c odoo_enterprise_20.conf -d plane_20
```

Select which `ai.connection` the replacement uses:

```bash
printf "connection_id = env['ai.connection'].search([('model', '=', 'llama3.1:latest')], limit=1)\nenv['ir.config_parameter'].sudo().set_int('ai.open_iap.connection_id', connection_id.id)\nenv.cr.commit()\nprint(connection_id.display_name, connection_id.id)\n" \
  | /home/weinni2000/venv_312_20/bin/python3 odoo/custom/src/odoo/odoo-bin shell \
      -c odoo_enterprise_20.conf -d plane_20
```

The same selection is available in the Odoo UI:

```text
AI -> AI Connection
```

The list view has a left sidebar registered with:

```text
js_class="ai_connection_list_with_sidebar"
```

Clicking a connection stores its id in:

```text
ai.open_iap.connection_id
```

Send Odoo AI back to the official service:

```bash
printf "env['ir.config_parameter'].sudo().set_str('ai.endpoint', 'https://ai.api.odoo.com')\nenv.cr.commit()\nprint(env['ir.config_parameter'].sudo().get_str('ai.endpoint'))\n" \
  | /home/weinni2000/venv_312_20/bin/python3 odoo/custom/src/odoo/odoo-bin shell \
      -c odoo_enterprise_20.conf -d plane_20
```

Provider environment examples:

```bash
export ODOO_AI_PROXY_BASE_URL="http://localhost:11434/v1"
export ODOO_AI_PROXY_MODEL="llama3.1"
export ODOO_AI_PROXY_API_KEY=""
```

Direct replacement smoke test:

```bash
curl -s http://127.0.0.1:8019/api/odoo_ai/1/get_completions_sync \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "method": "call",
    "id": "smoke",
    "params": {
      "instructions": "Answer briefly.",
      "messages": [
        {
          "role": "user",
          "content": [{"type": "text", "text": "Say hello from the replacement."}]
        }
      ],
      "tools": []
    }
  }'
```

## Replacement logging

All replacement proxy traffic is logged as JSON Lines under:

```text
/home/weinni2000/doodba20/odoo/custom/src/ai/ai_open_IAP/logging
```

The file name is the UTC date, for example:

```text
logging/2026-10-07.jsonl
```

Logged event kinds:

```text
odoo_request
odoo_response
provider_request
provider_response
callback_request
callback_response
```

Tail the latest log:

```bash
find /home/weinni2000/doodba20/odoo/custom/src/ai/ai_open_IAP/logging \
  -maxdepth 1 -type f -printf '%p\n' \
  | sort \
  | tail -1 \
  | xargs -r tail -50
```

The logs intentionally include full request and response payloads, including headers and model payloads. Treat this directory as sensitive and do not commit generated log files.

## Important diagnosis from `plane_20`

On 2026-10-07:

- `ai.endpoint` was already correct: `https://ai.api.odoo.com`.
- The `odoo_ai` IAP account was registered.
- `balance_amount` was `10`.
- Direct sync call to Odoo AI succeeded.
- The UI still stayed on `Thinking` because async chat needed a public callback URL.
- Setting `ai.webhook_url` to an active ngrok HTTPS URL fixed the local-development callback path.
