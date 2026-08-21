"""intradel integration constants."""

from homeassistant.const import Platform

DOMAIN = "intradel"

PLATFORMS = [Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = 720

# Only kept to describe entries created before login/password was removed; the
# integration authenticates with a session cookie exclusively.
CONF_TOWN = "town"
CONF_COOKIE = "cookie"

# Business-logic options. Every quota is town-specific and the household size is
# household-specific, so all of them are configurable; the defaults below are
# only sensible starting points, not Intradel-wide truth.
CONF_HOUSEHOLD_SIZE = "household_size"
CONF_QUOTA_ORGANIC_KG = "quota_organic_kg"
CONF_QUOTA_RESIDUAL_KG = "quota_residual_kg"
CONF_MAX_COLLECTIONS = "max_collections"

# Prices charged beyond the quotas, and the fixed yearly fee. Defaults are 0 so
# the cost sensors read zero until the town's real rates are entered.
CONF_ANNUAL_FEE = "annual_fee"
CONF_PRICE_ORGANIC_KG = "price_organic_kg"
CONF_PRICE_RESIDUAL_KG = "price_residual_kg"
DEFAULT_ANNUAL_FEE = 0.0
DEFAULT_PRICE_ORGANIC_KG = 0.0
DEFAULT_PRICE_RESIDUAL_KG = 0.0

# Currency of every cost sensor.
CURRENCY = "EUR"

# Minutes between session keep-alive pings for cookie-based entries; 0 disables.
CONF_KEEPALIVE_INTERVAL = "keepalive_interval"
DEFAULT_KEEPALIVE_INTERVAL = 15

# Kilograms per inhabitant and per year covered by the annual fee.
DEFAULT_QUOTA_ORGANIC_KG = 25.0
DEFAULT_QUOTA_RESIDUAL_KG = 50.0
# Bin emptyings per year covered by the annual fee (not per inhabitant).
DEFAULT_MAX_COLLECTIONS = 30
DEFAULT_HOUSEHOLD_SIZE = 1
ATTR_START_DATE = "start_date"
ATTR_BIN_COLLECTIONS = "collections"
ATTR_CHIP = "chip"

# Service letting a browser hand over a freshly captured session cookie.
SERVICE_SET_COOKIE = "set_cookie"
ATTR_COOKIE = "cookie"
