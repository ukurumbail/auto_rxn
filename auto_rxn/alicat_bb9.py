import serial
import alicat
import time
import os
import csv
import tabulate 
import copy
class Device():
	def __init__(self,params,config,mock=False,rxn_dir=None):
		self.config = config
		self.params = params
		self.wait_time = self.config["Wait Time (sec)"]

		self.subdevices = {}

		self.rxn_dirname = rxn_dir
		self.logfile_location = os.path.join(self.rxn_dirname, "{}.csv".format("6flow_flow_pv_log"))
		self.logtimer = time.time()
		self.log_time_interval = 10 #seconds
		self.cached_pv = None
		self.reactors = ["1","2","3","4","5","6"]
		self.headers = copy.copy(self.reactors)
		self.headers.insert(0,"Time")
		with open(self.logfile_location,'w') as f:
			csv_writer = csv.writer(f, delimiter=',', lineterminator='\n',quoting=csv.QUOTE_MINIMAL)
			csv_writer.writerow(self.headers) #write header

		if mock:
			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Mock_Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name],config["port"])
		else:

			#initializing each controller with its specific max flow, name, etc.


			for subdev_name in params.keys():
				print(subdev_name)
				self.subdevices[subdev_name] = Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name],config["port"])
				if subdev_name == "Bulk SP": #if bulk SP, initialize each reactor individually as well
					for reactor in self.reactors:
						time.sleep(0.05)
						self.subdevices[reactor] =Subdevice(reactor,params["Bulk SP"],config["Subdevices"][reactor],config["port"]) #params must come from Bulk SP since reactor is not invidiually driven from recipe.
				time.sleep(0.05)	

	def get_pv(self,subdev_name):
		if subdev_name == "Bulk SP":
			elapsed_time = time.time()-self.logtimer

			if elapsed_time > self.log_time_interval  or self.cached_pv == None:
				flows = [time.ctime(time.time())]
				for i in self.reactors:
					if self.subdevices[i].active_flow_controller == 1:
						flows.append(self.subdevices[i].get_pv())
						time.sleep(0.05)
					else:
						flows.append(-1)

				#write to logfile
				with open(self.logfile_location,'a') as f:
					csv_writer = csv.writer(f, delimiter=',', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
					csv_writer.writerow(flows)
				
				#Display
				print("================== Flows ===================")
				print(tabulate.tabulate([flows],headers=self.headers,floatfmt=".2f"))
				print("\n")

				self.logtimer = time.time()
				self.cached_pv = sum([i for i in flows if (i != -1 and type(i) != str)])/len([i for i in flows if (i != -1 and type(i) != str)])
				return self.cached_pv #average pv of all MFCs reading
			else:
				return self.cached_pv
			
		else:
			return self.subdevices[subdev_name].get_pv()

	def get_sp(self,subdev_name):
		return self.subdevices[subdev_name].get_sp()

	def set_sp(self,subdev_name,sp_value):
		bool_ret = True
		if subdev_name == "Bulk SP":
			for subdev_name in self.reactors:
				if self.subdevices[subdev_name].active_flow_controller==1: #is flow controller that is active
					bool_ret= bool_ret and self.subdevices[subdev_name].set_sp(sp_value) #take the AND value of all the configured MFCs

			self.subdevices["Bulk SP"].set_sp(sp_value)
			return bool_ret

		else:
			return self.subdevices[subdev_name].set_sp(sp_value)

	def is_emergency(self,subdev_name,pv_read_time,sp_set_time,current_sp,current_pv):
		return self.subdevices[subdev_name].is_emergency(self.wait_time,pv_read_time,sp_set_time,current_sp,current_pv)

	def get_subdevice_names(self):
		if "Bulk SP" in self.subdevices.keys():
			subdev_names = list(self.subdevices.keys())
			for r in self.reactors:
				subdev_names.remove(r)
			return subdev_names
		else:
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
		self.active_flow_controller = config["active_flow_controller"]
		if name != "Bulk SP":
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
		if self.dev.get()['control_point'] == "gauge pressure":
			time.sleep(0.05)
			return float(self.dev.get()['pressure'])
		else:
			time.sleep(0.05)
			return float(self.dev.get()['mass_flow'])



	def set_sp(self,setpoint_in):

		if self.name == "Bulk SP":
			self.current_sp = setpoint_in
			return True

		else:
			try:
				if self.dev.get()['control_point'] == "gauge pressure":
					time.sleep(0.05)
					self.dev.set_pressure(float(setpoint_in))
				else:
					time.sleep(0.05)
					self.dev.set_flow_rate(float(setpoint_in))
			except:
				return False
			time.sleep(0.05)
			self.current_sp = setpoint_in
			if float(self.dev.get()['setpoint']) == setpoint_in:
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