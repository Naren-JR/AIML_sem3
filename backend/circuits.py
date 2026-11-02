"""Explicit event identities, local availability, and dated participation evidence."""
import csv
from .data import ROOT

# No excluded Bahrain/Chinese/Japanese/Spanish event; Barcelona is a separate event.
EVENTS = [
 ('australian-grand-prix','Australia','Albert Park','albert-park-circuit',True),
 ('austrian-grand-prix','Austria','Red Bull Ring','red-bull-ring',True),
 ('azerbaijan-grand-prix','Azerbaijan','Baku','baku-city-circuit',True),
 ('barcelona-grand-prix','Barcelona-Catalunya','Barcelona-Catalunya','circuit-de-barcelona-catalunya',True),
 ('belgian-grand-prix','Belgium','Spa-Francorchamps','circuit-de-spa-francorchamps',True),
 ('british-grand-prix','Great Britain','Silverstone','silverstone',True),
 ('canadian-grand-prix','Canada','Circuit Gilles-Villeneuve','canada',True),
 ('dutch-grand-prix','Netherlands','Zandvoort','circuit-zandvoort',True),
 ('hungarian-grand-prix','Hungary','Hungaroring','hungary',True),
 ('italian-grand-prix','Italy','Monza','monza',True),
 ('miami-grand-prix','Miami','Miami International Autodrome','miami-international-autodrome',True),
 ('monaco-grand-prix','Monaco','Circuit de Monaco','circuit-de-monaco',True),
 ('singapore-grand-prix','Singapore','Marina Bay','marina-bay-street-circuit',True),
 ('united-states-grand-prix','United States','Circuit of the Americas','circuit-of-the-americas',True),
 ('mexico-city-grand-prix','Mexico','Autódromo Hermanos Rodríguez','autodrome-hermanos-rodriguez',True),
 ('abu-dhabi-grand-prix','Abu Dhabi','Yas Marina','yas-marina-circuit',False),
 ('emilia-romagna-grand-prix','Emilia-Romagna','Imola','emilia',False),
 ('qatar-grand-prix','Qatar','Lusail','lusail-international-circuit',False),
 ('saudi-arabian-grand-prix','Saudi Arabia','Jeddah','jeddah-corniche-circuit',False),
 ('são-paulo-grand-prix','Brazil','Interlagos','interlagos-circuit',False)]
SOURCE_2026='https://www.formula1.com/en/results/2026/drivers/ANDANT01/kimi-antonelli'
SOURCE_2025='https://www.formula1.com/en/results/2025/drivers/ANDANT01/andrea-kimi-antonelli'


def definition(circuit_id):
    return next((e for e in EVENTS if e[0]==circuit_id),None)


def reference_folder(circuit_id):
    options=sorted((ROOT/'frontend_unzipped').glob(f'*/{circuit_id}/master_track.json'))
    return options[0].parent if options else None


def catalog():
    rows=[]
    for key,event,name,stem,current in EVENTS:
        folder=reference_folder(key)
        section_file=ROOT/f'trackData/raw/sections/{stem}.json'
        if folder is None and not section_file.exists():
            continue
        geometry=0
        if folder and (folder/'track_geometry.csv').exists():
            with (folder/'track_geometry.csv').open(encoding='utf-8-sig',newline='') as f:
                geometry=sum(1 for _ in csv.DictReader(f))
        telemetry=key=='australian-grand-prix' and (ROOT/'dataPreprocess/rawData/australiar.csv').exists()
        rows.append({'id':key,'event':event,'name':name,'participation_years':[2025,2026] if current else [2025],
                     'participation_source':SOURCE_2026 if current else SOURCE_2025,'verified_on':'2026-11-02',
                     'race_telemetry_available':telemetry,'telemetry_year':2026 if telemetry else None,
                     'geometry_points':geometry,'sections_available':section_file.exists(),
                     'reference_available':folder is not None,'mode':'race_analysis' if telemetry else 'static_reference_only'})
    return rows
