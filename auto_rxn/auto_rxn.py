"""Main module."""
import pandas as pd
import importlib
import tabulate
import time
import csv
import os

class Reaction():
	def __init__(self,inputs_df,settings_df,rxn_name, rxn_dirname,use_gc):

		self.rxn_name = rxn_name
		self.rxn_dirname = rxn_dirname


		self.devices = {} #a dictionary of subdevices, organized by major device
		self.modules = {} #a dictionary of used auxiliary communication modules, organized by major device

		#set up subdevices
		for subdevice_name in inputs_df.columns[1:]:
			parent_device_name = inputs_df[subdevice_name][0]
			units = inputs_df[subdevice_name][1]
			emergency_setting = float(inputs_df[subdevice_name][2])
			subdevice_setpoints = [float(i) for i in inputs_df[subdevice_name][3:]]

			#initialize subdevice from relevant auxiliary communication module
			if parent_device_name not in self.devices.keys():
				self.modules[parent_device_name] = importlib.import_module(parent_device_name)
				self.devices[parent_device_name] = [self.modules[parent_device_name].initialize_subdevice(subdevice_name,units,emergency_setting,subdevice_setpoints)]
			else:
				self.devices[parent_device_name].append(self.modules[parent_device_name].initialize_subdevice(subdevice_name,units,emergency_setting,subdevice_setpoints))

		#set up logging file
		self.log_interval = float(settings_df["log_interval (s)"][0]) #in seconds
		self.logfile_location = os.path.join(self.rxn_dirname, settings_df["logfile_location"][0])
		self.log_header = list(inputs_df.columns)
		self.log_header[0] = "Reaction Name"
		self.log_header.insert(0,"Time")
		self.log_header = [str(i) for i in self.log_header]
		with open(self.logfile_location,'w') as f:
			csv_writer = csv.writer(f, delimiter=',', lineterminator='\n',quoting=csv.QUOTE_MINIMAL)
			csv_writer.writerow(self.log_header)



		#set up gc and gc logging file if activated
		if use_gc:
			self.gc_file_location = os.path.join(self.rxn_dirname, settings_df["gc_file_location"][0])
			self.gc_module_name = settings_df["gc_module_name"][0]
			self.gc_module = importlib.import_module(self.gc_module_name)
			self.gc = self.gc_module.initialize_subdevice()

			with open(self.gc_file_location,'w') as f:
				csv_writer = csv.writer(f, delimiter=',',lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
				csv_header = list(inputs_df.columns)
				csv_header.insert(0,"Reaction Name")
				csv_header.insert(0,"GC Run ID")
				csv_header.insert(0,self.gc_module_name)
				csv_header.insert(0,"GC Time Stamp")
				csv_writer.writerow(csv_header)
		else:
			self.gc_file_location = None
			self.gc_module_name = None
			self.gc_module = None
			self.gc = None		

		#set up reaction time and counters
		self.setpoint_switch_times = [60*float(i) for i in inputs_df["SubDevice"][3:]] #convert from s to min
		self.setpoint_switch_times.append(0) #The final setpt is an end setpt. No need to continue logging once this occurs. Just shut program off.
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
		self.current_sp += 1
		self.next_sp += 1	

	def log(self,headers=True):
		self.prev_log_time = time.time()
		
		#read all PVs
		log_values = [time.ctime(self.prev_log_time) ,self.rxn_name]
		for device_name in self.devices.keys():
			for subdevice in self.devices[device_name]:
				log_values.append(subdevice.read_pv())

		#write PVs to logfile
		with open(self.logfile_location,'a') as f:
			csv_writer = csv.writer(f, delimiter=',', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
			csv_writer.writerow(log_values)

		if self.is_emergency(log_values):
			self.set_emergency_sps()
			raise Error("Emergency! program shutting down.")

		if headers:
			print(tabulate.tabulate([log_values],headers=self.log_header,floatfmt=".2f"))
		else:
			print(tabulate.tabulate([log_values],floatfmt=".2f"))			
	
	def is_emergency(self,log_values):
		i = 0
		for device_name in self.devices.keys():
			for subdevice in self.devices[device_name]:
				emergency_values = subdevice.is_emergency(self.prev_log_time,self.setpoint_switch_time,self.current_sp,log_values[i])
				if emergency_values[0] == True: 
					print("{}.{} in emergency. Current SP: {} Current PV: {}".format(device_name,emergency_values[1],emergency_values[2],emergency_values[3]))
					return True
			i += 1
def run_rxn(inputs_df,settings_df,rxn_name,rxn_dirname,use_gc):


	print("\nInitializing devices...")
	rxn = Reaction(inputs_df,settings_df,rxn_name,rxn_dirname,use_gc)
	
	print("Starting reaction.")


	#beginning reaction
	print("\nSwitching setpoints...")
	rxn.increment_setpts()
	print("Setpoints switched.\n")

	log_counter = 0
	reaction_finished = False
	while not reaction_finished:
		#Switch setpoints if time has elapsed
		if time.time() >= (rxn.start_time+rxn.setpoint_switch_times[rxn.next_sp]):
			if rxn.next_sp == (len(rxn.setpoint_switch_times)-1):
					reaction_finished=True
			else:
				print("\nSwitching setpoints...")
				rxn.increment_setpts()
				print("Setpoints switched.\n")

		if time.time() >= (rxn.prev_log_time+rxn.log_interval):
			rxn.log()
			log_counter += 1

	
		time.sleep(5)


	rxn.log()
	print("Reaction completed. Finished logging.")



#initialize_subdevice()

