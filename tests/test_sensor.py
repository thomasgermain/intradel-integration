"""Test the Intradel sensors."""

import copy
from unittest.mock import AsyncMock

from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    UnitOfMass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intradel import async_remove_config_entry_device
from custom_components.intradel.const import DOMAIN, MANUFACTURER

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


def _device(hass: HomeAssistant, entry: MockConfigEntry, data_id: str) -> dr.DeviceEntry | None:
    """The entry's device for a bin, whatever the Home Assistant version.

    async_get_device is deprecated in recent Home Assistant releases and its
    replacement does not exist in the minimum supported one.
    """
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        if (DOMAIN, data_id) in device.identifiers:
            return device
    return None


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry, data: list) -> None:
    entry.runtime_data.async_set_updated_data(data)
    await hass.async_block_till_done()


async def test_entities_are_named_after_their_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """Without a user rename, the friendly name is the label scraped from the site."""
    ent_reg = await _setup(hass, mock_config_entry)
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_123456")
    assert entity_id == "sensor.organique"

    assert hass.states.get(entity_id).attributes[ATTR_FRIENDLY_NAME] == "ORGANIQUE"
    device = _device(hass, mock_config_entry, "123456")
    assert device is not None
    assert device.name == "ORGANIQUE"
    assert device.manufacturer == MANUFACTURER


async def test_renamed_entity_keeps_its_name(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A name chosen by the user in the registry wins over the device name."""
    ent_reg = await _setup(hass, mock_config_entry)
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_123456")
    ent_reg.async_update_entity(entity_id, name="Poubelle verte")
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).attributes[ATTR_FRIENDLY_NAME] == "Poubelle verte"


async def test_recypark_is_recognised_by_id_not_by_label(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A relabelled recypark must not turn into a weight sensor."""
    relabelled = copy.deepcopy(SAMPLE_DATA)
    relabelled[1]["name"] = "Recypark"
    mock_get_data.return_value = relabelled

    ent_reg = await _setup(hass, mock_config_entry)
    state = hass.states.get(ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_RECYPARC"))

    assert ATTR_UNIT_OF_MEASUREMENT not in state.attributes
    assert ATTR_DEVICE_CLASS not in state.attributes


async def test_empty_first_payload_creates_entities_later(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """Sensors appear once the site reports items, without a reload."""
    mock_get_data.return_value = []
    ent_reg = await _setup(hass, mock_config_entry)
    assert not er.async_entries_for_config_entry(ent_reg, mock_config_entry.entry_id)

    await _refresh(hass, mock_config_entry, copy.deepcopy(SAMPLE_DATA))

    assert ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_123456") is not None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_RECYPARC") is not None


async def test_new_item_gets_a_sensor_and_known_ones_are_not_duplicated(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """Only the item that appeared is added; the existing ones keep their entity."""
    mock_get_data.return_value = SAMPLE_DATA[:1]
    ent_reg = await _setup(hass, mock_config_entry)
    assert len(er.async_entries_for_config_entry(ent_reg, mock_config_entry.entry_id)) == 1

    await _refresh(hass, mock_config_entry, copy.deepcopy(SAMPLE_DATA))
    await _refresh(hass, mock_config_entry, copy.deepcopy(SAMPLE_DATA))

    assert len(er.async_entries_for_config_entry(ent_reg, mock_config_entry.entry_id)) == 2


async def test_item_missing_from_payload_becomes_unavailable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A vanished item is reported as unavailable, not as a stale value."""
    ent_reg = await _setup(hass, mock_config_entry)
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_123456")

    await _refresh(hass, mock_config_entry, copy.deepcopy(SAMPLE_DATA[1:]))

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


async def test_only_stale_devices_can_be_removed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_data: AsyncMock,
) -> None:
    """A device still reported by the site is kept; a vanished one may be deleted."""
    await _setup(hass, mock_config_entry)
    bin_device = _device(hass, mock_config_entry, "123456")
    assert bin_device is not None

    assert not await async_remove_config_entry_device(hass, mock_config_entry, bin_device)

    await _refresh(hass, mock_config_entry, copy.deepcopy(SAMPLE_DATA[1:]))

    assert await async_remove_config_entry_device(hass, mock_config_entry, bin_device)
