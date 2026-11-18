"""Vercel-compatible WSGI entrypoint. No SQLite or local demo in cloud mode."""
import json
import re
import sqlite3
from pathlib import Path
from flask import Flask, Response, request, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge

from cloud import db
from cloud.backend import CloudRequest, serialize
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


@app.after_request
def security_headers(result):
    result.headers['Cache-Control'] = 'no-store'
    result.headers['X-Content-Type-Options'] = 'nosniff'
    result.headers['Referrer-Policy'] = 'no-referrer'
    result.headers['X-Frame-Options'] = 'DENY'
    result.headers['X-Robots-Tag'] = 'noindex, nofollow'
    result.headers['Content-Security-Policy'] = ("default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'")
    return result


@app.errorhandler(ApiError)
def api_error(exc):
    return response({'error': exc.message, **({'detail':exc.detail} if exc.detail else {})},exc.status)


@app.errorhandler(RequestEntityTooLarge)
def body_error(_):
    return response({'error':'Слишком большой запрос'},413)


@app.route('/api/<path:route>', methods=['GET','POST','PATCH','DELETE'])
def api(route):
    path = '/api/'+route
    if request.method not in ('GET','HEAD'):
        origin = request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and origin not in (f'https://{request.host}',f'http://{request.host}')):
            return response({'error':'Запрос из другого источника отклонён'},403)
    handler = CloudRequest(request)
    try:
        # Rate limit ALL public API traffic in persistent storage. Auth-specific
        # and draw/reservation limits from the shared routes also apply.
        handler.throttled('api', 180)
        write = request.method not in ('GET','HEAD')
        # Auth calls use their own transactions; they do not take the global
        # business lock while waiting for Supabase Auth over the network.
        separate = path in ('/api/register','/api/login','/api/logout')
        with db.transaction(write=write,rate_limit=separate) as con:
            result = handler.handle_api('GET' if request.method=='HEAD' else request.method,path,con)
        return response(result[1],result[0],result[2])
    except ApiError:
        raise
    except sqlite3.IntegrityError:
        return response({'error':'Конфликт данных. Обнови страницу и повтори.'},409)
    except RequestEntityTooLarge:
        raise
    except Exception as exc:
        # Never log request URLs (bearer capabilities), secrets, or raw DB errors.
        app.logger.error('Cloud API failure: %s',type(exc).__name__)
        return response({'error':'Сервис временно недоступен. Повтори позже.'},503)


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
    if route in ('app.js','styles.css','favicon.svg'):
        return send_from_directory(ROOT/'public',route)
    # Serve only known app routes; never include the simulator or repository files.
    if route in ('','index.html','lists','santas') or re.fullmatch(r'(?:list|santa)/[0-9]{1,16}|(?:w|r|join|p)/[A-Za-z0-9_-]{1,128}',route):
        return send_from_directory(ROOT/'public','index.html')
    return response({'error':'Страница не найдена'},404)


if __name__ == '__main__':
    # Local cloud-mode smoke testing only; Vercel imports app via WSGI.
    app.run(host='127.0.0.1',port=8787,debug=False)
