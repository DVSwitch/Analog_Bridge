#!/bin/bash
# set -o errexit

######################################################
SCRIPT_VERSION="update config.php"                   #
SCRIPT_AUTHOR="N4IRS"                                #
SCRIPT_DATE="10/07/2020"                             #
######################################################

if [ "$1" != "" ]; then
    case $1 in
        -v|-V|--version) echo $SCRIPT_VERSION; exit 0 ;;
        -a|-A|--author)  echo $SCRIPT_AUTHOR;  exit 0 ;;
        -d|-D|--date)    echo $SCRIPT_DATE;    exit 0 ;;
                   *)    echo "Unknown parameter used: $1"; exit 1 ;;
    esac
fi

echo
echo $SCRIPT_VERSION $SCRIPT_DATE
echo

[ -x "/opt/MMDVM_Bridge/dvswitch.sh" ] && ABrxPort=$(/opt/MMDVM_Bridge/dvswitch.sh pif /opt/Analog_Bridge/Analog_Bridge.ini USRP rxPort)
echo "rxPort read from /opt/Analog_Bridge/Analog_Bridge =" $ABrxPort

filename="/var/www/html/include/config.php"
if [ -f "$filename" ]
then
        sed -i '/ABINFO/c\define("ABINFO",'\""$ABrxPort"\"');' /var/www/html/include/config.php
        echo "/var/www/html/include/config.php updated"
fi
echo

