# HASS-BME-Multiplexor. Used on Raspberry Pi 3
Enable i2c on Raspberry.  https://www.home-assistant.io/common-tasks/os#enable-i2c  
Requiments Rpi.GPIO in custom componets. https://github.com/thecode/ha-rpi_gpio  

/configuration.yaml  
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
