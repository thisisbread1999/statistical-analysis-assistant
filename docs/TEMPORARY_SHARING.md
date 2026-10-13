# Temporary HTTPS sharing

The UI can be shared through a Cloudflare Quick Tunnel while its Python backend and
models continue to run on the host computer. This is a temporary course-demo entry
point, not a permanently hosted server. The computer, UI process and tunnel must stay
running. A restarted Quick Tunnel normally supplies a new hostname.

## Start a new trial

1. Download `cloudflared` from the official Cloudflare release. In a separate terminal,
   run `cloudflared tunnel --url http://127.0.0.1:8766 --protocol http2 --no-autoupdate`.
   Read the HTTPS `trycloudflare.com` origin printed by the tool.
2. Generate a random access code in an ignored local file, using a Python environment
   with this project's requirements installed:

```python
from pathlib import Path
import secrets
path = Path("artifacts/runtime/share-code.txt")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(secrets.token_urlsafe(18), encoding="utf-8")
```

3. Start a dedicated, fresh UI workspace with that exact HTTPS origin:

```powershell
python ui_server.py --port 8766 --public-origin https://YOUR-HOST.trycloudflare.com --share-token-file artifacts/runtime/share-code.txt --runtime-dir artifacts/runtime/shared-ui
```

4. Share the HTTPS URL and access code with the intended testers. They enter the code
   on the login page. Start with Mock for a quick workflow demonstration; Real calls
   the configured models from the host computer. Local Ollama models must be running
   and downloaded. API configurations would instead use their configured providers.

Run `python ui_server.py --port 8765` without sharing options for the usual local UI.
The sharing process still binds only to loopback. It accepts only the configured public
Host and exact HTTPS Origin, so no router port forwarding or Ollama port exposure is
needed. Supplying a local Host to the sharing instance is rejected; it cannot bypass
login. An ordinary local-only instance retains its existing behavior.

## Access and data lifetime

The shared code is submitted as a form body, never as part of the URL. Each successful
login gets a separate random HttpOnly, Secure, SameSite=Strict cookie, valid for four
hours. Jobs and analysis sessions belong to that authenticated browser. Another browser
cannot read or change them even if it knows their IDs. Existing session/job/upload limits
and the single analysis worker remain in place. Share with a small course-testing group.

Uploads and audit files are stored on the host under ignored `artifacts/runtime/`.
Stopping the UI clears in-process sessions; it does not delete uploaded or audit files.
The code file, cookies and tunnel logs must not be committed. Stop both terminal processes
with Ctrl+C when the trial ends. Background trials started by Codex can be stopped from
the same chat; closing a browser tab alone does not stop the service.

## Verified trial

On 2026-10-13, 50 focused UI tests passed. An actual public HTTPS trial checked the login
page, unauthenticated API rejection, exact Origin, cross-browser job/follow-up isolation
and an 80-record synthetic Welch analysis in explicitly labelled Mock mode. The local
Ollama service and both configured models were available. This trial did not evaluate
live-model semantic accuracy. See `artifacts/verification/ui_tunnel_smoke.json`.

Sources: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
and [official cloudflared releases](https://github.com/cloudflare/cloudflared/releases).
