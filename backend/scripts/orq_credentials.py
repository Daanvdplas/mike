"""Load the existing server-side Orq credential without logging its value."""
import os
from pathlib import Path


def load_api_key(environment=None):
    environment = os.environ if environment is None else environment
    key = environment.get('ORQ_API_KEY', '').strip()
    if key:
        return key
    configured_file = environment.get('ORQ_API_KEY_FILE', '').strip()
    if not configured_file:
        return ''
    try:
        key = Path(configured_file).expanduser().read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError):
        raise ValueError('Het ingestelde Orq-sleutelbestand kan niet worden gelezen; controleer de serverconfiguratie.') from None
    if not key:
        raise ValueError('Het ingestelde Orq-sleutelbestand is leeg; controleer de serverconfiguratie.')
    return key
