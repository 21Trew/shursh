"""Vercel-compatible WSGI entrypoint. No SQLite or local demo in cloud mode."""
import time
_MODULE_IMPORT_STARTED = time.perf_counter()
import json
import os
import re
import sqlite3
from flask import g
from pathlib import Path
from flask import Flask, Response, request, send_from_directory, redirect
from werkzeug.exceptions import RequestEntityTooLarge

from cloud import db, auth, password_policy, activity
from cloud.backend import CloudRequest, serialize, valid_auth_email
from server import ApiError, LIMIT_BYTES

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = LIMIT_BYTES


def response(data, status=200, cookie=None):
    result = Response(json.dumps(data, ensure_ascii=False, default=serialize),
                      status=status, mimetype='application/json')
    if cookie:
        result.headers['Set-Cookie'] = cookie
    return result


@app.before_request
def timer_start():
    g.request_started = time.perf_counter()


@app.teardown_request
def release_database_connection(_error):
    db.close_request_connection()


@app.after_request
def security_headers(result):
    if request.path.startswith('/api/'):
        elapsed = (time.perf_counter() - g.request_started) * 1000
        db_ms=getattr(g,'db_connect_ms',0.0)
        db_count=getattr(g,'db_connect_count',0)
        sql_ms=getattr(g,'sql_exec_ms',0.0)
        sql_count=getattr(g,'sql_exec_count',0)
        region = os.environ.get('VERCEL_REGION', 'local')
        if not re.fullmatch(r'[a-z0-9]{2,8}',region):
            region = 'unknown'
        # This measures Python module import/initialization, not end-to-end cold
        # start (which also includes Vercel routing and worker provisioning).
        timing = (f'app;dur={elapsed:.1f}, db-connect;dur={db_ms:.1f};desc="{db_count} connection(s)", '
                  f'sql-exec;dur={sql_ms:.1f};desc="{sql_count} statement(s)", '
                  f'module-init;dur={_MODULE_INIT_MS:.1f}, region;desc="{region}"')
        auth_ms=getattr(g,'shursh_auth_ms',None)
        if auth_ms is not None:
            timing += f', auth-upstream;dur={auth_ms:.1f}'
        result.headers['Server-Timing'] = timing
    # Static UI assets are public and identical for every user. Reusing them
    # avoids repeated downloads on reload; HTML, APIs and capability URLs
    # must always remain private and uncached.
    if request.path in ('/app.js','/santa-ui.js','/social-ui.js','/styles.css','/polish.css','/fonts.css','/favicon.svg','/favicon.ico') or request.path.startswith('/fonts/'):
        result.headers['Cache-Control'] = 'public, max-age=300, must-revalidate'
    else:
        result.headers['Cache-Control'] = 'no-store'
    result.headers['X-Content-Type-Options'] = 'nosniff'
    result.headers['Referrer-Policy'] = 'no-referrer'
    result.headers['X-Frame-Options'] = 'DENY'
    result.headers['X-Robots-Tag'] = 'noindex, nofollow'
    result.headers['Content-Security-Policy'] = ("default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; font-src 'self'; "
        "script-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'")
    return result


@app.errorhandler(ApiError)
def api_error(exc):
    return response({'error': exc.message, **({'detail':exc.detail} if exc.detail else {})},exc.status)


@app.errorhandler(RequestEntityTooLarge)
def body_error(_):
    return response({'error':'Слишком большой запрос'},413)


@app.route('/api/<path:route>', methods=['GET','POST','PATCH','PUT','DELETE'])
def api(route):
    path = '/api/'+route
    if request.method not in ('GET','HEAD'):
        origin = request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and origin not in (f'https://{request.host}',f'http://{request.host}')):
            return response({'error':'Запрос из другого источника отклонён'},403)
    # These read-only bootstrap endpoints are safe without a database when no
    # session cookie exists. Avoid a Supavisor round-trip for every anonymous
    # landing-page visit (and every browser refresh).
    if request.method == 'GET' and not request.cookies.get('shursh_sid'):
        if path == '/api/me':
            return response({'user': None, 'demo': False})
        if path == '/api/dashboard':
            return response({'user': None, 'demo': False, 'lists': [], 'events': []})
    native_login=(path=='/api/login' and request.method=='POST' and
                  request.mimetype=='application/x-www-form-urlencoded')
    if native_login:
        origin=request.headers.get('Origin')
        if not origin and request.headers.get('Sec-Fetch-Site')!='same-origin':
            return response({'error':'Запрос из другого источника отклонён'},403)
        landing=request.form.get('return_path','/')
        if not re.fullmatch(r'/(?:join/(?:p/)?[A-Za-z0-9_-]{1,128}|w/[A-Za-z0-9_-]{1,128}|p/[A-Za-z0-9_-]{43})?',landing):
            landing='/'
    handler = CloudRequest(request)
    try:
        # Auth's upstream HTTP request must not run inside a DB transaction:
        # retain transactional session writes, but release the rate limiter
        # socket before the external request.
        if path == '/api/auth/resend' and request.method == 'POST':
            result=handler.resend_confirmation()
            return response(result[1],result[0],result[2])
        if path in ('/api/account/email','/api/account/password') and request.method=='POST':
            handler.throttled('account-update',8,600)
            data=handler.body()
            with db.transaction() as con:
                owner=handler.auth(con)
                owner_id=owner['id']
                owner_email=owner['email']
            db.close_request_connection()
            current_password=data.get('current_password')
            if not isinstance(current_password,str) or not (8<=len(current_password)<=200):
                raise ApiError(400,'Введи текущий пароль')
            if path.endswith('/email'):
                value=valid_auth_email(data.get('email'))
                if value.casefold()==owner_email.casefold():
                    raise ApiError(400,'Это уже твой адрес')
                change={'email':value}
            else:
                value=data.get('new_password')
                if not isinstance(value,str) or value==current_password:
                    raise ApiError(400,'Новый пароль должен отличаться от текущего')
                password_policy.validate_new_password(value)
                change={'password':value}
            auth.update_verified_account(owner_id,owner_email,current_password,change)
            return response({'ok':True,'pending_confirmation':'email' in change},200)
        if path == '/api/auth/complete' and request.method == 'POST':
            prepared=handler.prepare_confirmation()
            with db.transaction(write=True,rate_limit=True) as con:
                result=handler.finish_auth(con,prepared)
            activity.record_successful_visit(request,result[1].get('user'),app.logger)
            return response(result[1],result[0],result[2])
        if path in ('/api/register','/api/login') and request.method=='POST':
            form_data=request.form if native_login else None
            prepared=handler.prepare_auth(path,form_data)
            if prepared is None:
                return response({'user':None,'pending_confirmation':True},202)
            remember=(request.form.get('remember')=='on' if native_login else
                      (request.get_json(silent=True) or {}).get('remember') is True)
            with db.transaction(write=True,rate_limit=True) as con:
                result=handler.finish_auth(con,prepared,remember=path=='/api/login' and remember)
            activity.record_successful_visit(request,result[1].get('user'),app.logger)
            if native_login:
                destination='/' if landing.startswith('/p/') else landing
                reply=redirect(destination+'?shursh_login=ok',code=303)
                reply.headers['Set-Cookie']=result[2]
                return reply
            return response(result[1],result[0],result[2])
        # Authentication has a stricter dedicated limiter inside CloudRequest.
        # Avoid two separate PostgreSQL rate-limit transactions per login.
        # The read-only /api/me session check needs no generic rate write.
        if path not in ('/api/me','/api/login','/api/register','/api/logout'):
            handler.throttled('api', 180)
        # Avoid a second PostgreSQL connection/transaction while a chat write
        # holds the advisory write lock.
        if request.method=='POST' and re.fullmatch(
            r'/api/(?:santas/\d+|member/\d+|participant/[A-Za-z0-9_-]+)/messages/(?:general|to-recipient|from-santa)',path
        ):
            handler.throttled('chat',20)
            handler._chat_rate_checked=True
        if path=='/api/feedback' and request.method=='POST':
            handler.throttled('feedback',5,600)
            handler._feedback_rate_checked=True
        write = request.method not in ('GET','HEAD')
        # Auth calls use their own transactions; they do not take the global
        # business lock while waiting for Supabase Auth over the network.
        separate = path in ('/api/register','/api/login','/api/logout')
        with db.transaction(write=write,rate_limit=separate) as con:
            result = handler.handle_api('GET' if request.method=='HEAD' else request.method,path,con)
        if (request.method=='GET' and path in ('/api/me','/api/dashboard')
                and request.headers.get('X-Shursh-Visit')=='1' and result[0]==200):
            activity.record_successful_visit(request,result[1].get('user'),app.logger)
        return response(result[1],result[0],result[2])
    except ApiError as exc:
        if native_login:
            code='rate' if exc.status==429 else 'unavailable' if exc.status>=500 else 'invalid'
            return redirect(landing+'?shursh_login='+code,code=303)
        raise
    except sqlite3.IntegrityError:
        return response({'error':'Конфликт данных. Обнови страницу и повтори'},409)
    except RequestEntityTooLarge:
        raise
    except Exception as exc:
        # Never log request URLs (bearer capabilities), secrets, or raw DB errors.
        app.logger.error('Cloud API failure: %s',type(exc).__name__)
        if native_login:
            return redirect(landing+'?shursh_login=unavailable',code=303)
        return response({'error':'Сервис временно недоступен. Повтори позже'},503)


@app.get('/uploads/<filename>')
def image(filename):
    handler = CloudRequest(request)
    try:
        handler.throttled('images',180)
        with db.transaction() as con:
            payload,mime=handler.image(con,'/uploads/'+filename)
        return Response(payload,mimetype=mime)
    except ApiError:
        raise
    except Exception as exc:
        app.logger.error('Image failure: %s',type(exc).__name__)
        return response({'error':'Сервис временно недоступен'},503)


@app.get('/')
@app.get('/<path:route>')
def frontend(route=''):
    if route in ('app.js','santa-ui.js','social-ui.js','password-strength-worker.js','zxcvbn-4.4.2.js','styles.css','polish.css','fonts.css','favicon.svg','favicon.ico'):
        return send_from_directory(ROOT/'public',route)
    if re.fullmatch(r'fonts/(?:onest|unbounded)-(?:cyrillic|cyrillic-ext|latin)-wght-normal\.woff2',route):
        return send_from_directory(ROOT/'public',route)
    # Serve only known app routes; never include the simulator or repository files.
    if route in ('','index.html','lists','santas','friends','profile','notifications','admin','admin/users','admin/feedback') or re.fullmatch(r'(?:list|santa)/[0-9]{1,16}|(?:w|r|join|p)/[A-Za-z0-9_-]{1,128}|join/p/[A-Za-z0-9_-]{43}|users/[0-9a-fA-F-]{36}',route):
        return send_from_directory(ROOT/'public','index.html')
    return response({'error':'Страница не найдена'},404)


_MODULE_INIT_MS = (time.perf_counter() - _MODULE_IMPORT_STARTED) * 1000

if __name__ == '__main__':
    # Local cloud-mode smoke testing only; Vercel imports app via WSGI.
    app.run(host='127.0.0.1',port=8787,debug=False)
