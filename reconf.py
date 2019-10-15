#!/usr/bin/env python

################################################################################
# Launch reconfig-precision synthesis
################################################################################
import argparse as ap

from axpy.reconf.reconf import ReconfSynthesis
from axpy.helper import set_csh_env

# parse Arguments
parser = ap.ArgumentParser()
parser.add_argument('-c', '--config',
    help='Path to configuration file', required=True)
parser.add_argument('-od', '--output_directory',
    help='Output directory for netlist and sdc', required=True)
parser.add_argument('-ot', '--output_table',
    help='Output table with best scenarios', required=True)
args = vars(parser.parse_args())

# set environment
set_csh_env("DC-RM_env.csh")

# run analysis
engine = ReconfSynthesis()
engine.read_config(args['config'])
engine.run(output_dir = args['output_directory'], output_table = args['output_table'])
