import json
import time
import requests
import random

class Device():
	def __init__(self,params,config,mock=False):
		self.mock = mock
		self.config = config
		self.params = params
		self.subdevices = {}

		if "Delay Time" in params.keys():
			self.delay_exists=True 
			self.last_injection_time = 0
		else:
			self.delay_exists=False

		if self.mock:
			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Mock_Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name])
			self.prev_run_id = self.get_last_run_id()
		else:

			self.ip = config["IP Address"]
			self.default_method = config["Default Method"]
			self.load_method_status_code = self.load_method(self.default_method)
			if self.load_method_status_code == 500:
				raise ValueError("Default method could not be loaded. {}".format(self.default_method))
			else:
				print("Loaded method: {}".format(self.default_method))
			self.prev_run_id = self.get_last_run_id()
			if self.prev_run_id == -999:
				raise ValueError("Run ID value = -999. Failed run id request")

			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name])


	def get_last_run_id(self):
		if self.mock:
			return 'MOCK RUN {}'.format(random.randint(0,10000000))
		time.sleep(2)
		get_request = requests.get('http://' + self.ip + '/v1/lastRun').json()
		try:
			return get_request['dataLocation'].split('/')[-1]
		except:
			return -999

	def ready(self):
		if self.mock:
			if self.delay_exists:
				if time.time() > ((self.get_sp("Delay Time")*60) + self.last_injection_time):
					return True
				else:
					print("Injection delayed. Time until next injection:", round(((self.last_injection_time + self.get_sp("Delay Time")*60 - time.time()) - (self.last_injection_time + self.get_sp("Delay Time")*60 - time.time())%60)/60) , "minutes", round((self.last_injection_time + self.get_sp("Delay Time")*60 - time.time())%60), "seconds")
					return False
			else:
				return True
		else:
			if 'public:ready' in self.get_state():
				if self.delay_exists:
					if time.time() > (self.get_sp("Delay Time")*60 + self.last_injection_time):
						return True
					else:
						print("Injection delayed. Time until next injection:", round(((self.last_injection_time + self.get_sp("Delay Time")*60 - time.time()) - (self.last_injection_time + self.get_sp("Delay Time")*60 - time.time())%60)/60) , "minutes", round((self.last_injection_time + self.get_sp("Delay Time")*60 - time.time())%60), "seconds")
						return False
				else:
					return True 
			else:
				return False

	def get_state(self):
		get_request = requests.get('http://' + self.ip + '/v1/scm/sessions/system-manager/publicConfiguration').json()
		return get_request

	def load_method(self,method_name):
		get_request = requests.get('http://' + self.ip + '/v1/scm/sessions/system-manager!cmd.loadMethod?methodLocation=/methods/userMethods/'+method_name)
		if get_request.status_code == 200:
			return True
		else:
			return False

	def inject(self):
		if self.mock:
			self.subdevices["Number of Samples"].num_injections += 1
			self.last_injection_time = time.time()
			return True
		else:
			get_request = requests.get('http://' + self.ip + '/v1/scm/sessions/system-manager!cmd.run')
			if get_request.status_code == 200:
				self.subdevices["Number of Samples"].num_injections += 1 
				self.last_injection_time = time.time()
				return True		
			else: #Status code of 500 returned if injection unsuccessful
				return False


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

	def all_samples_collected(self):
		if self.subdevices["Number of Samples"].num_injections == self.subdevices["Number of Samples"].current_sp:
			return True
		else:
			return False


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

	def delay_time(self):
		if self.is_injection_counter == self.num_injections:
			time.sleep(delay_time)
		return True


class Subdevice():
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