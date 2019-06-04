#################################################################
#
#################################################################
function setCallAndID() {
    if [ ! ${DEBUG}xx == xx ]; then
        echo "setCallAndID $1"
    else
python - <<END
#!/usr/bin/env python

import sys
import socket
import struct

call = "$1"
dmr_id = $2
tlvLen = 3 + 4 + 3 + 1 + 1 + len(call) + 1                      # dmrID, repeaterID, tg, ts, cc, call, 0
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = struct.pack("BBBBBBBBBBBBBB", 0x08, tlvLen, ((dmr_id >> 16) & 0xff),((dmr_id >> 8) & 0xff),(dmr_id & 0xff),0,0,0,0,0,0,0,0,0)[0:14] + call + chr(0)
_sock.sendto(cmd, ('127.0.0.1', $TLV_PORT))
_sock.close()

END
    fi
}

TLV_PORT=31100
setCallAndID $1 $2

