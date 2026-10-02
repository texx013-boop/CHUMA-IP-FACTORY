import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from chuma_ip_factory.api import run
from chuma_ip_factory.core import HTTPImageProvider

if __name__ == '__main__':
    endpoint = os.getenv('CHUMA_IMAGE_ENDPOINT')
    api_key = os.getenv('CHUMA_IMAGE_API_KEY')
    provider = HTTPImageProvider(endpoint, api_key) if endpoint and api_key else None
    host = os.getenv('CHUMA_HOST', '0.0.0.0')
    port = int(os.getenv('PORT', os.getenv('CHUMA_PORT', '8097')))
    data_dir = Path(os.getenv('CHUMA_DATA_DIR', str(APP_ROOT / 'runtime')))
    data_dir.mkdir(parents=True, exist_ok=True)
    db = os.getenv('DATABASE_URL') or str(data_dir / 'chuma.db')
    media = Path(os.getenv('CHUMA_MEDIA_DIR', str(data_dir / 'media')))
    run(host=host, port=port, db=db, asset_root=str(media), image_provider=provider)
