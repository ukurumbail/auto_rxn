import pandas as pd
import json
import time
import os

def get_run_data(run_id):
	with open("./auto_rxn/bp_json.json",'r') as f:
		bp_json = json.load(f)
	return bp_json

def analyze(rxn_dirname):
	#takes in the directory for a reaction and produces an analysis

	gc_logfile_string = "gc_log_"+rxn_dirname.split('\\')[-1]
	config_file_string = "rxn_control_config.json"

	#load each gc data point
	gc_log_csv = os.path.join(rxn_dirname,gc_logfile_string)
	gc_log_csv += '.csv'
	gc_log_csv.replace("\\","/")
	df = pd.read_csv(gc_log_csv)

	#get the config of each subdevice used
	subdev_configs = {}
	with open(rxn_dirname+"\\"+config_file_string, 'r') as f:
		settings_json = json.load(f)
		for dev in settings_json.values():
			for subdev_name in dev["Subdevices"].keys():
				if subdev_name in df.columns:
					subdev_configs[subdev_name] = dev["Subdevices"][subdev_name]

	#Apply temperature correction
	for subdev in df.columns:
		if subdev not in ["Reaction Name","inficon_gc","GC Run ID","GC Time Stamp"]:	
			if subdev_configs[subdev]["Analysis Device Type"] == "Reactor Temp":
				df["Reactor Temperature Corrected"] = df[subdev] + subdev_configs[subdev]["T Correction"]

	#Apply flow correction
	flow_subdevs = []
	for subdev in df.columns:
		if subdev not in ["Reaction Name","inficon_gc","GC Run ID","GC Time Stamp","Reactor Temperature Corrected"]:
			if subdev_configs[subdev]["Analysis Device Type"] == "Flow":
				df[subdev+ " corrected"] = df[subdev]/subdev_configs[subdev]["Correction Factor"]
				flow_subdevs.append(subdev)

	#Get Total Flow
	df["Total Flow"] = 0
	for subdev in flow_subdevs:
		df["Total Flow"] += df[subdev+ " corrected"]

	#Get percent for each reactant
	for subdev in flow_subdevs:
		df[subdev+" percent"] = df[subdev+" corrected"] / df["Total Flow"] * 100

	#Identify major reactant
	major_reactant = None
	for subdev in flow_subdevs:
		if subdev_configs[subdev]["Major Reactant"] == "True":
			major_reactant = subdev
			break



	#Categorize the entries
	type_arr = []
	df = df.reset_index()
	for i, row in df.iterrows():
	    if df[major_reactant][i] < 0.1: 
	    	type_arr.append("Unanalyzed") #Unanalyzed -> No major reactant found
	    else:
	    	if df["Reactor Temperature Corrected"][i] < 200:
	    		type_arr.append("Bypass") #Bypass -> T < 200C
	    	else:
	    		type_arr.append("Reaction")
	df["Type"] = type_arr

	#sort values (Type --> Temperature --> Flow)
	df.sort_values(by=["Type","Reactor Temperature Corrected","Total Flow","GC Time Stamp"]) #sorts it into BP, Rxn, Unanalyzed


	#Rename MFCs so no naming conflicts
	df.rename(columns={i : i+" Flow" for i in flow_subdevs}, inplace=True)

	#Get GC Data
	gc_areas = {}
	gc_rts = {}
	df = df.reset_index()
	for i, row in df.iterrows():
		if df["Type"][i] != "Unanalyzed":
			run_id = row["GC Run ID"]
			gc_data = get_run_data(run_id)
			#time.sleep(2)
			gc_detector_data = gc_data["detectors"]
			for detector in ["moduleA:tcd","moduleB:tcd","moduleC:tcd"]:
				peaks = gc_detector_data[detector]["analysis"]["peaks"]
				for peak in peaks:
					if "label" not in peak.keys(): #the gc data reports peaks that aren't named as well. skip those
						pass
					else:
						if peak["label"] not in gc_areas.keys(): #if it's the first time we've run across this species
							gc_areas[peak["label"]] = [peak["area"]]
							gc_rts[peak["label"]] = [peak["top"]]
						else: #otherwise just append
							gc_areas[peak["label"]].append(peak["area"])
							gc_rts[peak["label"]].append(peak["top"])

	#add GC data to arrays\
	for species in gc_areas.keys():
		df[species] = gc_areas[species]
		df[species+" RT"] = gc_rts[species]


	prev_flows = None
	prev_temp = None

	#todo: only keep last 3 of each one
















