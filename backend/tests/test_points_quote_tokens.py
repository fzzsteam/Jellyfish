"""试算凭证（quote token）单测。

覆盖：
- `create_quote_token` / `decode_quote_token` 往返一致
- 校验 `sub == expected_user_id`，不匹配抛 `QuoteTokenError`
- 校验 `type == "points_quote"`，其他类型令牌被拒绝
- 签名被篡改抛 `QuoteTokenError`
- 过期令牌抛 `QuoteTokenError`
- `hash_quote_params` 对相同字典稳定且与键顺序无关
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.services.points import (
    QuoteClaims,
    QuoteTokenError,
    create_quote_token,
    decode_quote_token,
    hash_quote_params,
)


def _make_claims(**overrides) -> QuoteClaims:
    base = {
        "user_id": "u1",
        "business_type": "video_generation",
        "model_id": "video-model",
        "params_hash": hash_quote_params({"duration_seconds": 5, "resolution": "1080p"}),
        "required_points": 100,
    }
    base.update(overrides)
    return QuoteClaims(**base)


def test_quote_token_round_trip_and_expiry(monkeypatch):
    claims = _make_claims()
    token = create_quote_token(claims)
    assert decode_quote_token(token, expected_user_id="u1").required_points == 100
    with pytest.raises(QuoteTokenError):
        decode_quote_token(token, expected_user_id="u2")


def test_quote_token_expired_raises(monkeypatch):
    """过期令牌必须被拒绝（jwt 自动校验 exp）。"""
    monkeypatch.setattr(settings, "points_quote_expire_seconds", -1)
    token = create_quote_token(_make_claims())
    with pytest.raises(QuoteTokenError):
        decode_quote_token(token, expected_user_id="u1")


def test_quote_token_wrong_type_rejected():
    """type != 'points_quote' 的令牌（如 access token）必须被拒绝。"""
    from app.core.security import create_access_token

    access_token = create_access_token(user_id="u1", token_version=1)
    with pytest.raises(QuoteTokenError):
        decode_quote_token(access_token, expected_user_id="u1")


def test_quote_token_tampered_signature_rejected():
    """修改令牌签名后必须解码失败。"""
    token = create_quote_token(_make_claims())
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(QuoteTokenError):
        decode_quote_token(tampered, expected_user_id="u1")


def test_quote_token_decoded_fields_match_claims():
    claims = _make_claims(
        business_type="image_generation",
        model_id="img-model",
        required_points=42,
    )
    decoded = decode_quote_token(
        create_quote_token(claims), expected_user_id="u1"
    )
    assert decoded.user_id == "u1"
    assert decoded.business_type == "image_generation"
    assert decoded.model_id == "img-model"
    assert decoded.params_hash == claims.params_hash
    assert decoded.required_points == 42


def test_hash_quote_params_is_deterministic():
    a = hash_quote_params({"a": 1, "b": 2})
    b = hash_quote_params({"b": 2, "a": 1})
    assert a == b
    assert isinstance(a, str) and len(a) == 64  # SHA-256 hex


def test_hash_quote_params_distinguishes_values():
    assert hash_quote_params({"a": 1}) != hash_quote_params({"a": 2})
