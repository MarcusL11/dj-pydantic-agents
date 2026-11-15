from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.exceptions import ModelRateLimitError
from pydantic_ai.exceptions import UsageLimitExceeded

from dj_pydantic_agents.kit.errors import INTERNAL_ERROR
from dj_pydantic_agents.kit.errors import error_code_for
from tests.testcases import SimpleTestCase


class TestErrorCodeFor(SimpleTestCase):
    def test_usage_limit(self):
        assert error_code_for(UsageLimitExceeded("limit")) == "usage_limit"

    def test_subclass_comes_before_its_base_class(self):
        assert error_code_for(ModelRateLimitError("m", "slow down")) == "rate_limited"

    def test_other_model_api_error(self):
        assert (
            error_code_for(ModelHTTPError(status_code=500, model_name="m"))
            == "model_api_error"
        )

    def test_unknown_error(self):
        assert error_code_for(ValueError("bad")) == INTERNAL_ERROR
