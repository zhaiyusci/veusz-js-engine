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
COMMIT = '7b93c9b857a63e2610abe459cca49ba0a9190773'
VERSION = '0.2.0'
RAW_BASE = 'https://raw.githubusercontent.com/zhaiyusci/MolecularRenaissance/' + COMMIT
# In dependency load order. Hashes are over raw bytes, not normalized text.
ARTIFACTS = (
    ('dot-regions.js', 27436, '31194c110bbf515fe899559c629cb8db4f56c4b4528acb390c4b493f01d771a1'),
    ('boundaries.js', 53328, 'dad09e51b6add3abd714aaa127107f2fca310640300b3eeb7aeb98de166d37d6'),
    ('wash.js', 28091, 'af954e4c449475b6587741d44302c72c744296f4d5405e2406b2d851eaa05751'),
    ('dots.js', 45776, '87c023035c954e7fd2cd82785ee40dfe83e212cdda9a25ce881fdf9924a56981'),
    ('renderer.js', 1321176, '4319934870a1f2645944d6600bf561fd5fff660271cb6b2a02b98210cb1262ba'),
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
