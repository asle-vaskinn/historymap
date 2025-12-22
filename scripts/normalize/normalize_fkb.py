#!/usr/bin/env python3
"""
FKB-Bygning (Kartverket) building data normalization.

Converts FKB-Bygning GeoJSON to normalized schema.
FKB-Bygning is the authoritative source for current building geometry in Norway.

Key FKB properties:
- bygningsnummer: Links to Matrikkelen (building registry)
- bygningstype: Building type code (SOSI standard)
- datafangstdato: Date of data capture
- oppdateringsdato: Last update date
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseNormalizer


# SOSI building type codes → simplified categories
# Reference: https://register.geonorge.no/sosi-kodelister/fkb/bygning/4.6/bygningstype
BYGNINGSTYPE_MAP = {
    # Residential
    '111': 'residential',  # Enebolig
    '112': 'residential',  # Enebolig med hybel/sokkelleilighet
    '113': 'residential',  # Våningshus
    '121': 'residential',  # Tomannsbolig
    '122': 'residential',  # Tomannsbolig, vertikaldelt
    '123': 'residential',  # Våningshus tomannsbolig
    '131': 'residential',  # Rekkehus
    '133': 'residential',  # Kjedehus
    '135': 'residential',  # Terrassehus
    '136': 'residential',  # Andre småhus m 3 boliger eller fl
    '141': 'residential',  # Stort boligbygg (blokk)
    '142': 'residential',  # Stort boligbygg (blokk lavblokk)
    '143': 'residential',  # Stort boligbygg (blokk høyblokk)
    '144': 'residential',  # Stort boligbygg (bygård)
    '145': 'residential',  # Stort frittliggende
    '146': 'residential',  # Kombinert bolig/næring

    # Industrial
    '211': 'industrial',   # Fabrikkbygning
    '212': 'industrial',   # Verkstedbygning
    '214': 'industrial',   # Lagerhall
    '216': 'industrial',   # Kjøle/fryselager
    '219': 'industrial',   # Annen industribygning

    # Commercial
    '311': 'commercial',   # Kontor/administrasjonsbygning
    '312': 'commercial',   # Bankbygning
    '313': 'commercial',   # Postkontor
    '319': 'commercial',   # Annen kontorbygning
    '321': 'commercial',   # Kjøpesenter
    '322': 'commercial',   # Butikk/forretning
    '323': 'commercial',   # Bensinstasjon
    '329': 'commercial',   # Annen forretningsbygning

    # Public/institutional
    '611': 'public',       # Barnehage
    '612': 'public',       # Barneskole
    '613': 'public',       # Ungdomsskole
    '614': 'public',       # Kombinert skole
    '615': 'public',       # Videregående skole
    '616': 'public',       # Universitets/høgskolebygning
    '619': 'public',       # Annen skolebygning
    '621': 'public',       # Museum/galleri
    '623': 'public',       # Bibliotek
    '629': 'public',       # Annen kulturbygning
    '641': 'public',       # Sykehus
    '642': 'public',       # Sykehjem
    '651': 'public',       # Fengsel
    '661': 'public',       # Brannstasjon
    '662': 'public',       # Politistasjon
    '671': 'public',       # Rådhus

    # Religious
    '671': 'religious',    # Kirke/kapell
    '672': 'religious',    # Bedehus/menighetshus
    '673': 'religious',    # Krematorium/gravkapell
    '674': 'religious',    # Synagoge/moské
    '675': 'religious',    # Kloster

    # Agricultural
    '241': 'agricultural', # Driftsbygning
    '243': 'agricultural', # Veksthus
    '244': 'agricultural', # Driftsbygning fiske/fangst
    '245': 'agricultural', # Naust/båthus
    '248': 'agricultural', # Annen landbruksbygning

    # Transport
    '441': 'transport',    # Garasje/bilverksted
    '449': 'transport',    # Annen garasje/hangar

    # Leisure
    '161': 'leisure',      # Fritidsbolig (hytte)
    '162': 'leisure',      # Helårsbolig som fritidsbolig
    '163': 'leisure',      # Våningshus som fritidsbolig
    '171': 'leisure',      # Seterhus
    '181': 'leisure',      # Garasje/uthus til bolig
    '182': 'leisure',      # Uthus til fritidsbolig
    '183': 'leisure',      # Naust
}


def map_building_type(bygningstype: Optional[str]) -> Optional[str]:
    """Map FKB bygningstype code to simplified category."""
    if not bygningstype:
        return None
    return BYGNINGSTYPE_MAP.get(str(bygningstype).strip())


class Normalizer(BaseNormalizer):
    """FKB-Bygning official building data normalizer."""

    def __init__(self, **kwargs):
        super().__init__('fkb_bygning', **kwargs)

    def normalize(self) -> List[Dict]:
        """Normalize FKB-Bygning to common schema."""

        # Look for raw data
        raw_file = self.raw_dir / 'fkb_bygning.geojson'

        if not raw_file.exists():
            raise FileNotFoundError(
                f"No FKB-Bygning raw data found at {raw_file}\n"
                f"Run: python -m scripts.ingest.fkb_bygning"
            )

        print(f"  Reading from: {raw_file}")

        with open(raw_file) as f:
            data = json.load(f)

        features = []
        skipped = {'no_geometry': 0, 'no_id': 0, 'invalid': 0}

        for feat in data.get('features', []):
            props = feat.get('properties', {})
            geom = feat.get('geometry')

            # Skip features without geometry
            if not geom or not geom.get('coordinates'):
                skipped['no_geometry'] += 1
                continue

            # Get building ID (bygningsnummer links to Matrikkelen)
            bygningsnummer = props.get('bygningsnummer')
            lokalid = props.get('lokalId') or props.get('identifikasjon', {}).get('lokalId')

            if not bygningsnummer and not lokalid:
                skipped['no_id'] += 1
                continue

            src_id = str(bygningsnummer) if bygningsnummer else str(lokalid)

            # FKB doesn't have construction dates - that's in Matrikkelen
            # We mark these as "current" buildings with no start date
            # The merge process will combine with other sources for dates

            # Map building type
            bt = map_building_type(props.get('bygningstype'))

            # Extract useful metadata
            raw_props = {
                'bygningsnummer': bygningsnummer,
                'lokalId': lokalid,
                'bygningstype': props.get('bygningstype'),
                'bygningsstatus': props.get('bygningsstatus'),
                'datafangstdato': props.get('datafangstdato'),
                'oppdateringsdato': props.get('oppdateringsdato'),
            }

            # Create normalized feature
            # FKB is HIGH evidence for geometry but has no dates
            feature = self.create_normalized_feature(
                src_id=src_id,
                geometry=geom,
                sd=None,  # No construction date in FKB
                ed=None,  # Building exists (in FKB)
                ev='h',   # High evidence - official cadastral data
                bt=bt,
                nm=None,  # No name in FKB
                raw_props=raw_props
            )

            features.append(feature)

        # Report skipped features
        if any(skipped.values()):
            print(f"  Skipped: {sum(skipped.values())} features")
            for reason, count in skipped.items():
                if count > 0:
                    print(f"    - {reason}: {count}")

        return features


def main():
    """CLI entry point."""
    normalizer = Normalizer()
    success = normalizer.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
