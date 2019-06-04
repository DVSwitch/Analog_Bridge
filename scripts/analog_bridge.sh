#!/usr/bin/env bash
set -o errexit

# N4IRS 06/19/2018

#################################################
#                                               #
#                                               #
#                                               #
#################################################

# From Analog_Bridge .ini files
# dmr = /opt/Analog_Bridge/Analog_Bridge.sh dmr.ini
# dstar = /opt/Analog_Bridge/Analog_Bridge.sh dstar.ini
# nxdn = /opt/Analog_Bridge/Analog_Bridge.sh nxdn.ini
# p25 = /opt/Analog_Bridge/Analog_Bridge.sh p25.ini
# ysf = /opt/Analog_Bridge/Analog_Bridge.sh ysf.ini

echo copying $1 to /opt/opt/Analog_Bridge_Single_Port/Analog_Bridge.ini

cp /opt/Analog_Bridge_Single_Port/$1 /tmp/Analog_Bridge.ini
cp /opt/Analog_Bridge_Single_Port/$1 /opt/Analog_Bridge_Single_Port/Analog_Bridge.ini

mode=`cat /tmp/ABInfo_12345.json | python -c 'import json,sys;obj=json.load(sys.stdin); print obj["tlv"]["ambe_mode"];'`

/usr/local/sbin/ab-restart.sh $mode 0 5

# systemctl restart analog_bridge_ambe

