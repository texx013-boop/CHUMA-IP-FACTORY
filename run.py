import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from chuma_ip_factory.api import run, API
from mini_ip_ui import send_mini_ip

API.send_html = send_mini_ip
from chuma_ip_factory.core import HTTPImageProvider
from chuma_ip_factory.hf_image import HFImageProvider
from chuma_ip_factory.budget import BudgetGuardProvider, BudgetPolicy
from chuma_ip_factory.video_combain import HTTPVideoEngine, BudgetVideoEngine
from chuma_ip_factory.factory2_server import run_factory2


if __name__ == '__main__':
    if os.getenv('GLOBAL_FACTORY_2', '').strip().lower() in ('1','true','yes','on'):
        default_data_dir = '/data' if Path('/data').exists() else str(APP_ROOT / 'runtime')
        data_dir = Path(os.getenv('CHUMA_DATA_DIR', default_data_dir))
        data_dir.mkdir(parents=True, exist_ok=True)
        run_factory2(
            host=os.getenv('CHUMA_HOST', '0.0.0.0'),
            port=int(os.getenv('PORT', os.getenv('CHUMA_PORT', '8097'))),
            db=os.getenv('DATABASE_URL') or str(data_dir / 'factory2.db'),
            media_root=os.getenv('CHUMA_MEDIA_DIR', str(data_dir / 'media')),
        )
        raise SystemExit(0)

    policy = BudgetPolicy.from_env()
    hf_token = os.getenv('HF_TOKEN')
    hf_cost_class = 'free-credit'
    endpoint = os.getenv('CHUMA_IMAGE_ENDPOINT')
    api_key = os.getenv('CHUMA_IMAGE_API_KEY')
    retry_attempts = int(os.getenv('CHUMA_IMAGE_RETRY_ATTEMPTS', '3'))
    retry_delay = float(os.getenv('CHUMA_IMAGE_RETRY_DELAY', '0.25'))
    timeout = int(os.getenv('CHUMA_IMAGE_TIMEOUT', '120'))
    cost_class = os.getenv('CHUMA_IMAGE_COST_CLASS', 'metered').strip().lower()

    video_engine = None
    video_endpoint = os.getenv('CHUMA_VIDEO_ENDPOINT')
    video_api_key = os.getenv('CHUMA_VIDEO_API_KEY')
    if video_endpoint and video_api_key:
        video_candidate = HTTPVideoEngine(
            video_endpoint, video_api_key,
            max_attempts=int(os.getenv('CHUMA_VIDEO_RETRY_ATTEMPTS', '2')),
            timeout=int(os.getenv('CHUMA_VIDEO_TIMEOUT', '300')),
            retry_delay=float(os.getenv('CHUMA_VIDEO_RETRY_DELAY', '1.0')),
            max_output_bytes=int(os.getenv('CHUMA_VIDEO_MAX_OUTPUT_BYTES', str(256 * 1024 * 1024))),
        )
        video_cost_class = os.getenv('CHUMA_VIDEO_COST_CLASS', 'metered').strip().lower()
        video_engine = BudgetVideoEngine(video_candidate, policy, cost_class=video_cost_class)

    provider = None
    if hf_token and policy.allows(hf_cost_class):
        provider = HFImageProvider(hf_token)
    elif endpoint and api_key and policy.allows(cost_class):
        candidate = HTTPImageProvider(
            endpoint, api_key,
            max_attempts=retry_attempts,
            timeout=timeout,
            retry_delay=retry_delay,
        )
        provider = BudgetGuardProvider(candidate, policy, cost_class=cost_class)

    host = os.getenv('CHUMA_HOST', '0.0.0.0')
    port = int(os.getenv('PORT', os.getenv('CHUMA_PORT', '8097')))
    default_data_dir = '/data' if Path('/data').exists() else str(APP_ROOT / 'runtime')
    data_dir = Path(os.getenv('CHUMA_DATA_DIR', default_data_dir))
    data_dir.mkdir(parents=True, exist_ok=True)
    db = os.getenv('DATABASE_URL') or str(data_dir / 'chuma.db')
    media = Path(os.getenv('CHUMA_MEDIA_DIR', str(data_dir / 'media')))
    run(host=host, port=port, db=db, asset_root=str(media), image_provider=provider,
        budget_policy=policy, video_engine=video_engine)
