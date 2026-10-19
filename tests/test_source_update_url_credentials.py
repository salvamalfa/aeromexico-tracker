from uuid import uuid4

import pytest

from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect, validate_url


@pytest.mark.parametrize(
    "key",
    [
        "api%5Fkey",
        "%61pi-key",
        "%74oken",
        "access%5Ftoken",
        "pass%77ord",
        "se%63ret",
        "X-Amz-%53ignature",
        "X-Amz-Creden%74ial",
        "API%5fKEY",
        "token%5B%5D",
    ],
)
def test_encoded_credential_parameter_names_block_before_client_or_receipt(key):
    work = ROOT / "tmp/source-updates" / ("credential-guard-" + uuid4().hex)
    url = "https://www.eia.gov/fixture.json?" + key + "=synthetic-fixture"
    with pytest.raises(ValueError, match="without credentials"):
        validate_url(url, ["eia.gov"])

    def forbidden(*args, **kwargs):
        raise AssertionError("Credential URL must fail before HTTP client construction")

    item = {
        "id": "fixture",
        "product": "fuel",
        "source_system": "eia",
        "entity": "fixture",
        "period": "2026M09",
        "purpose": "data",
        "url": url,
        "extension": "json",
        "mode": "get",
    }
    with pytest.raises(ValueError, match="without credentials"):
        collect({"version": 1, "items": [item]}, work, execute=True, client_factory=forbidden)
    assert not work.exists()


def test_encoded_public_keys_and_credential_words_in_query_values_are_not_credentials():
    validate_url("https://www.eia.gov/fixture.json?q%75ery=token%3Dexample&format=json", ["eia.gov"])
