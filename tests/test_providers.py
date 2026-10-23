import io
import json
from urllib.error import HTTPError

import pytest

from game_translator.providers import DeepLProvider, ProviderError


class FakeOpener:
    """Explicit mock: never sends an HTTP request."""
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return io.BytesIO(json.dumps(self.response).encode())


def test_deepl_contract_without_live_call():
    opener = FakeOpener({"translations": [{"text": "Merhaba", "billed_characters": 5}]})
    provider = DeepLProvider("test-only-not-a-real-key:fx", opener)
    result = provider.translate_batch(["Hello"], "EN", "TR")
    assert result.texts == ["Merhaba"] and result.billed_characters == 5
    assert opener.requests[0].full_url == "https://api-free.deepl.com/v2/translate"
    assert json.loads(opener.requests[0].data)["target_lang"] == "TR"


@pytest.mark.parametrize("response", [[], {}, {"translations": []}, {"translations": [{"text": ""}]}])
def test_malformed_response_is_not_success(response):
    with pytest.raises(ProviderError):
        DeepLProvider("test-only", FakeOpener(response)).translate_batch(["Hello"], "EN", "TR")


def test_secret_not_exposed_in_errors():
    key = "test-only-not-a-real-key"
    error = HTTPError("https://api.deepl.com", 403, key, {}, None)
    with pytest.raises(ProviderError) as result:
        DeepLProvider(key, FakeOpener(error)).translate_batch(["Hello"], "EN", "TR")
    assert key not in str(result.value)
