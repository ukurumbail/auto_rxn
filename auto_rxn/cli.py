"""Console script for auto_rxn."""
import os
import json
import click
import shutil
import pathlib
import auto_rxn
import pandas as pd
import postrun_analysis
@click.command()
@click.option('--recipe_file',default=None,help='Filename for reaction input file utilized by rxn control.')
@click.option('--settings_file', default='rxn_control_config.json', help='Filename for settings file utilized by rxn control.')
@click.option('--recipe_directory',default='input_files',help='Directory for reaction input file utilized by rxn control.')
@click.option('--settings_directory', default='config_files', help='Directory for settings file utilized by rxn control.')
@click.option('--storage_directory', default='../rxn_files', help='Directory to store all outputs in.')
@click.option('--rxn_name', default='None', help='This name will be utilized to create a subdirectory for your reaction files.') #prompt='Name for reaction'
@click.option('--run_or_analyze',default="run",help="Choose whether to run a new reaction ('run'), analyze a previous reaction ('analyze'), or just dump gc data from a previous reaction ('just dump').")

def main(recipe_file,settings_file,recipe_directory,settings_directory,storage_directory,rxn_name,run_or_analyze):
	"""Console script for auto_rxn."""

	if run_or_analyze == "analyze" or run_or_analyze == "just dump":
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
		if run_or_analyze == "just dump":
			postrun_analysis.analyze(rxn_dirname,settings_dirname,just_dump=True)
		else:
			postrun_analysis.analyze(rxn_dirname,settings_dirname,just_dump=False)


	elif run_or_analyze == "run":
		dirname = pathlib.Path.cwd()

		#create new rxn folder
		click.echo('Checking for existing folder with that name...')
		folder_created = False
		while not folder_created:
			print(dirname,storage_directory)
			full_storage_dirname = os.path.join(dirname, storage_directory)
			rxn_dirname = os.path.join(full_storage_dirname,rxn_name)
			if os.path.isdir(rxn_dirname):
				click.echo('Directory already exists, please enter new rxn_name. Selected directory name: {}'.format(rxn_dirname))
				rxn_name = input("Enter new reaction name here: ")
				rxn_dirname = os.path.join(full_storage_dirname,rxn_name)
				pass
			else:
				os.mkdir(rxn_dirname)
				folder_created=True

		click.echo('Subdirectory successfully created.')

		#copy settings and recipe files over to new directory
		settings_dirname = os.path.join(dirname, settings_directory) #turn relative path into absolute path
		settings_file_full = os.path.join(settings_dirname, settings_file) #turn relative path into absolute path
		shutil.copy2(settings_file_full,rxn_dirname)

		if recipe_file is None :
			raise ValueError("Must include a recipe file name")
		recipe_dirname = os.path.join(dirname, recipe_directory) #turn relative path into absolute path
		recipe_file_full = os.path.join(recipe_dirname, recipe_file) #turn relative path into absolute path
		shutil.copy2(recipe_file_full,rxn_dirname)


		#load config/settings and recipe (params / setpoints)
		with open(settings_file_full, 'r') as f:
			settings_json = json.load(f)
		inputs_df = pd.read_csv(recipe_file_full)

		#initialize and begin reaction
		auto_rxn.run_rxn(inputs_df,settings_json,rxn_name,rxn_dirname)
	else:
		raise ValueError("Values for run_or_analyze parameter must be 'run', 'analyze', or 'just dump'.")


if __name__ == "__main__":
	main()

