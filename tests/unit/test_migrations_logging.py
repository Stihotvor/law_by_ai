import ast
from pathlib import Path

ENV = Path(__file__).resolve().parents[2] / "migrations" / "env.py"


def test_env_logging_keeps_existing_loggers() -> None:
    calls = [
        node
        for node in ast.walk(ast.parse(ENV.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "fileConfig"
    ]
    assert len(calls) == 1
    kwargs = {k.arg: k.value for k in calls[0].keywords}
    flag = kwargs.get("disable_existing_loggers")
    assert isinstance(flag, ast.Constant)
    assert flag.value is False
