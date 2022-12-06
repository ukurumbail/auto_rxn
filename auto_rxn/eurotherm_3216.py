import minimalmodbus
import simple_pid
import serial
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
			self.current_max_temp_setpt = self.get_sp("Furnace Temp")
		else:
			self.furnace_temp_exists=False
			raise NotImplementedError("Error! Trying to run furnace without Furnace Temp. Have not implemented this.")

		if "Ramp Rate" in params.keys():
			self.ramp_rate_exists=True
			self.last_sp_time = None
		else:
			self.ramp_rate_exists=False

		if "Reactor Temp" in params.keys():
			self.cascade_control_possible = True #need to check for AUTO or CASCADE control mode
			self.reactor_temp_expected_dTdt = config["Subdevices"]["Reactor Temp"]["Expected dT/dt"] #degC/sec
			self.cascade_control_start_time = None
			self.cascade_control_active = False
			self.cascade_pid_params = config["Subdevices"]["Reactor Temp"]["PID_params"]
			self.cascade_pid_sample_time = config["Subdevices"]["Reactor Temp"]["PID_sample_time"]
			self.cascade_controller = simple_pid.PID(self.cascade_pid_params[0],self.cascade_pid_params[1],self.cascade_pid_params[2],setpoint=0.0)
			self.cascade_controller.auto_mode = False #set cascade controller to manual to start! (overall control mode = AUTO, not CASCADE)
			self.cascade_controller.sample_time = self.cascade_pid_sample_time
			self.cascade_controller_max_movement = config["Subdevices"]["Reactor Temp"]["PID_max_movement"] #In degC, the total possible deviation up or down the furnace setpoint can move from its initial value
			self.prev_reactor_temp = None
			self.reactor_PV_error_counter = 0
		else:
			self.cascade_control_possible = False
			self.cascade_control_active = False

		if "PV Offset" in params.keys(): 
			self.static_PV_offset = config["Subdevices"]["Furnace Temp"]["T Correction"] #get static PV Offset from Furnace Temp subdevice
			if abs(self.static_PV_offset) > abs(config["Subdevices"]["PV Offset"]["Max Setting"]):
				raise ValueError("Static PV Offset larger than max allowed value. Throwing an error!")
			self.PV_offset_possible = True
			self.PV_offset_type = 0 #types are: 0 (no offset), 1 (static), 2 (remain at previous), 3 (active)
			self.PV_offset_dynamic_active = False
			self.PV_offset_trig_thresh = config["Subdevices"]["PV Offset"]["Trigger Threshold"]
		else:
			self.PV_offset_possible	= False
		print("Enabling ramp rate: {}".format(self.ramp_rate_exists))
		print("Enabling cascade control: {}".format(self.cascade_control_possible))
		print("Enabling PV Offset: {}".format(self.PV_offset_possible))
	def get_pv(self,subdev_name):
		return self.subdevices[subdev_name].get_pv(self.dev)

	def get_sp(self,subdev_name):
		return self.subdevices[subdev_name].get_sp(self.dev)

	def set_sp(self,subdev_name,sp_value):
		if self.ramp_rate_exists and subdev_name == "Furnace Temp":
			self.prev_max_setpt = self.current_max_temp_setpt
			self.current_max_temp_setpt = sp_value
			return True
		if subdev_name == "PV Offset":
			if sp_value == 0: #Offset should be set to 0
				self.PV_offset_dynamic_active = False
				if self.get_sp("PV Offset") != 0:
					return self.set_sp("PV Offset", 0)
				else: #no need to set if already 0
					return True
			elif sp_value == 1:
				self.PV_offset_dynamic_active = False
				if self.get_sp("PV Offset") != self.static_PV_offset:
					return self.set_sp("PV Offset", self.static_PV_offset)
				else:
					return True
			elif sp_value == 2:
				self.PV_offset_dynamic_active = False
				return True #no changes needed

			elif sp_value == 3:
				self.PV_offset_dynamic_active = True
				if "Reactor Temp" not in self.subdevices.keys():
					raise ValueError("Trying to set dynamic offset without a Reactor PV reading. Throwing an error.")
					return False
				else:
					return True


			else:
				print("Unknown sp value in PV Offset: {}, type: {}. Throwing an error!".format(sp_value,type(sp_value)))
				return False

		if self.cascade_control_possible:
			if subdev_name == "Reactor Temp":
				if sp_value == -1: #sp value of -1 means do not apply cascade control, only read PV from reactor temp monitor
					self.cascade_control_active = False 
				else:
					self.cascade_control_active = True
					self.cascade_control_start_time = time.time()
			elif subdev_name == "Furnace Temp":
				self.prev_sp = self.get_sp("Furnace Temp")
		
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
		if subdev_name == "Furnace Temp":
			if self.ramp_rate_exists:
				if self.last_sp_time == None:
					self.last_sp_time = time.time()
				new_sp = self.subdevices["Furnace Temp"].current_sp + (self.get_sp("Ramp Rate") * (time.time() - self.last_sp_time)/60)	
				if self.current_max_temp_setpt > self.prev_max_setpt:
					new_sp = min(new_sp,self.current_max_temp_setpt) #want minimum of the two if increasing temp

				elif self.current_max_temp_setpt < self.prev_max_setpt:
					new_sp = max(new_sp,self.current_max_temp_setpt)

				else: #no change in temp setpt
					return True
				if new_sp != self.subdevices["Furnace Temp"].current_sp:
					return self.set_sp("Furnace Temp",new_sp)
				else:
					return True #no need to re-set setpoint if we've reached our new resting point

			elif self.cascade_control_active: #dynamically setting furnace temp
				#first check to see if we are ready to enable cascade control. We only do this once the 
				#controller has had enough time for the inner loop to work its magic
				if (time.time()-self.cascade_control_start_time) > (abs(self.prev_sp-self.get_sp("Furnace Temp"))/self.reactor_temp_expected_dTdt):
					if self.cascade_controller.auto_mode == False: #if we just reached the time to start cascade control:
						curr_furnace_sp = self.get_sp("Furnace Temp")
						self.cascade_controller.output_limits = (curr_furnace_sp-self.cascade_controller_max_movement,curr_furnace_sp+self.cascade_controller_max_movement)
						self.cascade_controller.setpoint = self.get_sp("Reactor Temp")
						self.cascade_controller.set_auto_mode(True,last_output = curr_furnace_sp)
					current_reactor_pv = self.get_pv("Reactor Temp")
					if current_reactor_pv > 0: #no errors
						control = self.cascade_controller(current_reactor_pv)
						print("Cascade Controller Output: {:.3}".format(control))
						self.set_sp("Furnace Temp",control)


					else: #something went wrong reading the reactor PV. Start shutting down the program and executing emergency setpoints.
						print("Error getting current reactor PV!!!")
						return False
			else:
				return True #No need to update setpoint if there's no ramp rate
		elif subdev_name == "PV Offset":
			if self.PV_offset_dynamic_active: #if dynamic PV offset control, check to see if timer has elapsed:
				try:
					prev_sp_time = self.subdevices["PV Offset"].last_sp_time
				except AttributeError:
					prev_sp_time = time.time() #never called subdevice before
					self.subdevices["PV Offset"].last_sp_time = prev_sp_time

				if time.time()-prev_sp_time> 1: #only update this parameter once every 1 second or more.
					reactor_PV = self.get_pv("Reactor Temp")

					#Sometimes Omega device gives a weirdly high value ex. 5532. In these cases, only treat as error
					#if you see a high value twice in a row
					if reactor_PV > 1000: #most likely a weird error. Increment error counter
						print("Reactor PV of {} reported. Assuming for now this is an error. If it happens twice in a row will throw an emergency.".format(reactor_PV))
						self.reactor_PV_error_counter += 1
						if self.reactor_PV_error_counter >= 2:
							print("2 errors in a row for reactor PV found!")
							print("Sending the device into error!") #by not doing anything and letting it fail on PV_Offset
						else:
							reactor_PV = self.prev_reactor_temp
					else:
						self.prev_reactor_temp = reactor_PV
						self.reactor_PV_error_counter = 0 #reset error counter after a reasonable value
					furnace_PV = self.get_pv("Furnace Temp")
					furnace_PV_offset = self.get_sp("PV Offset")
					print("Furnace PV with Offset: {:.5} Reactor PV: {:.5}. Prev Offset: {}".format(furnace_PV,reactor_PV,furnace_PV_offset))
					#trigger a PV Offset change only when we are beyond the trigger threshold
					furnace_PV -= furnace_PV_offset #strip offset value to compare against offset trigger
					print("Furnace PV without offset: {}".format(furnace_PV))
					if abs((reactor_PV - furnace_PV) - self.get_sp("PV Offset")) > self.PV_offset_trig_thresh:
						print("Adjusting  offset!")
						return self.subdevices["PV Offset"].set_sp(self.dev,reactor_PV-furnace_PV)
					else:
						print("Not above offset trigger threshold")
						return True
				else:
					return True
			else:
				return True #No updates needed if we're not in dynamic mode

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
		self.config = config

		if self.name == "Reactor Temp":
			self.ser = serial.Serial(port=self.config["port"],baudrate=self.config["baudrate"])
			self.PV_arr = []
			try:
				self.ser.open()
			except serial.serialutil.SerialException: #port is already open
				pass
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
			else:
				print("Not implemented!")
				return [True,self.name,current_sp,current_pv] 
		else:
			return [False,self.name,current_sp,current_pv]


	def get_pv(self,dev):
		if self.name =="Furnace Temp":
			return dev.read_float(self.pv_read_address)
		elif self.name == "Reactor Temp":
			self.ser.write("F\r".encode())
			time.sleep(0.1)
			try: 
				read_val = self.ser.readline().decode().rstrip()
				read_val = read_val.replace('>','')
				read_val_degC = 5/9 * (float(read_val)-32) #convert F to C
				if len(self.PV_arr) < 1: #average 1 values
					self.PV_arr.append(read_val_degC)

				else:
					self.PV_arr.pop(0)
					self.PV_arr.append(read_val_degC)

				return sum(self.PV_arr)/len(self.PV_arr)

			except:
				print("PV read error!!!!")
				try:
					print("Val from thermocouple is {}".format(read_val))
					return -200
				except:
					return -200
		elif self.name == "PV Offset":
			return self.get_sp(dev)
	def set_sp(self,dev,sp_value):
		if self.current_sp == None:
			self.current_sp = self.get_sp(dev)
		sp_value = float(sp_value)

		if sp_value	< self.max_setting:
			if self.name == "Furnace Temp" or self.name == "PV Offset":
				dev.write_float(self.sp_write_address,sp_value)
				time.sleep(.5)
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