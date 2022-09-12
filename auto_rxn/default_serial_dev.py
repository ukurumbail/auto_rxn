import serial
import time

class Device():
	def __init__(self,params,config,mock=False):
		self.config = config
		self.params = params
		self.wait_time = self.config["Wait Time (sec)"]

		self.subdevices = {}

		if mock:
			self.ser = None
			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Mock_Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name])
		else:
			#generating the serial connection that each controller will use
			self.ser = serial.Serial(baudrate=config["baudrate"], timeout=config["timeout"])
			self.ser.port = config["port"]
			self.ser.close()
			self.ser.open()

			#initializing each controller with its specific max flow, name, etc.
			for subdev_name in config["Subdevices"].keys():
				self.subdevices[subdev_name] = Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name])
				self.subdevices[subdev_name].set_control_mode(self.ser) #Sets control mode to accept RS-232 setpoints
				time.sleep(1)	

	def get_pv(self,subdev_name):
		return self.subdevices[subdev_name].get_pv(self.ser)

	def get_sp(self,subdev_name):
		return self.subdevices[subdev_name].get_sp(self.ser)

	def set_sp(self,subdev_name,sp_value):
		return self.subdevices[subdev_name].set_sp(self.ser,sp_value)

	def is_emergency(self,subdev_name,pv_read_time,sp_set_time,current_sp,current_pv):
		return self.subdevices[subdev_name].is_emergency(self.wait_time,pv_read_time,sp_set_time,current_sp,current_pv)

	def get_subdevice_names(self):
		return self.subdevices.keys()

	def get_emergency_sp(self,subdev_name):
		return self.subdevices[subdev_name].emergency_setting
	def get_max_setting(self,subdev_name):
		return self.subdevices[subdev_name].get_max_setting()

class Mock_Subdevice():
	def __init__(self,name,params,config):
		self.name = name
		self.units = params["Units"]
		self.max_setting = config["Max Setting"]
		self.emergency_setting = params["Emergency Setpoint"]
		self.node = config["node"]
		self.current_sp = None
		self.dev_lim = config["Dev Lim"]

	def is_emergency(self,wait_time,pv_read_time,sp_set_time,current_sp,current_pv):
		return [False,self.name,current_sp,current_pv]
	def get_pv(self,ser):
		return self.current_sp
	def set_sp(self,ser,sp_value):
		self.current_sp = sp_value
		return True

	def get_sp(self,ser):
		return self.current_sp
	def get_max_setting(self):
		return self.max_setting

class Subdevice():

###
### This code was primarily adapted from code written by Ethan Young at UW-Madison. Nearly all the credit goes to them.
###
	def __init__(self,name,params,config):
		self.name = name
		self.units = params["Units"]
		self.max_setting = str(config["Max Setting"])
		self.emergency_setting = float(params["Emergency Setpoint"])
		self.node = '{:02x}'.format(int(config["node"]))
		self.current_sp = None
		self.dev_lim = float(config["Dev Lim"])

	def is_emergency(self,wait_time,pv_read_time,sp_set_time,current_sp,current_pv):
		if (pv_read_time-sp_set_time > wait_time):
			if current_pv > (current_sp+self.dev_lim) or current_pv<(current_sp-self.dev_lim):
				print("Error in: {} Current PV: {} Current SP: {} Current Dev Lim: {}".format(self.name,current_pv,current_sp,self.dev_lim))
				return [True,self.name,current_sp,current_pv]
			else:
				return [False,self.name,current_sp,current_pv]
		else:
			return [False,self.name,current_sp,current_pv]

	def get_pv(self,ser):
		""" Read the actual flow """ #If 10 errors then returns -99
		error = 0
		while error < 10:
			read_pressure = ':06' + self.node + '0401210120\r\n' # Read pressure
			val = self.comm(ser,read_pressure)

			try:
				val = val[11:] #Gets last 4 hex digits
				num = int(val, 16) #Converts to decimal
				pressure = (float(num)/ 32000) * float(self.max_setting) #Determines actual flow
				break

			except ValueError:
				pressure = -99
				error = error + 1
		return pressure


	def set_sp(self,ser,setpoint_in):
		if setpoint_in > 0:
			setpoint = (float(setpoint_in) / float(self.max_setting)) * 32000
			setpoint = hex(int(setpoint))
			setpoint = setpoint.upper()
			setpoint = setpoint[2:].rstrip('L')

			if len(setpoint) == 3:
				setpoint = '0' + setpoint

		else:
			setpoint = '0000'
		
		set_setpoint = ':06' + self.node + '010121' + setpoint + '\r\n' # Set setpoint
		response = self.comm(ser,set_setpoint)
		response_check = response[5:].strip()
		
		if response_check == '000005':
			response = True
			self.current_sp = setpoint_in
		else:
			response = False
			print("Failed to set SP for {}".format(self.name))
		
		return response


	def get_sp(self,ser):
		# read_setpoint = ':06' + self.node + '0401210121\r\n' # Read setpoint
		# response = self.comm(ser,read_setpoint)
		# response = int(response[11:], 16) #Grabs last 4 hex numbers and converts to decimal
		# response = (float(response) / 32000.0) * float(self.max_setting) #response / 32000 gives percentage, then multiply by max setting
		# return response
		return self.current_sp


	def comm(self, ser, command):
		""" Send commands to device and recieve reply """
		ser.write(command.encode('ascii'))
		time.sleep(0.1)

		return_string = ser.read(ser.inWaiting())
		return_string = return_string.decode()
		return return_string

	def set_control_mode(self,ser):
		""" Set the control mode to accept rs232 setpoint """
		set_control = ':05' + self.node + '01010412\r\n' #Sets control mode to value 18 (rs232)
		response = self.comm(ser,set_control)
		return str(response)
		
	def get_max_setting(self):
		return self.max_setting