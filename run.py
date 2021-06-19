#!/usr/bin/python
"""
Author: JP Meijers
Date: 2017-02-26
Based on: https://github.com/rayozzie/ttn-resin-gateway-rpi/blob/master/run.sh

2019-11-08: Modified by pe1mew to add GW_LOGGER and GW_AUTOQUIT_THRESHOLD
2021-06-11: Modified by kersing for TTS CE (also known as TTN V3)
"""
import os
import os.path
import sys
import urllib2
import time
import uuid
import json
import subprocess

# Allow testing on a 'regular' system
if os.environ.get('TEST') == None:
  try:
    import RPi.GPIO as GPIO
  except RuntimeError:
    print("Error importing RPi.GPIO!  This is probably because you need superuser privileges.  You can achieve this by using 'sudo' to run your script")

  if not os.path.exists("/opt/ttn-gateway/mp_pkt_fwd"):
    print ("ERROR: gateway executable not found. Is it built yet?")
    sys.exit(0)

GWID_PREFIX="FFFE"

if os.environ.get('HALT') != None:
  print ("*** HALT asserted - exiting ***")
  sys.exit(0)

# Show info about the machine we're running on
print ("*** Resin Machine Info:")
print ("*** Type: "+str(os.environ.get('BALENA_MACHINE_NAME')))
print ("*** Arch: "+str(os.environ.get('BALENA_ARCH')))

if os.environ.get("BALENA_HOST_CONFIG_core_freq")!=None:
  print ("*** Core freq: "+str(os.environ.get('BALENA_HOST_CONFIG_core_freq')))

if os.environ.get("BALENA_HOST_CONFIG_dtoverlay")!=None:
  print ("*** UART mode: "+str(os.environ.get('BALENA_HOST_CONFIG_dtoverlay')))


# Check if the correct environment variables are set

print ("*******************")
print ("*** Configuration:")
print ("*******************")

if os.environ.get("GW_EUI")==None:
  # The FFFE should be inserted in the middle (so xxxxxxFFFExxxxxx)
  my_eui = format(uuid.getnode(), '012x')
  my_eui = my_eui[:6]+GWID_PREFIX+my_eui[6:]
  my_eui = my_eui.upper()
else:
  my_eui = os.environ.get("GW_EUI")

print ("GW_EUI:\t"+my_eui)

if os.environ.get("GW_TTSCE_CLUSTER")==None:
  ttsce_domain="eu1.cloud.thethings.network"
else:
  ttsce_domain=os.environ.get("GW_TTSCE_CLUSTER")+".cloud.thethings.network"
print("TTS(CE) Cluster: %s" % ttsce_domain)

# Define default configs
description = os.getenv('GW_DESCRIPTION', "")
placement = ""
latitude = os.getenv('GW_REF_LATITUDE', 0)
longitude = os.getenv('GW_REF_LONGITUDE', 0)
altitude = os.getenv('GW_REF_ALTITUDE', 0)

# Fetch config from TTN if TTN is enabled
if(os.getenv('SERVER_TTN', "true")=="true"):
  print ("Enabling TTN gateway connector")

  if os.environ.get("GW_ID")==None:
    print ("WARNING: No GW_ID defined. Falling back to EUI.")
    my_gw_id = "eui-"+my_eui.lower()
    print ("GW_ID:\t"+my_gw_id)
  else:
    my_gw_id = os.environ.get("GW_ID")

  if os.environ.get("GW_KEY")==None:
    print ("ERROR: GW_KEY required")
    print ("See https://www.thethingsnetwork.org/docs/gateways/registration.html#via-gateway-connector")
    sys.exit(0)

  config_url = os.getenv('FREQ_PLAN_URL', "https://%s/api/v3/gcs/gateways/%s/semtechudp/global_conf.json" % (ttsce_domain,my_gw_id))

  print ("*******************")
  print ("*** Fetching config from TTN account server")
  print ("*******************")

  # Fetch the URL, if it fails try 30 seconds later again.
  config_response = ""
  while True:
    try:
      req = urllib2.Request(config_url)
      req.add_header('Authorization', 'Bearer '+os.environ.get("GW_KEY"))
      response = urllib2.urlopen(req, timeout=30)
      config_response = response.read()
    except urllib2.URLError as err: 
      print (err)
      print ("Unable to fetch configuration from TTN. Is the TTN API reachable from gateway? Are your GW_ID and GW_KEY correct? Retry       in 30s")
      time.sleep(30)
      continue
    break

  # Parse config
  ttn_config = {}
  try:
    ttn_config = json.loads(config_response)
  except:
    print ("Unable to parse configuration from TTN")
    sys.exit(0)

  if os.environ.get("ROUTER_MQTT_ADDRESS"):
    router = os.environ.get("ROUTER_MQTT_ADDRESS")
  elif "gateway_conf" in ttn_config:
    router = ttn_config['gateway_conf'].get('server_address', "eu1.cloud.thethings.network")
    router = router+':1881'
  else:
    router = "eu1.cloud.thethings.network:1881"

  print ("Gateway ID:\t"+my_gw_id)
  print ("Gateway Key:\t"+os.environ.get("GW_KEY"))
  print ("Router:\t\t"+router)
  print ("")
# Done fetching config from TTN
else:
  print ("TTN gateway connector disabled. Exitting.")
  sys.exit(1)

print ("Gateway EUI:\t"+my_eui)
print ("Has hardware GPS:\t"+str(os.getenv('GW_GPS', False)))
print ("Hardware GPS port:\t"+os.getenv('GW_GPS_PORT', "/dev/ttyAMA0"))

sx1301_conf = ttn_config['SX1301_conf']
sx1301_conf['antenna_gain'] = float(os.getenv('GW_ANTENNA_GAIN', 0))

# Build local_conf
gateway_conf = {}
gateway_conf['gateway_ID'] = my_eui
gateway_conf['contact_email'] = os.getenv('GW_CONTACT_EMAIL', "")
gateway_conf['description'] = description
gateway_conf['push_timeout_ms'] = int(os.getenv("GW_PUSH_TIMEOUT", 100)) # Default in code is 100


if(os.getenv('GW_FWD_CRC_ERR', "false")=="true"):
  #default is False
  gateway_conf['forward_crc_error'] = True

if(os.getenv('GW_FWD_CRC_VAL', "true")=="false"):
  #default is True
  gateway_conf['forward_crc_valid'] = False

if(os.getenv('GW_DOWNSTREAM', "true")=="false"):
  #default is True
  gateway_conf['downstream'] = False

# Parse GW_GPS env var. It is a string, we need a boolean.
if(os.getenv('GW_GPS', "false")=="true"):
  gw_gps = True
else:
  gw_gps = False

# Use hardware GPS
if(gw_gps):
  print ("Using real GPS")
  gateway_conf['gps'] = True
  gateway_conf['fake_gps'] = False
  gateway_conf['gps_tty_path'] = os.getenv('GW_GPS_PORT', "/dev/ttyAMA0")
# Use fake GPS with coordinates from TTN
elif(gw_gps==False and latitude!=0 and longitude!=0):
  print ("Using fake GPS")
  gateway_conf['gps'] = True
  gateway_conf['fake_gps'] = True
  gateway_conf['ref_latitude'] = float(latitude)
  gateway_conf['ref_longitude'] = float(longitude)
  gateway_conf['ref_altitude'] = float(altitude)
# No GPS coordinates
else:
  print ("Not sending coordinates")
  gateway_conf['gps'] = False
  gateway_conf['fake_gps'] = False

# Log all LoRaWAN packets to console
if(os.getenv('GW_LOGGER', "false")=="true"):
  gateway_conf['logger'] = True
  print ("Packet logging enabled")
else:
  gateway_conf['logger'] = False

# Autoquit when a number of PULL_ACKs have been missed
autoquit_threshold = int(os.getenv('GW_AUTOQUIT_THRESHOLD', 0))
if(autoquit_threshold > 0):
  gateway_conf['autoquit_threshold'] = int(os.getenv('GW_AUTOQUIT_THRESHOLD', 5))
  print ("Autoquit after", gateway_conf['autoquit_threshold'], "missed PULL_ACKs")

# Add server configuration
gateway_conf['servers'] = []

# Add TTN server
if(os.getenv('SERVER_TTN', "true")=="true"):
  server = {}
  server['serv_type'] = "ttn"
  server['server_address'] = router
  server['serv_gw_id'] = my_gw_id
  server['serv_gw_key'] = os.environ.get("GW_KEY")
  server['serv_enabled'] = True
  if(os.getenv('SERVER_TTN_DOWNLINK', "true")=="false"):
    server['serv_down_enabled'] = False
  else:
    server['serv_down_enabled'] = True
  gateway_conf['servers'].append(server)
else:
  if(os.getenv('SERVER_0_ENABLED', "false")=="true"):
    server = {}
    if(os.getenv('SERVER_0_TYPE', "semtech")=="ttn"):
      server['serv_type'] = "ttn"
      server['serv_gw_id'] = os.environ.get("SERVER_0_GWID")
      server['serv_gw_key'] = os.environ.get("SERVER_0_GWKEY")
    server['server_address'] = os.environ.get("SERVER_0_ADDRESS")
    server['serv_port_up'] = int(os.getenv("SERVER_0_PORTUP", 1700))
    server['serv_port_down'] = int(os.getenv("SERVER_0_PORTDOWN", 1700))
    server['serv_enabled'] = True
    if(os.getenv('SERVER_0_DOWNLINK', "false")=="true"):
      server['serv_down_enabled'] = True
    else:
      server['serv_down_enabled'] = False
    gateway_conf['servers'].append(server)

# Add up to 3 additional servers
if(os.getenv('SERVER_1_ENABLED', "false")=="true"):
  server = {}
  if(os.getenv('SERVER_1_TYPE', "semtech")=="ttn"):
    server['serv_type'] = "ttn"
    server['serv_gw_id'] = os.environ.get("SERVER_1_GWID")
    server['serv_gw_key'] = os.environ.get("SERVER_1_GWKEY")
  server['server_address'] = os.environ.get("SERVER_1_ADDRESS")
  server['serv_port_up'] = int(os.getenv("SERVER_1_PORTUP", 1700))
  server['serv_port_down'] = int(os.getenv("SERVER_1_PORTDOWN", 1700))
  server['serv_enabled'] = True
  if(os.getenv('SERVER_1_DOWNLINK', "false")=="true"):
    server['serv_down_enabled'] = True
  else:
    server['serv_down_enabled'] = False
  gateway_conf['servers'].append(server)

if(os.getenv('SERVER_2_ENABLED', "false")=="true"):
  server = {}
  if(os.getenv('SERVER_2_TYPE', "semtech")=="ttn"):
    server['serv_type'] = "ttn"
    server['serv_gw_id'] = os.environ.get("SERVER_2_GWID")
    server['serv_gw_key'] = os.environ.get("SERVER_2_GWKEY")
  server['server_address'] = os.environ.get("SERVER_2_ADDRESS")
  server['serv_port_up'] = int(os.getenv("SERVER_2_PORTUP", 1700))
  server['serv_port_down'] = int(os.getenv("SERVER_2_PORTDOWN", 1700))
  server['serv_enabled'] = True
  if(os.getenv('SERVER_2_DOWNLINK', "false")=="true"):
    server['serv_down_enabled'] = True
  else:
    server['serv_down_enabled'] = False
  gateway_conf['servers'].append(server)

if(os.getenv('SERVER_3_ENABLED', "false")=="true"):
  server = {}
  if(os.getenv('SERVER_3_TYPE', "semtech")=="ttn"):
    server['serv_type'] = "ttn"
    server['serv_gw_id'] = os.environ.get("SERVER_3_GWID")
    server['serv_gw_key'] = os.environ.get("SERVER_3_GWKEY")
  server['server_address'] = os.environ.get("SERVER_3_ADDRESS")
  server['serv_port_up'] = int(os.getenv("SERVER_3_PORTUP", 1700))
  server['serv_port_down'] = int(os.getenv("SERVER_3_PORTDOWN", 1700))
  server['serv_enabled'] = True
  if(os.getenv('SERVER_3_DOWNLINK', "false")=="true"):
    server['serv_down_enabled'] = True
  else:
    server['serv_down_enabled'] = False
  gateway_conf['servers'].append(server)


# We merge the json objects from the global_conf and local_conf and save it to the global_conf.
# Therefore there will not be a local_conf.json file.
local_conf = {'SX1301_conf': sx1301_conf, 'gateway_conf': gateway_conf}

if os.environ.get('TEST') == None:
  with open('/opt/ttn-gateway/global_conf.json', 'w') as the_file:
    the_file.write(json.dumps(local_conf, indent=4))
else:
  with open('global_conf.json', 'w') as the_file:
    the_file.write(json.dumps(local_conf, indent=4))
  sys.exit(0)

# Endless loop to reset and restart packet forwarder
while True:
  # Reset the gateway board - this only works for the Raspberry Pi.
  GPIO.setmode(GPIO.BOARD) # hardware pin numbers, just like gpio -1

  if (os.environ.get("GW_RESET_PIN")!=None):
    try:
      pin_number = int(os.environ.get("GW_RESET_PIN"))
      print ("[TTN Gateway]: Resetting concentrator on pin "+str(os.environ.get("GW_RESET_PIN")))
      GPIO.setup(pin_number, GPIO.OUT, initial=GPIO.LOW)
      GPIO.output(pin_number, 0)
      time.sleep(0.1)
      GPIO.output(pin_number, 1)
      time.sleep(0.1)
      GPIO.output(pin_number, 0)
      time.sleep(0.1)
      GPIO.input(pin_number)
      GPIO.cleanup(pin_number)
      time.sleep(0.1)
    except ValueError:
      print ("Can't interpret "+os.environ.get("GW_RESET_PIN")+" as a valid pin number.")

  else:
    print ("[TTN Gateway]: Resetting concentrator on default pin 22.")
    GPIO.setup(22, GPIO.OUT, initial=GPIO.LOW)
    GPIO.output(22, 0)
    time.sleep(0.1)
    GPIO.output(22, 1)
    time.sleep(0.1)
    GPIO.output(22, 0)
    time.sleep(0.1)
    GPIO.input(22)
    GPIO.cleanup(22)
    time.sleep(0.1)

  # Start forwarder
  subprocess.call(['/opt/ttn-gateway/mp_pkt_fwd', '-c', '/opt/ttn-gateway/', '-s', os.getenv('SPI_SPEED', '8000000')])
  time.sleep(15)
