"""Main module."""

class Reaction():
	def __init__(self,inputs_df,settings_df):
		self.devices = {} #a dictionary of subdevices, organized by major device
		self.modules = {} #a dictionary of used auxiliary communication modules, organized by major device

		#set up subdevices
		for subdevice_name in inputs_df.columns[1:]:
			parent_device_name = inputs_df[subdevice_name][0]
			units = inputs_df[subdevice_name][1]
			emergency_setting = inputs_df[subdevice_name][2]
			subdevice_setpoints = inputs_df[subdevice_name][3:]

			#initialize subdevice from relevant auxiliary communication module
			if parent_device_name not in self.devices.keys():
				self.modules[parent_device_name] = importlib.import_module(parent_device_name)
				self.devices[parent_device_name] = [self.modules[parent_device_name].initialize_subdevice(units,emergency_setting,subdevice_setpoints)]
			else:
				self.devices[parent_device_name].append(self.modules[parent_device_name].initialize_subdevice(units,emergency_setting,subdevice_setpoints))

		#set up logging file
		self.log_interval = settings_df["log_interval (s)"] #in seconds
		self.logfile_location = settings_df["logfile_location"]
		with open(self.logfile_location) as f:
			csv_writer = csv.writer(f, delimiter=' ', quotechar='|', quoting=csv.QUOTE_MINIMAL)
			self.log_header = inputs_df.columns
			self.log_header.insert(0,"Time")
			csv_writer.writerow(self.log_header)



		#set up gc and gc logging file if activated
		self.gc_file_location = settings_df["gc_file_location"]
		self.gc_module_name = settings_df["gc_module_name"]
		self.gc_module = None
		self.gc = None
		if self.gc_file_location != "":
			self.gc_module = importlib.import_module(self.gc_module_name)
			self.gc = self.gc_module.initialize_subdevice()

			with open(self.gc_file_location) as f:
				csv_writer = csv.writer(f, delimiter=' ', quotechar='|', quoting=csv.QUOTE_MINIMAL)
				csv_header = inputs_df.columns
				csv_header.insert(0,"GC Run ID")
				csv_header.insert(0,self.gc_module_name)
				csv_header.insert(0,"GC Time Stamp")
				csv_writer.writerow(csv_header)


		#set up reaction time and counters
		self.setpoint_switch_times = inputs_df["SubDevice"][3:]
		self.start_time = time.time()
		self.setpoint_switch_time = 0
		self.current_sp = -1
		self.next_sp = 0
		self.prev_log_time = 0

	def increment_setpts(self):
		for device_name in self.devices.keys():
			for subdevice in self.devices[device_name]:
				subdevice.set_sp(self.next_sp)

		self.setpoint_switch_time = time.time()
		rxn.current_sp += 1
		rxn.next_sp += 1	

	def log(self):
		self.prev_log_time = time.time()
		
		#read all PVs
		log_values = [self.prev_log_time]
		for device_name in self.devices.keys():
			for subdevice in self.devices[device_name]:
				log_values.append(subdevice.read_pv())

		#write PVs to logfile
		with open(self.logfile_location,'a') as f:
			csv_writer = csv.writer(f, delimiter=' ', quotechar='|', quoting=csv.QUOTE_MINIMAL)
			csv_writer.writerow(log_values)
	
		return log_values
	
	def is_emergency(self,log_values):
		for device_name in self.devices.keys():
			for subdevice in self.devices[device_name]:
				if subdevice.is_emergency(self.setpoint_switch_time,self.current_sp)


if __name__ == "__main__":
	import pandas as pd
	import importlib
	import time
	import csv

	#prompt users for input file, confirm it is correct


	inputs_df = pd.read_csv(input_file)
	settings_df = pd.read_csv("../config_files/rxn_control_config")

	print("Initializing devices...")
	rxn = Reaction(inputs_df,settings_df,rxn_folder)
	
	print("Starting reaction.")
	while rxn.next_sp != len(rxn.setpoint_switch_times):

		#Switch setpoints if time has elapsed
		if time.time() >= (rxn.start_time+rxn.setpoint_switch_times[rxn.next_sp]):
			print("Switching setpoints...")
			rxn.increment_setpts()


		if time.time() >= (rxn.prev_log_time+rxn.log_interval):
			log_values = rxn.log()
			if rxn.is_emergency(log_values):
				rxn.set_emergency_sps()
				raise Error("Emergency! program shutting down.")
			print(rxn.log_header)
			print(log_values)
	

	print("Reaction completed. Finished logging.")



#initialize_subdevice()

