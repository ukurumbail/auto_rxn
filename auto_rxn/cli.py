"""Console script for auto_rxn."""
import os
import json
import click
import shutil
import pathlib
import auto_rxn
import pandas as pd
import postrun_analysis
from optparse import OptionParser
@click.command()
@click.option('--recipe_file',default=None,help='Filename for reaction input file utilized by rxn control.')
@click.option('--settings_file', default='rxn_control_config.json', help='Filename for settings file utilized by rxn control.')
@click.option('--recipe_directory',default='input_files',help='Directory for reaction input file utilized by rxn control.')
@click.option('--settings_directory', default='config_files', help='Directory for settings file utilized by rxn control.')
@click.option('--storage_directory', default='../rxn_files', help='Directory to store all outputs in.')
@click.option('--rxn_name', help='This name will be utilized to create a subdirectory for your reaction files.') #prompt='Name for reaction'
@click.option('--run_or_analyze',default="run",help="Option is 'run' to run a reaction, 'analyze' to analyze an already-ran rxn, 'analyze_6flow' to do 6flow processing, or 'just_dump' to just get all the formatted gc data.")
def main(recipe_file,settings_file,recipe_directory,settings_directory,storage_directory,rxn_name,run_or_analyze):
	"""Console script for auto_rxn."""
	if run_or_analyze == "analyze" or run_or_analyze == "just_dump" or run_or_analyze == "analyze_6flow":
		dirname = pathlib.Path.cwd()

		rxn_dirname = os.path.join(dirname, storage_directory)
		rxn_dirname = os.path.join(rxn_dirname,rxn_name)

		settings_dirname = os.path.join(dirname, settings_directory) #turn relative path into absolute path

		if os.path.isdir(rxn_dirname) and rxn_name != 'None':
			pass
		else:
			pass
			raise ValueError("Reaction not found at location: {}. Or rxn_name not entered".format(rxn_dirname))

		click.echo('Found reaction. Beginning analysis.')
		if run_or_analyze == "just_dump":
			postrun_analysis.analyze(rxn_dirname,settings_dirname,just_dump=True,six_flow=False)
		elif run_or_analyze == "analyze_6flow":
			postrun_analysis.analyze(rxn_dirname,settings_dirname,just_dump=True,six_flow=True)
		else:
			postrun_analysis.analyze(rxn_dirname,settings_dirname,just_dump=False,six_flow=False)
	if run_or_analyze == "run":
		dirname = pathlib.Path.cwd()
		print(dirname,storage_directory)
		full_storage_dirname = os.path.join(dirname, storage_directory)
		#create new rxn folder
		if rxn_name is None:
			rxn_name = input("Enter name for reaction subdirectory: ")
			rxn_dirname = os.path.join(full_storage_dirname,rxn_name)
			if os.path.isdir(rxn_dirname):
				valid_dirname = False
				while not valid_dirname:
					click.echo('Directory already exists, please enter new rxn_name. Selected directory name: {}'.format(rxn_dirname))
					rxn_name = input("Enter new reaction name here: ")
					rxn_dirname = os.path.join(full_storage_dirname,rxn_name)
					if os.path.isdir(rxn_dirname):
						valid_dirname = False
					else:
						valid_dirname = True
		else:
			rxn_dirname = os.path.join(full_storage_dirname,rxn_name)
			if os.path.isdir(rxn_dirname):
				valid_dirname = False
				while not valid_dirname:
					click.echo('Directory already exists, please enter new rxn_name. Selected directory name: {}'.format(rxn_dirname))
					rxn_name = input("Enter new reaction name here: ")
					rxn_dirname = os.path.join(full_storage_dirname,rxn_name)

					if os.path.isdir(rxn_dirname):
						valid_dirname = False
					else:
						valid_dirname = True


		if recipe_file is None :
				raise ValueError("Must include a recipe file name")


		dirname = pathlib.Path.cwd()
		recipe_dirname = os.path.join(dirname, recipe_directory) #turn relative path into absolute path
		recipe_file_full = os.path.join(recipe_dirname, recipe_file) #turn relative path into absolute path


		#print the recipe file
		df = pd.read_csv(recipe_file_full)
		print(df.to_string())

		click.echo('Here is the data from the input file. Is this correct?')
		response = False
		while not response:
			yes_or_no = input("Yes or no: ")
			if yes_or_no == "yes" or yes_or_no == "Yes" or yes_or_no == "y" or yes_or_no == "Y" or yes_or_no == "correct":
				response = True
			else: 
				print("Terminating program")
				exit()


		#copy settings and recipe files over to new directory
		settings_dirname = os.path.join(dirname, settings_directory) #turn relative path into absolute path
		settings_file_full = os.path.join(settings_dirname, settings_file) #turn relative path into absolute path




		#load config/settings and recipe (params / setpoints)
		with open(settings_file_full, 'r') as f:
			settings_json = json.load(f)
			inputs_df = pd.read_csv(recipe_file_full)


		#Make sure that the user knows whether the reaction is a mock
		true_values = ["True","true","T"]
		false_values = ["False","false","F"]
		yes_values = ["yes","Yes","y","Y",]
		if settings_json["main"]["mock"] in true_values:
			proceed_or_quit = input("This is a mock reaction. Are you sure you want to proceed? ")
			if proceed_or_quit in yes_values:
				mock=True
				pass
			else:
				print("Aborting")
				quit()

		elif settings_json["main"]["mock"] in false_values:
			mock = False
			pass

		else:
			print("Aborting program! Mock parameter in config file must be a value in {} or {}".format(true_values,false_values))
			quit()

		#initialize and begin reaction


		os.mkdir(rxn_dirname)
		shutil.copy2(settings_file_full,rxn_dirname)
		shutil.copy2(recipe_file_full,rxn_dirname)
		click.echo('Subdirectory successfully created and populated.')


		auto_rxn.run_rxn(inputs_df,settings_json,rxn_name,rxn_dirname,mock)

if __name__ == "__main__":
	main()

