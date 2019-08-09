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
#########################################################
# Send the remote control TLV command  to Analog_Bridge #
# This function uses up to 3 possible parameters        #
# cmd address and port 					#
#########################################################
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

function setTLVRxPort() {
    echo "Setting TLV rxPort to $1 on port $port"
python - <<END
#!/usr/bin/env python

import sys
import socket
import struct

cmd = "rxport=$1"
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = struct.pack("BB", 0x05, len(cmd))[0:2] + cmd
_sock.sendto(cmd, ('127.0.0.1', $port))
_sock.close()

END
}

function setTLVTxPort() {
    echo "Setting TLV txPort to $1 on port $port"
python - <<END
#!/usr/bin/env python

import sys
import socket
import struct

cmd = "txport=$1"
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = struct.pack("BB", 0x05, len(cmd))[0:2] + cmd
_sock.sendto(cmd, ('127.0.0.1', $port))
_sock.close()

END
}

function exitAB() {
    echo "sending exit "0" "9" to AB on port $port"
python - <<END
#!/usr/bin/env python

import sys
import socket
import struct

cmd = "exit=0 9"
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = struct.pack("BB", 0x05, len(cmd))[0:2] + cmd
_sock.sendto(cmd, ('127.0.0.1', $port))
_sock.close()

END
}

function info() {
    echo "Seending info command on port $port"
python - <<END
#!/usr/bin/env python

import sys
import socket
import struct

cmd = "info"
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = struct.pack("BB", 0x05, len(cmd))[0:2] + cmd
_sock.sendto(cmd, ('127.0.0.1', $port))
_sock.close()

END
}

function determinePort() {
python - <<END
#!/usr/bin/env python

import json

json = json.loads(open('/tmp/ABInfo_12345.json').read())
port = json["tlv"]["rx_port"]
print port
END
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
		port=`determinePort`
    		tune $2
       ;;
        ambemode)
                port=`determinePort`
		setAmbeMode $2
        ;;
        tlvrxport)
                port=`determinePort`
                setTLVRxPort $2
       ;;
        tlvtxport)
                port=`determinePort`
                setTLVTxPort $2
       ;;
        info)
                port=`determinePort`
                info
       ;;
        exit)
		port=`determinePort`
		exitAB 0 9
        ;;
        stop)
            systemctl stop analog_bridge_ambe
            echo "Stop."
        ;;
        *)
    esac
fi


