import hashlib
import hmac
import json
import os
from pathlib import Path

from asyncer import asyncify
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from .logic import process_event
from .settings import Settings, log

settings = Settings.load_cached()
app = FastAPI()
THIS_DIR = Path(__file__).parent


@app.get('/')
@app.head('/')
def index():
    index_content = (THIS_DIR / 'index.html').read_text()
    commit = os.getenv('RENDER_GIT_COMMIT', '???')
    index_content = index_content.replace('{{ COMMIT }}', commit).replace('{{ SHORT_COMMIT }}', commit[:7])
    return HTMLResponse(content=index_content)


@app.get('/favicon.ico')
@app.head('/favicon.ico')
def favicon():
    return FileResponse(THIS_DIR / 'favicon.ico')


@app.post('/')
async def webhook(request: Request, x_hub_signature_256: str = Header(default='')):
    request_body = await request.body()

    digest = hmac.new(settings.webhook_secret.get_secret_value(), request_body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(f'sha256={digest}', x_hub_signature_256):
        log(f'Invalid signature: {digest=} {x_hub_signature_256=}')
        raise HTTPException(status_code=403, detail='Invalid signature')

    action_taken, message = await asyncify(process_event)(request_body=request_body, settings=settings)
    message = message if action_taken else f'{message}, no action taken'
    log(message)
    return PlainTextResponse(message, status_code=200 if action_taken else 202)


@app.post('/marketplace/')
async def marketplace_webhook(request: Request, x_hub_signature_256: str = Header(default='')):
    # this endpoint doesn't actually do anything, it's here in case we want to use it in future
    request_body = await request.body()

    secret = settings.marketplace_webhook_secret
    if secret is None:
        raise HTTPException(status_code=403, detail='Marketplace secret not set')

    digest = hmac.new(secret.get_secret_value(), request_body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(f'sha256={digest}', x_hub_signature_256):
        log(f'Invalid marketplace signature: {digest=} {x_hub_signature_256=}')
        raise HTTPException(status_code=403, detail='Invalid marketplace signature')

    body = json.loads(request_body)
    log(f'Marketplace webhook: { json.dumps(body, indent=2)}')
    return PlainTextResponse('ok', status_code=202)
