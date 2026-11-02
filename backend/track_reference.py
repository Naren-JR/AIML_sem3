"""Read supplied static references without treating them as race-aligned measurements."""
import csv
import hashlib
import json
from .data import ROOT, number
from .track_quality import track_quality
from .circuits import definition, reference_folder


def load_reference(circuit_id='australian-grand-prix'):
    entry = definition(circuit_id)
    if entry is None:
        raise ValueError('Unknown or excluded circuit')
    folder = reference_folder(circuit_id)
    if folder is None:
        return {'available': False, 'reason': 'Static reference not installed'}
    master_path = folder / 'master_track.json'
    folder = master_path.parent
    master = json.loads(master_path.read_text(encoding='utf-8-sig'))
    def rows(name):
        with (folder / name).open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    geometry = []
    for row in rows('track_geometry.csv'):
        x, y = number(row.get('x_source')), number(row.get('y_source'))
        if x is not None and y is not None:
            geometry.append({'x': x, 'y': y})
    sections = []
    for row in rows('sections.csv'):
        value = json.loads(row['value'])
        sections.append({'category': value[0], 'start_percent': value[1], 'end_percent': value[2]})
    corners = [{'number': row.get('Number'), 'x': number(row.get('X')), 'y': number(row.get('Y')),
                'source_distance': number(row.get('Distance'))} for row in rows('corners.csv')]
    event = master.get('event_or_circuit_label', entry[1])
    quality = track_quality(event)
    selected_session = next(iter(quality.get('event_summaries', [])), {}).get('geometry_source_folder_label')
    imported_source = str(master.get('geometry', {}).get('canonical_source', ''))
    version_conflict = (f'Imported geometry source is {imported_source}; processing report selects {selected_session}. Source versions require reconciliation.'
                        if selected_session and selected_session.casefold() not in imported_source.casefold() else None)
    for corner in corners:
        corner['reported_source_distance'] = corner['source_distance']
        corner['source_distance'] = None
        corner['distance_status'] = 'unverified_reference_lap_anchor_not_for_race_selection'
    display_geometry = []
    for point in geometry:
        if not display_geometry or point != display_geometry[-1]:
            display_geometry.append(point)
    return {'available': True, 'event': event, 'geometry': display_geometry,
            'source_geometry_point_count': len(geometry),
            'corners': corners, 'sections': sections,
            'telemetry_aligned': False, 'click_selection_enabled': False,
            'layout_identity': master.get('layout_identity'), 'geometry_metadata': master.get('geometry'),
            'aero_zone_rows': len(rows('active_aero_zones.csv')),
            'quality': quality,
            'source_version_conflict': version_conflict,
            'warning': 'Static reference only. Layout/year, coordinate units and race-distance alignment remain unverified. No activation is inferred.',
            'source': folder.relative_to(ROOT).as_posix(),
            'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()},
            'manifest': json.loads((folder / 'source_manifest.json').read_text(encoding='utf-8-sig'))}
