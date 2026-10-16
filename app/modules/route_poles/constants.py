"""Business rules of the v8 analysis. Explained in docs/v8-route-poles-codigo.md."""

# Cables
EXCLUDED_CABLE_PREFIXES = ('MIT', 'DROP', 'DRP')
CABLE_TYPE_PREFIXES = {
    'FO': 'FO',
    'F0': 'FO'
}
UNKNOWN_CABLE_TYPE = 'não informado'

# Overlap and poles
DUPLICATE_M = 4.0
PARALLEL_M = 15.0
PARALLEL_COS = 0.9
NO_POLE_M = 25.0

# Results
BASE_MIN_SHARE = 0.05
CLOSE_POLE_M = 5.0

# Upload
DEFAULT_RADIUS_M = 25.0
MAX_RADIUS_M = 100.0
MAX_UPLOAD_BYTES = 50_000_000
MAX_KML_BYTES = 200_000_000

# Sources
CEMIG_RELEASE = 'postes-2025-12-31'
EXTRA_RELEASE = 'postes-extra-2025-12-31'
STATES = {'31': 'MG', '35': 'SP'}
