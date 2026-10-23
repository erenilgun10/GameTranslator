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
    assert json.loads(opener.requests[0].data)["show_billed_characters"] is True


def test_missing_usage_is_unknown_without_losing_valid_translation():
    response = {"translations": [{"text": "Synthetic translation"}]}
    result = DeepLProvider("test-only", FakeOpener(response)).translate_batch(["Hello"], "EN", "TR")
    assert result.texts == ["Synthetic translation"] and result.billed_characters is None


def test_partially_missing_batch_usage_is_unknown():
    response = {"translations": [{"text": "One", "billed_characters": 3}, {"text": "Two"}]}
    result = DeepLProvider("test-only", FakeOpener(response)).translate_batch(["One", "Two"], "EN", "TR")
    assert result.billed_characters is None


def test_explicit_zero_usage_is_known():
    response = {"translations": [{"text": "Synthetic translation", "billed_characters": 0}]}
    result = DeepLProvider("test-only", FakeOpener(response)).translate_batch(["Hello"], "EN", "TR")
    assert result.billed_characters == 0


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


def test_rate_limit_has_bounded_backoff_without_real_wait():
    class SequenceOpener:
        calls = 0
        def open(self, request, timeout):
            self.calls += 1
            if self.calls < 3:
                raise HTTPError(request.full_url, 429, "Synthetic rate limit", {}, None)
            return io.BytesIO(b'{"translations":[{"text":"Synthetic result"}]}')
    class FastCancel:
        waits = []
        def is_set(self):
            return False
        def wait(self, delay):
            self.waits.append(delay)
            return False
    opener, cancel = SequenceOpener(), FastCancel()
    result = DeepLProvider("test-only", opener).translate_batch(["Hello"], "EN", "TR", cancel)
    assert result.texts == ["Synthetic result"] and opener.calls == 3
    assert cancel.waits == [1, 2]
