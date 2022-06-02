"""Switch Humidifier Platform"""
import logging
import json
import os
import time

import asyncio


import voluptuous as vol

from homeassistant.core import callback
from homeassistant.helpers.event import track_state_change, async_track_state_change_event

from homeassistant.components.humidifier import (
  ATTR_HUMIDITY,
  ATTR_MAX_HUMIDITY,
  ATTR_MIN_HUMIDITY,
  DEVICE_CLASS_DEHUMIDIFIER,
  DEVICE_CLASS_HUMIDIFIER,
  SUPPORT_MODES,
  PLATFORM_SCHEMA,
  HumidifierEntity,
  HumidifierEntityFeature
)
from homeassistant.const import (
  CONF_NAME,
  SERVICE_TURN_ON,
  SERVICE_TURN_OFF,
  SERVICE_TOGGLE,
  STATE_ON,
  STATE_OFF
)

from switchbot import Switchbot, GetSwitchbotDevices  # pylint: disable=import-error


import homeassistant.helpers.config_validation as cv
from homeassistant.components.humidifier.const import MODE_AUTO, MODE_NORMAL, MODE_BOOST, MODE_SLEEP, MODE_AWAY

AVAILABLE_MODES = [MODE_NORMAL, MODE_AUTO, MODE_SLEEP, MODE_BOOST]

SUPPORTED_FEATURES = SUPPORT_MODES


_LOGGER = logging.getLogger(__name__)

CONF_NAME = 'name'
DEFAULT_NAME = 'humidifier'

CONF_TYPE = 'type'
CONF_START_DELTA = 'start_delta'
CONF_STOP_DELTA = 'stop_delta'


DEHUMIDIFIER_TYPE = 'dehumidifier'
HUMIDIFIER_TYPE = 'humidifier'

TYPES = [
  DEHUMIDIFIER_TYPE,
  HUMIDIFIER_TYPE
]

DEFAULT_TYPE = HUMIDIFIER_TYPE
DEFAULT_HUMIDITY = 50
DEFAULT_START_DELTA = 0.1
DEFAULT_STOP_DELTA = 0.1
DEFAULT_SWITCH_STATE = STATE_OFF
MIN_HUMIDITY = 0
MAX_HUMIDITY = 100

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
  {
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_TYPE, default=DEFAULT_TYPE): vol.All(cv.string, vol.In(TYPES)),
    vol.Optional(CONF_START_DELTA, default=DEFAULT_START_DELTA): vol.Coerce(float),
    vol.Optional(CONF_STOP_DELTA, default=DEFAULT_STOP_DELTA): vol.Coerce(float),
  }
)

def setup_platform(hass, config, add_entities, discovery_info=None):
  """Set up the dehumidifier platform."""
  name = config[CONF_NAME]
  device_class = DEVICE_CLASS_DEHUMIDIFIER
  if config[CONF_TYPE] == HUMIDIFIER_TYPE:
    device_class = DEVICE_CLASS_HUMIDIFIER
  start_delta = config[CONF_START_DELTA]
  stop_delta = config[CONF_STOP_DELTA]
  devices = []
  switchHumidifier = BlueairAirPurifier(name, device_class, start_delta, stop_delta)
  devices.append(switchHumidifier)
  add_entities(devices, True)

  # Track sensor or switch state changes.
  # track_state_change(hass, [], switchHumidifier._state_changed)

  return True

class BlueairAirPurifier(HumidifierEntity):
	
  def __init__(self, name, device_class, start_delta, stop_delta):
    """Initialize the humidifier."""
    self.last_press = 0

    self._attr_available_modes = AVAILABLE_MODES

    self._attr_supported_features = SUPPORT_MODES

    self._humidity = DEFAULT_HUMIDITY

    self._switch_state = DEFAULT_SWITCH_STATE

    self._is_on = DEFAULT_SWITCH_STATE == STATE_ON

    self._device_class = device_class

    self._start_delta = start_delta

    self._stop_delta = stop_delta
    
    self._attr_mode = MODE_AUTO
    self._mode = MODE_AUTO

    self._supported_features = HumidifierEntityFeature.MODES

    # To cheack if the switch state change if fired by the platform
    self._self_changed_switch = False
    
    self._name = name

    # Persistence file to store persistent data
    self._persistence_final_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persistence.json")

    try:
      if os.path.isfile(self._persistence_final_path):
        self._persistence_json = json.load(open(self._persistence_final_path, 'r'))
      else:
        _LOGGER.warning("file doesnt exist")
        self._persistence_json = json.loads('{"target": ' + str(DEFAULT_HUMIDITY) + '}')

      self._target_humidity = self._persistence_json['target']
      self.save_target()

    except Exception as e:
      _LOGGER.error("Error occured loading: %s", str(e))
      self._target_humidity = DEFAULT_HUMIDITY

  def save_target(self): 
    """set target humidity to persistent JSON and store it."""
    self._persistence_json['target'] = self._target_humidity
    self.persistence_save()

  def persistence_save(self): 
    """Store persistent JSON as file."""
    if self._persistence_json is not None: #Check we have something to save
      try:
        with open(self._persistence_final_path, 'w') as fil:
          fil.write(json.dumps(self._persistence_json, ensure_ascii=False))
      except Exception as e:
        _LOGGER.error("Error occured saving: %s", str(e))

  def update(self):
    """Update called periodically"""

  @property
  def name(self):
    """Return the name of the humidifier."""
    return self._name

  @property
  def target_humidity(self):
    """Return the target humidity."""
    return self._target_humidity

  @property
  def min_humidity(self):
    """Return the target humidity."""
    return MIN_HUMIDITY

  @property
  def max_humidity(self):
    """Return the target humidity."""
    return MAX_HUMIDITY
      
  # def supported_features(self):
  #   """Return the list of supported features."""
  #   return (SUPPORT_MODES)

  @property
  def is_on(self):
    """Return if the dehumidifier is on."""
    return self._is_on

  @property
  def device_class(self):
    """Return Device class."""
    _LOGGER.debug('device_class')
    return self._device_class

  @property
  def mode(self) -> str:
    """Return current mode."""
    return self._mode

  def set_humidity(self, humidity):
    """Set target humidity."""
    _LOGGER.debug('set_humidity')
    if humidity is 0:
      self._target_humidity = humidity
      self.set_mode(MODE_AUTO)
    elif humidity > 0 and humidity <= 25:
      self._target_humidity = 20
      self.set_mode(MODE_SLEEP)
    elif humidity > 25 and humidity <= 75:
      self._target_humidity = 50
      self.set_mode(MODE_NORMAL)
    elif humidity > 75:
      self._target_humidity = 100
      self.set_mode(MODE_BOOST)
    self.save_target()

  def turn_on(self, **kwargs):
    """Turn the device ON."""
    _LOGGER.debug('turn_on')
    self._is_on = True
    if self._target_humidity is 0:
      self.set_mode(MODE_AUTO)
    elif self._target_humidity > 0 and self._target_humidity <= 25:
      self.set_mode(MODE_SLEEP)
    elif self._target_humidity > 25 and self._target_humidity <= 75:
      self.set_mode(MODE_NORMAL)
    elif self._target_humidity > 75:
      self.set_mode(MODE_BOOST)

  def turn_off(self, **kwargs):
    """Turn the device OFF."""
    _LOGGER.debug('turn_off')
    self.set_mode(MODE_AWAY)
    self._is_on = False

  def set_mode(self, mode):
    """Set new target preset mode."""
    current_mode = self._mode
    self._mode = mode
    self._attr_mode = mode
    self.from_state_to(current_mode, mode)

  async def async_set_mode(self, mode):
    """Set new target preset mode."""
    current_mode = self._mode
    self._mode = mode
    self._attr_mode = mode
    self.from_state_to(current_mode, mode)



  def step_from_off(self, bot: Switchbot, count=0):
    bot.press()
    self.last_press = time.time()


  def step(self, bot: Switchbot, count=0):
    if time.time() - self.last_press < 2500:
      bot.press()
      if time.time() - self.last_press > 4800:
        self.step(bot, count= count+1)
        _LOGGER.warning("Restart mission")
      else:
        self.last_press = time.time()
    else:
      if count > 4: # todo
        _LOGGER.warning("End mission")
        return
      
      # clear
      time.sleep(max(0, 5000 - (time.time() - self.last_press)))

      # press
      bot.press()
      self.last_press = time.time()
      self.step(bot, count=count+1)

  
  def from_state_to(self, from_state: str, to_state: str):
    _LOGGER.warning('Set mode to' + from_state + " to " + to_state)
 #   _LOGGER.warning(GetSwitchbotDevices().get_bots())
    bot: Switchbot = Switchbot(mac="c0:fd:37:e2:2f:ad")
    _LOGGER.warning(bot)
    self.next_state(from_state, to_state, bot)

  def next_state(self, from_state: str, to_state: str, bot: Switchbot):
    if from_state == "away":
      self.step_from_off()
    else:
      self.step(bot)
    new_state = self.get_next_state(from_state)
    self.next_state(new_state, to_state, bot)
  

  def get_next_state(self, from_state: str) -> str:
    if from_state == "auto":
      return "sleep"
    elif from_state == "sleep":
      return "normal"
    elif from_state == "normal":
      return "boost"
    elif from_state == "boost":
      return "away"
    elif from_state == "away":
      return "auto"


  ############################################################