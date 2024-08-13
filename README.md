# HASS-BME-Multiplexor. Used on Raspberry Pi 3
Enable i2c on Raspberry.  https://www.home-assistant.io/common-tasks/os#enable-i2c  
Requiments Rpi.GPIO in custom componets. https://github.com/thecode/ha-rpi_gpio  


  - platform: bme280_new_c
    name: SensorName  
    i2c_address: 0x76     # Address of BME280  
    i2c_channel: 4        # Channel on Multiplexer  
    operation_mode: 2     # 2 forced mode  
    time_standby: 5  
    oversampling_temperature: 4  
    oversampling_pressure: 4  
    oversampling_humidity: 4  
    delta_temperature: -2  
    monitored_conditions:  
      - temperature  
      - humidity  
      - pressure  
    scan_interval: 60  


Add to configuration.yaml  bme280_multiplexer: 'python3 /config/python_scripts/multi_bme280/bme280_multiplexer.py' 


i2c multplexer channel = 4, bme Sensor 0x76
sensor_4_0x76']['humidity']

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
    
Add a automation to refresh sensors

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

