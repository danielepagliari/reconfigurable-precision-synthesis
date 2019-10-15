from axpy.helper import voltage_to_string
from typing import List

class AxScenario(object):

    def __init__(self, accuracy: int, vdd: float,
            clock_multiplier: float = None,
            mode_signals: 'List[Tuple[str,int]]' = None):
        self.accuracy = accuracy
        self.vdd = vdd
        self.clock_multiplier = clock_multiplier
        self.mode_signals = mode_signals
        return

    def duplicate(self):
        new = AxScenario(
                self.vdd,
                self.accuracy,
                self.clock_multiplier,
                self.mode_signals)
        return new

    @property
    def name(self) -> str:
        _str = 'acc_{}bit_vdd_{}V'.format(
                self.accuracy,
                voltage_to_string(self.vdd)
                )
        return _str

    @property
    def tcl_description(self) -> str:
        _cmd = "{{ {} {}".format(
                self.accuracy,
                voltage_to_string(self.vdd)
                )
        if self.clock_multiplier is not None:
            _cmd += " {}".format(self.clock_multiplier)
        if self.mode_signals is not None:
            for (n, v) in self.mode_signals:
                _cmd += " {{ {} {} }} ".format(n, v)
        _cmd += "}"
        return _cmd

    def __str__(self) -> str:
        _str = "AxScenario[Accuracy: {} bit, VDD: {}V]".format(
                self.accuracy,
                voltage_to_string(self.vdd)
                )
        return _str

    def __repr__(self) -> str:
        return self.__str__()

