# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Security-critical regression tests for C7 Ed25519 identity-point hardening.

These tests prove that:
  - Both the canonical (0, 1) and the non-canonical (Q, 1) identity-point
    encodings are rejected by verify() before they can be used as universal
    forgery keys.
  - Legitimate keys and signatures are unaffected by the new guard.
  - _is_identity() correctly classifies all three cases: canonical identity,
    non-canonical identity (x=Q unreduced from decode_point), and the base
    point.
"""

from __future__ import annotations

import os
import unittest

import aiir._ed25519 as ed25519
from aiir._ed25519 import (
    _Q,
    _is_identity,
    decode_point,
    public_key_from_seed,
    sign,
    verify,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical_identity_bytes() -> bytes:
    """Encode the Edwards identity (0, 1) in canonical Ed25519 form.

    Little-endian 32-byte representation: y=1 with x-sign bit 0.
    The integer value is exactly 1.
    """
    return (1).to_bytes(32, "little")


def _noncanonical_identity_bytes() -> bytes:
    """Encode (Q, 1) — the non-canonical identity — as little-endian bytes.

    2^255 + 1 little-endian: the top bit encodes x's sign; since _xrecover(1)
    returns 0 and 0 & 1 == 0, setting the sign bit forces x = Q - 0 = Q.
    Q mod Q == 0, so this is still the identity point after reduction.
    """
    return ((1 << 255) + 1).to_bytes(32, "little")


# ---------------------------------------------------------------------------
# Tests for _is_identity predicate
# ---------------------------------------------------------------------------


class TestIsIdentityPredicate(unittest.TestCase):
    """Unit tests for the _is_identity helper (both sides of each branch)."""

    def test_canonical_identity_is_identified(self):
        # (0, 1) is the group identity; x % Q == 0 and y % Q == 1
        self.assertTrue(_is_identity((0, 1)))

    def test_noncanonical_identity_is_identified(self):
        # (Q, 1) can be returned by decode_point when the sign bit is set on
        # a zero x-coordinate; Q % Q == 0 so the predicate must use modular
        # arithmetic to catch it.
        self.assertTrue(_is_identity((_Q, 1)))

    def test_base_point_is_not_identity(self):
        # The base point _BASE has a non-zero x-coordinate and a y != 1;
        # _is_identity must return False for any non-degenerate point.
        base = ed25519._BASE
        self.assertFalse(_is_identity(base))

    def test_arbitrary_nonidentity_point_is_not_identity(self):
        # A random legitimate public key is never the identity.
        seed = bytes(range(1, 33))
        pubkey_bytes = public_key_from_seed(seed)
        point = decode_point(pubkey_bytes)
        self.assertFalse(_is_identity(point))


# ---------------------------------------------------------------------------
# Tests for the forgery vectors — BOTH must be rejected by verify()
# ---------------------------------------------------------------------------


class TestIdentityForgeryRejection(unittest.TestCase):
    """Regression tests that close the identity-point forgery vector.

    Before C7, verify(identity_pubkey, any_msg, identity_R + s=0) == True
    for both encoding forms of the identity.  After C7, both must be False.
    """

    MSG = b"arbitrary forgery test message"

    def _forged_signature(self, r_bytes: bytes) -> bytes:
        """Build a forgery: R = r_bytes, s = 0 (32 zero bytes)."""
        return r_bytes + b"\x00" * 32

    # -- Canonical (0, 1) identity encoding ---------------------------------

    def test_canonical_identity_pubkey_forgery_rejected(self):
        """verify() must reject a forged sig when the public key is (0, 1)."""
        identity = _canonical_identity_bytes()
        forged = self._forged_signature(identity)
        result = verify(identity, self.MSG, forged)
        self.assertFalse(
            result,
            "Identity public key (0,1) must never verify any message",
        )

    def test_canonical_identity_r_forgery_rejected(self):
        """verify() must reject a forged sig when R encodes the (0, 1) identity."""
        # Use a real (non-identity) pubkey so we isolate the R check.
        seed = bytes([0xAB]) * 32
        pubkey = public_key_from_seed(seed)
        identity = _canonical_identity_bytes()
        forged = self._forged_signature(identity)
        result = verify(pubkey, self.MSG, forged)
        self.assertFalse(
            result,
            "Signature whose R is identity (0,1) must be rejected",
        )

    # -- Non-canonical (Q, 1) identity encoding (2^255+1 little-endian) -----

    def test_noncanonical_identity_pubkey_forgery_rejected(self):
        """verify() must reject a forged sig when the public key encodes (Q, 1).

        The little-endian bytes of 2^255 + 1 set the top (sign) bit, causing
        decode_point to compute x = Q - 0 = Q.  Before the fix, [L]*(Q,1)
        == identity so the subgroup check passed; the forgery returned True.
        """
        nc_identity = _noncanonical_identity_bytes()
        # Sanity-check: decode_point must succeed and return (Q, 1)
        point = decode_point(nc_identity)
        self.assertEqual(point[0], _Q, "Decoded x should equal Q (unreduced)")
        self.assertEqual(point[1], 1, "Decoded y should equal 1")
        # The guard must catch x % Q == 0 even when x == Q
        self.assertTrue(_is_identity(point))
        # Full verify() must reject the forgery
        forged = self._forged_signature(nc_identity)
        result = verify(nc_identity, self.MSG, forged)
        self.assertFalse(
            result,
            "Non-canonical identity pubkey (Q,1) must never verify any message",
        )

    def test_noncanonical_identity_r_forgery_rejected(self):
        """verify() must reject a forged sig when R encodes the (Q, 1) identity."""
        seed = bytes([0xCD]) * 32
        pubkey = public_key_from_seed(seed)
        nc_identity = _noncanonical_identity_bytes()
        forged = self._forged_signature(nc_identity)
        result = verify(pubkey, self.MSG, forged)
        self.assertFalse(
            result,
            "Signature whose R is non-canonical identity (Q,1) must be rejected",
        )


# ---------------------------------------------------------------------------
# Regression: legitimate signatures are not broken by the new guard
# ---------------------------------------------------------------------------


class TestLegitimateSignatureUnaffected(unittest.TestCase):
    """Prove that no legitimate key or signature is newly rejected by C7."""

    def test_valid_signature_still_verifies(self):
        """A freshly generated Ed25519 signature must still return True."""
        seed = os.urandom(32)
        pubkey = public_key_from_seed(seed)
        msg = b"legitimate message"
        sig = sign(seed, msg)
        self.assertTrue(verify(pubkey, msg, sig))

    def test_tampered_message_still_rejected(self):
        """Tampering with the message must still yield False after C7."""
        seed = os.urandom(32)
        pubkey = public_key_from_seed(seed)
        msg = b"original message"
        sig = sign(seed, msg)
        self.assertTrue(verify(pubkey, msg, sig))
        self.assertFalse(verify(pubkey, b"tampered message", sig))

    def test_tampered_signature_still_rejected(self):
        """Flipping a byte in the signature must still yield False."""
        seed = os.urandom(32)
        pubkey = public_key_from_seed(seed)
        msg = b"message"
        sig = sign(seed, msg)
        # Flip the last byte of the scalar part
        bad_sig = sig[:63] + bytes([sig[63] ^ 0xFF])
        self.assertFalse(verify(pubkey, msg, bad_sig))

    def test_rfc8032_test_vector_still_verifies(self):
        """The RFC 8032 §6.1 test-vector-1 must still pass."""
        seed = bytes.fromhex(
            "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
        )
        public_key = bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
        )
        signature = bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a"
            "84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46b"
            "d25bf5f0595bbe24655141438e7a100b"
        )
        self.assertTrue(verify(public_key, b"", signature))

    def test_300_random_seeds_produce_no_identity_collisions(self):
        """No legitimate seed should produce an identity public key.

        Sanity-check that _is_identity returns False for 300 random keys,
        confirming the guard never fires on real inputs.
        """
        for i in range(300):
            seed = (i).to_bytes(32, "little") if i < 256 else os.urandom(32)
            pubkey_bytes = public_key_from_seed(seed)
            point = decode_point(pubkey_bytes)
            self.assertFalse(
                _is_identity(point),
                f"Seed {i!r} produced an identity public key — this must never happen",
            )


if __name__ == "__main__":
    unittest.main()
