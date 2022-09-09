import hashlib
import hmac

from src.settings import Settings

from .conftest import Client


def test_auth_ok_no_data(client: Client, settings: Settings):
    request_body = b'{}'
    digest = hmac.new(settings.marketplace_webhook_secret.get_secret_value(), request_body, hashlib.sha256).hexdigest()
    r = client.post('/marketplace/', data=request_body, headers={'x-hub-signature-256': f'sha256={digest}'})
    assert r.status_code == 202, r.text
    assert r.text == 'ok'


def test_auth_fails_no_header(client: Client, settings: Settings):
    request_body = b'{}'
    r = client.post('/marketplace/', data=request_body)
    assert r.status_code == 403, r.text
    assert r.json() == {'detail': 'Invalid marketplace signature'}


def test_auth_fails_wrong_header(client: Client, settings: Settings):
    request_body = b'{}'
    r = client.post('/marketplace/', data=request_body, headers={'x-hub-signature-256': 'sha256=foobar'})
    assert r.status_code == 403, r.text
    assert r.json() == {'detail': 'Invalid marketplace signature'}


def test_not_set(client: Client, settings: Settings):
    marketplace_webhook_secret = settings.marketplace_webhook_secret
    settings.marketplace_webhook_secret = None
    try:
        request_body = b'{}'
        r = client.post('/marketplace/', data=request_body, headers={'x-hub-signature-256': 'sha256=foobar'})
        assert r.status_code == 403, r.text
        assert r.json() == {'detail': 'Marketplace secret not set'}
    finally:
        settings.marketplace_webhook_secret = marketplace_webhook_secret
