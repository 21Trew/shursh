import hashlib
from urllib.error import URLError

import pytest

from cloud import password_policy
from server import ApiError

# Synthetic values only. No live credentials or upstream traffic in CI.
CANDIDATE = 'synthetic-candidate-for-unit-test'
HASH = hashlib.sha1(CANDIDATE.encode(), usedforsecurity=False).hexdigest().upper()


class RangeResponse:
    status = 200

    def __init__(self, request, body):
        self.request = request
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def geturl(self):
        return self.request.full_url

    def read(self, limit):
        assert limit == 200001
        return self.body


@pytest.mark.parametrize('count', [0, 1, 42])
def test_pwned_password_range(monkeypatch, count):
    def fake(request, timeout):
        assert request.full_url == 'https://api.pwnedpasswords.com/range/' + HASH[:5]
        assert request.get_header('Add-padding') == 'true'
        assert timeout == 4
        assert CANDIDATE not in request.full_url and HASH not in request.full_url
        return RangeResponse(request, (HASH[5:] + ':' + str(count) + '\r\n').encode())
    monkeypatch.setattr(password_policy, 'urlopen', fake)
    if count:
        with pytest.raises(ApiError) as caught:
            password_policy.screen_new_password(CANDIDATE)
        assert caught.value.status == 400
        assert 'утечках' in caught.value.message
    else:
        password_policy.screen_new_password(CANDIDATE)


@pytest.mark.parametrize('value', ['short', 'x'*73, 'я'*37, 'x'*15+'\x00', 'x'*15+'\ud800'])
def test_invalid_new_password_no_network(monkeypatch, value):
    def no_network(*args, **kwargs):
        pytest.fail('Malformed password reached HIBP')
    monkeypatch.setattr(password_policy, 'urlopen', no_network)
    with pytest.raises(ApiError) as caught:
        password_policy.screen_new_password(value)
    assert caught.value.status == 400


@pytest.mark.parametrize('body', [b'', b'malformed', b'F'*200001])
def test_bad_range_fails_closed(monkeypatch, body):
    monkeypatch.setattr(password_policy, 'urlopen',
                        lambda request, timeout: RangeResponse(request, body))
    with pytest.raises(ApiError) as caught:
        password_policy.screen_new_password(CANDIDATE)
    assert caught.value.status == 503


def test_unavailable_range_fails_closed(monkeypatch):
    def unavailable(*args, **kwargs):
        raise URLError('synthetic failure')
    monkeypatch.setattr(password_policy, 'urlopen', unavailable)
    with pytest.raises(ApiError) as caught:
        password_policy.screen_new_password(CANDIDATE)
    assert caught.value.status == 503
