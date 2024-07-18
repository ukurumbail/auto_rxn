import minimalmodbus
import asyncio
import simple_pid
import serial
import time
import numpy as np
from labjack import ljm
from simple_pid import PID
import os
import csv
import tabulate 
import copy
class Device():
	#If you need to activate port: Go to iTools OPC Server --> Edit --> iTools Control Panel and uncheck whatever port
	def __init__(self,params,config,mock=False,rxn_dir=None):
		self.config = config
		self.params = params
		# self.flow_dev_lim = 2
		# self.emergency_flows = {}
		self.subdevices = {}
		self.mock = mock

		self.rxn_dirname = rxn_dir
		self.logfile_location = os.path.join(self.rxn_dirname, "{}.csv".format("6flow_temp_pv_log"))
		self.logtimer = time.time()
		self.log_time_interval = 5 #seconds
		
		self.addressbook = {"R1":7020,"R2":7016,"R3":7012,"R4":7008,"R5":7004,"R6":7000}
		with open(self.logfile_location,'w') as f:
			csv_writer = csv.writer(f, delimiter=',', lineterminator='\n',quoting=csv.QUOTE_MINIMAL)
			self.headers = list(self.addressbook.keys())
			self.headers.insert(0,"Current SP")
			self.headers.insert(0,"Time")
			csv_writer.writerow(self.headers) #write header


		if self.mock:
			self.dev = None
			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Mock_Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name])
		else:
			self.dev = minimalmodbus.Instrument(self.config["port"],self.config["address"])
			self.dev.serial.baudrate = self.config["baudrate"]
			self.dev.serial.timeout = self.config["timeout"]
			for subdev_name in params.keys(): #for each subdevice in input file
				self.subdevices[subdev_name] = Subdevice(subdev_name,params[subdev_name],config["Subdevices"][subdev_name])

		#Establishing basic booleans to control high-level code functionalities (ramp rate, cascade control, etc.)
		if "Furnace Temp" in params.keys():
			self.furnace_temp_exists=True
		else:
			self.furnace_temp_exists=False
			raise NotImplementedError("Error! Trying to run furnace without Furnace Temp. Have not implemented this.")

		if "Ramp Rate" in params.keys():
			self.ramp_rate_exists=True
		else:
			self.ramp_rate_exists=False

		if "Reactor Temp" in params.keys():
			self.reactor_temp_exists = True
		else:
			self.reactor_temp_exists = False

		print("Ramp rate control available: {}".format(self.ramp_rate_exists))
		print("Reactor setpoint tracking available: {}".format(self.reactor_temp_exists))

		self.reactor_PV_error_counter = 0

		#setpoint values initialized at current value. See async_run fx for details on implementation
		self.new_SP = self.subdevices["Furnace Temp"].get_sp(self.dev)
		self.curr_SP = self.new_SP
		self.old_SP = self.new_SP
		self.SP_switch_occurred = False

		#boundaries
		self.min_SP = 0
		self.max_SP = float(self.subdevices["Furnace Temp"].max_setting)

		self.alt_sp_register = int(2*26+32768) #register for alternate setpoints
		self.ramp_in_progress = False
		self.ramp_start_time = None 
		self.ramp_start_temp = None

		self.tracker_start = None #timepoint of previous furnace setpoint switch
		self.tracker_db = 1 #degC deadband where tracker will cease to operate within. i.e. you're close enough to sp
		self.tracker_stabilization_time = 4 #minutes
		self.tracker_pv_stabilization_db = 1 #degC band of stability in SP for when you can execute next furnace setpoint switch
		self.tracker_pv_register_length = 480
		self.tracker_sensitivity = 1 #how aggressive the tracker tracks the delta b/w reactor pv and reactor sp when making a switch. 0-1


		self.tracking_in_progress = False
		self.cascade_in_progress = False
		self.ramp_in_progress = False

		# self.cascade_start = None #timepoint of previous furnace setpoint switch
		# self.cascade_db = 0.5 #degC deadband where cascade will cease to operate within. i.e. you're close enough to sp
		# self.cascade_pv_stabilization_db = 2 #degC band of stability for when you can execute next furnace setpoint switch
		# self.cascade_pv_register_length = 50

	def get_pv(self,subdev_name):
		return self.subdevices[subdev_name].get_pv(self.dev)

	def get_sp(self,subdev_name):
		return self.subdevices[subdev_name].get_sp(self.dev)

	def set_sp(self,subdev_name,sp_value):
		if subdev_name == "Furnace Temp":
			self.new_SP = sp_value
			self.SP_switch_occurred = True #flag to tell program to re-check for new control logic
			return True
		else:
			return self.subdevices[subdev_name].set_sp(self.dev,sp_value)

	def is_emergency(self,subdev_name,pv_read_time,sp_set_time,current_sp,current_pv):
		return self.subdevices[subdev_name].is_emergency(pv_read_time,sp_set_time,current_sp,current_pv)

	def get_subdevice_names(self):
		return self.subdevices.keys()

	def get_emergency_sp(self,subdev_name):
		return self.subdevices[subdev_name].emergency_setting

	def get_max_setting(self,subdev_name):
		return self.subdevices[subdev_name].get_max_setting()

	def log_reactor_pv(self):
		elapsed_time = time.time()-self.logtimer 

		if elapsed_time > self.log_time_interval:
			Ts = [time.ctime(time.time()),self.curr_SP]
			dataType = ljm.constants.FLOAT32
			for i in range(1,7,1):
				Ts.append(ljm.eReadAddress(self.subdevices["Reactor Temp"].handle, self.addressbook[f'R{i}'], dataType))
				time.sleep(0.05)

			#write to logfile
			with open(self.logfile_location,'a') as f:
				csv_writer = csv.writer(f, delimiter=',', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
				csv_writer.writerow(Ts)

			#Display
			print("=============== Temperatures ===============")
			print(tabulate.tabulate([Ts],headers=self.headers,floatfmt=".2f"))
			print("\n")
			self.logtimer = time.time()
		else:
			pass


	def ready_for_furnace_sp_switch(self):
		#This method determines whether furnace SP is ready for a switch during reactor PV tracking.


		#First, check and see if you have a runaway reaction. If reactor is way too hot, make the switch right away.
		furnace_reactor_delta = abs(self.tracker_reactor_pv_register[-1] - self.tracker_furnace_pv_register[-1])
		if  furnace_reactor_delta > 150 and len(self.tracker_reactor_pv_register) > 10 and not self.mock:
			print("Reactor is getting too far from setpoint. Likely exothermic reaction. Switching setpoint early.")
			print("Current Delta b/w furnace PV and reactor PV: {}".format(furnace_reactor_delta))
			return True 

		#Second, run the checks to see whether the reactor PV has stabilized for long enough. 
		else:

			if time.time() - self.tracker_start < self.tracker_stabilization_time*60: #if sufficient time has not passed
				print("Waiting on tracker stabilization time. Current Range: {} ".format(abs(max(self.tracker_reactor_pv_register) - min(self.tracker_reactor_pv_register))))
				return False

			elif abs(max(self.tracker_reactor_pv_register) - min(self.tracker_reactor_pv_register)) > self.tracker_pv_stabilization_db: #if pv has not stabilized from previous switch
				print("Waiting on tracker stabilization temperature. Current Range: {}".format(abs(max(self.tracker_reactor_pv_register) - min(self.tracker_reactor_pv_register))))
				return False

			elif abs(self.tracker_reactor_pv_register[-1] - self.new_SP) <= self.tracker_db: #if within deadband:
				#self.tracking_in_progress = False #Done tracking! You have completed all criteria...
				#print("Furnace tracking turned off for this step. PV has met requested SP and stabilized.")
				print("No change to SP. Within deadband.")
				return False

			else:
				return True 

	async def async_run(self):
		while True:
			try:
				if self.SP_switch_occurred: #Setpoint has changed. Need to deal with this.

					
					#reinitializing booleans to False
					self.SP_switch_occurred = False
					self.tracking_in_progress = False
					self.cascade_in_progress = False
					self.ramp_in_progress = False

					if self.new_SP == -999: #Hold Previous Value
						print("Received -999 SP. Holding Previous Value")
						self.new_SP = self.curr_SP
						self.old_SP = self.curr_SP
						self.subdevices["Furnace Temp"].current_sp = self.curr_SP

					else:
						#decide whether to execute tracking logic in the main loop
						if self.reactor_temp_exists:
							if self.get_sp("Reactor Temp") == 1: #tracking
								self.tracking_in_progress = True
								self.tracker_start = None

							elif self.get_sp("Reactor Temp") == 2: #cascade control
								self.cascade_in_progress = True
								self.casacde_start = None 
								#self.pid = PID(1,1/120.0,20,setpoint=self.new_SP) # high-T PID parameters
								self.pid  = PID(1.5,1/444.56,74.09,setpoint=self.new_SP) # 250C PID parameters
								#self.pid  = PID(2,1/566.81,94.47,setpoint=self.new_SP) # 175C PID parameters
								self.pid.output_limits = (self.new_SP-200,self.new_SP+50)
								self.pid.sample_time = 1 #minimum seconds b/w updates

								self.pid.auto_mode = False #turn pid off until control begins




						#decide whether to execute ramping logic in the main loop
						if self.ramp_rate_exists: #possibility of ramping the setpoint
							self.curr_ramp_rate = abs(self.subdevices["Ramp Rate"].current_sp) #only work with absolute value

							if self.curr_ramp_rate == 0: #ramp rate of zero --> straightforward setpoint change
								self.curr_SP = self.new_SP

							else: #ramp initialization logic

								self.ramp_start_time = time.time()
								self.ramp_start_temp = self.curr_SP
								self.ramp_in_progress = True

						else:
							self.curr_SP = self.new_SP

						self.old_SP = self.new_SP #move the new SP over to old SP

				else: #No new setpoint from auto_rxn. Execute loop logic
					self.prev_curr_SP = self.curr_SP
					
					if self.ramp_in_progress: #Ramp in progress! Change curr_SP based on ramping

						if self.curr_SP == self.new_SP: #ramp finished
							self.ramp_in_progress = False
						else:
							if self.ramp_start_temp <= self.new_SP: #ramping up:
								self.curr_SP = self.ramp_start_temp + self.curr_ramp_rate * (time.time() - self.ramp_start_time)/60
								self.curr_SP = min(self.curr_SP,self.new_SP)
							else: #ramping down
								self.curr_SP = self.ramp_start_temp - self.curr_ramp_rate * (time.time() - self.ramp_start_time)/60
								self.curr_SP = max(self.curr_SP,self.new_SP)

					elif self.tracking_in_progress: #Once ramping is finished, check for tracking: 
						if self.tracker_start == None:
							self.tracker_start = time.time() #Start the tracker
							self.tracker_reactor_pv_register = [] #reinitialize the pv_tracker
							self.tracker_furnace_pv_register = []
							self.tracker_time_register = []

						self.tracker_time_register.append(time.time())
						self.tracker_reactor_pv_register.append(self.get_pv("Reactor Temp")) #each iteration collect a new tracker PV
						self.tracker_furnace_pv_register.append(self.get_pv("Furnace Temp"))


						#check for bad pv from reactor. If you get one, remove from the array
						if self.tracker_reactor_pv_register[-1] < self.min_SP or self.tracker_reactor_pv_register[-1] > (self.max_SP + 200):  
							print("Bad PV! {}. Skipping this one.".format(self.tracker_reactor_pv_register[-1]))
							self.tracker_reactor_pv_register.pop(-1)
							self.tracker_furnace_pv_register.pop(-1)
							self.tracker_time_register.pop(-1)
						#pop the first element if tracker is at max length
						elif len(self.tracker_reactor_pv_register) > self.tracker_pv_register_length:
							self.tracker_reactor_pv_register.pop(0)
							self.tracker_furnace_pv_register.pop(0)
							self.tracker_time_register.pop(0)

						print("Current Time Delta on Register: {}".format(self.tracker_time_register[-1]-self.tracker_time_register[0]))
						if self.ready_for_furnace_sp_switch():
							chosen_pv = sum(self.tracker_reactor_pv_register[-5:-1])/len(self.tracker_reactor_pv_register[-5:-1]) 
							delta = chosen_pv - self.new_SP
							self.curr_SP -= delta*self.tracker_sensitivity

							print (f'Switching Furnace Setpoint. Reactor PV: {chosen_pv} Prev Furnace SP: {self.prev_curr_SP}. New Furnace SP: {self.curr_SP}')
							self.tracker_start = None

					elif self.cascade_in_progress: #Execute cascade control if active
						if self.pid.auto_mode == False: 
							self.pid.set_auto_mode(True,last_output=self.get_sp("Furnace Temp")) #turn pid on with 0 integral error

						pv = self.get_pv("Reactor Temp")
						if pv < self.min_SP or pv > self.max_SP: #sometimes TC returns a bad reading. In this case, skip it
							print("Bad thermocouple PV: {}".format(pv))
						else:
							self.curr_SP = self.pid(pv)
						p,i,d = self.pid.components
						print(f'P: {p} I: {i}, D: {d}')

					#make sure curr_SP is within boundaries
					self.curr_SP = max(self.min_SP,self.curr_SP)
					self.curr_SP = min(self.max_SP,self.curr_SP)
					self.curr_SP = float(self.curr_SP)
						
					#write curr_SP
					if self.mock:
						self.subdevices["Furnace Temp"].current_sp = self.curr_SP
					else:
						self.dev.write_float(self.alt_sp_register,self.curr_SP)
						if self.prev_curr_SP != self.curr_SP:
							print (f'Furnace update. Prev Furnace SP: {self.prev_curr_SP}. New Furnace SP: {self.curr_SP}')
						self.log_reactor_pv()
		
					await asyncio.sleep(.5)

			except Exception as e:
				print("Error: {}".format(e))


class Mock_Subdevice():
	def __init__(self,name,params,config):
		self.name = name
		self.units = params["Units"]
		self.emergency_setting = params["Emergency Setpoint"]
		self.current_sp = 25
		self.max_setting = config["Max Setting"]

	def is_emergency(self,pv_read_time,sp_set_time,current_sp,current_pv):
		return [False,self.name,current_sp,current_pv]
	def get_pv(self,dev):
		if self.name == "Reactor Temp":
			return np.random.uniform(505,510)
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
		self.config = config
		self.write_counter = 0
		if self.dev_type == "Sensor Break":
			self.sensor_break_counter = 0
			self.sensor_break_value = config["Sensor Break Value"]
			self.sensor_break_max = config["Sensor Break Max"]

		if self.name == "Reactor Temp":


			self.handle = ljm.openS("T7", "ANY", "ANY")  # T7, Any connection, Any identifier


			info = ljm.getHandleInfo(self.handle)

			print("Opened a LabJack with Device type: %i, Connection type: %i,\n"
      "Serial number: %i, IP address: %s, Port: %i,\nMax bytes per MB: %i" %
      (info[0], info[1], info[2], ljm.numberToIP(info[3]), info[4], info[5]))



	def is_emergency(self,pv_read_time,sp_set_time,current_sp,current_pv):
		if (pv_read_time-sp_set_time) > self.wait_time:
			if self.dev_type == "Change from previous": #Use dev_lim as a minimum change required from previous sp
				if current_sp == None:
					return [False,self.name,current_sp,current_pv]
				else:
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
			elif self.dev_type == "Do not check for emergency":
				return [False,self.name,current_sp,current_pv]

			elif self.dev_type == "Sensor Break": #Check for x number of bad PV values in a row. Error out if this is achieved.
				if int(current_pv) == int(self.sensor_break_value):
					self.sensor_break_counter += 1
					print(f'Bad Sensor Value detected in {self.name}. Break Counter: {self.sensor_break_counter} of {self.sensor_break_max}')
				else:
					self.sensor_break_counter=0 #reset counter
				if self.sensor_break_counter >= self.sensor_break_max:
					return [True,self.name,current_sp,current_pv]
				else:
					return [False,self.name,current_sp,current_pv]
				 
			else:
				print("Not implemented!")
				return [True,self.name,current_sp,current_pv] 
		else:
			return [False,self.name,current_sp,current_pv]


	def get_pv(self,dev):
		if self.name =="Furnace Temp":
			return dev.read_float(self.pv_read_address)
		elif self.name == "Reactor Temp":

			address = 7020  # Address for AIN10 configured output (degC) #R1
			#address = 7016  # Address for AIN10 configured output (degC) #R2
			#address = 7012  # Address for AIN10 configured output (degC) #R3
			#address = 7008  # Address for AIN10 configured output (degC) #R4
			#address = 7004  # Address for AIN10 configured output (degC) #R5
			#address = 7000  # Address for AIN10 configured output (degC) #R6
			dataType = ljm.constants.FLOAT32
			result = ljm.eReadAddress(self.handle, address, dataType)
			return result
		elif self.name == "PV Offset":
			return self.get_sp(dev)
		elif self.name == "Ramp Rate":
			return self.get_sp(dev)
	def set_sp(self,dev,sp_value):
		if self.current_sp == None:
			self.current_sp = self.get_sp(dev)
		sp_value = float(sp_value)

		if sp_value	< self.max_setting:
			if self.name == "Furnace Temp" or self.name == "PV Offset":
				curr_sp = self.get_sp(dev)
				if sp_value != curr_sp:
						dev.write_float(self.sp_write_address,sp_value)
						self.write_counter += 1
						print("Write Counter: {}".format(self.write_counter))
				else:
					print("New SP {} is same as current SP {} for furnace subdevice {}. Not re-writing value.".format(sp_value,curr_sp,self.name))
				time.sleep(.05)
				dev_sp = self.get_sp(dev)
				if abs(abs(dev_sp) - abs(sp_value))>.01: #if deviating by more than .01 the setpoint did not take
					print("SP did not take! Device SP: {} Requested SP: {}".format(dev_sp,sp_value))
					return False
				else:
					self.prev_sp = self.current_sp
					self.last_sp_time = time.time()
					self.current_sp = sp_value
					return True
			elif self.name == "Ramp Rate" : 
				self.current_sp = sp_value
				return True
			elif self.name == "Reactor Temp":
				self.current_sp = sp_value
				return True
			else:
				print("Trying to set setpt for {} which is not implemented yet.".format(self.name))
				return False 
		else:
			if self.name == "PV Offset" : 
				dev.write_float(self.sp_write_address,self.max_setting) #sometimes reactor PV will spike. just use max setting for offset
				time.sleep(.05)
				dev_sp = self.get_sp(dev)
				if dev_sp != sp_value:
					print("SP did not take! Device SP: {} Requested SP: {}".format(dev_sp,sp_value))
					return False
				else:
					self.prev_sp = self.current_sp
					self.last_sp_time = time.time()
					self.current_sp = sp_value
					return True
			else:
				print("Requested SP: {} is larger than max setpoint allowed: {}".format(sp_value,self.max_setting))
				return False


	def get_sp(self,dev):
		if self.name == "Furnace Temp":
			return dev.read_float(self.sp_read_address)
		elif self.name == "Reactor Temp":
			return self.current_sp
		elif self.name == "Ramp Rate": 
			return self.current_sp
		elif self.name == "PV Offset":
			return dev.read_float(self.sp_read_address)
		else:
			print("Trying to get SP for {} which is not implemented yet!".format(self.name))

	def get_max_setting(self):
		return self.max_setting