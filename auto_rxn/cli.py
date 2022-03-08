"""Console script for auto_rxn."""
import os
import click
import auto_rxn
import pandas as pd
from tkinter.filedialog import askopenfilename

@click.command()
@click.option('--input_file',default=None,help='Filepath for reaction input file utilized by rxn control.')
@click.option('--settings_file', default='../config_files/rxn_control_settings.csv', help='Filepath for settings file utilized by rxn control.')
@click.option('--storage_directory', default='../rxn_files/', help='Directory to store all outputs in.')
@click.option('--rxn_name', prompt='Name for reaction', help='This name will be utilized to create a subdirectory for your reaction files.')
def main(input_file,settings_file,storage_directory,rxn_name):
	"""Console script for auto_rxn."""
	dirname = os.path.dirname(__file__)

	#create new rxn folder
	click.echo('Checking for existing folder with that name...')
	folder_created = False
	while not folder_created:
		rxn_dirname = os.path.join(dirname, storage_directory)
		rxn_dirname = os.path.join(rxn_dirname,rxn_name)
		if os.path.isdir(rxn_dirname):
			click.echo('Directory already exists, please enter new rxn_name. Selected directory name: {}'.format(rxn_dirname))
			rxn_name = input("Enter new reaction name here: ")
		else:
			os.mkdir(rxn_dirname)
			folder_created=True

	#generate settings and input files
	click.echo('Subdirectory successfully created.')
	settings_file = os.path.join(dirname, settings_file) #turn relative path into absolute path
	if input_file is None:
		input_file= askopenfilename(initialdir="../input_files",title="Select Reaction Inputs File",filetypes=[("CSV", "*.csv")])
	inputs_df = pd.read_csv(input_file)
	settings_df = pd.read_csv(settings_file,dtype=str)

	#select whether to access gc or not
	response = ''
	while response not in ["yes","no"]:
		response = input("Use GC? (yes/no): ")
	if response == "no":
		use_gc = False
	elif response == "yes":
		use_gc = True
	else:
		raise NotImplementedError()

	#initialize and begin reaction
	auto_rxn.run_rxn(inputs_df,settings_df,rxn_name,rxn_dirname,use_gc)


if __name__ == "__main__":
	main()

