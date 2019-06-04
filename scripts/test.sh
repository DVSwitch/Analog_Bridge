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

function tune() {
python - <<END
#!/usr/bin/env python

import sys
import socket
import struct

cmd = "txTg=$1"
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = struct.pack("BB", 0x05, len(cmd))[0:2] + cmd
_sock.sendto(cmd, ('127.0.0.1', 35103))
_sock.close()

END
}

tune $1

# Note: the port number above matches Analog_Bridge RXPort in the [AMBE_AUDIO] stanza
# Example tune values for each mode.
#
# DSTAR: (Reflector type, Number, Module, L)
#     REF030CL
#     XRF012AL
#     DCS006ZL
#
# DMR, P25, NXDN: (Just the tg number)
#     10200
#     310
#     3166
#
# YSF: (IP:PORT)
#     amlink.alabamalink.info:42001
#     96.47.95.121:42000

