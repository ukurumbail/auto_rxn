"""Main module."""
import pandas as pd
import importlib
import tabulate
import time
import json
import csv
import os

class Reaction():
	def __init__(self,inputs_df,settings_json,rxn_name, rxn_dirname):
		self.rxn_name = rxn_name
		self.rxn_dirname = rxn_dirname


		self.devices = {} #a dictionary of devices
		self.device_parameters = {} #Keep in mind parameters vs. config. Parameters = The parameters in the recipe specific to each subdevice/control point (emergency setpt, units, parent device name)
		self.device_config = {} #config = the metadata stored in the settings json that is used to connect to the actual device, etc.
		self.modules = {} #a dictionary of auxiliary communication modules, organized by major device

		#set up 
		self.num_subdevs = 0
		for subdevice_name in inputs_df.columns[1:]:
			self.num_subdevs += 1
			parent_device_name = inputs_df[subdevice_name][2]
			units = inputs_df[subdevice_name][0]
			emergency_setting = float(inputs_df[subdevice_name][1])

			if parent_device_name not in self.device_parameters.keys():
				self.device_parameters[parent_device_name] = {subdevice_name: {"Units" : units,
																"Emergency Setpoint" : emergency_setting
																}
															}
			else:
				self.device_parameters[parent_device_name][subdevice_name] = {"Units" : units,
																"Emergency Setpoint" : emergency_setting
																}		
			
		#initialize devices	
		for device_name in self.device_parameters.keys():										
			self.modules[device_name] = importlib.import_module(device_name)	
			self.device_config[device_name] = settings_json[device_name]
			self.devices[device_name] = self.modules[device_name].Device(self.device_parameters[device_name],self.device_config[device_name],mock = bool(settings_json["main"]["mock"]))

		#set up logging file
		self.log_interval = float(settings_json["logger"]["log_interval (s)"]) #in seconds
		self.logfile_location = os.path.join(self.rxn_dirname, "rxn_log_{}.csv".format(self.rxn_name))
		self.num_subdev = len(inputs_df.columns[1:])
		self.log_header = inputs_df.columns[1:].tolist()
		for i in range(len(self.log_header)):
			self.log_header.append(self.log_header[i]) #doubling up all items so we can have pv and sp!
		self.log_header = [str(i) for i in self.log_header]
		for i in range(self.num_subdev):
			self.log_header[i] += " SP"
			self.log_header[i+(self.num_subdev)] += " PV"
		self.log_header.insert(0, "Reaction Name")
		self.log_header.insert(0,"Time")

		with open(self.logfile_location,'w') as f:
			csv_writer = csv.writer(f, delimiter=',', lineterminator='\n',quoting=csv.QUOTE_MINIMAL)
			csv_writer.writerow(self.log_header)

		#set up setpoint matrix
		print(inputs_df.head())
		self.setpt_matrix = inputs_df.iloc[4:,:].apply(pd.to_numeric)
		for subdev_name in self.setpt_matrix.columns[1:]: #check to make sure each sp is below its max
			parent_device_name = inputs_df[subdev_name][2]
			for sp in self.setpt_matrix[subdev_name]:
				config_max = self.device_config[parent_device_name]["Subdevices"][subdev_name]["Max Setting"]
				if config_max != "None" and sp > config_max:
					raise ValueError("Configured SP {} for subdevice {} exceeds max {}".format(sp,subdev_name,config_max))


		#set up gc and gc logging file
		self.gc_logfile_location = os.path.join(self.rxn_dirname, "gc_log_{}.csv".format(self.rxn_name))
		self.gc_module_name = settings_json["main"]["GC Module Name"]
		self.gc = self.devices[self.gc_module_name]
		self.gc_needs_logging = False

		with open(self.gc_logfile_location,'w') as f:
			csv_writer = csv.writer(f, delimiter=',',lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
			self.gc_header = list(inputs_df.columns[1:])
			self.gc_header.insert(0,"GC Time Stamp")
			self.gc_header.insert(0,"GC Run ID")
			self.gc_header.insert(0,self.gc_module_name)
			self.gc_header.insert(0, "Reaction Name")
			csv_writer.writerow(self.gc_header)
	

		#set up reaction time and counters
		self.setpoint_switch_times = [60*float(i) for i in inputs_df["Control Point Name"][4:]] #convert from min to sec
		self.setpoint_switch_times.append(0) #The final setpt is an end setpt. No need to continue logging once this occurs. Just shut program off.
		self.start_time = time.time()
		self.setpoint_switch_time = 0
		self.current_sp = -1
		self.next_sp = 0
		self.prev_log_time = 0

	def set_setpts(self):

		for device_name in self.devices.keys():
			for subdevice_name in self.devices[device_name].get_subdevice_names():
				if self.devices[device_name].set_sp(subdevice_name,self.setpt_matrix[subdevice_name].iloc[self.next_sp]): #device should return whether setpt took successfully or not
					pass
				else:
					print("Emergency! Subdevice {} should return True if it succesfully takes its given SP [here: {}], but subdevice returned False.".format(subdevice_name,self.setpt_matrix[subdevice_name].iloc[self.next_sp]))
					self.set_emergency_sps()

		self.setpoint_switch_time = time.time()
		self.current_sp += 1
		self.next_sp += 1	

	def log(self,headers=True):
		self.prev_log_time = time.time()
		
		#add time and reaction name to log
		self.log_values = [time.ctime(self.prev_log_time) ,self.rxn_name]

		#add all setpoints to log
		for device_name in self.devices.keys():
			for subdevice_name in self.devices[device_name].get_subdevice_names():
				self.log_values.append(self.devices[device_name].get_sp(subdevice_name))
		for device_name in self.devices.keys():
			for subdevice_name in self.devices[device_name].get_subdevice_names():
				self.log_values.append(self.devices[device_name].get_pv(subdevice_name))

		#write to logfile
		with open(self.logfile_location,'a') as f:
			csv_writer = csv.writer(f, delimiter=',', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
			csv_writer.writerow(self.log_values)

		if headers:
			print(tabulate.tabulate([self.log_values],headers=self.log_header,floatfmt=".2f"))
		else:
			print(tabulate.tabulate([self.log_values],floatfmt=".2f"))			
	
	def set_emergency_sps(self):
		print("\nSetting emergency setpoints...\n")
		for device_name in self.devices.keys():
			for subdevice_name in self.devices[device_name].get_subdevice_names():
				emergency_sp = self.devices[device_name].get_emergency_sp(subdevice_name)
				print(self.devices[device_name].set_sp(subdevice_name,emergency_sp))
		time.sleep(5)
		self.log()
		raise IOError("Emergency setpoints set due to IO Error!")

	def create_gc_log(self):
		gc_run_id = None
		gc_inject_time = time.time()
		
		self.gc_log_values = [self.rxn_name,self.gc_module_name,gc_run_id,gc_inject_time]
		#add all setpoints to log
		for device_name in self.devices.keys():
			for subdevice_name in self.devices[device_name].get_subdevice_names():
				self.gc_log_values.append(self.devices[device_name].get_sp(subdevice_name))

	def log_gc(self):
		with open(self.gc_logfile_location,'a') as f:
			csv_writer = csv.writer(f, delimiter=',', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
			csv_writer.writerow(self.gc_log_values)	


	def is_emergency(self):
		i = 2 #skipping Time and rxn_name log values

		for device_name in self.devices.keys():
			for subdevice_name in self.devices[device_name].get_subdevice_names():
				subdev_sp = self.devices[device_name].get_sp(subdevice_name)
				emergency_values = self.devices[device_name].is_emergency(subdevice_name,self.prev_log_time,self.setpoint_switch_time,subdev_sp,self.log_values[i+self.num_subdevs]) #need to get to PVs, not SPs by adding self.num_subdevs
				if emergency_values[0] == True: 
					print("{}.{} in emergency. Current SP: {} Current PV: {}".format(device_name,emergency_values[1],emergency_values[2],emergency_values[3]))
					return True
				i += 1
	def email(self):
		rxn.set_emergency_sps()
		print("Switched to emergency setpoints. Make sure you implement this so as to avoid in the future...")
		raise NotImplementedError()

def run_rxn(inputs_df,settings_json,rxn_name,rxn_dirname):
	print("\nInitializing devices...")
	rxn = Reaction(inputs_df,settings_json,rxn_name,rxn_dirname)
	
	print("Starting reaction.")


	#beginning reaction
	print("\nSwitching setpoints...")
	rxn.set_setpts()
	print("Setpoints switched.\n")

	reaction_finished = False
	while not reaction_finished:
		#Switch setpoints if time has elapsed
		if time.time() >= (rxn.setpoint_switch_time+rxn.setpoint_switch_times[rxn.current_sp]):
			print("time is ready for next switch!")
			print("{} <- curr time sp_switch_time -> {} duration -> {}".format(time.time(),rxn.setpoint_switch_time,rxn.setpoint_switch_times[rxn.next_sp]))
			if rxn.gc.all_samples_collected():
				if rxn.next_sp == (len(rxn.setpoint_switch_times)-1):
						reaction_finished=True
				else:
					print("\nSwitching setpoints...")
					rxn.set_setpts()
					print("Setpoints switched.\n")
			time.sleep(5)
		if time.time() >= (rxn.prev_log_time+rxn.log_interval):
			rxn.log()
			if rxn.is_emergency():
				rxn.set_emergency_sps()
				raise NotImplementedError("Emergency! program shutting down. TBD- create a specific Exception class.")

			if rxn.gc_needs_logging:
				new_run_id = rxn.gc.get_last_run_id()
				if new_run_id == -999:
					rxn.email("Failed to get previous run id!")
				if new_run_id != rxn.gc.prev_run_id:
					rxn.gc_log_values[2] = new_run_id
					rxn.gc.prev_run_id = new_run_id
					rxn.log_gc()
					rxn.gc_needs_logging = False
			if not rxn.gc.all_samples_collected():
				time.sleep(2)
				if rxn.gc.ready():
					print("\nInjecting new GC sample...")
					if rxn.gc.inject():
						print("Injection successful.\n")
						rxn.create_gc_log()
						rxn.gc_needs_logging = True
					else:
						print("Injection unsuccessful!\n")
						rxn.email("Unsuccessful GC injection occurred @ {}\n".format(time.ctime(time.time)))

		time.sleep(5)


	while not rxn.gc.ready(): #wait for gc to finish up if needed
		time.sleep(10)
		rxn.log()

	if rxn.gc_needs_logging: #finish logging the last gc run
		new_run_id = rxn.gc.get_last_run_id()
		if new_run_id == -999:
			rxn.email("Failed to get previous run id!")
		if new_run_id != rxn.gc.prev_run_id:
			rxn.gc_log_values[2] = new_run_id
			rxn.gc.prev_run_id = new_run_id
			rxn.log_gc()
			rxn.gc_needs_logging = False		


	print("Reaction completed. Finished logging.")



