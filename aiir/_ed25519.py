# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Pure-Python Ed25519 helpers for offline transparency verification.

Portions of the field arithmetic and point operations in this module are
derived from Daniel J. Bernstein's public-domain Ed25519 reference
implementation (the xrecover routine using I = 2^((q-1)/4), the base point
By = 4*inv(5), the on-curve test, and affine (twisted) Edwards point
addition). That reference is dedicated to the public domain.

AIIR's modifications over the reference: fail-closed verify() with explicit
length checks, canonical-y range rejection and on-curve validation in
decode_point, cofactor/subgroup ([L]A == identity) checks, scalar-range
(s < L) enforcement, low-order/identity point rejection, PEP 8 naming, and
type annotations. The signer helpers are non-constant-time test fixtures.
"""

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


def _is_identity(point: tuple[int, int]) -> bool:
    """Return True if *point* is the Edwards group identity (0, 1) mod Q.

    Catches BOTH the canonical encoding (x=0, y=1) AND the non-canonical
    encoding (x=Q, y=1) that decode_point can return when the sign bit is set
    on a zero x-coordinate (Q - 0 = Q, unreduced).  Using ``% _Q`` is the
    correct predicate; a tuple-equality check against ``_IDENTITY = (0, 1)``
    would miss the (Q, 1) case and leave a universal-forgery hole open.
    """
    x, y = point
    return x % _Q == 0 and y % _Q == 1


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
    """Test fixture only.  NOT constant-time; leaks secret material via timing;
    never call with production private keys.  Production code imports only verify().
    """
    if len(seed) != 32:
        raise ValueError("Ed25519 seeds must be 32 bytes")
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def public_key_from_seed(seed: bytes) -> bytes:
    """Test fixture only.  NOT constant-time; leaks secret material via timing;
    never call with production private keys.  Production code imports only verify().
    """
    scalar, _ = _secret_expand(seed)
    return encode_point(_scalar_mult(_BASE, scalar))


def sign(seed: bytes, message: bytes) -> bytes:
    """Test fixture only.  NOT constant-time; leaks secret material via timing;
    never call with production private keys.  Production code imports only verify().
    """
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

    if _is_identity(point_a) or _is_identity(point_r):
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
