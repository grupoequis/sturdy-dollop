#!/usr/bin/env python
# -*- coding: utf-8 -*-

import signal
import select
import argparse
import sys
import ipaddress
from socket import *
from struct import pack
from struct import unpack
from IPy import IP
from twisted.internet.defer import maybeDeferred, succeed
import os
import re

__all__ = ['NetasciiSenderProxy', 'NetasciiReceiverProxy',
           'to_netascii', 'from_netascii']

CR = b'\x0d'
LF = b'\x0a'
CRLF = CR + LF
NUL = b'\x00'
CRNUL = CR + NUL
if isinstance(os.linesep, bytes):
    NL = os.linesep
else:
    NL = os.linesep.encode("ascii")


re_from_netascii = re.compile(b'(\x0d\x0a|\x0d\x00)')

def _convert_from_netascii(match_obj):
    if match_obj.group(0) == CRLF:
        return NL
    elif match_obj.group(0) == CRNUL:
        return CR

def from_netascii(data):
    return re_from_netascii.sub(_convert_from_netascii, data)

_re_to_netascii = b'(NL|\x0d)'
re_to_netascii = re.compile(_re_to_netascii.replace(b"NL", NL))

def _convert_to_netascii(match_obj):
    if match_obj.group(0) == NL:
        return CRLF
    elif match_obj.group(0) == CR:
        return CRNUL

def to_netascii(data):
    return re_to_netascii.sub(_convert_to_netascii, data)

error_message = {
    0: "Not defined, see error message (if any).",
    1: "File not found.",
    2: "Access violation.",
    3: "Disk full or allocation exceeded.",
    4: "Illegal TFTP operation.",
    5: "Unknown transfer ID.",
    6: "File already exists.",
    7: "No such user."
}

sock = socket(AF_INET, SOCK_DGRAM,0)
server_address = ('localhost', 69)
port = 69
sent_address = ('localhost',69)
mode = "octet"
verbose = False
trace = False
host = 'none'
serverset = False
def sendACK(ack_data, server):
	ack = bytearray(ack_data)
	#print('received DATA <block=',ack,',',ack,'bytes>')
	ack[0] = 0	
	ack[1] = 4
	sock.sendto(ack, server)
	

def console():
	global verbose, host, mode, serverset, server_address
	try:
		while True:
			print("tftp> ",end='')
			cmd = input()
			cmds = cmd.split(" ")
			if(cmds[0] == "put"):
				if len(cmds) < 2:
					print("usage: put filename")
					continue
				if verbose:
					print('putting', cmds[1],'to',host,':', cmds[1],'[',mode,']')
				put(cmds[1])
			elif(cmds[0] == 'get'):
				if len(cmds) < 2:
					print("usage: get filename")
					continue
				if verbose:
					print('getting from',host,':',cmds[1],'to',cmds[1],'[',mode,']')
				get(cmds[1])
			elif(cmds[0] == 'verbose'):
				verbose = not verbose
				if verbose:
					print('Verbose mode on')
				else:
					print('Verbose mode off')
			elif(cmds[0] == 'trace'):
				verbose = True
				print('Packet tracing on')
			elif(cmds[0] == 'mode'):
				if len(cmds) < 2:
					print("Using %s mode to transfer files" % mode)
					continue
				moode = cmds[1]
				if moode == 'ascii':
					mode = 'netascii'
				elif moode == 'binary' or moode == 'octet':
					mode = 'octet'
				else:
					mode = 'netascii'
				print('Using',mode,'mode to transfer files')

			elif(cmds[0] == 'connect'):
				if len(cmds) < 2:
					print("Usage connect host-name" % mode)
					continue
				
				try:
					IP(cmds[1])	
				except Exception as ex:
				    print('the address is not ipv4 address')
				    print(ex)
				    continue
				print('Host:',cmds[1])
				host = cmds[1]
				server_address = (cmds[1],69)
				serverset = True
			elif(cmds[0] == 'q'):
				exit()
	except EOFError as error:
		exit()



def get(filename):
	if(not serverset):
		print("server not set")
		return
	request = bytearray()
	request.append(0)	
	request.append(1)	  
	request += bytearray(filename.encode('utf-8'))
	request.append(0)
	request += bytearray(bytes(mode, 'utf-8'))
	request.append(0)
	sock.sendto(request, server_address)
	if verbose:
			print('sent RRQ <file=',filename,', mode=',mode,'>')
	file = open(filename, "wb")
	started = False
	oldack = 0
	while True:
		# Wait for the data from the server
		
		for i in range(4):
			try:
				sock.settimeout(1)
				data, server = sock.recvfrom(600)
			except Exception as ex:
				print(ex)
				if started:
					sendACK(data[0:4], server)
				else:
					sock.sendto(request, server_address)
				continue
			break
		else:
			print("connection lost")
			return


		if error(data):
			error_code = int.from_bytes(data[2:4], byteorder='big')
			print(error_message[error_code])
			if(error_code == 1):
				os.remove(filename)

			break
		started = True
		ackn = int.from_bytes(data[2:4],"big")
		if(oldack > ackn):
			continue
		oldack=ackn
		sendACK(data[0:4], server)
		if(mode=='netascii'):
			file.write(from_netascii(data[4:]))
		else:
			file.write(data[4:])

		# Last block
		if len(data) < 516:		    	
			print('Received')			
			break
		

def put(filename):
	if(not serverset):
		print("server not set")
		return


	try:
		f=open(filename, "rb")
	except FileNotFoundError as ex:
		print("file not found")
		return
	n=0
	request = bytearray()
	request.append(0)
	request.append(2)
	request += bytearray(filename.encode('utf-8'))
	request.append(0)
	request += bytearray(mode.encode('utf-8'))
	request.append(0)
	res = ''
	tries = 0
	while(res != 'ack' and tries < 4):
		sock.sendto(request,server_address)
		if verbose:
			print('sent WRQ <file=',filename,', mode=',mode,'>')
		res = waitack(n)
		if(res == 'error'):
			return
		tries+=1
	if(tries >= 4):
		print('connection lost')
		return

	if verbose:
			print('received ACK <block=',n,'>')
	filebytes = bytearray(f.read())
	lenght = len(filebytes)
	if (mode == 'netascii'):
		filebytes = to_netascii(filebytes)
	i = 0
	n+=1
	tries = 0

	while i < lenght:
		try:
			nb = n.to_bytes(2, byteorder='big')
		except OverflowError as error:
			n = 0
			nb = n.to_bytes(2, byteorder='big')
		n+=1
		print(n)
		request = bytes.fromhex("0003")
		request += nb
		
		res = 'no'
		tries = 0
		while(res!= 'ack' and tries < 4):
			
			sock.sendto(request + filebytes[i:i+512],sent_address)
			print('enviando algo')
			if verbose:
				print('sent DATA <block=',str(n),',',lenght,'bytes> to' + str(sent_address))
			res = waitack(n)
			
		else:
			if(tries >= 4):
				print('connection time out')
				return


		i +=512
		n +=1
	print('Sent')
def waitack(ackn):
	global sent_address
	while True:
		sock.settimeout(1)
		try:
			data, address = sock.recvfrom(600)
		except:
			return 'timeout'
		sent_address = address
		ack = 4
		if error(data):
			error_code = int.from_bytes(data[2:4], byteorder='big')
			print(error_message[error_code])
			return 'error'
		results = unpack('>'+'h'*(len(data)//2),data)
		if ack == results[0] and ackn == results[1]:
			ackn += 1
			return "ack"

		return 'none'



def error(data):
	opcode = data[:2]
	return int.from_bytes(opcode, byteorder='big') == 5

def signal_handler(sig, frame):
        sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def main():
	global host
	global sent_address
	global server_address
	global serverset

	if(len(sys.argv) > 1):
		try:
		    IP(sys.argv[1])
		    server_address = (sys.argv[1],69)
		    sent_address = server_address
		    print('Host:',sys.argv[1])
		    host = sys.argv[1]
		    serverset = True
		except Exception as ex:
		    print('the address is not ipv4 address')
		    
				
	console()

if __name__ == '__main__':
    main()


