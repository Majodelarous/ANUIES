from compania.agente.bot import credenciales_aws


def test_credenciales_desde_variables(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA_PRUEBA")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secreto")
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    cred = credenciales_aws()
    assert cred == {
        "access_key_id": "AKIA_PRUEBA",
        "secret_access_key": "secreto",
        "session_token": None,
        "region": "us-east-1",
    }
