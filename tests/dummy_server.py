from aiohttp import web
from aiohttp.abc import Request
from aiohttp.web_response import Response, json_response


async def repo_details(request: Request) -> Response:
    github_base_url = request.app['dynamic']['github_base_url']
    return json_response({'url': f'{github_base_url}/repos/foo/bar'})


async def pull_details(request: Request) -> Response:
    github_base_url = request.app['dynamic']['github_base_url']
    org = request.match_info['org']
    repo = request.match_info['repo']
    return json_response({'issue_url': f'{github_base_url}/repos/{org}/{repo}/issues'})


async def comment_details(request: Request) -> Response:
    github_base_url = request.app['dynamic']['github_base_url']
    org = request.match_info['org']
    repo = request.match_info['repo']
    comment_id = request.match_info['comment_id']
    return json_response({'url': f'{github_base_url}/repos/{org}/{repo}/comments/{comment_id}'})


async def comment_reaction(_request: Request) -> Response:
    return json_response({})


async def get_labels(_request: Request) -> Response:
    return json_response({})


async def add_labels(_request: Request) -> Response:
    return json_response({})


async def add_assignee(_request: Request) -> Response:
    return json_response({'assignees': []})


async def repo_apps_installed(_request: Request) -> Response:
    return json_response({'id': '654321'})


async def installation_access_token(_request: Request) -> Response:
    return json_response({'token': 'foobar'})


async def catch_all(request: Request) -> Response:
    print(f'{request.method}: {request.path} 404')
    return Response(body=f'{request.method} {request.path} 404', status=404)


routes = [
    web.get('/repos/{org}/{repo}', repo_details),
    web.get('/repos/{org}/{repo}/pulls/{pull_id}', pull_details),
    web.get('/repos/{org}/{repo}/comments/{comment_id}', comment_details),
    web.post('/repos/{org}/{repo}/comments/{comment_id}/reactions', comment_reaction),
    web.get('/repos/{org}/{repo}/issues/labels', get_labels),
    web.post('/repos/{org}/{repo}/issues/labels', add_labels),
    web.post('/repos/{org}/{repo}/issues/assignees', add_assignee),
    web.get('/repos/{org}/{repo}/installation', repo_apps_installed),
    web.post('/app/installations/{installation}/access_tokens', installation_access_token),
    web.route('*', '/{path:.*}', catch_all),
]
