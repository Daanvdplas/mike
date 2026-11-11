"""Small server-controlled set of verified tool/structured-output model snapshots."""
DEFAULT_MODEL = 'openai/gpt-4.1-mini-2025-04-14'
SUPPORTED_MODELS = {
    DEFAULT_MODEL: 'GPT-4.1 mini',
    'openai/gpt-4.1-2025-04-14': 'GPT-4.1',
}


class UnsupportedModel(ValueError):
    pass


class ModelIdentityError(ValueError):
    pass


class ModelCatalog:
    def __init__(self, default_model=DEFAULT_MODEL, configured=None):
        ids = configured.split(',') if configured is not None else list(SUPPORTED_MODELS)
        ids = [item.strip() for item in ids]
        if not ids or len(set(ids)) != len(ids) or any(item not in SUPPORTED_MODELS for item in ids):
            raise UnsupportedModel('De serverallowlist bevat een onbekend of dubbel model.')
        if default_model not in ids:
            raise UnsupportedModel('Het standaardmodel staat niet in de serverallowlist.')
        self.default_model = default_model
        self.ids = ids

    def select(self, requested=None):
        if requested is None:
            return self.default_model
        if not isinstance(requested, str) or requested not in self.ids:
            raise UnsupportedModel('Het gekozen model is niet ondersteund door deze server. Kies een model uit de lijst.')
        return requested

    def payload(self):
        return {'default_model': self.default_model,
                'models': [{'id': model, 'label': SUPPORTED_MODELS[model]} for model in self.ids]}


def provider_model(response, requested):
    actual = response.get('model')
    if actual is None:
        return None
    if not isinstance(actual, str) or not actual.strip():
        raise ModelIdentityError('De provider gaf geen geldige modelidentiteit terug.')
    if actual.removeprefix('openai/') != requested.removeprefix('openai/'):
        raise ModelIdentityError('De provider gebruikte een ander model dan het gekozen model; er is geen fallback geaccepteerd.')
    return actual
