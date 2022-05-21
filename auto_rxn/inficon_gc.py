class Device():
	def __init__(self,params,config,mock=False):
		self.config = config
		self.params = params
		self.subdevices = {}

		if config["IP Address"] == "DUMMY" or mock:
			mock = True
		else:
			mock = False

		if mock:
			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Mock_Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name])
		else:
			raise NotImplementedError()

	def get_pv(self,subdev_name):
		return self.subdevices[subdev_name].get_pv()

	def get_sp(self,subdev_name):
		return self.subdevices[subdev_name].get_sp()

	def set_sp(self,subdev_name,sp_value):
		return self.subdevices[subdev_name].set_sp(sp_value)

	def is_emergency(self,subdev_name,pv_read_time,sp_set_time,current_sp,current_pv):
		return self.subdevices[subdev_name].is_emergency()

	def get_subdevice_names(self):
		return self.subdevices.keys()

	def get_emergency_sp(self,subdev_name):
		return self.subdevices[subdev_name].emergency_setting

	def inject(self):
		self.subdevices["Number of Samples"].num_injections += 1 
		return True

	def ready(self):
		return True

	def all_samples_collected(self):
		if self.subdevices["Number of Samples"].num_injections == self.subdevices["Number of Samples"].current_sp:
			return True
		else:
			return False

	def get_run_id(self):
		return "MOCK"

	def get_inject_time(self):
		return 0

class Mock_Subdevice():
	def __init__(self,name,params,config):
		self.name = name
		self.emergency_setting = params["Emergency Setpoint"]
		self.current_sp = None

		if name == "Number of Samples":
			self.is_injection_counter = True
			self.num_injections = None
		else:
			self.is_injection_counter = False

	def is_emergency(self):
		return [False,self.name,self.current_sp,self.get_pv()]

	def get_pv(self):
		if self.is_injection_counter:
			return self.num_injections
		else:
			return self.current_sp

	def set_sp(self,sp_value):
		self.current_sp = sp_value
		if self.is_injection_counter:
			self.num_injections = 0
		return True

	def get_sp(self):
		return self.current_sp