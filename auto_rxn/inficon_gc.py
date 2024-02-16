import json
import time
import requests
import random

class Device():
	def __init__(self,params,config,mock=False,rxn_dir=None):
		self.mock = mock
		self.config = config
		self.params = params
		self.subdevices = {}

		if "Delay Time" in params.keys():
			self.delay_exists=True 
			self.last_injection_time = 0
		else:
			self.delay_exists=False

		if "Injection Offset" in params.keys():
			self.offset_exists=True
			self.last_sp_change_time = 0
		else:
			self.offset_exists=False

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
		time.sleep(0.05)
		try:
			get_request = requests.get('http://' + self.ip + '/v1/lastRun')
			get_request_json = get_request.json()
			return get_request_json['dataLocation'].split('/')[-1]
		except json.decoder.JSONDecodeError:
			print("Unable to decode GC get request: {}".format(get_request.content))
			print("Going to try again")
			try_counter = 0
			while try_counter < 10:
				time.sleep(2)
				try:
					get_request = requests.get('http://' + self.ip + '/v1/lastRun')
					get_request_json = get_request.json()
					return get_request_json['dataLocation'].split('/')[-1]
				except:
					try_counter += 1
					print("Failed to read json again. Trying {} more times".format(10-try_counter))
			return -999
		except:
			print("Unknown error trying to read json!!!")
			import sys
			print(sys.exc_info()[0])
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
			if 'public:ready' in self.get_state(): #Physical GC instrument is ready. Next check our timers.
				return_value=True
				if self.delay_exists: #This delays injections to prevent injecting more frequently than every x minutes.
					if time.time() > (self.get_sp("Delay Time")*60 + self.last_injection_time):
						pass #no change to return value needed
					else:
						print("Injection delayed due to delay time. Time until next injection:", round(((self.last_injection_time + self.get_sp("Delay Time")*60 - time.time()) - (self.last_injection_time + self.get_sp("Delay Time")*60 - time.time())%60)/60) , "minutes", round((self.last_injection_time + self.get_sp("Delay Time")*60 - time.time())%60), "seconds")
						return_value=False
				else:
					pass #ignore delay time. Move on to inject offset
				if self.offset_exists: #This delays the first injection of a new recipe step for x minutes.
					if time.time() > (self.get_sp("Injection Offset")*60+self.last_sp_change_time):
						pass #ready to inject based on offset.
					else:
						print("Injection delayed due to injection offset. Time until next injection: {:.4} seconds".format(self.get_sp("Injection Offset")*60-(time.time()-self.last_sp_change_time)))
						return_value=False
				return return_value
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
		if subdev_name == "Injection Offset":
			self.last_sp_change_time=time.time()
			print(f'New injection offset time: {self.last_sp_change_time}')
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
			print(f'Collections. Injections: {self.subdevices["Number of Samples"].num_injections} Reqd: {self.subdevices["Number of Samples"].current_sp}')
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