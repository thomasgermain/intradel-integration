"""Test the Intradel sensors."""

import copy
from unittest.mock import AsyncMock

from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel.const import (
    CONF_HOUSEHOLD_SIZE,
    CONF_MAX_COLLECTIONS,
    CONF_PRICE_ORGANIC_KG,
    CONF_QUOTA_ORGANIC_KG,
    DOMAIN,
)

from .const import SAMPLE_DATA


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> er.EntityRegistry:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return er.async_get(hass)


async def test_sensors_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """One sensor per dataset is created with the right value, unit and attributes."""
    ent_reg = await _setup(hass, mock_config_entry)

    bin_entity = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_123456")
    recypark_entity = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_RECYPARC")
    assert bin_entity is not None
    assert recypark_entity is not None

    bin_state = hass.states.get(bin_entity)
    assert bin_state is not None
    assert bin_state.state == "61.0"
    assert bin_state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfMass.KILOGRAMS
    assert bin_state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.WEIGHT
    assert bin_state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL_INCREASING
    assert bin_state.attributes["start_date"] == "01-01-2026"
    assert len(bin_state.attributes["details"]) == 2

    recypark_state = hass.states.get(recypark_entity)
    assert recypark_state is not None
    assert recypark_state.state == "1.0"
    assert ATTR_UNIT_OF_MEASUREMENT not in recypark_state.attributes
    assert ATTR_DEVICE_CLASS not in recypark_state.attributes
    assert recypark_state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL_INCREASING

    # Every sensor (including recypark) is attached to its own device.
    assert ent_reg.async_get(bin_entity).device_id is not None
    assert ent_reg.async_get(recypark_entity).device_id is not None


async def test_sensor_value_updates_on_refresh(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A coordinator refresh updates the existing entity's state (regression)."""
    ent_reg = await _setup(hass, mock_config_entry)
    bin_entity = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_123456")
    assert bin_entity is not None
    assert hass.states.get(bin_entity).state == "61.0"

    updated = copy.deepcopy(SAMPLE_DATA)
    updated[0]["total"] = "99"
    mock_get_data.return_value = updated

    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(bin_entity).state == "99.0"


async def test_derived_bin_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """Cost, quota and pace sensors are created for each chipped bin."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            CONF_HOUSEHOLD_SIZE: 1,
            CONF_QUOTA_ORGANIC_KG: 25.0,
            CONF_PRICE_ORGANIC_KG: 0.10,
            CONF_MAX_COLLECTIONS: 30,
        },
    )
    ent_reg = await _setup(hass, mock_config_entry)

    def _state(key: str) -> str:
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_123456_{key}")
        assert entity_id is not None, key
        state = hass.states.get(entity_id)
        assert state is not None, key
        return state.state

    # SAMPLE_DATA: 61 kg of organic waste over 2 collections.
    assert _state("collections") == "2"
    assert _state("collections_remaining") == "28"
    assert _state("average_per_collection") == "30.5"
    # 61 kg against a 25 kg quota -> 36 kg billed at 0.10.
    assert _state("quota_used") == "244.0"
    assert _state("quota_remaining") == "0.0"
    assert _state("cost") == "3.6"


async def test_household_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """Household-wide sensors aggregate every bin."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_MAX_COLLECTIONS: 30})
    ent_reg = await _setup(hass, mock_config_entry)

    def _state(key: str) -> str:
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_account_{key}")
        assert entity_id is not None, key
        state = hass.states.get(entity_id)
        assert state is not None, key
        return state.state

    assert _state("total_weight") == "61.0"
    assert _state("total_collections") == "2"
    assert _state("total_collections_remaining") == "28"
    # SAMPLE_DATA's single recypark visit dropped off 0.35 m3.
    assert _state("recyparc_volume") == "0.35"
    # No price configured: the bill is zero, not unknown.
    assert _state("total_cost") == "0.0"


async def test_legacy_sensors_are_preserved(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """The original weight sensors keep their unique ids, so history survives."""
    ent_reg = await _setup(hass, mock_config_entry)

    assert ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_123456") is not None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_RECYPARC") is not None
