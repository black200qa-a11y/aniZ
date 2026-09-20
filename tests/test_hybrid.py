import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("aniz_check_env", Path(__file__).parents[1] / "scripts" / "check_env.py")
check_env = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(check_env)


def test_cloud_validation_does_not_require_telegram_or_aria2():
    ok, detail = check_env.validate_config({
        "DEPLOYMENT_ROLE": "cloud",
        "MONGODB_URI": "mongodb+srv://user:pass@cluster.example/aniz",
        "DATABASE_NAME": "aniz",
        "ADMIN_PASSWORD": "strong-password",
        "ADMIN_SESSION_SECRET": "long-session-secret",
    })
    assert ok, detail


def test_pc_validation_requires_telegram_bot_and_aria2():
    ok, detail = check_env.validate_config({"DEPLOYMENT_ROLE": "pc", "MONGODB_URI": "mongodb+srv://cluster", "DATABASE_NAME": "aniz"})
    assert not ok
    assert "API_HASH" in detail
