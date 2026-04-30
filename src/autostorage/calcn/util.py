"""Calculation data utilities."""

import hashlib
import json
from typing import Any, Union

KeywordDict = dict[str, Union[str, "KeywordDict", None]]
CalculationDict = dict[str, Any]


def hash_from_dict(calc_dct: CalculationDict) -> str:
    """
    Generate hash from calculation dictionary.

    Parameters
    ----------
    calc_dct
        Calculation dictionary.

    Returns
    -------
        Hash string.
    """
    calc_json = json.dumps(
        calc_dct, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(calc_json).hexdigest()


def project_keywords(keywords: KeywordDict, template: object) -> KeywordDict:
    """
    Project keywords dictionary onto template.

    Parameters
    ----------
    keywords
        Keywords dictionary.
    template
        Keywords dictionary template.

    Returns
    -------
        Projected keywords dictionary.

    Raises
    ------
    TypeError
        If keywords template is not a dictionary.
    TypeError
        If keywords template keys are not strings.
    """
    if not isinstance(template, dict):
        msg = "Keywords template must be a dictionary."
        raise TypeError(msg)

    projected_dict: dict[str, object] = {}
    for key, val in template.items():
        if not isinstance(key, str):
            msg = "Keywords template keys must be strings."
            raise TypeError(msg)

        if key in keywords:
            if isinstance(val, dict) and isinstance(keywords[key], dict):
                projected_dict[key] = project_keywords(keywords[key], val)
            else:
                projected_dict[key] = keywords[key]
    return projected_dict
