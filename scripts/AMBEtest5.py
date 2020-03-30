#!/usr/bin/env python3
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
# ported to python3    CSylvain KB3CS    2020-03-29
###############################################################################

import serial
import sys
import getopt
import array

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
getVersion_expected = bytearray.fromhex("31563132302e453130302e585858582e433130362e473531342e523030392e4230303130343131
2e433030323032303800")

setDMR = bytearray.fromhex("61 00 0D 00 0A 04 31 07 54 24 00 00 00 00 00 6F 48")
encodeAMBE = bytearray.fromhex("61 00 0B 01 01 48")
encodePCM = bytearray.fromhex("61 01 42 02")

silence = bytearray.fromhex("AC AA 40 20 00 44 40 80 80")

shouldStopOnError = False
errorCount = 0
verbose = False
is_encdec = False

def padstring( s, w ): # s is type str; w type int
    fmt='{:<'+str(w)+'}'
    return fmt.format(s)

def stopOnError():
    global errorCount
    errorCount += 1
    if shouldStopOnError == True:
        quit()

def ambeSend( port, cmd ):
    if useSerial == True:
        try:
            rv = port.write(cmd)
        except BaseException as err:
            print(err)
            stopOnError()
            return 0
    else:
        try:
            rv = _sock.sendto(cmd, (ip_address, UDP_PORT))
        except BaseException as err:
            print(err)
            stopOnError()
            return 0
    return rv

def ambeRecv( port ):
    if useSerial == True:
        try:
            _val1 = port.read(4)                                # Read the header
        except BaseException as err:
            print(err)
            stopOnError()
            return 0, ''

        if len(_val1) == 4:
            _packetLen = int.from_bytes(_val1[1:3],byteorder='big',signed=False) # grab the 16bit packet length

            try:
                _val2 = port.read(_packetLen)                       # Read the rest of the data
            except BaseException as err:
                print(err)
                stopOnError()
                return 0, ''

            _val = _val1 + _val2                                # Concat the header and the payload
        elif len(_val1) == 0:
            print('Unable to read from serial port. (device disconnected or wrong baud rate?)')
            stopOnError()
            return 0, ''
        else:
            print('Error, AMBE header was corrupt')
            stopOnError()
            return 0, ''
        return len(_val), _val
    else:
        try:
            _sock.settimeout(2)
            data, addr = _sock.recvfrom(1024) # buffer size is 1024 bytes
        except BaseException as err:
            print(err)
            stopOnError()
            data = ''
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
            print('Error, no reply from DV3000. Command issued was:', label)
            stopOnError()
        else:
            if buffer[0:1] != b'\x61':
                print('Error, DV3000 sent back invalid start byte. Expected 0x61 and got 0x'+bytearray(buffer[0:1]).hex
(),label)
                print(buffer.hex())
                stopOnError()
            else:
#                _packetLen = (ord(buffer[1]) * 256) + ord(buffer[2]) # (python2)
                _packetLen = int.from_bytes(buffer[1:3],byteorder='big',signed=False) # grab 16bit packet length
                if _readLen != (_packetLen+4):
                    print('Error, read', _readLen,'bytes and AMBE header says it has',_packetLen,'bytes',label)
                    print(buffer.hex())
                    stopOnError()
                else:
                    _payload = buffer[4:]
                    if len(_payload) > 0:
                        for x in range(0,len(expect)):
                            if _payload[x:x+1] != expect[x:x+1]:
                                print("In test", label)
                                print('Error, did not get expected value from DV3000.  Got:',_payload,'expected',expect
)
                                print(_payload.hex())
                                stopOnError()
                                return None, None
                    if verbose == True:
                        print('Test result: Success ('+buffer.hex()+')')
                    elif is_encdec != True:
                        print(padstring(label+':',16)+'\t','Pass')
                    return buffer[0:4], _payload
    return None, None

def cmdusage():
    print('\nAMBEtest5.py -h\t(help: command usage)')
    print('AMBEtest5.py --help\n')
    print('AMBEtest5.py [-e -v] -s <serial port>\t\t(for DV3000, DV3K, Star*DV, DVstick, etc.)')
    print('AMBEtest5.py [-e -v] -n -s <serial port>\t(for ThumbDV)')
    print('AMBEtest5.py [-e -v] -i <ip address>\n')
    print('AMBEtest5.py [--error --verbose] --serial <serial port>')
    print('AMBEtest5.py [--error --verbose] --thumbdv --serial <serial port>')
    print('AMBEtest5.py [--error --verbose] --ip <ip address>\n')

def main(argv):
    global useSerial
    global _sock
    global ip_address
    global verbose
    global shouldStopOnError
    global is_encdec

    useSerial = True
    SERIAL_BAUD=230400
    serialport = "/dev/ttyAMA0"
    try:
        opts, args = getopt.getopt(argv,"vehns:i:",["serial=","ip=","verbose","help","error","thumbdv"])
    except getopt.GetoptError as err:
        print('\nError:',err)
        cmdusage()
        exit(2)
    for opt, arg in opts:
        if opt in ('-h','--help'):
            cmdusage()
            exit()
        elif opt in ("-s", "--serial"):
            serialport = arg
        elif opt in ("-i", "--ip"):
            useSerial = False
            ip_address = arg
        elif opt in ("-e", "--error"):
            shouldStopOnError = True
        elif opt in ("-v", "--verbose"):
            verbose = True
        elif opt in ("-n", "--thumbdv"):
            SERIAL_BAUD=460800

    if useSerial == True:
        try:
            print('Opening serial port')
            port = serial.Serial(serialport, baudrate=SERIAL_BAUD, timeout=1.0, bytesize=serial.EIGHTBITS, parity=seria
l.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False, dsrdtr=False)
        except:
            print('Error opening serial port', serialport)
            exit(2)

        port.flushInput()
        port.flushOutput()

        print('-'*48)
        print('Serial port parameters\n')
        print(padstring('Port name:',16)+'\t',serialport)
        print(padstring('Baudrate:',16)+'\t',port.baudrate)
        print(padstring('Byte size:',16)+'\t',port.bytesize)
        print(padstring('Parity:',16)+'\t',port.parity)
        print(padstring('Stop bits:',16)+'\t',port.stopbits)
        print(padstring('xon/xoff:',16)+'\t',port.xonxoff)
        print(padstring('RTS/CTS:',16)+'\t',port.rtscts)
        print(padstring('DST/DTR:',16)+'\t',port.dsrdtr)

        time.sleep(0.02)
        rcv = port.read(10)
        sys.stdout.buffer.write(rcv)
    else:
        _sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        _sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        port = _sock

        print('-'*48)
        print('Network parameters\n')
        print(padstring('IP address:',16)+'\t',ip_address)
        print(padstring('UDP port:',16)+'\t',UDP_PORT)

    print('-'*48)
    if verbose == True:
        print('\nVerbose testing mode.....')

    ambeValidate(port, reset, bytearray.fromhex("39"), 'Reset DV3000')
    ambeValidate(port, getProdId, bytearray.fromhex("30414d4245333030305200"), 'Get Product ID')

    ambeValidate(port, getVersion, getVersion_expected, 'Get Version')

    ambeValidate(port, setDstar, bytearray.fromhex("0a00"), 'Set DSTAR Mode')
    ambeValidate(port, reset, bytearray.fromhex("39"), 'Reset DV3000')
    ambeValidate(port, setDMR, bytearray.fromhex("0a00"), 'Set DMR Mode')

    is_encdec = True # next series of tests are encodes/decodes. be patient.
    if verbose != True:
        print('\nbegin encode/decode testing using 1000 packets... this will take a while...')

    for _ in range(0,1000):
        DMRAmbe = encodeAMBE + silence
        _header, _payload = ambeValidate(port, DMRAmbe, '', 'Decode AMBE')
        if _payload != None:
            if _header+_payload == bytearray.fromhex("6100010039"):
                print("Error, the DV3000 has unexpectly reset")
                stopOnError()
            elif len(_payload) != 322: # 320 of PCM plus one field ID and one bit length byte
                print('Error, did not get the right number of PCM bytes back from an encode',len(_payload))
                stopOnError()
            elif (_payload[0:1] != b'\x00') or (_payload[1:2] != b'\xa0'):
                print('Error, PCM should be channel 0 and have 320 bits')
                stopOnError()
            elif _header[3:4] != b'\x02': # type is AUDIO
                print('Error, PCM type is invalid 0x'+bytearray(_header[3:4]).hex())
                stopOnError()
            DMRPCM = encodePCM + _payload
            expect = bytearray.fromhex("48954be6500310b00777")
            _header, _payload = ambeValidate(port, DMRPCM, '', 'Encode PCM')
            if _payload != None:
                if _header+_payload == bytearray.fromhex("6100010039"):
                    print("Error, the DV3000 has unexpectedly reset")
                    stopOnError()
                elif len(_payload) != 11: # 9 of AMBE plus one bit length byte
                    print('Error, did not get the right number of AMBE bytes back from an encode',len(_payload))
                    stopOnError()
                elif _header[3:4] != b'\x01': # type is AMBE
                    print('Error, AMBE type is invalid 0x'+bytearray(_header[3:4]).hex())
                    stopOnError()
                elif _payload[0:1] != b'\x01': #channel ID must be 1
                    print('AMBE channel ID is not correct')
                    stopOnError()
                elif _payload[1:2] != b'\x48': # 72 bits in length
                    print('AMBE bit length is not correct 0x'+bytearray(_payload[1:2]).hex())
                    stopOnError()
            else:
                print('Error, encode PCM to AMBE returned no results')
                stopOnError()
        else:
            print('Error, decode AMBE to PCM returned no results')
            stopOnError()
    print('Error count = {0}'.format(errorCount))
    if errorCount == 0:
        print('No errors. Well done!')
    else:
        print('Errors found. Check baud rate and USB port voltage (some devices throw errors when the voltage is low)')

if __name__ == "__main__":
    main(sys.argv[1:])
