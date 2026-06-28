"""Test the Intradel sensors."""

import copy
from unittest.mock import AsyncMock

from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel.const import DOMAIN

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
    assert bin_state.state == "61"
    assert bin_state.attributes["unit_of_measurement"] == UnitOfMass.KILOGRAMS
    assert bin_state.attributes["start_date"] == "01-01-2026"
    assert len(bin_state.attributes["details"]) == 2

    recypark_state = hass.states.get(recypark_entity)
    assert recypark_state is not None
    assert recypark_state.state == "1"
    assert "unit_of_measurement" not in recypark_state.attributes


async def test_sensor_value_updates_on_refresh(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A coordinator refresh updates the existing entity's state (regression)."""
    ent_reg = await _setup(hass, mock_config_entry)
    bin_entity = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_123456")
    assert bin_entity is not None
    assert hass.states.get(bin_entity).state == "61"

    updated = copy.deepcopy(SAMPLE_DATA)
    updated[0]["total"] = "99"
    mock_get_data.return_value = updated

    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(bin_entity).state == "99"
