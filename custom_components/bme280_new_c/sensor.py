"""Support for BME280 temperature, humidity and pressure sensor."""
import asyncio
from datetime import timedelta
import logging
from functools import partial
from time import sleep

import smbus  # pylint: disable=import-error
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    PERCENTAGE,
    TEMP_FAHRENHEIT,
)

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
from homeassistant.util.temperature import celsius_to_fahrenheit
from math import log10

__version__ = '1.0.0'

DEFAULT_DELAY_SEC = 5

DOMAIN = "bme280m"

_LOGGER = logging.getLogger(__name__)

CONF_I2C_CHANNEL = "i2c_channel"
CONF_I2C_ADDRESS = "i2c_address"
CONF_I2C_BUS = "i2c_bus"
CONF_OVERSAMPLING_TEMP = "oversampling_temperature"
CONF_OVERSAMPLING_PRES = "oversampling_pressure"
CONF_OVERSAMPLING_HUM = "oversampling_humidity"
CONF_OPERATION_MODE = "operation_mode"
CONF_T_STANDBY = "time_standby"
CONF_FILTER_MODE = "filter_mode"
CONF_DELTA_TEMP = "delta_temperature"

DEFAULT_NAME = "BME280 Sensor"
DEFAULT_I2C_CHANNEL = -1
DEFAULT_I2C_ADDRESS = "0x76"
DEFAULT_I2C_BUS = 1
DEFAULT_OVERSAMPLING_TEMP = 1  # Temperature oversampling x 1
DEFAULT_OVERSAMPLING_PRES = 1  # Pressure oversampling x 1
DEFAULT_OVERSAMPLING_HUM = 1  # Humidity oversampling x 1
DEFAULT_OPERATION_MODE = 3  # Normal mode (forced mode: 2)
DEFAULT_T_STANDBY = 5  # Tstandby 5ms
DEFAULT_FILTER_MODE = 0  # Filter off
DEFAULT_DELTA_TEMP = 0.0

CONF_CHANNEL_DISABLED = -1
CONF_CHANNEL_0 = 1
CONF_CHANNEL_1 = 2
CONF_CHANNEL_2 = 4
CONF_CHANNEL_3 = 8
CONF_CHANNEL_4 = 16
CONF_CHANNEL_5 = 32
CONF_CHANNEL_6 = 64
CONF_CHANNEL_7 = 128

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=30)

SENSOR_TEMP = "temperature"
SENSOR_HUMID = "humidity"
SENSOR_PRESS = "pressure"
SENSOR_TYPES = {
    SENSOR_TEMP: ["Temperature", None],
    SENSOR_HUMID: ["Humidity", PERCENTAGE],
    SENSOR_PRESS: ["Pressure", "mb"],
}
DEFAULT_MONITORED = [SENSOR_TEMP, SENSOR_HUMID, SENSOR_PRESS]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS): cv.string,
        vol.Optional(CONF_I2C_CHANNEL, default=DEFAULT_I2C_CHANNEL): vol.Coerce(int),
        vol.Optional(CONF_MONITORED_CONDITIONS, default=DEFAULT_MONITORED): vol.All(
            cv.ensure_list, [vol.In(SENSOR_TYPES)]
        ),
        vol.Optional(CONF_I2C_BUS, default=DEFAULT_I2C_BUS): vol.Coerce(int),
        vol.Optional(
            CONF_OVERSAMPLING_TEMP, default=DEFAULT_OVERSAMPLING_TEMP
        ): vol.Coerce(int),
        vol.Optional(
            CONF_OVERSAMPLING_PRES, default=DEFAULT_OVERSAMPLING_PRES
        ): vol.Coerce(int),
        vol.Optional(
            CONF_OVERSAMPLING_HUM, default=DEFAULT_OVERSAMPLING_HUM
        ): vol.Coerce(int),
        vol.Optional(CONF_OPERATION_MODE, default=DEFAULT_OPERATION_MODE): vol.Coerce(
            int
        ),
        vol.Optional(CONF_T_STANDBY, default=DEFAULT_T_STANDBY): vol.Coerce(int),
        vol.Optional(CONF_FILTER_MODE, default=DEFAULT_FILTER_MODE): vol.Coerce(int),
        vol.Optional(CONF_DELTA_TEMP, default=DEFAULT_DELTA_TEMP): vol.Coerce(float),
    }
)


def check_multi_inuse(hass, bus, i2c_channel):
    """ 0 = Multiplexer not in use, Then Continue,
        Check the i2c channel is the same if so add one to inuse
        else:
        1 = Multiplex In use Wait untill Free
         """
    chk_string = hass.states.is_state("bme280m.multi_inuse", "0")

    ''' both above are true meaning they are not in use '''
    c = 0
    while not chk_string:
        #  Check is Multiplexer is set to same i2c channel
        if hass.states.is_state("bme280m.multi_channel_inuse", str(i2c_channel)):
            multi_now = get_state_sting(hass) + 1
            hass.states.async_set("bme280m.multi_inuse", str(multi_now), force_update=True)
            # _LOGGER.info("Active on Channel %s - %s Active Sensors", i2c_channel, multi_now)
            return True
        else:
            #sleep(0.5)

            chk_string = hass.states.is_state("bme280m.multi_inuse", "0")
            # _LOGGER.info("Check String is not 0: String is %s", hass.states.get("bme280m.multi_inuse"))
            # _LOGGER.info("Check String is %s - Waiting ", chk_string)
            c = c + 1
            if c >= 20:
                break

    hass.states.async_set("bme280m.multi_inuse", "1", force_update=True)
    hass.states.async_set("bme280m.multi_channel_inuse", str(i2c_channel), force_update=True)
    bus.write_byte_data(0x70, 0x04, int(i2c_channel))
    sleep(0.5)
    return True


def get_state_sting(hass):
    for num in range(0, 10, 1):
        if hass.states.is_state("bme280m.multi_inuse", str(num)):
            return num
    return -1


def finished_update(hass):
    """<state bme280m.multi_inuse=0"""
    """01234567890123456789101234567"""
    for num in range(0, 10, 1):
        counter_inuse = hass.states.is_state("bme280m.multi_inuse", str(num))
        if counter_inuse:
            # _LOGGER.warning(" Finished found %s", str(num))
            if num == 0:
                hass.states.async_set("bme280m.multi_inuse", "0", force_update=True)
                hass.states.async_set("bme280m.multi_channel_inuse", "0", force_update=True)
                # _LOGGER.info("Sensor Finished set to 0")
                return
            elif num >= 1:
                active_count = num - 1
                # _LOGGER.info("Sensor is equal or greater than 1 set to %s", str(active_count))
                if active_count <= 0:
                    hass.states.async_set("bme280m.multi_inuse", "0", force_update=True)
                    hass.states.async_set("bme280m.multi_channel_inuse", "0", force_update=True)
                    # _LOGGER.info("Active Count is %s - Setting to 0", str(active_count))
                    return
                else:
                    # _LOGGER.info("Active Count is %s - Keeping Same Channel", str(active_count))
                    hass.states.async_set("bme280m.multi_inuse", active_count, force_update=True)
                return
    _LOGGER.info("Sensor Finished & Done Nothing")


def setup_i2c_channel(channel):
    if channel == -1:
        return -1
    if channel == 0:
        return 1
    elif channel == 1:
        return 2
    elif channel == 2:
        return 4
    elif channel == 3:
        return 8
    elif channel == 4:
        return 16
    elif channel == 5:
        return 32
    elif channel == 6:
        return 64
    elif channel == 7:
        return 128


def create_multiplexer(hass_in):
    if hass_in.states.async_available("bme280m.multi_inuse"):
        _LOGGER.info("BME280M Async State Created")
        hass_in.states.async_set("bme280m.multi_inuse", "0", force_update=True)
        hass_in.states.async_set("bme280m.multi_channel_inuse", "0", force_update=True)
    else:
        _LOGGER.info("BME280M Async State already created Skipping")


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the BME280 sensor."""

    SENSOR_TYPES[SENSOR_TEMP][1] = hass.config.units.temperature_unit
    name = config[CONF_NAME]
    i2c_address = config[CONF_I2C_ADDRESS]
    i2c_channel = setup_i2c_channel(config[CONF_I2C_CHANNEL])
    bus = smbus.SMBus(config[CONF_I2C_BUS])

    create_multiplexer(hass)
    check_multi_inuse(hass, bus, i2c_channel)

    sensor = await hass.async_add_executor_job(
        partial(
            BME280,
            bus,
            i2c_address,
            osrs_t=config[CONF_OVERSAMPLING_TEMP],
            osrs_p=config[CONF_OVERSAMPLING_PRES],
            osrs_h=config[CONF_OVERSAMPLING_HUM],
            mode=config[CONF_OPERATION_MODE],
            t_sb=config[CONF_T_STANDBY],
            filter_mode=config[CONF_FILTER_MODE],
            delta_temp=config[CONF_DELTA_TEMP],
            logger=_LOGGER,
        )
    )
    finished_update(hass)
    if not sensor.sample_ok:
        _LOGGER.error("BME280 sensor not detected at %s", i2c_address)
        return False
    check_multi_inuse(hass, bus, i2c_channel)
    sensor_handler = await hass.async_add_executor_job(BME280Handler, sensor)
    dev = []
    try:
        for variable in config[CONF_MONITORED_CONDITIONS]:
            dev.append(
                BME280Sensor(sensor_handler, variable, SENSOR_TYPES[variable][1], name, i2c_channel, bus)
            )
    except KeyError:
        pass
    finished_update(hass)
    async_add_entities(dev, True)
    try:
        _LOGGER.info("BME280 Finished setting up: %s on Channel/Address:%s:%s", name, i2c_channel, i2c_address)
    except Exception as E:
        _LOGGER.error("BME280 Finished Error :%s", E)


class BME280Handler:
    """BME280 sensor working in i2C bus."""

    def __init__(self, sensor):
        """Initialize the sensor handler."""
        self.sensor = sensor
        self.update(True)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self, first_reading=False):
        """Read sensor data."""
        self.sensor.update(first_reading)


class BME280Sensor(Entity):
    """Implementation of the BME280 sensor."""

    def __init__(self, bme280_client, sensor_type, temp_unit, name, i2c_channel, bus):
        """Initialize the sensor."""
        self.client_name = name
        self._name = SENSOR_TYPES[sensor_type][0]
        self.bme280_client = bme280_client
        self.temp_unit = temp_unit
        self.type = sensor_type
        self._state = None
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self.i2c_channel = i2c_channel
        self.bus = bus

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.client_name} {self._name}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement

    async def async_update(self):
        """Get the latest data from the BME280 and update the states."""
        await self.hass.async_run_job(self.check_multi_inuse)
        await self.hass.async_add_executor_job(self.bme280_client.update)
        if self.bme280_client.sensor.sample_ok:
            if self.type == SENSOR_TEMP:
                temperature = round(self.bme280_client.sensor.temperature, 2)
                if self.temp_unit == TEMP_FAHRENHEIT:
                    temperature = round(celsius_to_fahrenheit(temperature), 2)
                self._state = temperature
            elif self.type == SENSOR_HUMID:
                self._state = round(self.bme280_client.sensor.humidity, 1)
            elif self.type == SENSOR_PRESS:
                self._state = round(self.bme280_client.sensor.pressure, 1)
        else:
            _LOGGER.warning("Bad update of sensor.%s", self.name)
        self.finished_update()

    async def check_multi_inuse(self):
        """ 0 = Multiplexer not in use, Then Continue,
            Check the i2c channel is the same if so add one to inuse
            else:
            1 = Multiplex In use Wait untill Free
             """
        chk_string = self.hass.states.is_state("bme280m.multi_inuse", "0")

        ''' both above are true meaning they are not in use '''
        c = 0
        while not chk_string:
            #  Check is Multiplexer is set to same i2c channel
            if self.hass.states.is_state("bme280m.multi_channel_inuse", str(self.i2c_channel)):
                multi_now = self.get_state_sting() + 1
                self.hass.states.async_set("bme280m.multi_inuse", str(multi_now), force_update=True)
                # self.bme280_client.sensor.log_error("Active on Channel %s - %s Active Sensors",
                # self.i2c_channel, multi_now)
                return True
            else:

                await asyncio.sleep(1)
                chk_string = self.hass.states.is_state("bme280m.multi_inuse", "0")
                # self.bme280_client.sensor.log_error("Check String is not 0: String is %s",
                # self.hass.states.get("bme280m.multi_inuse"))
                # self.bme280_client.sensor.log_error("Check String is %s - Waiting ", chk_string)
                c = c + 1
                if c >= 20:
                    break

        self.hass.states.async_set("bme280m.multi_inuse", "1", force_update=True)
        self.hass.states.async_set("bme280m.multi_channel_inuse", str(self.i2c_channel), force_update=True)
        self.bus.write_byte_data(0x70, 0x04, int(self.i2c_channel))
        # removed 08/04/23- Lots of errors in loggs 
        #sleep(0.2)
        await asyncio.sleep(1)
        return True

    def get_state_sting(self):
        try:
            for num in range(0, 10, 1):
                if self.hass.states.is_state("bme280m.multi_inuse", str(num)):
                    # self.bme280_client.sensor.log_error("State Number is : %s", str(num))
                    return num
                # else:
                #   self.bme280_client.sensor.log_error("State is NOT Number: %s", str(num))

            return -1

        except Exception as E:
            self.bme280_client.sensor.log_error("get state string : %s", E)
            return -1
        pass

    def finished_update(self):
        """<state bme280m.multi_inuse=0"""
        """01234567890123456789101234567"""
        for num in range(0, 10, 1):
            counter_inuse = self.hass.states.is_state("bme280m.multi_inuse", str(num))
            if counter_inuse:
                # _LOGGER.warning(" Finished found %s", str(num))
                if num == 0:
                    self.hass.states.async_set("bme280m.multi_inuse", "0", force_update=True)
                    self.hass.states.async_set("bme280m.multi_channel_inuse", "0", force_update=True)
                    # self.log_warning("Sensor Finished set to 0")
                    return
                elif num >= 1:
                    active_count = num - 1
                    # self.log_warning("Sensor is equal or greater than 1 set to %s", str(active_count))
                    if active_count <= 0:
                        self.hass.states.async_set("bme280m.multi_inuse", "0", force_update=True)
                        self.hass.states.async_set("bme280m.multi_channel_inuse", "0", force_update=True)
                        # self.bme280_client.sensor.log_warning("Active Count is %s - Setting to 0", str(active_count))
                        return
                    else:
                        # self.bme280_client.sensor.log_warning("Active Count is %s - Keeping Same Channel",
                        #                                      str(active_count))
                        self.hass.states.async_set("bme280m.multi_inuse", active_count, force_update=True)
                    return
        # self.bme280_client.sensor.log_warning("Sensor Finished & Done Nothing")


class I2cVariableNotImplemented(Exception):
    """Sensor variable is not present in this instance."""

    def __init__(self, *args, **kwargs):  # real signature unknown
        pass


class I2cBaseClass(object):
    """Base class for sensors working in i2C bus."""

    def __init__(self, bus_handler, i2c_address, logger=None):
        """Init the sensor direction."""
        self._bus = bus_handler
        self._i2c_add = int(i2c_address, 0)
        self._ok = False
        self._logger = logger

    def __repr__(self):
        """String representation of the i2c sensor"""
        return "<I2c sensor at %s. Current state: %s>" % (
            hex(self._i2c_add), self.current_state_str)

    def log_error(self, msg, *args):
        """Log an error or print in stdout if no logger."""
        if self._logger is not None:
            self._logger.error(msg, *args)
        else:
            print(msg % args)

    def log_warning(self, msg, *args):
        """Log an error or print in stdout if no logger."""
        if self._logger is not None:
            self._logger.warning(msg, *args)
        else:
            print(msg % args)

    def update(self):
        """Read sensor data and update state and variables."""
        raise NotImplementedError

    @property
    def bus_check(self):
        """Return bus state."""
        return self._bus

    @property
    def sample_ok(self):
        """Return sensor ok state."""
        return self._ok

    @property
    def temperature(self):
        """Return temperature in celsius."""
        raise I2cVariableNotImplemented

    @property
    def humidity(self):
        """Return relative humidity in percentage."""
        raise I2cVariableNotImplemented

    @property
    def pressure(self):
        """Return pressure in hPa."""
        raise I2cVariableNotImplemented

    @property
    def light_level(self):
        """Return light level in lux."""
        raise I2cVariableNotImplemented

    def _get_value_opc_attr(self, attr_name, prec_decimals=2):
        """Return sensor attribute with precission, or None if not present."""
        try:
            value = getattr(self, attr_name)
            if value is not None:
                return round(value, prec_decimals)
        except I2cVariableNotImplemented:
            pass
        return None

    @property
    def current_state_str(self):
        """Return string representation of the current state of the sensor."""
        if self.sample_ok:
            msg = ''
            temperature = self._get_value_opc_attr('temperature')
            if temperature is not None:
                msg += 'Temp: %s ºC, ' % temperature
            humidity = self._get_value_opc_attr('humidity')
            if humidity is not None:
                msg += 'Humid: %s %%, ' % humidity
            pressure = self._get_value_opc_attr('pressure')
            if pressure is not None:
                msg += 'Press: %s mb, ' % pressure
            light_level = self._get_value_opc_attr('light_level')
            if light_level is not None:
                msg += 'Light: %s lux, ' % light_level
            return msg[:-2]
        else:
            return "Bad sample"

    @property
    def dew_point_temperature(self):
        """Return the dew point temperature in ºC for the last measurement.

        For sensors implementing temperature and humidity values.
        Extracted from the HTU21D sensor spec sheet."""
        if self.sample_ok:
            temperature = self._get_value_opc_attr('temperature', 3)
            humidity = self._get_value_opc_attr('humidity', 3)
            if temperature is not None and humidity is not None:
                # Calc dew point temperature in celsius
                coef_a, coef_b, coef_c = 8.1332, 1762.39, 235.66
                part_press = 10 ** (coef_a - coef_b / (temperature + coef_c))
                dewp = - coef_c
                dewp -= coef_b / (log10(humidity * part_press / 100.) - coef_a)
                return dewp
        return None


class BME280(I2cBaseClass):
    """BME280 sensor working in i2C bus."""

    def __init__(self, bus,
                 i2c_address=DEFAULT_I2C_ADDRESS,
                 osrs_t=DEFAULT_OVERSAMPLING_TEMP,
                 osrs_p=DEFAULT_OVERSAMPLING_PRES,
                 osrs_h=DEFAULT_OVERSAMPLING_HUM,
                 mode=DEFAULT_OPERATION_MODE,
                 t_sb=DEFAULT_T_STANDBY,
                 filter_mode=DEFAULT_FILTER_MODE,
                 delta_temp=DEFAULT_DELTA_TEMP,
                 spi3w_en=0,  # 3-wire SPI Disable
                 logger=None):
        """Initialize the sensor handler."""
        I2cBaseClass.__init__(self, bus, i2c_address, logger)
        # BME280 parameters
        self.mode = mode
        self.ctrl_meas_reg = (osrs_t << 5) | (osrs_p << 2) | self.mode
        self.config_reg = (t_sb << 5) | (filter_mode << 2) | spi3w_en
        self.ctrl_hum_reg = osrs_h

        self._delta_temp = delta_temp
        self._with_pressure = osrs_p > 0
        self._with_humidity = osrs_h > 0

        # Calibration data
        self._calibration_t = None
        self._calibration_h = None
        self._calibration_p = None
        self._temp_fine = None

        # Sensor data
        self._temperature = None
        self._humidity = None
        self._pressure = None

        self.update(True)

    def _compensate_temperature(self, adc_t):
        """Compensate temperature.

        Formula from datasheet Bosch BME280 Environmental sensor.
        8.1 Compensation formulas in double precision floating point
        Edition BST-BME280-DS001-10 | Revision 1.1 | May 2015
        """
        var_1 = ((adc_t / 16384.0 - self._calibration_t[0] / 1024.0)
                 * self._calibration_t[1])
        var_2 = ((adc_t / 131072.0 - self._calibration_t[0] / 8192.0)
                 * (adc_t / 131072.0 - self._calibration_t[0] / 8192.0)
                 * self._calibration_t[2])
        self._temp_fine = var_1 + var_2
        if self._delta_temp != 0.:  # temperature correction for self heating
            temp = self._temp_fine / 5120.0 + self._delta_temp
            self._temp_fine = temp * 5120.0
        else:
            temp = self._temp_fine / 5120.0
        return temp

    def _compensate_pressure(self, adc_p):
        """Compensate pressure.

        Formula from datasheet Bosch BME280 Environmental sensor.
        8.1 Compensation formulas in double precision floating point
        Edition BST-BME280-DS001-10 | Revision 1.1 | May 2015.
        """
        var_1 = (self._temp_fine / 2.0) - 64000.0
        var_2 = ((var_1 / 4.0) * (var_1 / 4.0)) / 2048
        var_2 *= self._calibration_p[5]
        var_2 += ((var_1 * self._calibration_p[4]) * 2.0)
        var_2 = (var_2 / 4.0) + (self._calibration_p[3] * 65536.0)
        var_1 = (((self._calibration_p[2]
                   * (((var_1 / 4.0) * (var_1 / 4.0)) / 8192)) / 8)
                 + ((self._calibration_p[1] * var_1) / 2.0))
        var_1 /= 262144
        var_1 = ((32768 + var_1) * self._calibration_p[0]) / 32768

        if var_1 == 0:
            return 0

        pressure = ((1048576 - adc_p) - (var_2 / 4096)) * 3125
        if pressure < 0x80000000:
            pressure = (pressure * 2.0) / var_1
        else:
            pressure = (pressure / var_1) * 2

        var_1 = (self._calibration_p[8]
                 * (((pressure / 8.0) * (pressure / 8.0)) / 8192.0)) / 4096
        var_2 = ((pressure / 4.0) * self._calibration_p[7]) / 8192.0
        pressure += ((var_1 + var_2 + self._calibration_p[6]) / 16.0)

        return pressure / 100

    def _compensate_humidity(self, adc_h):
        """Compensate humidity.

        Formula from datasheet Bosch BME280 Environmental sensor.
        8.1 Compensation formulas in double precision floating point
        Edition BST-BME280-DS001-10 | Revision 1.1 | May 2015.
        """
        var_h = self._temp_fine - 76800.0
        if var_h == 0:
            return 0

        var_h = ((adc_h - (self._calibration_h[3] * 64.0 +
                           self._calibration_h[4] / 16384.0 * var_h))
                 * (self._calibration_h[1] / 65536.0
                    * (1.0 + self._calibration_h[5] / 67108864.0 * var_h
                       * (1.0 + self._calibration_h[2] / 67108864.0 * var_h))))
        var_h *= 1.0 - self._calibration_h[0] * var_h / 524288.0

        if var_h > 100.0:
            var_h = 100.0
        elif var_h < 0.0:
            var_h = 0.0

        return var_h

    def _populate_calibration_data(self):
        """Populate calibration data.

        From datasheet Bosch BME280 Environmental sensor.
        """
        calibration_t = []
        calibration_p = []
        calibration_h = []
        raw_data = []

        try:
            for i in range(0x88, 0x88 + 24):
                raw_data.append(self._bus.read_byte_data(self._i2c_add, i))
            raw_data.append(self._bus.read_byte_data(self._i2c_add, 0xA1))
            for i in range(0xE1, 0xE1 + 7):
                raw_data.append(self._bus.read_byte_data(self._i2c_add, i))
        except OSError as exc:
            self.log_error("Can't populate calibration data: %s", exc)
            return

        calibration_t.append((raw_data[1] << 8) | raw_data[0])
        calibration_t.append((raw_data[3] << 8) | raw_data[2])
        calibration_t.append((raw_data[5] << 8) | raw_data[4])

        if self._with_pressure:
            calibration_p.append((raw_data[7] << 8) | raw_data[6])
            calibration_p.append((raw_data[9] << 8) | raw_data[8])
            calibration_p.append((raw_data[11] << 8) | raw_data[10])
            calibration_p.append((raw_data[13] << 8) | raw_data[12])
            calibration_p.append((raw_data[15] << 8) | raw_data[14])
            calibration_p.append((raw_data[17] << 8) | raw_data[16])
            calibration_p.append((raw_data[19] << 8) | raw_data[18])
            calibration_p.append((raw_data[21] << 8) | raw_data[20])
            calibration_p.append((raw_data[23] << 8) | raw_data[22])

        if self._with_humidity:
            calibration_h.append(raw_data[24])
            calibration_h.append((raw_data[26] << 8) | raw_data[25])
            calibration_h.append(raw_data[27])
            calibration_h.append((raw_data[28] << 4) | (0x0F & raw_data[29]))
            calibration_h.append(
                (raw_data[30] << 4) | ((raw_data[29] >> 4) & 0x0F))
            calibration_h.append(raw_data[31])

        for i in range(1, 2):
            if calibration_t[i] & 0x8000:
                calibration_t[i] = (-calibration_t[i] ^ 0xFFFF) + 1

        if self._with_pressure:
            for i in range(1, 8):
                if calibration_p[i] & 0x8000:
                    calibration_p[i] = (-calibration_p[i] ^ 0xFFFF) + 1

        if self._with_humidity:
            for i in range(0, 6):
                if calibration_h[i] & 0x8000:
                    calibration_h[i] = (-calibration_h[i] ^ 0xFFFF) + 1

        self._calibration_t = calibration_t
        self._calibration_h = calibration_h
        self._calibration_p = calibration_p

    def _take_forced_measurement(self):
        """Take a forced measurement.

        In forced mode, the BME sensor goes back to sleep after each
        measurement and we need to set it to forced mode once at this point,
        so it will take the next measurement and then return to sleep again.
        In normal mode simply does new measurements periodically.
        """
        # set to forced mode, i.e. "take next measurement"

        self._bus.write_byte_data(self._i2c_add, 0xF4, self.ctrl_meas_reg)
        while self._bus.read_byte_data(self._i2c_add, 0xF3) & 0x08:
        
             # removed 08/04/23- Lots of errors in loggs 
            sleep(1)
            
    def update(self, first_reading=False):
        """Read raw data and update compensated variables."""

        try:
            if first_reading or not self._ok:
                self._bus.write_byte_data(self._i2c_add, 0xF2,
                                          self.ctrl_hum_reg)
                self._bus.write_byte_data(self._i2c_add, 0xF5, self.config_reg)
                self._bus.write_byte_data(self._i2c_add, 0xF4,
                                          self.ctrl_meas_reg)
                self._populate_calibration_data()

            if self.mode == 2:  # MODE_FORCED
                self._take_forced_measurement()

            data = []
            for i in range(0xF7, 0xF7 + 8):
                data.append(self._bus.read_byte_data(self._i2c_add, i))
        except OSError as exc:
            self.log_error("Bad update: %s", exc)
            self._ok = False

            return

        pres_raw = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        temp_raw = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        hum_raw = (data[6] << 8) | data[7]
        self._ok = False

        temperature = self._compensate_temperature(temp_raw)
        if (temperature >= -20) and (temperature < 80):
            self._temperature = temperature
            self._ok = True
        if self._with_humidity:
            humidity = self._compensate_humidity(hum_raw)
            if (humidity >= 0) and (humidity <= 100):
                self._humidity = humidity
            else:
                self._ok = False
        if self._with_pressure:
            pressure = self._compensate_pressure(pres_raw)
            if pressure > 100:
                self._pressure = pressure
            else:
                self._ok = False

    @property
    def temperature(self):
        """Return temperature in celsius."""
        return self._temperature

    @property
    def humidity(self):
        """Return relative humidity in percentage."""
        return self._humidity

    @property
    def pressure(self):
        """Return pressure in hPa."""
        return self._pressure
