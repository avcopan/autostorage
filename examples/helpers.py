"""examples helpers."""

import re

import pyparsing as pp
from pyparsing import pyparsing_common as ppc


def orca_parse_zpe(text_block: str) -> float:
    """Parse zero point energy from orca stdout."""
    match = re.search(r"Zero point energy\s+\.\.\.\s+([\d\.]+)\s+Eh", text_block)

    if match:
        return float(match.group(1))

    msg = "Zero point energy line could not be parsed."
    raise ValueError(msg)


INTEGER = ppc.integer.set_parse_action(lambda t: int(t[0]))
FLOAT_NUMBER = ppc.sci_real.set_parse_action(lambda t: float(t[0]))


def orca_parse_gradient(text_block: str) -> list[float]:
    """Parse energy gradient from orca .engrad."""
    header = (
        pp.Literal("# The current gradient in Eh/bohr")
        + pp.LineEnd()
        + pp.Literal("#")
        + pp.LineEnd()
    )
    footer = pp.Literal("#")

    gradient_parser = (
        pp.SkipTo(header) + header + pp.OneOrMore(FLOAT_NUMBER)("values") + footer
    )

    results = gradient_parser.parse_string(text_block)

    return list(results["values"])


def orca_parse_hessian(text_block: str) -> list[list[float]]:
    """Parse Hessian from orca .hess."""
    # Find the $hessian section
    match = re.search(r"\$hessian\s+(\d+)\s+(.*?)\$", text_block, re.DOTALL)
    if not match:
        msg = "No $hessian section found"
        raise ValueError(msg)

    dimension = int(match.group(1))
    body = match.group(2)

    hess: list[list[float]] = [[] for _ in range(dimension)]

    # Data line: integer index followed by floats
    data_line_re = re.compile(
        r"^\s+(\d+)((?:\s+[+-]?\d+\.\d+E[+-]\d+)+)\s*$", re.MULTILINE
    )

    for line in body.splitlines():
        m = data_line_re.match(line)
        if m:
            row_idx = int(m.group(1))
            vals = [float(v) for v in m.group(2).split()]
            hess[row_idx].extend(vals)

    return hess


def orca_parse_spe(text_block: str) -> float:
    """Parse final single point energy from orca stdout."""
    match = re.search(r"FINAL SINGLE POINT ENERGY\s+([-+]?\d+\.\d+)", text_block)

    if match:
        return float(match.group(1))

    msg = "Final single point energy line could not be parsed."
    raise ValueError(msg)
