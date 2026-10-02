from chuma_ip_factory.api import API

def test_ui_defaults_and_no_cache_headers():
    import pathlib
    src=pathlib.Path(__file__).parents[1]/'chuma_ip_factory'/'api.py'
    s=src.read_text(encoding='utf-8')
    assert 'value="CHUMA"' in s
    assert 'value=\"CHUMA\"' not in s
    assert 'placeholder="Краткая карточка персонажа (необязательно)"' in s
    assert 'Cache-Control' in s and 'no-store' in s

def test_cloud_runtime_contract():
    import pathlib
    root=pathlib.Path(__file__).parents[1]
    assert (root/'Dockerfile').exists()
    assert '0.0.0.0' in (root/'run.py').read_text()
    assert 'DATABASE_URL' in (root/'run.py').read_text()
    assert 'CHUMA_ADMIN_TOKEN' in (root/'chuma_ip_factory'/'api.py').read_text()
