"""intradel integration constants."""

from homeassistant.const import Platform

DOMAIN = "intradel"

PLATFORMS = [Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = 720

CONF_TOWN = "town"
ATTR_START_DATE = "start_date"
ATTR_BIN_COLLECTIONS = "collections"
ATTR_CHIP = "chip"
