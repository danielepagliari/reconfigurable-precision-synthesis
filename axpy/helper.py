"""
Container for axpy helper functions

"""
import os
import re

# convert voltage float value to string in STM format
def voltage_to_string(v: float) -> str:
    if v < 0:
        return "m{:.2f}".format(abs(v))
    else:
        return "{:.2f}".format(v)

# read csh environment setup script and replicate its behavior
def set_csh_env(filename: str):
    with open(filename, "r") as f:
        for l in f.readlines():
            if re.match("setenv", l):
                w = l.split()
                # TODO: make safer
                val = os.path.expandvars(w[2])
                # previous command makes sure that the value uses other env
                # variables as such and not as literals
                os.environ[w[1]] = val
    return
