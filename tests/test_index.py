import pytest

from .conftest import Client


@pytest.mark.parametrize(
    'method',
    [
        'get',
        pytest.param('head', marks=[pytest.mark.xfail(reason='Looks like a TestClient bug with the "HEAD" method')]),
    ],
)
def test_index(client: Client, method):
    r = client.request(method, '/')
    assert r.status_code == 200, r.text
    assert r.headers['content-type'] == 'text/html; charset=utf-8'
    if method == 'get':
        assert '<h1>Hooky</h1>' in r.text
        assert '<code>???</code>' in r.text
    else:
        assert r.text == ''


@pytest.mark.parametrize(
    'method',
    [
        'get',
        pytest.param('head', marks=[pytest.mark.xfail(reason='Looks like a TestClient bug with the "HEAD" method')]),
    ],
)
def test_favicon(client: Client, method):
    r = client.request(method, '/favicon.ico')
    assert r.status_code == 200, r.text
    # different on linux ('image/vnd.microsoft.icon') and macos ('image/x-icon')
    assert r.headers['content-type'] in {'image/vnd.microsoft.icon', 'image/x-icon'}
