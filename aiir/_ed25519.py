# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Pure-Python Ed25519 helpers for offline transparency verification."""

from __future__ import annotations

import hashlib


_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _Q - 2, _Q)) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)
_IDENTITY = (0, 1)


def _inv(value: int) -> int:
    return pow(value, _Q - 2, _Q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x & 1:
        x = _Q - x
    return x


_BY = (4 * _inv(5)) % _Q
_BX = _xrecover(_BY)
_BASE = (_BX, _BY)


def _is_on_curve(point: tuple[int, int]) -> bool:
    x, y = point
    return (-x * x + y * y - 1 - _D * x * x * y * y) % _Q == 0


def _edwards_add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = left
    x2, y2 = right
    denominator_x = _inv(1 + _D * x1 * x2 * y1 * y2)
    denominator_y = _inv(1 - _D * x1 * x2 * y1 * y2)
    x3 = (x1 * y2 + x2 * y1) * denominator_x
    y3 = (y1 * y2 + x1 * x2) * denominator_y
    return x3 % _Q, y3 % _Q


def _scalar_mult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    result = _IDENTITY
    addend = point
    value = scalar
    while value > 0:
        if value & 1:
            result = _edwards_add(result, addend)
        addend = _edwards_add(addend, addend)
        value >>= 1
    return result


def encode_point(point: tuple[int, int]) -> bytes:
    x, y = point
    encoded = y | ((x & 1) << 255)
    return encoded.to_bytes(32, "little")


def decode_point(encoded: bytes) -> tuple[int, int]:
    if len(encoded) != 32:
        raise ValueError("Ed25519 points must be 32 bytes")
    value = int.from_bytes(encoded, "little")
    y = value & ((1 << 255) - 1)
    if y >= _Q:
        raise ValueError("Ed25519 point has out-of-range y coordinate")
    x = _xrecover(y)
    if (x & 1) != (value >> 255):
        x = _Q - x
    point = (x, y)
    if not _is_on_curve(point):
        raise ValueError("Ed25519 point is not on the curve")
    return point


def _secret_expand(seed: bytes) -> tuple[int, bytes]:
    if len(seed) != 32:
        raise ValueError("Ed25519 seeds must be 32 bytes")
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def public_key_from_seed(seed: bytes) -> bytes:
    scalar, _ = _secret_expand(seed)
    return encode_point(_scalar_mult(_BASE, scalar))


def sign(seed: bytes, message: bytes) -> bytes:
    scalar, prefix = _secret_expand(seed)
    public_key = public_key_from_seed(seed)
    nonce = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    encoded_r = encode_point(_scalar_mult(_BASE, nonce))
    challenge = (
        int.from_bytes(
            hashlib.sha512(encoded_r + public_key + message).digest(),
            "little",
        )
        % _L
    )
    scalar_s = (nonce + challenge * scalar) % _L
    return encoded_r + scalar_s.to_bytes(32, "little")


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False

    try:
        point_a = decode_point(public_key)
        point_r = decode_point(signature[:32])
    except ValueError:
        return False

    if _scalar_mult(point_a, _L) != _IDENTITY:
        return False
    if _scalar_mult(point_r, _L) != _IDENTITY:
        return False

    scalar_s = int.from_bytes(signature[32:], "little")
    if scalar_s >= _L:
        return False

    challenge = (
        int.from_bytes(
            hashlib.sha512(signature[:32] + public_key + message).digest(),
            "little",
        )
        % _L
    )
    left = _scalar_mult(_BASE, scalar_s)
    right = _edwards_add(point_r, _scalar_mult(point_a, challenge))
    return left == right
