import json
import configparser
import os
import shutil
import subprocess

from typing import List, Tuple

from axpy.circuit  import AxCircuit
from axpy.scenario import AxScenario
from axpy.helper   import voltage_to_string


class ReconfSynthesis(object):
    """
    Code to run reconfigurable-precision synthesis in DC

    """

    # exceptions thrown
    class TimingException(Exception):
        pass
    class PowerCalcException(Exception):
        pass
    class ConfigException(Exception):
        pass

    # directory configurations
    DEFAULT_LOG_DIR = 'log'
    DEFAULT_WORK_DIR = 'work_reconf'
    LOG_REDIRECT = True
    DELETE_DATA  = False

    def __init__(self, log_dir: str = DEFAULT_LOG_DIR, work_dir: str = DEFAULT_WORK_DIR):
        self.log_dir            = log_dir
        self.work_dir           = work_dir
        self._weights           = None
        self._circuit           = None
        self._vdd_list          = None
        self._acc_list          = None
        self._clock_multipliers = None
        self._mode_inputs       = None
        self._mode_values       = None
        self._power_table       = None
        self._scen_table        = None
        return

    ################################################################################
    # read configuration file
    ################################################################################
    def read_config(self, filename: str):

        config = configparser.ConfigParser()
        # to have case sensitive keys
        config.optionxform = str
        config.read(filename)

        ip = dict(config['Input Ports'])
        op = dict(config['Output Ports'])
        pm = dict(config['Port Multipliers'])
        self._circuit = AxCircuit(
                input_ports=ip,
                output_ports=op,
                port_multipliers=pm,
                )

        self._vdd_list = [float(_) for _ in json.loads(config['Scenarios']['vdd'])]
        self._acc_list = [int(_) for _ in json.loads(config['Scenarios']['precision'])]

        #clock period multipliers for different accuracies (for DVAFS)
        if 'clock_multipliers' in config['Scenarios']:
            self._clock_multipliers = json.loads(config['Scenarios']['clock_multipliers'])
        else:
            self._clock_multipliers = [None for _ in self._acc_list]

        #explicit mode inputs (for DVAFS)
        if 'mode_inputs' in config['Scenarios']:
            self._mode_inputs = json.loads(config['Scenarios']['mode_inputs'])
            self._mode_values = json.loads(config['Scenarios']['mode_values'])
            # convert strings to int
            for i in range(len(self._mode_values)):
                for j in range(len(self._mode_values[i])):
                    self._mode_values[i][j] = int(self._mode_values[i][j])
            self._check_mode_inputs()

        if 'weights' in config['Scenarios']:
            tmp_w = json.loads(config['Scenarios']['weights'])
            if len(tmp_w) != len(self._acc_list):
                raise ReconfSynthesis.ConfigException("Wrong number of precision weights!");
            self._weights = tmp_w
        else:
            print("[Reconf] Info: Using default weight for all accuracies: 1.0");
            self._weights = [1] * len(self._acc_list)

        return

    ################################################################################
    # Synthesize Reconf netlist finding best voltage for each scenario
    ################################################################################
    def run(self, output_dir: str, output_table: str = None) -> 'List[Tuple[float,AxScenario]]':

        # initialize work and output directories
        self._init_dirs(output_dir, output_table)

        # sort precision (largest value is assumed as nominal)
        sorted_idx = sorted(range(len(self._acc_list)),
                key=lambda _: self._acc_list[_], reverse = True)

        self._acc_list = [self._acc_list[_] for _ in sorted_idx]
        if self._mode_values is not None:
            self._mode_values = [self._mode_values[_] for _ in sorted_idx]

        # sort voltages (largest value is assumed as nominal)
        self._vdd_list.sort(reverse = True)

        # initialize power and scenario table to None
        self._scen_table  = { _ : None for _ in self._acc_list}
        self._power_table  = { _ : None for _ in self._acc_list}

        # create nominal scenario
        nom_mode = self._create_mode(0)
        nom_scenario = AxScenario(
                self._acc_list[0],
                self._vdd_list[0],
                self._clock_multipliers[0],
                nom_mode)

        # run first (nominal synthesis)
        print("[Reconf] Running nominal synthesis with scenario:", nom_scenario)
        power, ok = self._call_dc(add_scenario = nom_scenario)
        print("[Reconf] Power:", power, "(Total:", self._weighted_total_power(power), ") Compliant:", ok)
        if not ok:
            raise ReconfSynthesis.TimingException("Cannot close timing on nominal condition synthesis")

        # save nominal scenario
        self._scen_table[self._acc_list[0]] = nom_scenario

        # optimize voltage for all other accuracies
        curr_vdd_id = 0
        for curr_acc_id in range(1,len(self._acc_list)):
            curr_mode = self._create_mode(curr_acc_id)
            # initially consider same voltage of previous precision
            curr_scenario = AxScenario(
                    self._acc_list[curr_acc_id],
                    self._vdd_list[curr_vdd_id],
                    self._clock_multipliers[curr_acc_id],
                    curr_mode)
            print("[Reconf] Running synthesis with new scenario:", curr_scenario)
            curr_power, ok = self._call_dc(add_scenario = curr_scenario)
            curr_tot_power = self._weighted_total_power(curr_power)
            print("[Reconf] Power:", curr_power, "(Total:", curr_tot_power, ") Compliant:", ok)
            if not ok:
                raise ReconfSynthesis.TimingException("Timing error when adding smaller precision, at same voltage")

            for new_vdd_id in range(curr_vdd_id + 1, len(self._vdd_list)):
                new_scenario = AxScenario(
                        self._acc_list[curr_acc_id],
                        self._vdd_list[new_vdd_id],
                        self._clock_multipliers[curr_acc_id],
                        curr_mode)
                print("[Reconf] Running synthesis with new scenario:", new_scenario)
                new_power, ok = self._call_dc(add_scenario = new_scenario)
                new_tot_power = self._weighted_total_power(new_power)
                print("[Reconf] Power:", new_power, "(Total:", new_tot_power, ") Compliant:", ok)

                if ok and new_tot_power <= curr_tot_power:
                    curr_power = new_power
                    curr_tot_power = new_tot_power
                    curr_scenario = new_scenario
                    curr_vdd_id = new_vdd_id
                else:
                    break

            # save best for this precision
            self._scen_table[self._acc_list[curr_acc_id]] = curr_scenario

        # save final power
        self._power_table = {i : j for i, j in zip(self._acc_list, curr_power)}

        # output on screen final best result
        print("[Reconf] Final Best Solution:")
        for a in self._acc_list:
            print("\tScenario:", self._scen_table[a], "Power:", self._power_table[a])

        # write final output table
        if output_table is not None:
            with open(output_table, "w") as f:
                for a in self._acc_list:
                    print(a, self._power_table[a], self._scen_table[a].vdd, file=f)

        # write final netlist
        self._save_netlist(output_dir)

        # return (power, scenario) tuple for each precision
        return [(self._power_table[_], self._scen_table[_]) for _ in self._acc_list]

    ################################################################################
    # call Design Compiler to synthesize scenarios
    ################################################################################
    def _call_dc(self, add_scenario: 'AxScenario' = None) -> Tuple[List[float], bool]:

        scen_comb_name = self._combined_scenario_name(add_scenario = add_scenario)
        log_file = "{}/{}.log".format(self.log_dir, scen_comb_name)
        data_file = "{}/{}.dat".format(self.work_dir, scen_comb_name)
        netlist_file = "{}/{}.v".format(self.work_dir, scen_comb_name)
        sdc_file = "{}/{}.sdc".format(self.work_dir, scen_comb_name)
        spef_file = "{}/{}.spef".format(self.work_dir, scen_comb_name)

        _cmd = self._circuit.tcl_description
        _cmd += "set TARGET_SCENARIOS { " + self._combined_scenario_desc(add_scenario = add_scenario) + " } ;"
        _cmd += "set OUT_FILE {};".format(data_file)
        _cmd += "set NETLIST_FILE {};".format(netlist_file)
        _cmd += "set SDC_FILE {};".format(sdc_file)
        _cmd += "set SPEF_FILE {};".format(spef_file)
        _cmd += "source custom_dc_scripts/ax/reconf/reconf_synth.tcl;"

        _call_arg = ["dc_shell-xg-t", "-topo", "-x", _cmd]
        if ReconfSynthesis.LOG_REDIRECT:
            with open(log_file, "w") as flog:
                subprocess.call(_call_arg, stdout=flog)
        else:
            subprocess.call(_call_arg)

        # parse output
        power, ok = self._parse_data(data_file)

        if ReconfSynthesis.DELETE_DATA:
            os.unlink(data_file)

        return (power, ok)

    ################################################################################
    # create needed directories
    ################################################################################
    def _init_dirs(self, output_dir: str, output_table: str):
        out_tab_dir = os.path.dirname(output_table)
        if out_tab_dir != "" and not os.access(out_tab_dir, os.W_OK):
            raise FileNotFoundError("Cannot access directory \"" + out_tab_dir + "\" for writing!");
        if ReconfSynthesis.LOG_REDIRECT and not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)
        else:
            shutil.rmtree(self.work_dir)
            os.makedirs(self.work_dir)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        return

    ################################################################################
    # parse primetime output
    ################################################################################
    def _parse_data(self, filename: str) -> Tuple[List[float], bool]:
        with open(filename, "r") as f:
            l = f.readlines()[0]
            w = l.split()
            power = [float(_) for _ in w[:-1]]
            ok = True if int(w[-1]) == 1 else False
        return (power, ok)

    ################################################################################
    # combine scenario names
    ################################################################################
    def _combined_scenario_name(self, add_scenario: 'AxScenario' = None):
        _str = "_".join([_.name for _ in self._scen_table.values() if _ is not None])
        _str += "" if add_scenario is None else "_" + add_scenario.name
        return _str

    ################################################################################
    # combine scenario TCL descriptions
    ################################################################################
    def _combined_scenario_desc(self, add_scenario: 'AxScenario' = None):
        _str = " ".join([_.tcl_description for _ in self._scen_table.values() if _ is not None])
        _str += "" if add_scenario is None else " " + add_scenario.tcl_description
        return _str

    ################################################################################
    # compute weighted total power (can be classmethod)
    ################################################################################
    def _weighted_total_power(self, power: List[float]):
        # extract the first weights
        weights = self._weights[:len(power)]
        return sum([ i * j for i, j in zip(power, weights)])

    ################################################################################
    # combine scenario TCL descriptions
    ################################################################################
    def _save_netlist(self, output_dir: str):
        scen_comb_name = self._combined_scenario_name()
        src_netlist = "{}/{}.v".format(self.work_dir, scen_comb_name)
        dst_netlist = "{}/{}.v".format(output_dir, scen_comb_name)
        shutil.copyfile(src_netlist, dst_netlist)
        src_sdc = "{}/{}.sdc".format(self.work_dir, scen_comb_name)
        dst_sdc = "{}/{}.sdc".format(output_dir, scen_comb_name)
        shutil.copyfile(src_sdc, dst_sdc)
        src_spef = "{}/{}.spef".format(self.work_dir, scen_comb_name)
        dst_spef = "{}/{}.spef".format(output_dir, scen_comb_name)
        shutil.copyfile(src_spef, dst_spef)
        return

    ################################################################################
    # check configuration relative to  mode inputs/values
    ################################################################################
    def _check_mode_inputs(self):
        if self._mode_inputs is None:
            return
        if len(self._acc_list) != len(self._mode_values):
            raise ReconfSynthesis.ConfigException(
                "Precision list and mode values list should have same length")
        for m in self._mode_values:
            if len(m) != len(self._mode_inputs):
                raise ReconfSynthesis.ConfigException(
                    "Each mode values sublist should match the mode inputs length")
            for v in m:
                if v != 0 and v != 1:
                    raise ReconfSynthesis.ConfigException(
                        "Valid mode values are 0 and 1")

    ################################################################################
    # create "mode" (list of signal names/values tuples) for the target precision
    ################################################################################
    def _create_mode(self, precision_index: int) -> List[Tuple[str, int]]:
        if self._mode_inputs is not None:
            mode = [(self._mode_inputs[_], self._mode_values[precision_index][_])
                    for _ in range(len(self._mode_inputs))]
        else:
            mode = None
        return mode

    def __str__(self) -> str:
        _str = "Reconf Synthesis Launcher"
        return _str

    def __repr__(self) -> str:
        return self.__str__()
