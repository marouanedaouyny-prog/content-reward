from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict

from clipping.instagram import InstagramAPIError

COOKIE = 'instagram_oauth_state'
CALLBACK = '/api/v1/clipping/accounts/instagram/callback'

class RedactedValidationRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse({'detail': 'Send an empty JSON object. Instagram credentials are read from server configuration.'},
                                    status_code=422, headers={'Cache-Control': 'no-store'})
        return handler


router = APIRouter(prefix='/api/v1/clipping/accounts/instagram', tags=['Instagram connection'],
                   route_class=RedactedValidationRoute)


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


def connection(request: Request):
    return request.app.state.instagram


@router.get('')
def status(response: Response, account=Depends(connection)):
    response.headers['Cache-Control'] = 'no-store'
    return account.status()


@router.post('/verify')
def verify(body: VerifyRequest, response: Response, account=Depends(connection)):
    response.headers['Cache-Control'] = 'no-store'
    return account.verify()


@router.post('/connect')
def connect(body: VerifyRequest, request: Request, account=Depends(connection)):
    try:
        if not account.oauth_ready():
            raise InstagramAPIError('oauth_not_configured')
        redirect = urlparse(account.oauth_redirect_uri())
        if (redirect.scheme, redirect.netloc) != (request.url.scheme, request.url.netloc):
            raise InstagramAPIError('oauth_redirect_mismatch')
        authorization_url, state = account.begin_oauth()
    except InstagramAPIError as exc:
        return JSONResponse({'status': exc.code, 'message': str(exc)}, status_code=409,
                            headers={'Cache-Control': 'no-store'})
    response = JSONResponse({'authorization_url': authorization_url}, headers={'Cache-Control': 'no-store'})
    response.set_cookie(COOKIE, state, max_age=600, httponly=True, samesite='lax',
                        secure=request.url.scheme == 'https', path=CALLBACK)
    return response


@router.get('/callback', include_in_schema=False)
def callback(request: Request, account=Depends(connection)):
    result = 'connected'
    params = request.query_params
    # Uvicorn logs this same scope after responding. Keep authorization codes
    # and provider error text out of access logs on every callback branch.
    request.scope['query_string'] = b''
    try:
        if len(params.getlist('state')) != 1 or len(params.getlist('code')) > 1:
            raise InstagramAPIError('oauth_state_invalid')
        state, cookie = params.get('state'), request.cookies.get(COOKIE)
        if 'error' in params:
            if not account._consume_oauth_state(state, cookie):
                raise InstagramAPIError('oauth_state_invalid')
            raise InstagramAPIError('access_denied')
        account.complete_oauth(state, cookie, params.get('code'))
        checked = account.verify()
        if checked['status'] not in ('verified', 'profile_verified'):
            raise InstagramAPIError(checked['status'])
    except InstagramAPIError as exc:
        result = exc.code
    response = RedirectResponse('/?instagram=' + result + '#social-accounts', status_code=303,
                                headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
    response.delete_cookie(COOKIE, path=CALLBACK, httponly=True, samesite='lax',
                           secure=request.url.scheme == 'https')
    return response


def instagram_script():
    return FileResponse(Path(__file__).with_name('instagram.js'), media_type='text/javascript')
