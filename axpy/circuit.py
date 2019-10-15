from enum import Enum
from typing import Dict, Tuple

class AxCircuit(object):
    """
    Container for an approximate (energy/accuracy scalable) circuit

    """

    class PortDirection(Enum):
        INPUT = 1
        OUTPUT = 2

    class DuplicatePortException(Exception):
        pass

    class UnknownPortException(Exception):
        pass

    def __init__(self, input_ports: Dict[str, int] = dict(), output_ports: Dict[str, int] = dict(), port_multipliers: Dict[str, int] = dict()):
        self.input_ports = input_ports
        self.output_ports = output_ports
        for name in port_multipliers.keys():
            if name not in self.input_ports and name not in self.output_ports:
                raise AxCircuit.UnknownPortException("No port with name {}".format(name))
        self.port_multipliers = port_multipliers
        return

    def add_port(self, name: str, width: int, direction: 'AxCircuit.PortDirection', multiplier: int = 1):
        if direction == AxCircuit.PortDirection.INPUT:
            if name in self.input_ports:
                raise AxCircuit.DuplicatePortException("An input port with name {} already exists".format(name))
            self.input_ports[name] = width
        else:
            if name in self.output_ports:
                raise AxCircuit.DuplicatePortException("An output port with name {} already exists".format(name))
            self.output_ports[name] = width
        return

    def change_port_width(self, name: str, width: int):
        if name not in self.input_ports and name not in self.output_ports:
            raise AxCircuit.UnknownPortException("No port with name {}".format(name))
        if name in self.input_ports:
            self.input_ports[name] = width
        elif name in self.output_ports:
            self.output_ports[name] = width
        return

    def change_port_multiplier(self, name: str, multiplier: int):
        if name not in self.input_ports and name not in self.output_ports:
            raise AxCircuit.UnknownPortException("No port with name {}".format(name))
        self.port_multipliers[name] = multiplier
        return

    def remove_port(self, name: str):
        if name not in self.input_ports and name not in self.output_ports:
            raise AxCircuit.UnknownPortException("No port with name {}".format(name))
        if name in self.input_ports:
            del self.input_ports[name]
        elif name in self.output_ports:
            del self.output_ports[name]
        if name in self.port_multipliers:
            del self.port_multipliers[name]
        return

    def duplicate(self):
        new = AxCircuit(self.input_ports.copy(), self.output_ports.copy(), self.port_multipliers.copy())
        return new

    @property
    def tcl_description(self) -> str:
        _cmd = "set IN_PORTS { "
        for n, w in self.input_ports.items():
            m = 1 if n not in self.port_multipliers else self.port_multipliers[n]
            _cmd += "{{\"{}\" {} {}}} ".format(n, w, m)
        _cmd += "};"
        _cmd += "set OUT_PORTS { "
        for n, w in self.output_ports.items():
            m = 1 if n not in self.port_multipliers else self.port_multipliers[n]
            _cmd += "{{\"{}\" {} {}}} ".format(n, w, m)
        _cmd += "};"
        return _cmd

    def __str__(self) -> str:
        _str = "AxCircuit["
        for n, w in self.input_ports.items():
            m = 1 if n not in self.port_multipliers else self.port_multipliers[n]
            _str += ", Input {}: {} bit, multiplier: {}".format(n, w, m)
        for n, w in self.output_ports.items():
            m = 1 if n not in self.port_multipliers else self.port_multipliers[n]
            _str += ", Output {}: {} bit, multiplier: {}".format(n, w, m)
        _str += "]"
        return _str

    def __repr__(self) -> str:
        return self.__str__()

