"""Vendor upstream SmilesDrawer, without executing npm scripts.

    python features/smiles/tools/vendor_smiles.py
    python features/smiles/tools/vendor_smiles.py --archive path/to/smiles-drawer-2.4.1.tgz

The package and transitive bundled dependencies are pinned by the archive hash.
Only two named files are read from the tarball; no paths are extracted from it.
"""
import argparse
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request

VERSION = '2.4.1'
URL = 'https://registry.npmjs.org/smiles-drawer/-/smiles-drawer-2.4.1.tgz'
SHA512 = ('909783f75069f04c0b4d0a2eab86b3ee19f9cd461d21a2d0a3216df1796caab8'
          'ae80f89939d04500324c5277ea0d8a72bb75caf521690604ee0ed733a5b4946c')
BUNDLE_SHA256 = '6b0397cd52a708eeafb995f191d6d972449377e5603ae603cb210f537666fddc'
FEATURE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Use an already downloaded npm tarball')
    args = parser.parse_args()
    if args.archive:
        data = args.archive.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read()
    if hashlib.sha512(data).hexdigest() != SHA512:
        raise SystemExit('Archive SHA-512 mismatch; nothing was written')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        bundle = archive.extractfile('package/dist/smiles-drawer.min.js').read()
        license_text = archive.extractfile('package/LICENSE.md').read()
    if hashlib.sha256(bundle).hexdigest() != BUNDLE_SHA256:
        raise SystemExit('Bundle SHA-256 mismatch; nothing was written')
    (FEATURE / 'smiles-drawer.js').write_bytes(bundle)
    (FEATURE / 'LICENSE-SMILESDRAWER.txt').write_bytes(license_text)
    print('Vendored unmodified smiles-drawer@' + VERSION)
    print('Bundle SHA-256: ' + BUNDLE_SHA256)


if __name__ == '__main__':
    main()
