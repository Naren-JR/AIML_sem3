"""Restore known archived graphics and account for every supplied report warning."""
import json
from pathlib import Path
import zipfile
from backend.data import ROOT
from backend.track_quality import track_quality


def restore_assets(root=ROOT):
    restored = []
    for kind in ('svg', 'webp'):
        archive = root / f'trackData/raw/images/{kind}.zip'
        if not archive.exists():
            continue
        destination = (root / f'trackData/raw/images/{kind}').resolve()
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                member = Path(name)
                if name.endswith('/') or member.suffix.lower() != f'.{kind}':
                    continue
                if '..' in member.parts or member.is_absolute():
                    raise ValueError('Unsafe archived asset path')
                target = (destination / member.name).resolve()
                if target.parent != destination:
                    raise ValueError('Archived asset leaves destination')
                payload = z.read(name)
                if target.exists():
                    if target.read_bytes() != payload:
                        raise ValueError(f'Existing asset differs; preserved: {target}')
                else:
                    destination.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                restored.append(str(target.relative_to(root)))
    return restored


def main():
    restored = restore_assets()
    quality = track_quality()
    report = {'asset_paths_verified_or_restored': restored,
              'report_rewritten': False, 'quality': quality,
              'remaining_blockers': ['Original circuitMap.json and session raw sources missing locally',
                                     'Historical layout compatibility and telemetry alignment unverified',
                                     'Imported exports and supplied processing report select different sessions',
                                     'Image annotations lack verified activation distances',
                                     '70 reported weather/race-control sessions are unverified and not locally supplied']}
    destination = ROOT / 'results/track_reconciliation.json'
    destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Verified/restored {len(restored)} graphics; accounted for {len(quality["warnings"])} warnings and {len(quality["candidates"])} image candidates.')
    print(f'Written {destination}. Original report and imported sources preserved.')


if __name__ == '__main__':
    main()
