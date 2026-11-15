import random

import pytest


@pytest.fixture(autouse=True)
def _seed():
    """AI のランダム要素を固定して、テスト結果を再現可能にする。"""
    random.seed(1234)
