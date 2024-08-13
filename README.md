# HASS-BME-Multiplexor. Used on Raspberry Pi 3
I2C Multiplexr 7 channels to pull 14 x BME280 sensors 

Enable i2c on Raspberry.  https://www.home-assistant.io/common-tasks/os#enable-i2c  
Requiments Rpi.GPIO in custom componets. https://github.com/thecode/ha-rpi_gpio  

Copy files to  /config/python_scripts/multi_bme280

#i2c Channel 4  BME280 Sensor 0x76
sensor_4_0x76 Change values to suit your Sensors
sensor_0_0x76
sensor_0_0x77

Add to configuration.yaml 

shell_command:
bme280_multiplexer: 'python3 /config/python_scripts/multi_bme280/bme280_multiplexer.py' 

command_line:
  - sensor: 
      name: BME 280 Pressure Sensor 
      command: "cat /config/python_scripts/multi_bme280/sensor_data.json"
      value_template: "{{ value_json['sensor_4_0x76']['pressure'] }}"
      unit_of_measurement: "hPa"
      scan_interval: 10
    
  - sensor: 
      name: BME 280 Humidity Sensor 
      command: "cat /config/python_scripts/multi_bme280/sensor_data.json"
      value_template: "{{ value_json['sensor_4_0x76']['humidity'] }}"
      unit_of_measurement: "%"
      scan_interval: 10
  
  - sensor:
      name: BME 280 Temperature Sensor 
      command: "cat /config/python_scripts/multi_bme280/sensor_data.json"
      value_template: "{{ value_json['sensor_4_0x77']['temperature'] }}"
      unit_of_measurement: "°C"
      scan_interval: 10
    
    ### Channel 5, BME = 0x76
  - sensor: 
      name: BME 280 Pressure Sensor 
      command: "cat /config/python_scripts/multi_bme280/sensor_data.json"
      value_template: "{{ value_json['sensor_5_0x76']['pressure'] }}"
      unit_of_measurement: "hPa"
      scan_interval: 10
    
  - sensor: 
      name: BME 280 Humidity Sensor 
      command: "cat /config/python_scripts/multi_bme280/sensor_data.json"
      value_template: "{{ value_json['sensor_5_0x76']['humidity'] }}"
      unit_of_measurement: "%"
      scan_interval: 10
  
  - sensor:
      name: BME 280 Temperature Sensor 
      command: "cat /config/python_scripts/multi_bme280/sensor_data.json"
      value_template: "{{ value_json['sensor_5_0x77']['temperature'] }}"
      unit_of_measurement: "°C"
      scan_interval: 10
    
Add a automation to refresh sensors.

alias: Pool BME280
description: ""
trigger:
  - platform: homeassistant
    event: start
  - platform: time_pattern
    seconds: "10"
condition: []
action:
  - metadata: {}
    data: {}
    action: shell_command.bme280_multiplexer
mode: single

