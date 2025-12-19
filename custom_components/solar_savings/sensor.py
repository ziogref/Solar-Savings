"""Sensor platform for Solar Savings."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Solar Savings sensors."""
    
    # This file is reserved for future calculated sensors (like Total Savings)
    entities = []

    # logic for future sensors will go here...
    
    async_add_entities(entities)