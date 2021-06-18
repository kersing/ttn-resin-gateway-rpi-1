# Script to check the python code creates a valid global_conf.json file on a Linux system running python2
export TEST=true
export BALENA_MACHINE_NAME='**None**'
export BALENA_ARCH='Not resin, testing'
export TTSCE_CLUSTER=eu1
export SERVER_TTN=true
export GW_CONTACT_EMAIL='me@my.email.domain'
export GW_DESCRIPTION='my gateway'
export GW_ID=gateway-id-from-console
export GW_KEY=gateway-key-with-link-gateway-to-gateway-server-rights
python2 run.py
