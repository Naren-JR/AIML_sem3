"""Validated local race registry with bounded in-memory dataset caching."""
from functools import lru_cache
from .data import ROOT, Dataset

RACES = {'australian-grand-prix':'Australian Grand Prix','austrian-grand-prix':'Austrian Grand Prix','italian-grand-prix':'Italian Grand Prix'}


def race_path(circuit_id):
    if circuit_id not in RACES:
        raise ValueError('No imported race telemetry for selected circuit')
    return ROOT/f'dataPreprocess/rawData/2026/{circuit_id}/telemetry.csv'


def available_races():
    return [{'id':key,'event':event,'year':2026,'driver':'Kimi Antonelli','session':'GP Race'}
            for key,event in RACES.items() if race_path(key).exists() and race_path(key).with_name('manifest.json').exists()]


@lru_cache(maxsize=5)
def load_race(circuit_id):
    return Dataset(race_path(circuit_id))
