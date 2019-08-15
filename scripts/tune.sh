#!/bin/bash

# /*
#  * Copyright (C) 2018 N4IRR
#  *
#  * Permission to use, copy, modify, and/or distribute this software for any
#  * purpose with or without fee is hereby granted, provided that the above
#  * copyright notice and this permission notice appear in all copies.
#  *
#  * THE SOFTWARE IS PROVIDED "AS IS" AND ISC DISCLAIMS ALL WARRANTIES WITH
#  * REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
#  * AND FITNESS.  IN NO EVENT SHALL ISC BE LIABLE FOR ANY SPECIAL, DIRECT,
#  * INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
#  * LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
#  * OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
#  * PERFORMANCE OF THIS SOFTWARE.
#  */

# tune.sh mode TG

# /usr/local/sbin/tune.sh tune dmr 93

##########################################

# Connect and disconnect from echo
# DMR
# /usr/local/sbin/tune.sh tune dmr 10
# /usr/local/sbin/tune.sh tune dmr 4000

# NXDN
# /usr/local/sbin/tune.sh tune nxdn 10
# /usr/local/sbin/tune.sh tune nxdn 9999

# P25
# /usr/local/sbin/tune.sh tune p25 10
# /usr/local/sbin/tune.sh tune p25 9999

# YSF
# /usr/local/sbin/tune.sh tune ysf "127.0.0.1:42012"
# /usr/local/sbin/tune.sh tune ysf disconnect

###############################################

# tune.sh mode nxdn

####################################

# "DMR", "YSFN", "NXDN", "P25", "YSFW", "DSTAR", "DMR_IPSC"
#  72      72      72     88      88      48        49

####################################


DMR_PORT=31100
DSTAR_PORT=32100
NXDN_PORT=33100
P25_PORT=34100
YSF_PORT=35100

function tune() {
    echo "Tuning to TG $1 on port $port"
python - <<END
#!/usr/bin/env python

import sys
import socket
import struct

cmd = "txTg=$1"
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = struct.pack("BB", 0x05, len(cmd))[0:2] + cmd
_sock.sendto(cmd, ('127.0.0.1', $port))
_sock.close()

END
}

function setAmbeMode() {
    echo "Setting AMBE mode to $1 on port $port"
python - <<END
#!/usr/bin/env python

import sys
import socket
import struct

cmd = "ambeMode=$1"
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = struct.pack("BB", 0x05, len(cmd))[0:2] + cmd
_sock.sendto(cmd, ('127.0.0.1', $port))
_sock.close()

END
}

function exitAB() {
    echo "exiting AB on port $port"
python - <<END
#!/usr/bin/env python

import sys
import socket
import struct

cmd = "exit=$3 $4"
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = struct.pack("BB", 0x05, len(cmd))[0:2] + cmd
_sock.sendto(cmd, ('127.0.0.1', $port))
_sock.close()

END
}

function determinePort() {
    case $1 in
        dmr | DMR)
            port=$DMR_PORT
        ;;
        ysf | YSF | YSFN | YSFW)
            port=$YSF_PORT
        ;;
        nxdn | NXDN)
            port=$NXDN_PORT
        ;;
        p25 | P25)
            port=$P25_PORT
        ;;
        dstar | DSTAR)
            port=$DSTAR_PORT
        ;;
        *)
            echo "Unknown mode"
            exit 1
        ;;
    esac
}

#################################################################
# The main application
#################################################################
if [ "${1}xxx" == "xxx" ]; then
    usage
else
    case $1 in
        -h|--help|"-?")
            usage
        ;;
        tune)
		determinePort $2
    		tune $3
       ;;
        none)
		none $2
        ;;
        ambemode)
		setAmbeMode $2
        ;;
        none)
		none
        ;;
        exit)
		determinePort $2
		exitAB $2 $3 $4
        ;;
        stop)
            systemctl stop analog_bridge
            echo "Stop."
        ;;
        *)
    esac
fi







#if [ $1 == exit ]; then
#    determinePort $2
#    exitAB $2 $3
#elif [ $1 == mode ]; then
#    determinePort $2
#    setAmbeMode $2
#elif [ $1 == exit ]; then
#    determinePort $2
#    exitAB $2 $3
#else
#    determinePort $1
#    tune $2
#fi

