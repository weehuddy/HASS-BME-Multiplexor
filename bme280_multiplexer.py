
import smbus2
import time
import logging
import yaml
import json
from ctypes import c_short, c_byte, c_ubyte

# Set up logging for debugging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Function to load configuration from YAML file
def load_config(config_file='/config/python_scripts/multi_bme280/config.yaml'):
    """
    Load configuration settings from a YAML file.
    
    :param config_file: Path to the configuration file.
    :return: Dictionary containing configuration settings.
    """
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
            logger.debug(f"Configuration loaded: {config}")
            return config['multiplexer']
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise

# Initialize I2C bus with a default value, will be overwritten by config
bus = None

def switch_channel(multiplexer_address, channel):
    """
    Switch to the specified channel on the TCA9548A multiplexer.

    :param multiplexer_address: I2C address of the TCA9548A multiplexer.
    :param channel: The channel number to switch to (0-7).
    """
    if 0 <= channel <= 7:
        bus.write_byte(multiplexer_address, 1 << channel)
        logger.debug(f"Switched to channel {channel} on TCA9548A.")
    else:
        logger.error(f"Invalid channel: {channel}. Must be between 0 and 7.")
        raise ValueError("Channel must be between 0 and 7")

def get_short(data, index):
    return c_short((data[index + 1] << 8) + data[index]).value

def get_ushort(data, index):
    return (data[index + 1] << 8) + data[index]

def read_bme280_calibration_data(address):
    """
    Read calibration data from the BME280 sensor.

    :param address: I2C address of the BME280 sensor.
    :return: Calibration data.
    """
    calibration = []
    for i in range(0x88, 0x88+24):
        calibration.append(bus.read_byte_data(address, i))
    calibration.append(bus.read_byte_data(address, 0xA1))
    for i in range(0xE1, 0xE1+7):
        calibration.append(bus.read_byte_data(address, i))

    dig_T1 = get_ushort(calibration, 0)
    dig_T2 = get_short(calibration, 2)
    dig_T3 = get_short(calibration, 4)

    dig_P1 = get_ushort(calibration, 6)
    dig_P2 = get_short(calibration, 8)
    dig_P3 = get_short(calibration, 10)
    dig_P4 = get_short(calibration, 12)
    dig_P5 = get_short(calibration, 14)
    dig_P6 = get_short(calibration, 16)
    dig_P7 = get_short(calibration, 18)
    dig_P8 = get_short(calibration, 20)
    dig_P9 = get_short(calibration, 22)

    dig_H1 = calibration[24]
    dig_H2 = get_short(calibration, 25)
    dig_H3 = calibration[27]

    dig_H4 = (calibration[28] << 4) | (calibration[29] & 0xF)
    dig_H5 = (calibration[30] << 4) | (calibration[29] >> 4)
    dig_H6 = c_byte(calibration[31]).value

    return {
        'T1': dig_T1, 'T2': dig_T2, 'T3': dig_T3,
        'P1': dig_P1, 'P2': dig_P2, 'P3': dig_P3, 'P4': dig_P4,
        'P5': dig_P5, 'P6': dig_P6, 'P7': dig_P7, 'P8': dig_P8, 'P9': dig_P9,
        'H1': dig_H1, 'H2': dig_H2, 'H3': dig_H3, 'H4': dig_H4, 'H5': dig_H5, 'H6': dig_H6
    }

def compensate_temperature(adc_T, calibration):
    """
    Convert raw temperature data to actual temperature in Celsius.
    """
    var1 = ((((adc_T >> 3) - (calibration['T1'] << 1))) * calibration['T2']) >> 11
    var2 = (((((adc_T >> 4) - calibration['T1']) * ((adc_T >> 4) - calibration['T1'])) >> 12) * calibration['T3']) >> 14
    t_fine = var1 + var2
    temperature = (t_fine * 5 + 128) >> 8
    return temperature / 100.0, t_fine

def compensate_pressure(adc_P, calibration, t_fine):
    """
    Convert raw pressure data to actual pressure in hPa.
    """
    var1 = t_fine - 128000
    var2 = var1 * var1 * calibration['P6']
    var2 = var2 + ((var1 * calibration['P5']) << 17)
    var2 = var2 + ((calibration['P4']) << 35)
    var1 = ((var1 * var1 * calibration['P3']) >> 8) + ((var1 * calibration['P2']) << 12)
    var1 = (((1 << 47) + var1) * calibration['P1']) >> 33

    if var1 == 0:
        return 0  # avoid exception caused by division by zero

    pressure = 1048576 - adc_P
    pressure = (((pressure << 31) - var2) * 3125) // var1
    var1 = (calibration['P9'] * (pressure >> 13) * (pressure >> 13)) >> 25
    var2 = (calibration['P8'] * pressure) >> 19

    pressure = ((pressure + var1 + var2) >> 8) + (calibration['P7'] << 4)
    return pressure / 25600.0

def compensate_humidity(adc_H, calibration, t_fine):
    """
    Convert raw humidity data to actual humidity in %.
    """
    var_H = t_fine - 76800
    var_H = (((((adc_H << 14) - (calibration['H4'] << 20) - (calibration['H5'] * var_H)) + 16384) >> 15) *
             (((((((var_H * calibration['H6']) >> 10) * (((var_H * calibration['H3']) >> 11) + 32768)) >> 10) + 2097152) *
               calibration['H2'] + 8192) >> 14))
    var_H = var_H - (((((var_H >> 15) * (var_H >> 15)) >> 7) * calibration['H1']) >> 4)
    var_H = 0 if var_H < 0 else var_H
    var_H = 419430400 if var_H > 419430400 else var_H
    return (var_H >> 12) / 1024.0

def read_bme280_sensor(address, calibration):
    """
    Read temperature, humidity, and pressure data from a BME280 sensor.
    
    :param address: I2C address of the BME280 sensor.
    :param calibration: Calibration data required for conversion.
    :return: A dictionary containing temperature, humidity, and pressure.
    """
    try:
        # Write to control and config registers (default settings)
        bus.write_byte_data(address, 0xF4, 0x27)  # Control register
        bus.write_byte_data(address, 0xF5, 0xA0)  # Config register

        time.sleep(0.5)  # Wait for the sensor to complete measurements

        # Reading raw data from the BME280
        data = bus.read_i2c_block_data(address, 0xF7, 8)
        adc_T = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        adc_P = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_H = (data[6] << 8) | data[7]

        # Compensate the raw data to get actual values
        temperature, t_fine = compensate_temperature(adc_T, calibration)
        pressure = compensate_pressure(adc_P, calibration, t_fine)
        humidity = compensate_humidity(adc_H, calibration, t_fine)
        format_pressure = "{:.2f}".format(pressure)
        format_humidity = "{:.2f}".format(humidity)
        return {
            'temperature': temperature,
            'pressure': format_pressure,
            'humidity': format_humidity
        }
    except Exception as e:
        logger.error(f"Failed to read from BME280 at address {hex(address)}: {e}")
        return None

def main():
    global bus
    
    # Load configuration
    config = load_config()
    
    # Initialize I2C bus with the configured bus number
    bus = smbus2.SMBus(config['i2c_bus'])
    
    # Optionally enable or disable debug mode based on the configuration
    #if config['debug']:
    #    logger.setLevel(logging.DEBUG)
   # else:
   #     logger.setLevel(logging.INFO)

    sensor_data_all = {}

    # Iterate through each sensor defined in the configuration
    for sensor in config['sensors']:
        channel = sensor['channel']
        address = sensor['address']
        
        try:
            # Switch to the appropriate channel on the multiplexer
            switch_channel(config['multiplexer_address'], channel)
            
            # Read calibration data for the BME280 sensor
            calibration = read_bme280_calibration_data(address)

            # Read actual sensor data from the BME280 sensor
            sensor_data = read_bme280_sensor(address, calibration)
            
            if sensor_data:
                sensor_data_all[f"sensor_{channel}_{hex(address)}"] = sensor_data
                logger.info(f"Sensor data from channel {channel}, address {hex(address)}: {sensor_data}")
            else:
                logger.warning(f"No data returned from sensor at channel {channel}, address {hex(address)}")
        except Exception as e:
            logger.error(f"Error while reading from channel {channel}, address {hex(address)}: {e}")

    # Output all sensor data as JSON
    json_data = json.dumps(sensor_data_all, indent=4)
    print(json_data)

    # Optionally, save to a file
    with open("/config/python_scripts/multi_bme280/sensor_data.json", "w") as json_file:
        json_file.write(json_data)

if __name__ == "__main__":
    main()
