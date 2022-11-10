import minimalmodbus
import time
class Device():
	#If you need to activate port: Go to iTools OPC Server --> Edit --> iTools Control Panel and uncheck whatever port
	def __init__(self,params,config,mock=False):
		self.config = config
		self.params = params
		# self.flow_dev_lim = 2
		# self.emergency_flows = {}
		self.subdevices = {}

		if mock:
			self.dev = None
			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Mock_Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name])
		else:
			self.dev = minimalmodbus.Instrument(self.config["port"],self.config["address"])
			self.dev.serial.baudrate = self.config["baudrate"]
			self.dev.serial.timeout = self.config["timeout"]
			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name])


		if "Furnace Temp" in params.keys():
			self.furnace_temp_exists=True
			self.current_max_temp_setpt = self.get_sp("Furnace_Temp")
		else:
			self.furnace_temp_exists=False
			raise NotImplementedError("Error! Trying to run furnace without Furnace Temp. Have not implemented this.")
		if "Ramp Rate" in params.keys():
			self.ramp_rate_exists=True
			self.last_sp_time = None
		else:
			self.ramp_rate_exists=False

	def get_pv(self,subdev_name):
		return self.subdevices[subdev_name].get_pv(self.dev)

	def get_sp(self,subdev_name):
		return self.subdevices[subdev_name].get_sp(self.dev)

	def set_sp(self,subdev_name,sp_value):
		if self.ramp_rate_exists and subdev_name is "Furnace Temp":
			self.prev_max_setpt = self.current_max_temp_setpt
			self.current_max_temp_setpt = sp_value
			return True
		return self.subdevices[subdev_name].set_sp(self.dev,sp_value)

	def is_emergency(self,subdev_name,pv_read_time,sp_set_time,current_sp,current_pv):
		return self.subdevices[subdev_name].is_emergency(pv_read_time,sp_set_time,current_sp,current_pv)

	def get_subdevice_names(self):
		return self.subdevices.keys()

	def get_emergency_sp(self,subdev_name):
		return self.subdevices[subdev_name].emergency_setting

	def get_max_setting(self,subdev_name):
		return self.subdevices[subdev_name].get_max_setting()

	def update_sp(self,subdev_name):
		if subdev_name is "Furnace Temp":
			if self.ramp_rate_exists:
				if self.last_sp_time is None:
					self.last_sp_time = time.time()
				new_sp = self.subdevices["Furnace Temp"].current_sp + (self.get_sp("Ramp Rate") * (time.time() - self.last_sp_time)/60)	
				if self.current_max_temp_setpt > self.prev_max_setpt:
					new_sp = min(new_sp,self.current_max_temp_setpt) #want minimum of the two if increasing temp

				elif self.current_max_temp_setpt < self.prev_max_setpt:
					new_sp = max(new_sp,self.current_max_temp_setpt)

				else: #no change in temp setpt
					return True
				if new_sp != self.subdevices["Furnace Temp"].current_sp:
					self.set_sp("Furnace Temp",new_sp)
				else:
					return True
			else:
				return True #No need to update setpoint if there's no ramp rate


			return True
		else:
			print("Trying to update setpoint for {} which is not listed as dynamic!!".format(subdev_name))
			return False


class Mock_Subdevice():
	def __init__(self,name,params,config):
		self.name = name
		self.units = params["Units"]
		self.emergency_setting = params["Emergency Setpoint"]
		self.current_sp = None
		self.max_setting = config["Max Setting"]

	def is_emergency(self,pv_read_time,sp_set_time,current_sp,current_pv):
		return [False,self.name,current_sp,current_pv]
	def get_pv(self,dev):
		return self.current_sp
	def set_sp(self,dev,sp_value):
		self.current_sp = sp_value
		return True

	def get_sp(self,dev):
		return self.current_sp

	def get_max_setting(self):
		return self.max_setting

class Subdevice():
	def __init__(self,name,params,config):
		self.name = name
		self.units = params["Units"]
		self.emergency_setting = params["Emergency Setpoint"]
		self.prev_sp = None
		self.current_sp = None
		self.max_setting = config["Max Setting"]
		self.sp_write_address = config["SP Write Address"]
		self.sp_read_address = config["SP Read Address"]
		self.pv_read_address = config["PV Read Address"]
		self.wait_time = config["Change Wait Time"]
		self.dev_lim = config["Dev Lim"]
		self.dev_type = config["Dev Type"]
	def is_emergency(self,pv_read_time,sp_set_time,current_sp,current_pv):
		if (pv_read_time-sp_set_time) > self.wait_time:
			if self.dev_type == "Change from previous": #Use dev_lim as a minimum change required from previous sp
				if abs(abs(self.prev_sp)-abs(current_pv)) < abs(self.dev_lim) and abs(abs(self.prev_sp)-abs(current_sp)) > abs(self.dev_lim):
					print("{} failed to change from previous SP in enough time!".format(self.name))
					return [True,self.name,current_sp,current_pv] 
				else:
					return [False,self.name,current_sp,current_pv]
			elif self.dev_type == "Within setpt tolerance": #Use dev_lim as a tolerance bar around the expected pv value
				if abs(abs(current_sp)-abs(current_pv)) > abs(self.dev_lim):
					return [True,self.name,current_sp,current_pv] 
				else:
					return [False,self.name,current_sp,current_pv] 
			else:
				print("Not implemented!")
				return [False,self.name,current_sp,current_pv] 
		else:
			return [False,self.name,current_sp,current_pv]


	def get_pv(self,dev):
		return dev.read_float(self.pv_read_address)
	def set_sp(self,dev,sp_value):
		if self.current_sp == None:
			self.current_sp = self.get_sp(dev)
		sp_value = float(sp_value)

		if sp_value	< self.max_setting:
			if self.name is "Furnace Temp":
				dev.write_float(self.sp_write_address,sp_value)
				time.sleep(.5)
				dev_sp = self.get_sp(dev)
				if dev_sp != sp_value:
					print("SP did not take! Device SP: {} Requested SP: {}".format(dev_sp,sp_value))
					return False
				else:
					self.prev_sp = self.current_sp
					self.last_sp_time = time.time()
					self.current_sp = sp_value
					return True
			elif self.name is "Ramp Rate" : 
				self.current_sp = sp_value
				return True
			else:
				print("Trying to set setpt for {} which is not implemented yet.".format(self.name))
				return False 
		else:
			print("Requested SP: {} is larger than max setpoint allowed: {}".format(sp_value,self.max_setting))
			return False


	def get_sp(self,dev):
		if self.name is "Furnace Temp":
			return dev.read_float(self.sp_read_address)
		elif self.name is "Ramp Rate" : 
			return self.current_sp
		else:
			print("Trying to get SP for {} which is not implemented yet!".format(self.name))

	def get_max_setting(self):
		return self.max_setting