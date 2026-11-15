import random

import pytest


@pytest.fixture(autouse=True)
def _seed():
    """Fix the AIs' randomness so test results are reproducible."""
    random.seed(1234)
