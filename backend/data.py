"""Lossless source adapter. Derived data never overwrite recorded channels."""
from pathlib import Path
import csv
import hashlib
import math
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RACE = ROOT / 'dataPreprocess/rawData/2026/australian-grand-prix/telemetry.csv'
if not RACE.exists():
    RACE = ROOT / 'dataPreprocess/rawData/australiar.csv'
UNITS = {'time': 's (session cumulative)', 'distance': 'm (lap local)',
         'rel_distance': 'fraction', 'speed': 'km/h', 'rpm': 'rpm', 'gear': 'integer',
         'throttle': '%', 'brake': 'binary', 'x': 'source units (unverified)',
         'y': 'source units (unverified)', 'z': 'source units (unverified)',
         'acc_x': 'unverified', 'acc_y': 'unverified', 'acc_z': 'unverified',
         'DistanceToDriverAhead': 'm (source convention)'}


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


class Dataset:
    def __init__(self, path=RACE):
        self.path = Path(path)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        manifest_path = self.path.with_name('manifest.json')
        self.manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else None
        if self.manifest and self.manifest['telemetry_sha256'] != self.sha256:
            raise ValueError('Imported telemetry checksum does not match manifest')
        with self.path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            if not {'time', 'distance', 'rel_distance', 'speed'} <= set(fields):
                raise ValueError('Required channels: time, distance, rel_distance, speed')
            raw = list(reader)
        if not raw:
            raise ValueError('Telemetry is empty')
        self.fields = fields
        self.samples = []
        lap = 1
        previous_rel = None
        previous_time = None
        self.quality = {'invalid_timestamps': 0, 'duplicate_timestamps': 0,
                        'large_gaps': 0, 'missing': {k: 0 for k in fields}}
        # Infer laps in original order before chronological integration.
        for index, source in enumerate(raw):
            recorded = {k: number(v) for k, v in source.items()}
            for k, v in recorded.items():
                self.quality['missing'][k] += v is None
            rel, t = recorded['rel_distance'], recorded['time']
            if 'lap_number' in fields:
                original = recorded['lap_number']
                if original is None or original != int(original) or int(original) not in (lap, lap+1) or (index==0 and original!=1):
                    raise ValueError('Invalid or missing original lap sequence')
                lap = int(original)
            elif previous_rel is not None and rel is not None and previous_rel > .75 and rel < .25:
                lap += 1
            if rel is not None:
                previous_rel = rel
            if t is None:
                self.quality['invalid_timestamps'] += 1
                continue
            if previous_time is not None and t < previous_time:
                raise ValueError('Time reversal: repair source chronology explicitly before modelling')
            flags = []
            if previous_time == t:
                self.quality['duplicate_timestamps'] += 1
                flags.append('duplicate_timestamp')
            if previous_time is not None and t - previous_time > .5:
                self.quality['large_gaps'] += 1
                flags.append('sampling_gap')
            previous_time = t
            self.samples.append({'sample_id': index, 'lap': lap, 'recorded': recorded,
                                 'source_fields': source, 'calculated': {}, 'quality_flags': flags})
        if not self.samples or self.samples[0]['recorded']['time'] != 0:
            raise ValueError('Full race must start at time 0 to impose the initial condition')
        # Causal local linear fit over 0.6 s. Duplicate times are safe; no gap bridging.
        start = 0
        for i, sample in enumerate(self.samples):
            t = sample['recorded']['time']
            if i and t - self.samples[i-1]['recorded']['time'] > .5:
                start = i
            while start < i and t - self.samples[start]['recorded']['time'] > .6:
                start += 1
            pairs = [(s['recorded']['time'], s['recorded']['speed'])
                     for s in self.samples[start:i+1] if s['recorded']['speed'] is not None]
            a = None
            if len(pairs) >= 2 and pairs[-1][0] - pairs[0][0] > .05:
                times = np.array([p[0] - t for p in pairs])
                speeds = np.array([p[1] / 3.6 for p in pairs])
                centered = times - times.mean()
                denominator = float(centered @ centered)
                if denominator > 1e-12:
                    a = float(centered @ (speeds - speeds.mean()) / denominator)
            sample['calculated'] = {'acceleration_mps2': a,
                                    'speed_mps': None if sample['recorded']['speed'] is None else sample['recorded']['speed'] / 3.6}
        self.by_lap = {}
        for s in self.samples:
            self.by_lap.setdefault(s['lap'], []).append(s)
        self.laps = [{'lap': k, 'samples': len(v), 'start_time_s': v[0]['recorded']['time'],
                      'end_time_s': v[-1]['recorded']['time'],
                      'max_distance_m': max((s['recorded']['distance'] for s in v if s['recorded']['distance'] is not None), default=0),
                      'numbering': 'original source lap_number' if 'lap_number' in fields else 'inferred from rel_distance wrap; original lap IDs unavailable'}
                     for k, v in self.by_lap.items()]
        diagnostics = []
        for summary in self.laps:
            rows = self.by_lap[summary['lap']]
            integrated = 0.
            known_duration = 0.
            for a, b in zip(rows, rows[1:]):
                dt = b['recorded']['time'] - a['recorded']['time']
                va, vb = a['calculated']['speed_mps'], b['calculated']['speed_mps']
                if 0 < dt <= .5 and va is not None and vb is not None:
                    integrated += .5 * (va + vb) * dt
                    known_duration += dt
            distances = [s['recorded']['distance'] for s in rows if s['recorded']['distance'] is not None]
            source_span = max(distances)-min(distances) if distances else None
            diagnostics.append({'lap': summary['lap'], 'speed_integrated_distance_m': integrated,
                                'recorded_distance_span_m': source_span, 'known_duration_s': known_duration,
                                'difference_m': None if source_span is None else integrated-source_span})
        self.quality['distance_diagnostics'] = diagnostics

    def lap(self, lap):
        if lap not in self.by_lap:
            raise KeyError(f'Lap {lap} is unavailable')
        return self.by_lap[lap]

    def point(self, lap, distance):
        samples = [s for s in self.lap(lap) if s['recorded']['distance'] is not None]
        if not samples:
            raise ValueError('No distance samples in this lap')
        low, high = min(s['recorded']['distance'] for s in samples), max(s['recorded']['distance'] for s in samples)
        if not 0 <= distance <= high:
            raise ValueError(f'Distance must be between 0 and {high:.3f} m')
        return min(samples, key=lambda s: abs(s['recorded']['distance'] - distance))

    def metadata(self):
        metadata = {'driver': 'Kimi Antonelli', 'session': 'GP Race', 'event': 'Australian Grand Prix',
                'year': 2026, 'source': str(self.path.relative_to(ROOT)) if self.path.is_relative_to(ROOT) else self.path.name,
                'sha256': self.sha256, 'samples': len(self.samples), 'laps': len(self.laps),
                'fields': self.fields, 'units': UNITS, 'quality': self.quality,
                'provenance': 'Supplied CSV; fetchKimi.py attributes it to TracingInsights/2026. Upstream commit and retrieval date absent.',
                'unit_evidence': 'Project v2 specifies km/h, seconds and metres. Position/acceleration units remain unverified.',
                'excluded_events': ['Bahrain', 'China', 'Japan', 'Spain'],
                'lap_numbering': 'inferred; 57 relative-distance wraps, no source lap identifiers',
                'missing_context': ['battery current/voltage', 'electrical power', 'ICE map', 'Straight Mode activation', 'pit/flag metadata', 'source commit']}
        if self.manifest:
            metadata.update(event=self.manifest['event'], circuit_id=self.manifest['circuit_id'],
                            provenance=f"TracingInsights/2026, commit {self.manifest['commit']}; original JSON retained locally",
                            lap_numbering='Original source lap IDs; original session-clock gaps retained',
                            manifest=self.manifest)
            metadata['missing_context'] = ['battery current/voltage', 'electrical power', 'ICE map', 'Straight Mode activation']
        return metadata
