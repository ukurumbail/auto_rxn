class Subdevice():
	def __init__(self,subdevice_name,units,emergency_setting,subdevice_setpoints):
		self.name = subdevice_name
		self.units = units
		self.emergency_setting = emergency_setting
		self.setpoints = subdevice_setpoints

	def is_emergency(self,pv_read_time,sp_set_time,current_sp,current_pv):
		return [False,self.name,current_sp,current_pv]
	def read_pv(self):
		return 0

	def set_sp(self,setpt_idx):
		pass

def initialize_subdevice(subdevice_name,units,emergency_setting,subdevice_setpoints):
	return Subdevice(subdevice_name,units,emergency_setting,subdevice_setpoints)