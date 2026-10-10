from pathlib import Path


def test_application_entrypoints_are_syntactically_valid():
    root = Path(__file__).parents[1]
    for relative in ("run.py", "mini_ip_ui.py", "chuma_ip_factory/factory2_server.py", "chuma_ip_factory/factory2_ui.py"):
        source = root / relative
        compile(source.read_text(encoding="utf-8"), str(source), "exec")
