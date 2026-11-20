"""Fast offline regression gates for the staged UX/social changes."""
from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]

def test_social_navigation_contract():
    script=(ROOT/'public/app.js').read_text(encoding='utf-8')
    assert "['/','/lists','/santas','/friends','/profile','/notifications']" in script
    assert "header-bell" in script
    assert "data-notification-count" in script
    assert '.site-header [data-nav]' in script
    assert "dashboard-metrics" not in script
    assert 'data-action="edit-game-preferences"' in script
    assert 'id="santa-preferences-form" hidden' in script
    assert 'form.hidden=true' in script

def test_friend_cancel_and_santa_claim_are_authorized():
    ui=(ROOT/'public/social-ui.js').read_text(encoding='utf-8')
    backend=(ROOT/'cloud/social.py').read_text(encoding='utf-8')
    server=(ROOT/'server.py').read_text(encoding='utf-8')
    assert 'Найти друга' in ui and 'Отменить заявку' in ui
    assert "old['requested_by']!=user['id']" in backend
    assert "kind='friend_request'" in backend
    assert "existing['user_id'] is not None" in backend
    assert "WHERE event_id=? AND user_id=?" in backend
    assert "p.event_id,p.user_id" in server
    ast.parse(backend)
    ast.parse(server)
