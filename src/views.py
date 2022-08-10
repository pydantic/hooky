import hashlib
import hmac
import os
from pathlib import Path

from asyncer import asyncify
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from .logic import Event, process_event
from .settings import Settings, log

settings = Settings()
app = FastAPI()
THIS_DIR = Path(__file__).parent


@app.get('/')
def index():
    index_content = (THIS_DIR / 'index.html').read_text()
    commit = os.getenv('RENDER_GIT_COMMIT', '???')
    index_content = index_content.replace('{{ COMMIT }}', commit).replace('{{ SHORT_COMMIT }}', commit[:7])
    return HTMLResponse(content=index_content)


@app.get('/favicon.ico')
def favicon():
    return FileResponse(THIS_DIR / 'favicon.ico')


@app.post('/')
async def webhook(request: Request, event: Event, x_hub_signature_256: str = Header(default='')):
    request_body = await request.body()

    digest = hmac.new(settings.webhook_secret.get_secret_value(), request_body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(f'sha256={digest}', x_hub_signature_256):
        log(f'{digest=} {x_hub_signature_256=}')
        raise HTTPException(status_code=403, detail='Invalid signature')

    action_taken, message = await asyncify(process_event)(event=event, settings=settings)
    message = message if action_taken else f'{message}, no action taken'
    log(message)
    return PlainTextResponse(message, status_code=200 if action_taken else 202)
