"""Coarse last-visit metadata. No raw UA, IP, device ID or history."""
from datetime import datetime, timezone
from cloud import db


def platform_family(headers):
    ua = (headers.get('User-Agent') or '').lower()
    hint = (headers.get('Sec-CH-UA-Platform') or '').strip('"').lower()
    if headers.get('X-Shursh-Platform') == 'ios' and ('macintosh' in ua or 'ipad' in ua):
        return 'ios'
    if any(x in ua for x in ('iphone','ipad','ipod')) or hint == 'ios':
        return 'ios'
    if 'android' in ua or hint == 'android':
        return 'android'
    if 'windows' in ua or hint == 'windows':
        return 'windows'
    if 'cros' in ua or hint == 'chrome os':
        return 'unknown'
    if 'macintosh' in ua or 'mac os x' in ua or hint == 'macos':
        return 'macos'
    if 'linux' in ua or hint == 'linux':
        return 'linux'
    return 'unknown'


def record_successful_visit(request, user, logger):
    if not user:
        return
    # Capture server time; client cannot provide a timestamp or another UID.
    seen = datetime.now(timezone.utc)
    try:
        # Independent write after the business transaction; no global write lock.
        # This runs once on a real bootstrap or successful authentication,
        # never on polling or normal warm navigation.
        with db.transaction(write=True,rate_limit=True) as con:
            con.execute("""INSERT INTO admin_user_activity(user_id,last_seen_at,last_platform)
                VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,last_platform=excluded.last_platform
                WHERE admin_user_activity.last_seen_at<excluded.last_seen_at""",
                (user['id'],seen,platform_family(request.headers)))
    except Exception as exc:
        # An optional admin metric must never prevent sign-in or page opening.
        logger.warning('Admin visit recording failed: %s',type(exc).__name__)
