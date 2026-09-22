import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.auth.service import AuthService
from backend.app.config.settings import settings

@pytest.fixture(autouse=True)
def auth_state(monkeypatch):
    monkeypatch.setattr(settings, 'AUTH_ENABLED', True)
    monkeypatch.setattr(settings, 'AUTH_ALLOW_REGISTRATION', False)
    monkeypatch.setattr(settings, 'APP_ENV', 'test')
    AuthService.reset()
    yield
    AuthService.reset()

client = TestClient(app)

def login(identifier='azhar@agentos.local', password='agentos123'):
    return client.post('/api/v1/auth/login', json={'email': identifier, 'password': password})

def test_username_and_email_resolve_same_server_role():
    a, b = login(), login('AZHAR ALI')
    assert a.status_code == b.status_code == 200
    assert a.json()['user_id'] == b.json()['user_id']
    assert b.json()['role'].upper() == 'USER'

@pytest.mark.parametrize('header', ['Authorization', 'X-API-Key'])
def test_logout_revokes_session_and_protected_routes(header):
    token = login().json()['token']
    headers = {header: ('Bearer ' if header == 'Authorization' else '') + token}
    for _ in range(2):
        assert client.get('/api/v1/auth/me', headers=headers).status_code == 200
    assert client.post('/api/v1/auth/logout', headers=headers).status_code == 200
    assert client.get('/api/v1/auth/me', headers=headers).status_code == 401
    assert client.get('/api/v1/tasks', headers=headers).status_code == 401
    assert client.get('/api/v1/tasks').status_code == 401

def test_lockout_cannot_be_bypassed_with_username():
    for i in range(AuthService.MAX_FAILED_ATTEMPTS):
        assert login('Azhar Ali' if i % 2 else 'azhar@agentos.local', 'wrong').status_code == 401
    assert login().status_code == 429
    assert login('Azhar Ali').status_code == 429

def test_expired_session_rejected():
    token = login().json()['token']
    AuthService._users_by_hash[AuthService.hash_api_key(token)].expires_at = 0
    assert client.get('/api/v1/auth/me', headers={'X-API-Key': token}).status_code == 401

account = {'email': 'new@example.com', 'username': 'New Engineer', 'password': 'Unique-test!'}

def test_registration_disabled_and_production_guard(monkeypatch):
    assert client.get('/api/v1/auth/options').json() == {'registration_enabled': False}
    assert client.post('/api/v1/auth/register', json=account).status_code == 404
    monkeypatch.setattr(settings, 'AUTH_ALLOW_REGISTRATION', True)
    monkeypatch.setattr(settings, 'APP_ENV', 'production')
    assert client.post('/api/v1/auth/register', json=account).status_code == 404
    assert client.get('/api/v1/auth/options').json() == {'registration_enabled': False}

def test_registration_stores_hash_and_cannot_replace_accounts(monkeypatch, caplog):
    monkeypatch.setattr(settings, 'AUTH_ALLOW_REGISTRATION', True)
    assert client.get('/api/v1/auth/options').json() == {'registration_enabled': True}
    response = client.post('/api/v1/auth/register', json=account)
    assert response.status_code == 201
    assert account['password'] not in response.text + caplog.text
    assert AuthService._credentials_by_email[account['email']].password_hash != account['password']
    signed_in = login(account['email'], account['password'])
    assert signed_in.status_code == 200 and signed_in.json()['role'].upper() == 'USER'
    assert client.post('/api/v1/auth/register', json={**account, 'email': 'NEW@example.com', 'password': 'Another-password!'}).status_code == 400
    assert client.post('/api/v1/auth/register', json={**account, 'email': 'other@example.com', 'username': 'NEW ENGINEER'}).status_code == 400
    assert login(account['email'], account['password']).status_code == 200

@pytest.mark.parametrize('changes', [{'password': 'short' }, {'role': 'ADMIN'}, {'email': 'invalid'}, {'username': '  '}])
def test_invalid_registration_cannot_leak_credentials(monkeypatch, changes, caplog):
    monkeypatch.setattr(settings, 'AUTH_ALLOW_REGISTRATION', True)
    data = {**account, **changes}
    response = client.post('/api/v1/auth/register', json=data)
    assert response.status_code == 422
    assert data['password'] not in response.text + caplog.text
    assert account['email'] not in AuthService._credentials_by_email


@pytest.mark.parametrize('password,accepted', [('a'*6+'!',False),('a'*7+'!',True),('a'*8,False),('a'*19+'!',True),('a'*20+'!',False),('a'*19+' ',False),('\U0001f642'*7+'!',True),('space phrase!',True)])
def test_registration_password_boundaries(monkeypatch,password,accepted):
    monkeypatch.setattr(settings,'AUTH_ALLOW_REGISTRATION',True)
    response=client.post('/api/v1/auth/register',json={**account,'password':password})
    assert response.status_code == (201 if accepted else 422)
    if accepted:
        assert login(account['email'],password).status_code == 200
        hashed=AuthService._credentials_by_email[account['email']].password_hash
        assert not AuthService.verify_password(password[:-1]+'z',hashed)
    else:
        assert response.json()['detail'] == 'Use 8 to 20 characters and at least one special character (such as !, @, # or $).'
        with pytest.raises(ValueError,match='8 to 20'):
            AuthService.register_local_account(account['email'],account['username'],password)

@pytest.mark.parametrize('password',['a'*7+'!','a'*19+'!','\U0001f642'*19+'!'])
def test_registration_service_accepts_valid_lengths(password):
    assert AuthService.register_local_account(account['email'],account['username'],password)
    assert AuthService.verify_password(password,AuthService._credentials_by_email[account['email']].password_hash)

@pytest.mark.parametrize('enabled',[False,True])
@pytest.mark.parametrize('environment',['development','production','prod'])
def test_registration_options_from_env_file(monkeypatch,tmp_path,enabled,environment):
    from backend.app.config.settings import Settings, PROJECT_ROOT
    assert Settings.model_config['env_file'] == str(PROJECT_ROOT / '.env')
    monkeypatch.delenv('AUTH_ALLOW_REGISTRATION',raising=False)
    monkeypatch.delenv('APP_ENV',raising=False)
    env=tmp_path/'.env'
    env.write_text(f'AUTH_ALLOW_REGISTRATION={str(enabled).lower()}\nAPP_ENV={environment}\n')
    loaded=Settings(_env_file=env)
    monkeypatch.setattr(settings,'AUTH_ALLOW_REGISTRATION',loaded.AUTH_ALLOW_REGISTRATION)
    monkeypatch.setattr(settings,'APP_ENV',loaded.APP_ENV)
    assert client.get('/api/v1/auth/options').json()['registration_enabled'] == (enabled and environment=='development')

def test_normal_root_env_is_loaded_from_another_directory(monkeypatch,tmp_path):
    from backend.app.config.settings import Settings, PROJECT_ROOT
    from dotenv import dotenv_values
    monkeypatch.delenv('AUTH_ALLOW_REGISTRATION',raising=False)
    monkeypatch.chdir(tmp_path)
    configured=dotenv_values(PROJECT_ROOT/'.env').get('AUTH_ALLOW_REGISTRATION','false')
    assert Settings().AUTH_ALLOW_REGISTRATION == (configured.lower() in ('true','1','yes','on'))

@pytest.mark.parametrize('origin',['http://localhost:3001','http://127.0.0.1:3001'])
def test_registration_availability_cors_for_alternate_frontend(monkeypatch,origin):
    monkeypatch.setattr(settings,'AUTH_ALLOW_REGISTRATION',True)
    response=client.get('/api/v1/auth/options',headers={'Origin':origin})
    assert response.json()['registration_enabled'] is True
    assert response.headers['access-control-allow-origin'] == origin
    preflight=client.options('/api/v1/auth/register',headers={'Origin':origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
    assert preflight.status_code == 200
    assert preflight.headers['access-control-allow-origin'] == origin

def test_registration_cors_does_not_allow_arbitrary_origins():
    response=client.get('/api/v1/auth/options',headers={'Origin':'https://untrusted.example'})
    assert 'access-control-allow-origin' not in response.headers
