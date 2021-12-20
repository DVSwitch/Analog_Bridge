###############################################################################
#
#   Copyright (C) 2017 Mike Zingman N4IRR
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
#
###############################################################################


import serial
import sys
import getopt
import array
import _thread
import time
import string
from time import sleep
import socket

_sock = None
useSerial = True
ip_address = "127.0.0.1"
UDP_PORT = 2460


reset = bytearray.fromhex("61 00 07 00 34 05 00 00 0F 00 00")
setDstar = bytearray.fromhex("61 00 0d 00 0a 01 30 07 63 40 00 00 00 00 00 00 48")
getProdId = bytearray.fromhex("61 00 01 00 30")
getVersion = bytearray.fromhex("61 00 01 00 31")
setDMR = bytearray.fromhex("61 00 0D 00 0A 04 31 07 54 24 00 00 00 00 00 6F 48")
encodeAMBE = bytearray.fromhex("61 00 0B 01 01 48")
encodePCM = bytearray.fromhex("61 01 42 02")

silence = bytearray.fromhex("AC AA 40 20 00 44 40 80 80")

shouldStopOnError = False
errorCount = 0
verbose = False

def stopOnError():
    global errorCount
    errorCount += 1
    if shouldStopOnError == True:
        quit()

def ambeSend( port, cmd ):
    if useSerial == True:
        return port.write(cmd)
    else:
        return _sock.sendto(cmd, (ip_address, UDP_PORT))

def ambeRecv( port ):
    if useSerial == True:
        _val1 = port.read(4)                                # Read the header
        if len(_val1) == 4:
            _packetLen = (_val1[1] * 256) + _val1[2]            # Grab the packet length
            _val2 = port.read(_packetLen)                       # Read the rest of the data
            _val = _val1 + _val2                                # Concat the header and the payload
        else:
            print('Error, AMBE header was corrupt')
            stopOnError()
            return 0, ''
        return len(_val), _val
    else:
        try:
            _sock.settimeout(2)
            data, addr = _sock.recvfrom(1024) # buffer size is 1024 bytes
        except:
            data = ""
        return len(data), data

def ambeValidate( port, cmd, expect, label ):
    if verbose == True:
        print("Testing", label)
    _wrote = ambeSend( port, cmd )
    if _wrote != len(cmd):
        print('Error, tried to write', len(cmd),'and did write',_wrote,'bytes',label)
        stopOnError()
    else:
        _readLen, buffer = ambeRecv(port)
        if _readLen == 0:
            print('Error, no reply from DV3000.  Command issued was:', label)
            stopOnError()
        else:
            if buffer[0] != 0x61:
                print('Errror, DV3000 send back invalid start byte.  Expected 0x61 and got', buffer[0],label)
                print(''.join('{:02x}'.format(x) for x in buffer))
                stopOnError()
            else:
                _packetLen = (buffer[1] * 256) + buffer[2]
                if _readLen != (_packetLen+4):
                    print('Error, read', _readLen,'Bytes and AMBE header says it has',_packetLen,'bytes',label)
                    print(''.join('{:02x}'.format(x) for x in buffer))
                    stopOnError()
                else:
                    _payload = buffer[4:]
                    if len(_payload) > 0:
                        for x in range(0,len(expect)):
                            if _payload[x] != expect[x]:
                                print("In test", label)
                                print('Error, did not get expected value from DV3000.  Got:',_payload,'expected',expect)
                                print(''.join('{:02x}'.format(x) for x in _payload))
                                stopOnError()
                                return None, None
                    if verbose == True:
                        print('Test result: Success ('+''.join('{:02x}'.format(x) for x in buffer)+")")
                    return buffer[0:4], _payload
    return None, None


def main(argv):
    global useSerial
    global _sock
    global ip_address
    global verbose
    global shouldStopOnError
    
    useSerial = True
    SERIAL_BAUD=230400
    serialport = "/dev/ttyAMA0"
    try:
        opts, args = getopt.getopt(argv,"vehns:i:",["serial="])
    except getopt.GetoptError:
        print('AMBEtest4.py [-e -v] -s <serial port>')
        print('AMBEtest4.py [-e -v -n] -s <serial port> (for ThumbDV Model A)')
        print('AMBEtest4.pi [-e -v] -i address')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('AMBEtest4.py -s <serial port>')
            sys.exit()
        elif opt in ("-s", "--serial"):
            serialport = arg
        elif opt in ("-i", "--ip"):
            useSerial = False
            ip_address = arg
        elif opt in ("-e", "--error"):
            shouldStopOnError = True
        elif opt in ("-v", "--verbose"):
            verbose = True
        elif opt == "-n":
            SERIAL_BAUD=460800

    if useSerial == True:
        try:
            print('Setting serial port')
            port = serial.Serial(serialport, baudrate=SERIAL_BAUD, timeout=1.0, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False, dsrdtr=False)
        except:
            print('Error opening serial port', serialport)
            exit(2)
            
        port.flushInput()
        port.flushOutput()

        print('Serial port parameters:')
        print('Port name:\t', serialport)
        print('Baudrate:\t', str(port.baudrate))
        print('Byte size:\t', port.bytesize)
        print('Parity:\t\t', port.parity)
        print('Stop bits:\t', port.stopbits)
        print('Xon Xoff:\t', port.xonxoff)
        print('RTS/CTS:\t', port.rtscts)
        print('DST/DTR:\t', port.dsrdtr)

        time.sleep(0.02)
        rcv = port.read(10)
        sys.stdout.write(rcv)
    else:
        _sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        _sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port = _sock

    print('*********************')
    if verbose != True:
        print('Silent testing mode.....')

    ambeValidate(port, reset, bytearray.fromhex("39"), 'Reset DV3000')
    ambeValidate(port, getProdId, bytearray.fromhex("30414d4245333030305200"), 'Get Product ID')
    ambeValidate(port, getVersion, bytearray.fromhex("31563132302e453130302e585858582e433130362e473531342e523030392e42303031303431312e433030323032303800"), 'Get Version')
    ambeValidate(port, setDstar, bytearray.fromhex("0a00"), 'Set DSTAR Mode')

    ambeValidate(port, reset, bytearray.fromhex("39"), 'Reset DV3000')
    ambeValidate(port, setDMR, bytearray.fromhex("0a00"), 'Set DMR Mode')

    for _ in range(0,1000):
        DMRAmbe = encodeAMBE + silence
        _header, _payload = ambeValidate(port, DMRAmbe, '', 'Decode AMBE')
        if _payload != None:
            if _header+_payload == str(bytearray.fromhex("6100010039")):
                print("Error, the DV3000 has unexpectly reset")
                stopOnError()
            elif len(_payload) != 322: # 320 of PCM plus one field ID and one bit length byte
                print('Error, did not get the right number of PCM bytes back from an encode',len(_payload))
                stopOnError()
            elif (_payload[0] != 0x00) or (_payload[1] != 0xa0):
                print('Error, PCM should be channel 0 and have 320 bits')
                stopOnError()
            elif _header[3] != 0x02: # type is AUDIO
                print('Error, PCM type is invalid', _header[3])
                stopOnError()
            DMRPCM = encodePCM + _payload 
            expect = bytearray.fromhex("48954be6500310b00777")
            _header, _payload = ambeValidate(port, DMRPCM, '', 'Encode PCM')
            if _payload != None:
                if _header+_payload == str(bytearray.fromhex("6100010039")):
                    print("Error, the DV3000 has unexpectly reset")
                    stopOnError()
                elif len(_payload) != 11: # 9 of AMBE plus one bit length byte
                    print('Error, did not get the right number of AMBE bytes back from an encode',len(_payload))
                    stopOnError()
                elif _header[3] != 0x01: # type is AMBE
                    print('Error, AMBE type is invalid', _header[3])
                    stopOnError()
                elif _payload[0] != 0x01: #channel ID must be 1
                    print('AMBE channel ID is not correct')
                    stopOnError()
                elif _payload[1] != 0x48: # 72 bits in length
                    print('AMBE bit length is not correct', _payload[1])
                    stopOnError()
            else:
                print('Error, encode PCM to AMBE return no results')
                stopOnError()
        else:
            print('Error, decode AMBE to PCM return no results')
            stopOnError()
    print('Error count = ', errorCount)

if __name__ == "__main__":
    main(sys.argv[1:])
