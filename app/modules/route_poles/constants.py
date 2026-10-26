"""Business rules of the route poles analysis."""

# Cables
EXCLUDED_CABLE_PREFIXES = ('MIT', 'DROP', 'DRP')
CABLE_TYPE_PREFIXES = {'FO': 'FO', 'F0': 'FO'}
UNKNOWN_CABLE_TYPE = 'não informado'

# Overlap and poles
DUPLICATE_M = 4.0
PARALLEL_M = 15.0
PARALLEL_COS = 0.9
NO_POLE_M = 25.0

# Results
BASE_MIN_SHARE = 0.05
CLOSE_POLE_M = 5.0

# Licensed poles
# Max distance between a licensed marker and a pole in use that are the same
# pole
MATCH_TOLERANCE_M = 10.0
# The BDGD puts some poles 10-20 m off: a pole in use and a licensed marker
# that matched nothing, this close, are that pole displaced
DISPLACED_POLE_M = 20.0
# A licensed marker between two in use, each within this span and on opposite
# sides (120 degrees or more apart), is in use too: the cable drawing cuts
# corners away from its poles
SEQUENCE_SPAN_M = 50.0
SEQUENCE_MAX_COS = -0.5
# A licensed marker is in use when a cable passes this near, or within the
# radius of the analysis when it is wider: the licensing says which poles the
# cables hang on, and the cables are drawn loosely
LICENSED_CABLE_M = 25.0
# Poles in use of two analyses this close are the same pole
SAME_POLE_M = 1.0

# Upload
# Poles in use are up to this far from a cable. Against the licensed poles of
# Lavras, 25 m counted 18% more poles than the cables use (mostly across the
# street) and 12 m about as many
DEFAULT_RADIUS_M = 12.0
MAX_RADIUS_M = 100.0
MAX_UPLOAD_BYTES = 50_000_000
MAX_KML_BYTES = 200_000_000

# Sources
CEMIG_RELEASE = 'postes-2025-12-31'
EXTRA_RELEASE = 'postes-extra-2025-12-31'
STATES = {'31': 'MG', '35': 'SP'}
