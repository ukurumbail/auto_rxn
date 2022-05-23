import pandas as pd
import numpy as np
import json
import time
import os
import shutil
from openpyxl import load_workbook

def get_run_data(run_id):
	with open("./auto_rxn/bp_json.json",'r') as f:
		bp_json = json.load(f)
	return bp_json

def analyze(rxn_dirname,settings_dirname):
	#takes in the directory for a reaction and produces an analysis

	rxn_name = rxn_dirname.split('\\')[-1]
	gc_logfile_string = "gc_log_"+rxn_name
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






	#select and group bypass runs by input values

	sorted_rows = {}
	flow_pcts = {}
	idx = 0

	df_bypass = df.loc[df['Type'] == "Bypass"]
	#sort values (Type --> Total Flow --> Time for sorted_rows)
	df_bypass.sort_values(by=["Total Flow","GC Time Stamp"]) #sorts it into BP, Rxn, Unanalyzed



	for i, row in df_bypass.iterrows(): #for each bypass entry
		row_flow_pcts = {sub+" percent" : row[sub+" percent"] for sub in flow_subdevs}
		is_same_flow_pcts = False
		for key in sorted_rows.keys(): #iterate through existing sets of flow percentages
			if np.allclose(list(flow_pcts[key]),list(row_flow_pcts.values())): #if all flow percentages are the same as an existing entry
				is_same_flow_pcts = True
				is_same_flow_tot = False #now try and find the correct flowrate
				for flow_key in sorted_rows[key][-999].keys():
					if np.isclose([flow_key],[row["Total Flow"]]):
						sorted_rows[key][-999][flow_key].append(row)
						is_same_flow_tot = True
					else:
						pass
				if is_same_flow_tot:
					pass 
				else: #found the right flow percentages but haven't yet found an entry with the same flowrate. Make a new one
					sorted_rows[key][-999][row["Total Flow"]] = [row]
			else:
				pass


		if is_same_flow_pcts: #the new row has the same flow percentages as an existing row. i.e. it belongs in the same bypass file
			pass

		else: #totally new bypass file should be made for this entry.
			sorted_rows[idx] = {-999:{row["Total Flow"]:[row]}} #-999 corresponds to bypass
			flow_pcts[idx] = row_flow_pcts.values()
			idx += 1

	#Now repeat for the different reaction flows
	df_rxn = df.loc[df['Type'] == "Reaction"]

	df_rxn.sort_values(by=["Type","Reactor Temperature Corrected","Total Flow","GC Time Stamp"]) 

	for i, row in df_rxn.iterrows(): #for each bypass entry
		row_flow_pcts = {sub+" percent" : row[sub+" percent"] for sub in flow_subdevs}
		my_idx = None
		for key in sorted_rows.keys():
			if np.allclose(list(flow_pcts[key]),list(row_flow_pcts.values())):
				my_idx = key
				break

		T_exists = False
		
		for T in sorted_rows[my_idx].keys():
			if np.isclose([row["Reactor Temperature Corrected"]],[T]):
				T_exists = True
				Flow_exists = False
				for flow in sorted_rows[my_idx][T].keys():
					if np.isclose([flow],row["Total Flow"]):
						sorted_rows[my_idx][T][flow].append(row)
						Flow_exists = True

				if not Flow_exists:
					sorted_rows[my_idx][T][row["Total Flow"]] = [row]

		if not T_exists:
			sorted_rows[my_idx][row["Reactor Temperature Corrected"]] = {row["Total Flow"] : [row]}



	#only keep last 3 of each set of data
	for (idx, dataset) in sorted_rows.items():
		for (T,rowset) in dataset.items():
			for (flow,rows) in rowset.items():
				sorted_rows[idx][T][flow] = rows[-3:]

	#Now begin writing to files
	for (idx,dataset) in sorted_rows.items():
		
		#Creating copy of analysis file
		filestr = rxn_dirname + "\\" + rxn_name+ "_Analysis" 
		for species, pct in zip(flow_subdevs,flow_pcts[idx]):
			pct = round(pct)
			filestr += "_"
			filestr +=species
			filestr +="-"
			filestr += str(pct) 
		filestr += ".xlsx"
		print(filestr)
		shutil.copy2(settings_dirname+"\\AnalysisTemplate.xlsx",filestr)

		#Constructing new dataframe to add to template
		df = pd.DataFrame(columns = df_bypass.columns)
		bypass_flow_rates = []
		bypasses_added = 0

		for (key,val) in dataset.items():
			if key == -999: #bypass
				for (flow,rows) in val.items():
					bypass_flow_rates.append(flow)
					df = pd.concat([df,pd.DataFrame(rows)])
					bypasses_added += len(rows)

		blank_rows_needed = 21 - bypasses_added

		#add blank bypass rows
		blank_df = []
		for i in range(blank_rows_needed):
			blank_df.append([None for i in df.columns])
		blank_df=pd.DataFrame(blank_df,columns=df.columns)
		df=pd.concat([df,blank_df])


		#now add rxn rows
		for (key,val) in dataset.items():
			if key != -999: #skip bypass rows
				rows_added = 0
				for i,(flow,rows) in enumerate(val.items()):
					curr_bp_flow = bypass_flow_rates[i]
					if flow == curr_bp_flow:
						df = pd.concat([df,pd.DataFrame(rows,columns=df.columns)])
					else:
						blank_df = []
						for i in range(3):
							blank_df.append([None for i in df.columns])
						blank_df=pd.DataFrame(blank_df,columns=df.columns)
						df=pd.concat([df,blank_df])
					i +=1
					rows_added += 3

				#make up the rest of the rows with blanks	
				blank_df = []
				for i in range(21-rows_added):
					blank_df.append([None for i in df.columns])
				blank_df=pd.DataFrame(blank_df,columns=df.columns)
				df=pd.concat([df,blank_df])
				rows_added = 0
				i = 0 


		#https://stackoverflow.com/questions/42370977/how-to-save-a-new-sheet-in-an-existing-excel-file-using-pandas
		book = load_workbook(filestr)
		writer = pd.ExcelWriter(filestr, engine = 'openpyxl')
		writer.book = book
		df = df.drop(['level_0','index'],axis=1)
		df.to_excel(writer, sheet_name = 'gc_data_from_prog',index=False)
		print("Printed to Analysis Template")
		writer.save()
		writer.close()



















