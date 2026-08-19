"""
Tests for backend/app/security/sensitive_files.py

Covers:
- Basename pattern matching (.env, .pem, .key, id_rsa, etc.)
- Full path pattern matching (.env in subdirectories, .ssh/**, etc.)
- Content pattern detection (API keys, private key headers, tokens)
- sensitive_file_reason() returns useful messages
- Non-sensitive files are correctly passed through
"""

import pytest
from backend.app.security.sensitive_files import (
    contains_secrets,
    is_sensitive_path,
    sensitive_file_reason,
)


# ---------------------------------------------------------------------------
# is_sensitive_path — basename patterns
# ---------------------------------------------------------------------------

class TestIsSensitivePathBasename:
    def test_dot_env(self):
        assert is_sensitive_path(".env")

    def test_dot_env_local(self):
        assert is_sensitive_path(".env.local")

    def test_dot_env_production(self):
        assert is_sensitive_path(".env.production")

    def test_pem_file(self):
        assert is_sensitive_path("server.pem")

    def test_key_file(self):
        assert is_sensitive_path("private.key")

    def test_p12_file(self):
        assert is_sensitive_path("cert.p12")

    def test_pfx_file(self):
        assert is_sensitive_path("cert.pfx")

    def test_credentials_bare(self):
        assert is_sensitive_path("credentials")

    def test_credentials_json(self):
        assert is_sensitive_path("credentials.json")

    def test_secrets_bare(self):
        assert is_sensitive_path("secrets")

    def test_secrets_yaml(self):
        assert is_sensitive_path("secrets.yaml")

    def test_id_rsa(self):
        assert is_sensitive_path("id_rsa")

    def test_id_rsa_pub(self):
        assert is_sensitive_path("id_rsa.pub")

    def test_id_ed25519(self):
        assert is_sensitive_path("id_ed25519")

    def test_id_ed25519_pub(self):
        assert is_sensitive_path("id_ed25519.pub")

    def test_jks(self):
        assert is_sensitive_path("keystore.jks")

    def test_keystore(self):
        assert is_sensitive_path("app.keystore")

    def test_netrc(self):
        assert is_sensitive_path(".netrc")

    def test_pgpass(self):
        assert is_sensitive_path(".pgpass")


# ---------------------------------------------------------------------------
# is_sensitive_path — full path patterns (sub-directories)
# ---------------------------------------------------------------------------

class TestIsSensitivePathFullPath:
    def test_dot_env_in_subdirectory(self):
        assert is_sensitive_path("config/.env")

    def test_dot_env_nested(self):
        assert is_sensitive_path("backend/config/.env.local")

    def test_ssh_directory(self):
        assert is_sensitive_path(".ssh/id_rsa")

    def test_aws_credentials(self):
        assert is_sensitive_path(".aws/credentials")

    def test_aws_config(self):
        assert is_sensitive_path(".aws/config")

    def test_gnupg(self):
        assert is_sensitive_path(".gnupg/secring.gpg")

    def test_docker_config(self):
        assert is_sensitive_path(".docker/config.json")


# ---------------------------------------------------------------------------
# is_sensitive_path — non-sensitive files
# ---------------------------------------------------------------------------

class TestIsSensitivePathNonSensitive:
    def test_regular_python_file(self):
        assert not is_sensitive_path("main.py")

    def test_readme(self):
        assert not is_sensitive_path("README.md")

    def test_requirements(self):
        assert not is_sensitive_path("requirements.txt")

    def test_calculator(self):
        assert not is_sensitive_path("calculator.py")

    def test_test_file(self):
        assert not is_sensitive_path("test_calculator.py")

    def test_json_non_secret(self):
        assert not is_sensitive_path("config.json")   # not "credentials.json"

    def test_typescript(self):
        assert not is_sensitive_path("index.ts")

    def test_nested_python(self):
        assert not is_sensitive_path("backend/app/main.py")


# ---------------------------------------------------------------------------
# contains_secrets — content detection
# ---------------------------------------------------------------------------

class TestContainsSecrets:
    def test_openai_key(self):
        assert contains_secrets("OPENAI_API_KEY=sk-abc123456789012345678901234567890123456")

    def test_aws_key_id(self):
        assert contains_secrets("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")

    def test_aws_secret_key(self):
        assert contains_secrets("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")

    def test_rsa_private_key_header(self):
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
        assert contains_secrets(content)

    def test_openssh_private_key(self):
        content = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA"
        assert contains_secrets(content)

    def test_bearer_token(self):
        assert contains_secrets("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc")

    def test_github_token(self):
        assert contains_secrets("GITHUB_TOKEN=ghp_1234567890abcdef")

    def test_generic_password_field(self):
        assert contains_secrets("password=supersecret123")

    def test_bytes_content(self):
        assert contains_secrets(b"api_key=mysecretkey12345")

    def test_innocent_code_no_secrets(self):
        code = "def add(a, b):\n    return a + b\n"
        assert not contains_secrets(code)

    def test_empty_string(self):
        assert not contains_secrets("")

    def test_only_scans_first_4kb(self):
        # Pad with 4100 bytes of innocuous content, then secret
        content = "x" * 4100 + "\npassword=secret"
        # The secret is beyond 4 KB — should NOT be detected
        assert not contains_secrets(content)


# ---------------------------------------------------------------------------
# sensitive_file_reason
# ---------------------------------------------------------------------------

class TestSensitiveFileReason:
    def test_returns_nonempty_string_for_sensitive(self):
        reason = sensitive_file_reason(".env")
        assert isinstance(reason, str)
        assert len(reason) > 0

    def test_mentions_pattern(self):
        reason = sensitive_file_reason("id_rsa")
        assert "id_rsa" in reason or "sensitive" in reason.lower()
