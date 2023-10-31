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


	def __init__(self,name,params,config):
		self.name = name
		self.max_setting = str(config["Max Setting"])
		self.emergency_setting = float(params["Emergency Setpoint"])
		self.node = str(config["node"])
		self.current_sp = None
		self.dev_lim = float(config["Dev Lim"])

	def is_emergency(self,wait_time,pv_read_time,sp_set_time,current_sp,current_pv):
		if (pv_read_time-sp_set_time > wait_time):
			if current_pv != current_sp:
				print("Error in: {} Current PV: {} Current SP: {} Current Dev Lim: {}".format(self.name,current_pv,current_sp,self.dev_lim))
				return [True,self.name,current_sp,current_pv]
			else:
				return [False,self.name,current_sp,current_pv]
		else:
			return [False,self.name,current_sp,current_pv]

	def get_pv(self,ser):
		""" Read the actual flow """ #If 5 errors then returns whatever it received from valve
		error = 0
		while error < 5:
			read_str = 'CP'+'\r\n' #constructing read string
			val = self.comm(ser,read_str)

			try:
				return int(val.rstrip()[2:])
			except:
				print("Error! {}".format(val))
				return None

	def set_sp(self,ser,setpoint_in):
		if setpoint_in not in [1,2,3,4,5,6,7,8]:
			print("Unknown setpoint received! {}".format(setpoint_in))
			return False
		else:
			write_str = "GO"+str(setpoint_in)+'\r\n'
			response = self.comm(ser,write_str)
			self.current_sp = setpoint_in
			return True


	def get_sp(self,ser):
		# read_setpoint = ':06' + self.node + '0401210121\r\n' # Read setpoint
		# response = self.comm(ser,read_setpoint)
		# response = int(response[11:], 16) #Grabs last 4 hex numbers and converts to decimal
		# response = (float(response) / 32000.0) * float(self.max_setting) #response / 32000 gives percentage, then multiply by max setting
		# return response
		return self.current_sp


	def comm(self, ser, command):
		""" Send commands to device and recieve reply """
		ser.write(command.encode())
		time.sleep(0.5)

		return_string = ser.readline()
		return_string = return_string.decode()
		return return_string
		
	def get_max_setting(self):
		return self.max_setting