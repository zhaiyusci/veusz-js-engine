#!/usr/bin/env python3
"""Vendor exact upstream classic scripts; standard library only, no npm/build.

Run normally to download pinned bytes, or --check to verify local artifacts
without network access. UPSTREAM.md records provenance and permission context.
"""
import argparse
import hashlib
from pathlib import Path
import urllib.request

REPOSITORY = 'https://github.com/zhaiyusci/MolecularRenaissance'
COMMIT = 'b351c7b22085ab9c107e4f526c86fc673d3702a6'
VERSION = '0.2.0'
RAW_BASE = 'https://raw.githubusercontent.com/zhaiyusci/MolecularRenaissance/' + COMMIT
# In dependency load order. Hashes are over raw bytes, not normalized text.
ARTIFACTS = (
    ('dot-regions.js', 27097, '641597db1605395112e223f8837948d3e5683f7641b545c0f6d0985d440bf647'),
    ('boundaries.js', 39769, '4cb52442ab94dcf56962dc89c7aa13b7dc63f802fd8d873caf3e08cd75f9a74f'),
    ('wash.js', 28091, 'af954e4c449475b6587741d44302c72c744296f4d5405e2406b2d851eaa05751'),
    ('dots.js', 36547, '528939c79a007d24e53497f2af0d43852a1a6f0d60163b3440c648805cc15241'),
    ('renderer.js', 181441, '339d294c87367656cd9ed70299768db6ee6a1609fcaf1d82cc1f4410304c2fa4'),
)
DESTINATION = Path(__file__).resolve().parents[1]


def verify(name, data, length, digest):
    actual = hashlib.sha256(data).hexdigest()
    if len(data) != length or actual != digest:
        raise ValueError(f'{name}: integrity mismatch: {len(data)} bytes, SHA256 {actual}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='verify local files offline')
    args = parser.parse_args()
    downloaded = []
    for name, length, digest in ARTIFACTS:
        if args.check:
            data = (DESTINATION / name).read_bytes()
        else:
            request = urllib.request.Request(RAW_BASE + '/' + name,
                                             headers={'User-Agent': 'veusz-molecule3d-vendor'})
            with urllib.request.urlopen(request, timeout=30) as response:
                # Bound unexpected server payloads, and reject oversized bytes.
                data = response.read(length + 1)
        verify(name, data, length, digest)
        downloaded.append((name, data))
        print(f'OK {name} {length} {digest}')
    # Verify the entire download set before touching any installed artifact.
    if not args.check:
        for name, data in downloaded:
            (DESTINATION / name).write_bytes(data)
    print(f'MolecularRenaissance {VERSION} @ {COMMIT}; ' +
          ('local bytes verified' if args.check else 'unmodified bytes vendored'))


if __name__ == '__main__':
    main()
