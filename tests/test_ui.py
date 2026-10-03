from chuma_ip_factory.api import API

def test_ui_defaults_and_no_cache_headers():
    import pathlib
    src=pathlib.Path(__file__).parents[1]/'chuma_ip_factory'/'api.py'
    s=src.read_text(encoding='utf-8')
    assert 'value="CHUMA"' in s
    assert 'placeholder="Коротко опиши характер, визуальный образ и особенности…"' in s
    assert 'Cache-Control' in s and 'no-store' in s

def test_cloud_runtime_contract():
    import pathlib
    root=pathlib.Path(__file__).parents[1]
    assert (root/'Dockerfile').exists()
    assert '0.0.0.0' in (root/'run.py').read_text()
    assert 'DATABASE_URL' in (root/'run.py').read_text()
    assert 'CHUMA_ADMIN_TOKEN' in (root/'chuma_ip_factory'/'api.py').read_text()


def test_cloud_environment_contract_details():
    import pathlib
    root=pathlib.Path(__file__).parents[1]
    run_src=(root/'run.py').read_text()
    assert "os.getenv('PORT'" in run_src
    assert "os.getenv('CHUMA_DATA_DIR'" in run_src
    assert "os.getenv('CHUMA_MEDIA_DIR'" in run_src
    assert "os.getenv('CHUMA_IMAGE_ENDPOINT'" in run_src
    assert "os.getenv('CHUMA_IMAGE_API_KEY'" in run_src


def test_chuma_ui_live_telemetry_contract():
    import pathlib
    src=(pathlib.Path(__file__).parents[1]/'chuma_ip_factory'/'api.py').read_text(encoding='utf-8')
    assert 'health-badge' in src
    assert 'job-badge' in src
    assert "setInterval(()=>{if(owner)status()" in src
    assert 'SYSTEM READY' in src
