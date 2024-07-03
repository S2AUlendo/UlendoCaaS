
SIMULATION = False
SIMULATION_f1 = 80

FSM_UPDATE_RATE_SEC = 0.25
ACCLRMTR_LIVE_VIEW_RATE_SEC = 0.1
ACCLRMTR_LIVE_VIEW_NUM_SAMPLES = 200

VERBOSE = 1 # 0 -- Muted.
            # 1 -- Send errors to octoprint logger.
            # 2 -- Send all info messages to octoprint logger.
            # 3 -- Send printer messages to octoprint logger.

MOVE_TO_CENTER_SPEED_MM_PER_MIN = 6000

FSM_SWEEP_START_DLY = 0.5

T_DFLT = 1./1600.    # Default sample time to use (accelerometer sample time).

MAX_RETRIES_FOR_MISSED_SAMPLES = 2
GET_AXIS_INFO_TIMEOUT = 10.
CENTER_AXIS_TIMEOUT = 12.

SERVICE_URL = 'https://loc6hkp2pk.execute-api.us-east-2.amazonaws.com/beta/solve'
SERVICE_TIMEOUT_THD = 30
