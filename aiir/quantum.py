# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
Quantum workload provenance — public re-export surface.

Usage::

    from aiir.quantum import package, bind, verify

See :mod:`aiir._quantum` for full documentation.
"""

from aiir._quantum import (  # noqa: F401
    # Core workflow
    package,
    bind,
    verify,
    verify_or_explain,
    # I/O
    save_bundle,
    load_bundle,
    # Schema constants
    WORKLOAD_SCHEMA,
    EXECUTION_SCHEMA,
    BUNDLE_SCHEMA,
    LOGICAL_WORKLOAD_SCHEMA,
    # Provider constants
    PROVIDER_IBM,
    PROVIDER_BRAKET,
    PROVIDER_CIRQ,
    PROVIDER_RIGETTI,
    PROVIDER_IONQ,
    PROVIDER_PENNYLANE,
    PROVIDER_GENERIC,
)

__all__ = [
    "package",
    "bind",
    "verify",
    "verify_or_explain",
    "save_bundle",
    "load_bundle",
    "WORKLOAD_SCHEMA",
    "EXECUTION_SCHEMA",
    "BUNDLE_SCHEMA",
    "LOGICAL_WORKLOAD_SCHEMA",
    "PROVIDER_IBM",
    "PROVIDER_BRAKET",
    "PROVIDER_CIRQ",
    "PROVIDER_RIGETTI",
    "PROVIDER_IONQ",
    "PROVIDER_PENNYLANE",
    "PROVIDER_GENERIC",
]
