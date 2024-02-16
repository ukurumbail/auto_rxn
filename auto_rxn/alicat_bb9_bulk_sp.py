import serial
import alicat
import time


# This class is for an Alicat communications device where you get one setpoint and distribute to all the reactors.
class Device():
	def __init__(self,params,config,mock=False,rxn_dir=None):
		self.config = config
		self.params = params
		self.wait_time = self.config["Wait Time (sec)"]

		self.subdevices = {}

		if mock:
			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Mock_Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name],config["port"])
		else:

			#initializing each controller with its specific max flow, name, etc.
			for subdev_name in config["Subdevices"].keys():
				self.subdevices[subdev_name] = Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name],config["port"])
				time.sleep(1)	

	def get_pv(self,subdev_name):
		return self.subdevices[subdev_name].get_pv()

	def get_sp(self,subdev_name):
		return self.subdevices[subdev_name].get_sp()

	def set_sp(self,subdev_name,sp_value):
		if subdev_name == "Bulk SP":
			for subdev_name in subdevices.keys():
				return self.subdevices[subdev_name].set_sp(sp_value)

	def is_emergency(self,subdev_name,pv_read_time,sp_set_time,current_sp,current_pv):
		return self.subdevices[subdev_name].is_emergency(self.wait_time,pv_read_time,sp_set_time,current_sp,current_pv)

	def get_subdevice_names(self):
		return self.subdevices.keys()

	def get_emergency_sp(self,subdev_name):
		return self.subdevices[subdev_name].emergency_setting
	def get_max_setting(self,subdev_name):
		return self.subdevices[subdev_name].get_max_setting()

class Mock_Subdevice():
	def __init__(self,name,params,config,port):
		self.name = name
		self.units = params["Units"]
		self.max_setting = config["Max Setting"]
		self.emergency_setting = params["Emergency Setpoint"]
		self.node = config["node"]
		self.current_sp = None
		self.dev_lim = config["Dev Lim"]

	def is_emergency(self,wait_time,pv_read_time,sp_set_time,current_sp,current_pv):
		return [False,self.name,current_sp,current_pv]
	def get_pv(self):
		return self.current_sp
	def set_sp(self,sp_value):
		self.current_sp = sp_value
		return True

	def get_sp(self):
		return self.current_sp
	def get_max_setting(self):
		return self.max_setting

class Subdevice():

###
### This code was primarily adapted from code written by Ethan Young at UW-Madison. Nearly all the credit goes to them.
###
	def __init__(self,name,params,config,port):
		self.name = name
		self.units = params["Units"]
		self.max_setting = str(config["Max Setting"])
		self.emergency_setting = float(params["Emergency Setpoint"])
		self.current_sp = None
		self.dev_lim = float(config["Dev Lim"])
		self.dev = alicat.FlowController(port=port,address=config["node"])

	def is_emergency(self,wait_time,pv_read_time,sp_set_time,current_sp,current_pv):
		if (pv_read_time-sp_set_time > wait_time):
			if current_pv > (current_sp+self.dev_lim) or current_pv<(current_sp-self.dev_lim):
				print("Error in: {} Current PV: {} Current SP: {} Current Dev Lim: {}".format(self.name,current_pv,current_sp,self.dev_lim))
				return [True,self.name,current_sp,current_pv]
			else:
				return [False,self.name,current_sp,current_pv]
		else:
			return [False,self.name,current_sp,current_pv]

	def get_pv(self):
		""" Read the actual flow """ #If 10 errors then returns -99
		return self.dev.get()['mass_flow']


	def set_sp(self,setpoint_in):
		try:
			self.dev.set_flow_rate(float(setpoint_in))
		except:
			return False
		time.sleep(1)
		self.current_sp = setpoint_in
		if self.dev.get()['setpoint'] == setpoint_in:
			return True

		else:
			return False


	def get_sp(self):
		# read_setpoint = ':06' + self.node + '0401210121\r\n' # Read setpoint
		# response = self.comm(ser,read_setpoint)
		# response = int(response[11:], 16) #Grabs last 4 hex numbers and converts to decimal
		# response = (float(response) / 32000.0) * float(self.max_setting) #response / 32000 gives percentage, then multiply by max setting
		# return response
		return self.current_sp
		
	def get_max_setting(self):
		return self.max_setting