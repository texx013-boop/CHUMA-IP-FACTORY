import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from chuma_ip_factory.api import run
from chuma_ip_factory.core import HTTPImageProvider
from chuma_ip_factory.hf_image import HFImageProvider
from chuma_ip_factory.budget import BudgetGuardProvider, BudgetPolicy


if __name__ == '__main__':
    policy = BudgetPolicy.from_env()
    hf_token = os.getenv('HF_TOKEN')
    hf_cost_class = 'free-credit'
    endpoint = os.getenv('CHUMA_IMAGE_ENDPOINT')
    api_key = os.getenv('CHUMA_IMAGE_API_KEY')
    retry_attempts = int(os.getenv('CHUMA_IMAGE_RETRY_ATTEMPTS', '3'))
    retry_delay = float(os.getenv('CHUMA_IMAGE_RETRY_DELAY', '0.25'))
    timeout = int(os.getenv('CHUMA_IMAGE_TIMEOUT', '120'))
    cost_class = os.getenv('CHUMA_IMAGE_COST_CLASS', 'metered').strip().lower()

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
    data_dir = Path(os.getenv('CHUMA_DATA_DIR', str(APP_ROOT / 'runtime')))
    data_dir.mkdir(parents=True, exist_ok=True)
    db = os.getenv('DATABASE_URL') or str(data_dir / 'chuma.db')
    media = Path(os.getenv('CHUMA_MEDIA_DIR', str(data_dir / 'media')))
    run(host=host, port=port, db=db, asset_root=str(media), image_provider=provider,
        budget_policy=policy)
